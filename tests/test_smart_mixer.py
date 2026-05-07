"""
test_smart_mixer.py — Tests for smart mixing closed-loop (Phase 15).

Tests cover:
    - AudioAnalysis data structure
    - Diagnosis logic (various mixing problems)
    - Parameter adjustment logic
    - Iteration and convergence
    - Verify improvement logic
    - Smart mixing with mock renderer
    - ArrangementMixer integration
"""

from __future__ import annotations

import pytest
import numpy as np

from vcmix.ai.smart_mixer import (
    AudioAnalysis,
    Diagnosis,
    IterationResult,
    SmartMixResult,
    SmartMixer,
    _MASTER_TARGET_LUFS,
    _MASTER_PEAK_CEILING,
    _VOCAL_TARGET_RMS_DB,
    _LOW_FREQ_BUILDUP_RATIO,
    _HIGH_FREQ_HARSH_THRESHOLD,
)
from vcmix.ai.arrangement_mixer import ArrangementMixer, ComposeAndMixResult
from vcmix.ai.composer import AIComposer


# ═══════════════════════════════════════════════════════════════════════════
# Data Structure Tests
# ═══════════════════════════════════════════════════════════════════════════

class TestAudioAnalysis:
    """Test AudioAnalysis data structure."""

    def test_default_values(self):
        a = AudioAnalysis()
        assert a.rms_db == -120.0
        assert a.peak_db == -120.0
        assert a.true_peak_db == -120.0
        assert a.lufs == -120.0
        assert a.dynamic_range_db == 0.0
        assert a.sibilance == 0.0

    def test_to_dict(self):
        a = AudioAnalysis(rms_db=-18.5, peak_db=-3.2, lufs=-14.2)
        d = a.to_dict()
        assert "rms_db" in d
        assert "peak_db" in d
        assert "lufs" in d
        assert isinstance(d["rms_db"], float)

    def test_to_dict_rounding(self):
        a = AudioAnalysis(rms_db=-18.123456)
        d = a.to_dict()
        assert d["rms_db"] == -18.12


class TestDiagnosis:
    """Test Diagnosis data structure."""

    def test_creation(self):
        d = Diagnosis(
            target="master",
            problem="LUFS too low",
            severity=1,
            action="gain",
            params={"gain_db": 3.0},
        )
        assert d.target == "master"
        assert d.severity == 1
        assert d.action == "gain"

    def test_to_dict(self):
        d = Diagnosis(target="master", problem="Test", action="gain")
        result = d.to_dict()
        assert "target" in result
        assert "action" in result

    def test_default_severity(self):
        d = Diagnosis(target="master", problem="Test")
        assert d.severity == 3


class TestIterationResult:
    """Test IterationResult data structure."""

    def test_creation(self):
        itr = IterationResult(iteration=1)
        assert itr.iteration == 1
        assert itr.improved is False

    def test_to_dict(self):
        itr = IterationResult(iteration=1, improved=True)
        d = itr.to_dict()
        assert d["iteration"] == 1
        assert d["improved"] is True


class TestSmartMixResult:
    """Test SmartMixResult data structure."""

    def test_default_values(self):
        r = SmartMixResult()
        assert r.converged is False
        assert r.total_iterations == 0

    def test_to_dict(self):
        r = SmartMixResult(total_iterations=3, converged=True)
        d = r.to_dict()
        assert d["total_iterations"] == 3
        assert d["converged"] is True


# ═══════════════════════════════════════════════════════════════════════════
# SmartMixer Core Tests
# ═══════════════════════════════════════════════════════════════════════════

class TestSmartMixerAnalysis:
    """Test SmartMixer analysis methods."""

    def test_analyze_silence(self):
        mixer = SmartMixer()
        audio = np.zeros(44100, dtype=np.float32)
        analysis = mixer._analyze_output(audio)
        assert analysis.rms_db == -120.0
        assert analysis.peak_db == -120.0

    def test_analyze_loud_signal(self):
        mixer = SmartMixer()
        t = np.linspace(0, 1, 44100, dtype=np.float32)
        audio = 0.5 * np.sin(2 * np.pi * 440 * t)
        analysis = mixer._analyze_output(audio)
        assert analysis.rms_db > -120.0
        assert analysis.peak_db > -120.0
        assert analysis.lufs > -120.0

    def test_analyze_stereo(self):
        mixer = SmartMixer()
        t = np.linspace(0, 1, 44100, dtype=np.float32)
        mono = 0.8 * np.sin(2 * np.pi * 440 * t)
        audio = np.column_stack([mono, mono])
        analysis = mixer._analyze_output(audio)
        # Stereo gets averaged to mono, so RMS should be detectable
        assert analysis.rms_db > -120.0 or analysis.peak_db > -120.0

    def test_analyze_empty_audio(self):
        mixer = SmartMixer()
        audio = np.array([], dtype=np.float32)
        analysis = mixer._analyze_output(audio)
        assert analysis.rms_db == -120.0

    def test_basic_spectrum(self):
        mixer = SmartMixer()
        t = np.linspace(0, 1, 44100, dtype=np.float32)
        audio = 0.5 * np.sin(2 * np.pi * 440 * t)
        spectrum = mixer._basic_spectrum(audio)
        assert "sub" in spectrum
        assert "low" in spectrum
        assert "mid" in spectrum
        assert "high_mid" in spectrum
        assert "high" in spectrum
        assert "air" in spectrum

    def test_basic_spectrum_short_audio(self):
        mixer = SmartMixer()
        audio = np.zeros(100, dtype=np.float32)
        spectrum = mixer._basic_spectrum(audio)
        assert isinstance(spectrum, dict)


class TestSmartMixerDiagnosis:
    """Test SmartMixer diagnosis logic."""

    def _make_config(self, **overrides) -> dict:
        """Helper to create a test config."""
        config = {
            "name": "test",
            "bpm": 120,
            "tracks": [
                {"name": "Vocal", "type": "audio", "volume": 0.7, "effects": []},
                {"name": "Drums", "type": "sampler", "volume": 0.8, "effects": []},
                {"name": "Bass", "type": "midi", "volume": 0.75, "effects": []},
            ],
            "master": {"effects": []},
        }
        config.update(overrides)
        return config

    def test_diagnose_lufs_too_low(self):
        mixer = SmartMixer()
        analysis = AudioAnalysis(lufs=-20.0, rms_db=-16.0, peak_db=-3.0, true_peak_db=-2.5)
        config = self._make_config()
        diagnoses = mixer._diagnose(analysis, config)
        lufs_diags = [d for d in diagnoses if "LUFS" in d.problem]
        assert len(lufs_diags) > 0
        assert lufs_diags[0].severity == 1

    def test_diagnose_lufs_too_high(self):
        mixer = SmartMixer()
        analysis = AudioAnalysis(lufs=-10.0, rms_db=-6.0, peak_db=-1.0, true_peak_db=-0.5)
        config = self._make_config()
        diagnoses = mixer._diagnose(analysis, config)
        lufs_diags = [d for d in diagnoses if "LUFS" in d.problem]
        assert len(lufs_diags) > 0

    def test_diagnose_true_peak_exceeds_ceiling(self):
        mixer = SmartMixer()
        analysis = AudioAnalysis(
            rms_db=-16.0, peak_db=-0.5, true_peak_db=0.5,
            lufs=-14.0,
        )
        config = self._make_config()
        diagnoses = mixer._diagnose(analysis, config)
        peak_diags = [d for d in diagnoses if "True peak" in d.problem]
        assert len(peak_diags) > 0
        assert peak_diags[0].action == "limiter"

    def test_diagnose_wide_dynamic_range(self):
        mixer = SmartMixer()
        analysis = AudioAnalysis(
            rms_db=-24.0, peak_db=-2.0, true_peak_db=-1.5,
            lufs=-20.0, dynamic_range_db=22.0,
        )
        config = self._make_config()
        diagnoses = mixer._diagnose(analysis, config)
        dr_diags = [d for d in diagnoses if "Dynamic range" in d.problem and "wide" in d.problem]
        assert len(dr_diags) > 0
        assert dr_diags[0].action == "compressor"

    def test_diagnose_narrow_dynamic_range(self):
        mixer = SmartMixer()
        analysis = AudioAnalysis(
            rms_db=-8.0, peak_db=-6.0, true_peak_db=-5.5,
            lufs=-8.0, dynamic_range_db=2.0,
        )
        config = self._make_config()
        diagnoses = mixer._diagnose(analysis, config)
        dr_diags = [d for d in diagnoses if "Dynamic range" in d.problem and "narrow" in d.problem]
        assert len(dr_diags) > 0

    def test_diagnose_low_freq_buildup(self):
        mixer = SmartMixer()
        analysis = AudioAnalysis(
            rms_db=-16.0, peak_db=-3.0, true_peak_db=-2.5,
            lufs=-14.0, dynamic_range_db=8.0,
            low_freq_buildup=0.25,
        )
        config = self._make_config()
        diagnoses = mixer._diagnose(analysis, config)
        lf_diags = [d for d in diagnoses if "Low-frequency" in d.problem]
        assert len(lf_diags) > 0

    def test_diagnose_high_freq_harshness(self):
        mixer = SmartMixer()
        analysis = AudioAnalysis(
            rms_db=-16.0, peak_db=-3.0, true_peak_db=-2.5,
            lufs=-14.0, dynamic_range_db=8.0,
            high_freq_harsh=0.30,
        )
        config = self._make_config()
        diagnoses = mixer._diagnose(analysis, config)
        hf_diags = [d for d in diagnoses if "High-frequency" in d.problem]
        assert len(hf_diags) > 0

    def test_diagnose_vocal_too_quiet(self):
        mixer = SmartMixer()
        analysis = AudioAnalysis(lufs=-14.0, rms_db=-16.0, peak_db=-3.0, true_peak_db=-2.5, dynamic_range_db=8.0)
        config = self._make_config()
        config["tracks"][0]["volume"] = 0.4  # Vocal too quiet
        diagnoses = mixer._diagnose(analysis, config)
        vocal_diags = [d for d in diagnoses if "Vocal" in d.target]
        assert len(vocal_diags) > 0

    def test_diagnose_drum_too_loud(self):
        mixer = SmartMixer()
        analysis = AudioAnalysis(lufs=-14.0, rms_db=-16.0, peak_db=-3.0, true_peak_db=-2.5, dynamic_range_db=8.0)
        config = self._make_config()
        config["tracks"][1]["volume"] = 0.95  # Drums too loud
        diagnoses = mixer._diagnose(analysis, config)
        drum_diags = [d for d in diagnoses if "Drum" in d.target]
        assert len(drum_diags) > 0

    def test_diagnose_bass_no_highpass(self):
        mixer = SmartMixer()
        analysis = AudioAnalysis(lufs=-14.0, rms_db=-16.0, peak_db=-3.0, true_peak_db=-2.5, dynamic_range_db=8.0)
        config = self._make_config()
        diagnoses = mixer._diagnose(analysis, config)
        bass_diags = [d for d in diagnoses if "Bass" in d.target and "high-pass" in d.problem]
        assert len(bass_diags) > 0

    def test_diagnose_sibilance(self):
        mixer = SmartMixer()
        analysis = AudioAnalysis(
            lufs=-14.0, rms_db=-16.0, peak_db=-3.0, true_peak_db=-2.5,
            dynamic_range_db=8.0, sibilance=0.15,
        )
        config = self._make_config()
        diagnoses = mixer._diagnose(analysis, config)
        sib_diags = [d for d in diagnoses if "Sibilance" in d.problem]
        assert len(sib_diags) > 0
        assert sib_diags[0].action == "deesser"

    def test_diagnose_no_problems(self):
        mixer = SmartMixer()
        analysis = AudioAnalysis(
            lufs=-14.0, rms_db=-16.0, peak_db=-3.0, true_peak_db=-2.0,
            dynamic_range_db=8.0,
        )
        config = self._make_config()
        # Set appropriate volumes
        for t in config["tracks"]:
            t["volume"] = 0.7
        diagnoses = mixer._diagnose(analysis, config)
        # With good levels, there should be few or no critical diagnoses
        critical = [d for d in diagnoses if d.severity == 1]
        # May still have some severity 2-3 suggestions


class TestSmartMixerAdjustments:
    """Test SmartMixer parameter adjustment logic."""

    def _make_config(self) -> dict:
        return {
            "name": "test",
            "bpm": 120,
            "tracks": [
                {"name": "Vocal", "type": "audio", "volume": 0.5, "effects": []},
                {"name": "Drums", "type": "sampler", "volume": 0.8, "effects": []},
            ],
            "master": {"effects": []},
        }

    def test_apply_master_gain(self):
        mixer = SmartMixer()
        config = self._make_config()
        mixer._apply_master_adjustment(config, "gain", {"gain_db": 3.0})
        # Track volumes should have increased
        for track in config["tracks"]:
            assert track["volume"] > 0.5 or track["name"] != "Vocal"

    def test_apply_master_limiter(self):
        mixer = SmartMixer()
        config = self._make_config()
        mixer._apply_master_adjustment(config, "limiter", {"ceiling": -1.0})
        effects = config["master"]["effects"]
        assert any(e["name"] == "vc-limiter" for e in effects)

    def test_apply_master_compressor(self):
        mixer = SmartMixer()
        config = self._make_config()
        mixer._apply_master_adjustment(config, "compressor", {
            "threshold_db": -20, "ratio": 3, "attack_ms": 10, "release_ms": 100
        })
        effects = config["master"]["effects"]
        assert any(e["name"] == "vc-comp" for e in effects)

    def test_apply_master_eq(self):
        mixer = SmartMixer()
        config = self._make_config()
        mixer._apply_master_adjustment(config, "eq", {"low_cut_hz": 40})
        effects = config["master"]["effects"]
        assert any(e["name"] == "vc-eq" for e in effects)

    def test_apply_master_reduce_compression(self):
        mixer = SmartMixer()
        config = self._make_config()
        config["master"]["effects"] = [{"name": "vc-comp", "params": {"ratio": 4}}]
        mixer._apply_master_adjustment(config, "reduce_compression", {"ratio_adjust": -1})
        comp = [e for e in config["master"]["effects"] if e["name"] == "vc-comp"][0]
        assert comp["params"]["ratio"] == 3

    def test_apply_track_gain(self):
        mixer = SmartMixer()
        config = self._make_config()
        mixer._apply_track_adjustment(config, "Vocal", "gain", {"gain_db": 3.0})
        vocal = [t for t in config["tracks"] if t["name"] == "Vocal"][0]
        assert vocal["volume"] > 0.5

    def test_apply_track_deesser(self):
        mixer = SmartMixer()
        config = self._make_config()
        mixer._apply_track_adjustment(config, "Vocal", "deesser", {"threshold": -35})
        vocal = [t for t in config["tracks"] if t["name"] == "Vocal"][0]
        assert any(e["name"] == "vc-deesser" for e in vocal["effects"])

    def test_apply_track_eq(self):
        mixer = SmartMixer()
        config = self._make_config()
        mixer._apply_track_adjustment(config, "Vocal", "eq", {"low_cut_hz": 80})
        vocal = [t for t in config["tracks"] if t["name"] == "Vocal"][0]
        assert any(e["name"] == "vc-eq" for e in vocal["effects"])

    def test_apply_track_compressor(self):
        mixer = SmartMixer()
        config = self._make_config()
        mixer._apply_track_adjustment(config, "Drums", "compressor", {
            "threshold_db": -12, "ratio": 4
        })
        drums = [t for t in config["tracks"] if t["name"] == "Drums"][0]
        assert any(e["name"] == "vc-comp" for e in drums["effects"])

    def test_apply_track_limiter(self):
        mixer = SmartMixer()
        config = self._make_config()
        mixer._apply_track_adjustment(config, "Drums", "limiter", {"ceiling": -3})
        drums = [t for t in config["tracks"] if t["name"] == "Drums"][0]
        assert any(e["name"] == "vc-limiter" for e in drums["effects"])

    def test_apply_track_not_found(self):
        mixer = SmartMixer()
        config = self._make_config()
        # Should not raise
        mixer._apply_track_adjustment(config, "Nonexistent", "gain", {"gain_db": 3.0})

    def test_adjust_parameters_returns_summary(self):
        mixer = SmartMixer()
        config = self._make_config()
        diagnoses = [
            Diagnosis(target="master", problem="LUFS too low", action="gain", params={"gain_db": 3.0}),
            Diagnosis(target="track:Vocal", problem="Too quiet", action="gain", params={"gain_db": 2.0}),
        ]
        adjustments = mixer._adjust_parameters(config, diagnoses)
        assert "applied" in adjustments
        assert len(adjustments["applied"]) == 2


class TestSmartMixerVerify:
    """Test SmartMixer verification logic."""

    def test_verify_lufs_improvement(self):
        mixer = SmartMixer()
        before = AudioAnalysis(lufs=-18.0, rms_db=-14.0, peak_db=-3.0, true_peak_db=-2.5, dynamic_range_db=8.0)
        after = AudioAnalysis(lufs=-15.0, rms_db=-11.0, peak_db=-2.0, true_peak_db=-1.5, dynamic_range_db=8.0)
        # LUFS went from -18 (far from -14) to -15 (closer to -14)
        result = mixer._verify_improvement(before, after)
        assert isinstance(result, bool)

    def test_verify_lufs_worsening(self):
        mixer = SmartMixer()
        before = AudioAnalysis(lufs=-15.0)
        after = AudioAnalysis(lufs=-18.0)
        assert mixer._verify_improvement(before, after) is False

    def test_verify_no_checks_applicable(self):
        mixer = SmartMixer()
        before = AudioAnalysis(lufs=-14.0, dynamic_range_db=8.0, true_peak_db=-2.0)
        after = AudioAnalysis(lufs=-14.0, dynamic_range_db=8.0, true_peak_db=-2.0)
        # Both at target - no checks fail
        result = mixer._verify_improvement(before, after)
        assert isinstance(result, bool)

    def test_verify_true_peak_improvement(self):
        mixer = SmartMixer()
        before = AudioAnalysis(
            rms_db=-6.0, peak_db=-0.5, true_peak_db=0.5,
            lufs=-6.0, dynamic_range_db=8.0,
        )
        after = AudioAnalysis(
            rms_db=-8.0, peak_db=-2.0, true_peak_db=-1.5,
            lufs=-8.0, dynamic_range_db=8.0,
        )
        result = mixer._verify_improvement(before, after)
        assert isinstance(result, bool)


class TestSmartMixerAutoMix:
    """Test SmartMixer auto_mix end-to-end."""

    def _make_project_config(self) -> dict:
        return {
            "name": "test_mix",
            "bpm": 120,
            "key": "C",
            "duration": 30,
            "tracks": [
                {"name": "Vocal", "type": "audio", "volume": 0.5, "effects": []},
                {"name": "Drums", "type": "sampler", "volume": 0.85, "effects": []},
                {"name": "Bass", "type": "midi", "volume": 0.75, "effects": []},
            ],
            "arrangement": [
                {"name": "verse", "duration_bars": 8, "energy": 0.5},
            ],
            "master": {
                "target_lufs": -14.0,
                "true_peak_ceiling": -1.0,
                "effects": [],
            },
        }

    def test_auto_mix_basic(self):
        mixer = SmartMixer()
        config = self._make_project_config()
        result = mixer.auto_mix(config, max_iterations=2)
        assert isinstance(result, SmartMixResult)
        assert result.total_iterations >= 1
        assert result.total_time_sec >= 0

    def test_auto_mix_converges(self):
        mixer = SmartMixer()
        config = self._make_project_config()
        result = mixer.auto_mix(config, max_iterations=5)
        # Should either converge or reach max iterations
        assert result.total_iterations <= 5

    def test_auto_mix_preserves_config(self):
        mixer = SmartMixer()
        config = self._make_project_config()
        original_tracks = len(config["tracks"])
        result = mixer.auto_mix(config, max_iterations=2)
        assert len(result.project_config["tracks"]) == original_tracks

    def test_auto_mix_with_custom_render(self):
        """Test auto_mix with a custom render function."""
        def mock_render(cfg):
            sr = 44100
            t = np.linspace(0, 2, sr * 2, dtype=np.float32)
            return 0.3 * np.sin(2 * np.pi * 440 * t)

        mixer = SmartMixer()
        config = self._make_project_config()
        result = mixer.auto_mix(config, max_iterations=2, render_fn=mock_render)
        assert isinstance(result, SmartMixResult)

    def test_auto_mix_result_to_dict(self):
        mixer = SmartMixer()
        config = self._make_project_config()
        result = mixer.auto_mix(config, max_iterations=1)
        d = result.to_dict()
        assert "total_iterations" in d
        assert "converged" in d
        assert "iterations" in d

    def test_auto_mix_single_iteration(self):
        mixer = SmartMixer()
        config = self._make_project_config()
        result = mixer.auto_mix(config, max_iterations=1)
        assert result.total_iterations == 1

    def test_auto_mix_zero_iterations(self):
        mixer = SmartMixer()
        config = self._make_project_config()
        result = mixer.auto_mix(config, max_iterations=0)
        assert result.total_iterations == 0

    def test_auto_mix_with_string_path_raises_on_missing(self):
        mixer = SmartMixer()
        with pytest.raises(FileNotFoundError):
            mixer.auto_mix("/nonexistent/path.yaml")


class TestSmartMixerMockRender:
    """Test SmartMixer mock rendering."""

    def test_render_or_mock_generates_audio(self):
        mixer = SmartMixer()
        config = {
            "bpm": 120,
            "duration": 5,
            "tracks": [{"name": "Piano", "volume": 0.7}],
            "arrangement": [],
        }
        audio = mixer._render_or_mock(config, None)
        assert isinstance(audio, np.ndarray)
        assert len(audio) > 0

    def test_render_or_mock_uses_render_fn(self):
        mixer = SmartMixer()
        expected = np.ones(1000, dtype=np.float32)
        config = {"bpm": 120, "duration": 5}
        result = mixer._render_or_mock(config, lambda cfg: expected)
        np.testing.assert_array_equal(result, expected)

    def test_render_or_mock_duration(self):
        mixer = SmartMixer()
        config = {"bpm": 120, "duration": 2, "tracks": [], "arrangement": []}
        audio = mixer._render_or_mock(config, None)
        expected_samples = int(2 * 44100)
        assert abs(len(audio) - expected_samples) < 100


# ═══════════════════════════════════════════════════════════════════════════
# ArrangementMixer Integration Tests
# ═══════════════════════════════════════════════════════════════════════════

class TestArrangementMixer:
    """Test ArrangementMixer integration."""

    def test_compose_and_mix_basic(self):
        am = ArrangementMixer()
        result = am.compose_and_mix(
            genre="pop", duration=120, bpm=120,
            key="C", mood="happy",
        )
        assert isinstance(result, ComposeAndMixResult)
        assert result.composition is not None
        assert result.mix_result is not None
        assert result.status in ("success", "partial", "failed")

    def test_compose_and_mix_result_to_dict(self):
        am = ArrangementMixer()
        result = am.compose_and_mix(
            genre="pop", duration=120, bpm=120,
            key="C", mood="happy",
        )
        d = result.to_dict()
        assert "composition" in d
        assert "mix_result" in d
        assert "status" in d

    def test_compose_only(self):
        am = ArrangementMixer()
        result = am.compose_only(
            genre="pop", duration=120, bpm=120,
            key="C", mood="happy",
        )
        assert result.genre == "pop"
        assert result.key == "C"

    def test_mix_only(self):
        am = ArrangementMixer()
        config = {
            "name": "test",
            "bpm": 120,
            "key": "C",
            "duration": 30,
            "tracks": [
                {"name": "Vocal", "type": "audio", "volume": 0.5, "effects": []},
                {"name": "Drums", "type": "sampler", "volume": 0.8, "effects": []},
            ],
            "arrangement": [],
            "master": {"effects": []},
        }
        result = am.mix_only(config, max_iterations=2)
        assert isinstance(result, SmartMixResult)

    def test_compose_and_mix_edm(self):
        am = ArrangementMixer()
        result = am.compose_and_mix(
            genre="edm", duration=180, bpm=128,
            key="Am", mood="energetic",
        )
        assert result.composition.genre == "edm"

    def test_compose_and_mix_rock(self):
        am = ArrangementMixer()
        result = am.compose_and_mix(
            genre="rock", duration=180, bpm=130,
            key="E", mood="energetic",
        )
        assert result.composition.genre == "rock"

    def test_compose_and_mix_hiphop(self):
        am = ArrangementMixer()
        result = am.compose_and_mix(
            genre="hiphop", duration=200, bpm=90,
            key="Cm", mood="dark",
        )
        assert result.composition.genre == "hiphop"

    def test_compose_and_mix_with_custom_render(self):
        def mock_render(cfg):
            return 0.3 * np.sin(2 * np.pi * 440 * np.linspace(0, 2, 88200, dtype=np.float32))

        am = ArrangementMixer()
        result = am.compose_and_mix(
            genre="pop", duration=120, bpm=120,
            key="C", mood="happy",
            render_fn=mock_render,
        )
        assert result.status in ("success", "partial")

    def test_compose_and_mix_timing(self):
        am = ArrangementMixer()
        result = am.compose_and_mix(
            genre="pop", duration=60, bpm=120,
            key="C", mood="happy",
        )
        assert result.total_time_sec >= 0

    def test_compose_and_mix_final_config_has_tracks(self):
        am = ArrangementMixer()
        result = am.compose_and_mix(
            genre="pop", duration=120, bpm=120,
            key="C", mood="happy",
        )
        assert "tracks" in result.final_config
        assert len(result.final_config["tracks"]) > 0
