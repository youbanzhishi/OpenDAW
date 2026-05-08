"""Tests for vcmix.automation module — Phase 9 automation curves."""
import pytest

from vcmix.automation.automation_curve import AutomationCurve, AutomationPoint, CurveType
from vcmix.automation.automation_engine import AutomationEngine, TrackAutomation

# ── AutomationPoint Tests ────────────────────────────────────────────────

class TestAutomationPoint:
    def test_point_creation(self):
        point = AutomationPoint(time_beat=0.0, value=-6.0, curve_type=CurveType.LINEAR)
        assert point.time_beat == 0.0
        assert point.value == -6.0
        assert point.curve_type == CurveType.LINEAR

    def test_point_default_curve_type(self):
        point = AutomationPoint(time_beat=0.0, value=0.0)
        assert point.curve_type == CurveType.LINEAR

    def test_point_negative_time_raises(self):
        with pytest.raises(ValueError, match="negative"):
            AutomationPoint(time_beat=-1.0, value=0.0)

    def test_point_from_list_two_elements(self):
        point = AutomationPoint.from_list([4.0, 0.5])
        assert point.time_beat == 4.0
        assert point.value == 0.5
        assert point.curve_type == CurveType.LINEAR

    def test_point_from_list_three_elements(self):
        point = AutomationPoint.from_list([0.0, -6.0, "smooth"])
        assert point.time_beat == 0.0
        assert point.value == -6.0
        assert point.curve_type == CurveType.SMOOTH

    def test_point_from_list_step(self):
        point = AutomationPoint.from_list([8.0, 0.0, "step"])
        assert point.curve_type == CurveType.STEP

    def test_point_from_list_invalid(self):
        with pytest.raises(ValueError):
            AutomationPoint.from_list([0.0])  # Need at least 2 elements


# ── AutomationCurve Tests ────────────────────────────────────────────────

class TestAutomationCurve:
    def test_empty_curve_returns_default(self):
        curve = AutomationCurve(default_value=1.0)
        assert curve.value_at(0.0) == 1.0
        assert curve.value_at(100.0) == 1.0

    def test_single_point_curve(self):
        curve = AutomationCurve(points=[
            AutomationPoint(time_beat=4.0, value=0.5),
        ])
        # Before the point
        assert curve.value_at(0.0) == 0.5
        # At the point
        assert curve.value_at(4.0) == 0.5
        # After the point
        assert curve.value_at(8.0) == 0.5

    def test_linear_interpolation(self):
        curve = AutomationCurve(points=[
            AutomationPoint(time_beat=0.0, value=0.0, curve_type=CurveType.LINEAR),
            AutomationPoint(time_beat=8.0, value=-6.0, curve_type=CurveType.LINEAR),
        ])
        # At start
        assert curve.value_at(0.0) == 0.0
        # Midpoint
        assert abs(curve.value_at(4.0) - (-3.0)) < 0.001
        # At end
        assert curve.value_at(8.0) == -6.0

    def test_step_interpolation(self):
        curve = AutomationCurve(points=[
            AutomationPoint(time_beat=0.0, value=-6.0, curve_type=CurveType.STEP),
            AutomationPoint(time_beat=8.0, value=0.0, curve_type=CurveType.STEP),
            AutomationPoint(time_beat=32.0, value=-12.0, curve_type=CurveType.STEP),
        ])
        # Step holds until next point
        assert curve.value_at(0.0) == -6.0
        assert curve.value_at(4.0) == -6.0
        assert curve.value_at(7.9) == -6.0
        assert curve.value_at(8.0) == 0.0
        assert curve.value_at(16.0) == 0.0
        assert curve.value_at(31.9) == 0.0
        assert curve.value_at(32.0) == -12.0

    def test_smooth_interpolation(self):
        curve = AutomationCurve(points=[
            AutomationPoint(time_beat=0.0, value=0.0, curve_type=CurveType.SMOOTH),
            AutomationPoint(time_beat=10.0, value=10.0, curve_type=CurveType.SMOOTH),
        ])
        # At endpoints
        assert curve.value_at(0.0) == 0.0
        assert curve.value_at(10.0) == 10.0
        # Midpoint should be close to 5.0 (cosine interpolation)
        mid = curve.value_at(5.0)
        assert 4.5 < mid < 5.5  # Close to linear midpoint

    def test_mixed_curve_types(self):
        """Test a curve with mixed interpolation types (like the YAML example).

        Note: curve_type on a point determines interpolation FROM that point TO the next.
        STEP holds the value until the next point.
        SMOOTH applies cosine interpolation from this point to the next.
        """
        curve = AutomationCurve(points=[
            AutomationPoint(time_beat=0, value=-6, curve_type=CurveType.LINEAR),
            AutomationPoint(time_beat=8, value=0, curve_type=CurveType.LINEAR),
            AutomationPoint(time_beat=32, value=0, curve_type=CurveType.STEP),
            AutomationPoint(time_beat=40, value=-12, curve_type=CurveType.SMOOTH),
        ])
        # Fade in (linear from -6 to 0 over beats 0-8)
        assert abs(curve.value_at(4.0) - (-3.0)) < 0.01
        # Hold at 0 (step holds value from beat 8 point through beat 32 point)
        assert abs(curve.value_at(16.0)) < 0.01
        assert abs(curve.value_at(31.9)) < 0.01
        # Step at beat 32: holds 0 until beat 40 (STEP on beat 32 point)
        assert abs(curve.value_at(36.0)) < 0.01  # Step holds 0
        # At beat 40: value is -12
        assert abs(curve.value_at(40.0) - (-12.0)) < 0.01

    def test_point_count(self):
        curve = AutomationCurve(points=[
            AutomationPoint(time_beat=0.0, value=0.0),
            AutomationPoint(time_beat=8.0, value=-6.0),
        ])
        assert curve.point_count == 2

    def test_value_range(self):
        curve = AutomationCurve(points=[
            AutomationPoint(time_beat=0.0, value=-12.0),
            AutomationPoint(time_beat=8.0, value=6.0),
        ])
        assert curve.value_range == (-12.0, 6.0)

    def test_add_point(self):
        curve = AutomationCurve()
        curve.add_point(AutomationPoint(time_beat=4.0, value=1.0))
        curve.add_point(AutomationPoint(time_beat=0.0, value=0.0))
        assert curve.point_count == 2
        # Points should be sorted
        assert curve.points[0].time_beat == 0.0
        assert curve.points[1].time_beat == 4.0

    def test_to_list(self):
        curve = AutomationCurve(points=[
            AutomationPoint(time_beat=0.0, value=-6.0, curve_type=CurveType.LINEAR),
            AutomationPoint(time_beat=8.0, value=0.0, curve_type=CurveType.STEP),
        ])
        data = curve.to_list()
        assert len(data) == 2
        assert data[0] == [0.0, -6.0, "linear"]
        assert data[1] == [8.0, 0.0, "step"]

    def test_from_list(self):
        data = [
            [0, -6, "linear"],
            [8, 0, "linear"],
            [32, 0, "step"],
            [40, -12, "smooth"],
        ]
        curve = AutomationCurve.from_list(data)
        assert curve.point_count == 4
        assert curve.value_at(0.0) == -6.0
        assert curve.value_at(8.0) == 0.0

    def test_values_at_beats(self):
        curve = AutomationCurve(points=[
            AutomationPoint(time_beat=0.0, value=0.0, curve_type=CurveType.LINEAR),
            AutomationPoint(time_beat=10.0, value=10.0, curve_type=CurveType.LINEAR),
        ])
        values = curve.values_at_beats([0.0, 5.0, 10.0])
        assert len(values) == 3
        assert abs(values[0] - 0.0) < 0.01
        assert abs(values[1] - 5.0) < 0.01
        assert abs(values[2] - 10.0) < 0.01

    def test_curve_repr(self):
        curve = AutomationCurve(points=[
            AutomationPoint(time_beat=0.0, value=0.0),
        ])
        assert "AutomationCurve" in repr(curve)

    def test_start_end_beat(self):
        curve = AutomationCurve(points=[
            AutomationPoint(time_beat=4.0, value=0.0),
            AutomationPoint(time_beat=16.0, value=1.0),
        ])
        assert curve.start_beat == 4.0
        assert curve.end_beat == 16.0


# ── TrackAutomation Tests ────────────────────────────────────────────────

class TestTrackAutomation:
    def test_no_gain_automation(self):
        ta = TrackAutomation(track_name="vocal")
        assert ta.get_gain_at_beat(0.0) is None

    def test_gain_automation(self):
        gain_curve = AutomationCurve(points=[
            AutomationPoint(time_beat=0, value=-6, curve_type=CurveType.LINEAR),
            AutomationPoint(time_beat=8, value=0, curve_type=CurveType.LINEAR),
        ])
        ta = TrackAutomation(track_name="vocal", gain_curve=gain_curve)
        assert abs(ta.get_gain_at_beat(4.0) - (-3.0)) < 0.01

    def test_plugin_automation(self):
        wet_curve = AutomationCurve(points=[
            AutomationPoint(time_beat=0, value=0.2, curve_type=CurveType.LINEAR),
            AutomationPoint(time_beat=16, value=0.5, curve_type=CurveType.LINEAR),
        ])
        ta = TrackAutomation(
            track_name="vocal",
            plugin_curves={"vc-reverb": {"wet": wet_curve}},
        )
        params = ta.get_plugin_params_at_beat("vc-reverb", 8.0)
        assert "wet" in params
        assert abs(params["wet"] - 0.35) < 0.01

    def test_plugin_not_found(self):
        ta = TrackAutomation(track_name="vocal")
        params = ta.get_plugin_params_at_beat("vc-reverb", 0.0)
        assert params == {}


# ── AutomationEngine Tests ───────────────────────────────────────────────

class TestAutomationEngine:
    def test_empty_engine(self):
        engine = AutomationEngine()
        assert not engine.has_automation
        assert engine.get_params_at_beat("vocal", 0.0) == {}

    def test_from_config(self):
        track_configs = [
            {
                "name": "vocal",
                "file": "vocal.wav",
                "automation": {
                    "gain": [
                        [0, -6, "linear"],
                        [8, 0, "linear"],
                    ],
                    "vc-reverb.wet": [
                        [0, 0.2, "linear"],
                        [16, 0.5, "linear"],
                    ],
                },
            },
        ]
        engine = AutomationEngine.from_config(track_configs, bpm=120)
        assert engine.has_automation
        assert "vocal" in engine.automated_track_names

    def test_get_params_at_beat(self):
        track_configs = [
            {
                "name": "vocal",
                "file": "vocal.wav",
                "automation": {
                    "gain": [
                        [0, -6, "linear"],
                        [8, 0, "linear"],
                    ],
                },
            },
        ]
        engine = AutomationEngine.from_config(track_configs, bpm=120)
        params = engine.get_params_at_beat("vocal", 4.0)
        assert "gain" in params
        assert abs(params["gain"] - (-3.0)) < 0.01

    def test_get_plugin_params_at_beat(self):
        track_configs = [
            {
                "name": "vocal",
                "file": "vocal.wav",
                "automation": {
                    "vc-reverb.wet": [
                        [0, 0.2, "linear"],
                        [16, 0.5, "linear"],
                    ],
                },
            },
        ]
        engine = AutomationEngine.from_config(track_configs, bpm=120)
        params = engine.get_plugin_params_at_beat("vocal", "vc-reverb", 8.0)
        assert "wet" in params
        assert abs(params["wet"] - 0.35) < 0.01

    def test_get_gain_at_beat(self):
        track_configs = [
            {
                "name": "vocal",
                "file": "vocal.wav",
                "automation": {
                    "gain": [[0, -6, "step"], [8, 0, "step"]],
                },
            },
        ]
        engine = AutomationEngine.from_config(track_configs, bpm=120)
        assert engine.get_gain_at_beat("vocal", 4.0) == -6.0
        assert engine.get_gain_at_beat("vocal", 8.0) == 0.0

    def test_apply_automation_to_params(self):
        track_configs = [
            {
                "name": "vocal",
                "file": "vocal.wav",
                "automation": {
                    "vc-reverb.wet": [
                        [0, 0.1, "linear"],
                        [32, 0.8, "linear"],
                    ],
                },
            },
        ]
        engine = AutomationEngine.from_config(track_configs, bpm=120)
        static_params = {"room": 30, "wet": 0.3, "decay": 35}
        result = engine.apply_automation_to_params("vocal", "vc-reverb", static_params, 16.0)
        # wet should be overridden by automation at beat 16 -> 0.45
        assert result["room"] == 30
        assert result["decay"] == 35
        assert abs(result["wet"] - 0.45) < 0.01

    def test_apply_automation_no_overrides(self):
        """If no automation for a plugin, static params are returned unchanged."""
        engine = AutomationEngine()
        params = {"room": 30, "wet": 0.3}
        result = engine.apply_automation_to_params("vocal", "vc-reverb", params, 0.0)
        assert result == params

    def test_time_to_beat_conversion(self):
        engine = AutomationEngine(bpm=120)
        # 120 BPM = 2 beats/sec
        assert engine.time_to_beat(1.0) == 2.0
        assert engine.time_to_beat(0.5) == 1.0

    def test_beat_to_time_conversion(self):
        engine = AutomationEngine(bpm=120)
        assert engine.beat_to_time(1.0) == 0.5
        assert engine.beat_to_time(2.0) == 1.0

    def test_multiple_tracks(self):
        track_configs = [
            {
                "name": "vocal",
                "file": "vocal.wav",
                "automation": {"gain": [[0, -6, "linear"], [8, 0, "linear"]]},
            },
            {
                "name": "drums",
                "file": "drums.wav",
                "automation": {"gain": [[0, 0, "step"], [16, -3, "step"]]},
            },
        ]
        engine = AutomationEngine.from_config(track_configs, bpm=120)
        assert len(engine.automated_track_names) == 2
        assert engine.get_gain_at_beat("vocal", 4.0) == -3.0
        assert engine.get_gain_at_beat("drums", 4.0) == 0.0

    def test_smooth_fade_between_points(self):
        """Test smooth interpolation from one point to the next."""
        curve = AutomationCurve(points=[
            AutomationPoint(time_beat=0, value=0, curve_type=CurveType.SMOOTH),
            AutomationPoint(time_beat=8, value=-12, curve_type=CurveType.SMOOTH),
        ])
        # At start
        assert abs(curve.value_at(0.0)) < 0.01
        # At end
        assert abs(curve.value_at(8.0) - (-12.0)) < 0.01
        # Midpoint (smooth cosine interpolation, should be near -6)
        mid = curve.value_at(4.0)
        assert -7.0 < mid < -5.0

    def test_yaml_integration(self):
        """Test automation defined in YAML project config."""
        import tempfile
        from pathlib import Path

        yaml_content = """
name: automation_test
bpm: 120
tracks:
  - name: vocal
    file: vocal.wav
    automation:
      gain:
        - [0, -6, linear]
        - [8, 0, linear]
        - [32, 0, step]
        - [40, -12, smooth]
      vc-reverb.wet:
        - [0, 0.2, linear]
        - [16, 0.5, linear]
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(yaml_content)
            f.flush()
            tmp_name = f.name

        # File is now closed (exited the with block), safe to parse on Windows
        from vcmix.config.parser import parse_project
        config = parse_project(tmp_name)

        # Build engine from parsed config
        track_dicts = [
            {
                "name": t.name,
                "file": t.file,
                "automation": t.automation,
            }
            for t in config.tracks
            if t.automation
        ]
        engine = AutomationEngine.from_config(track_dicts, bpm=config.bpm)

        # Verify gain automation
        params = engine.get_params_at_beat("vocal", 4.0)
        assert "gain" in params
        assert abs(params["gain"] - (-3.0)) < 0.01

        # Verify plugin automation
        reverb_params = engine.get_plugin_params_at_beat("vocal", "vc-reverb", 8.0)
        assert "wet" in reverb_params
        assert abs(reverb_params["wet"] - 0.35) < 0.01

        Path(tmp_name).unlink(missing_ok=True)
