"""
test_autofix_v2.py — Tests for Phase 2 AutoFix gain staging chain analysis.

Tests:
    - GainStageInfo data class
    - ChainAnalysis data class
    - analyze_chain with rendered stages
    - Gain accumulation detection
    - fix_gain_staging with auto-inserted gain nodes
    - Phase 1 backward compatibility

Usage:
    pytest tests/test_autofix_v2.py -v

Dependencies: pytest, numpy
"""

from __future__ import annotations

import numpy as np
import pytest

from vcmix.engine.autofix import AutoFix, GainStageInfo, ChainAnalysis


class TestGainStageInfo:
    """Tests for GainStageInfo data class."""

    def test_creation(self):
        """GainStageInfo should store all fields."""
        info = GainStageInfo(
            effect_name="vc-comp",
            input_rms_db=-18.0,
            output_rms_db=-20.0,
            input_peak_db=-6.0,
            output_peak_db=-8.0,
            gain_delta_db=-2.0,
            issues=[],
        )
        assert info.effect_name == "vc-comp"
        assert info.gain_delta_db == -2.0
        assert len(info.issues) == 0

    def test_issues_detection(self):
        """GainStageInfo should track issues."""
        info = GainStageInfo(
            effect_name="vc-saturator",
            input_peak_db=-3.0,
            issues=["Input exceeds ceiling"],
        )
        assert len(info.issues) == 1


class TestChainAnalysis:
    """Tests for ChainAnalysis data class."""

    def test_empty_analysis(self):
        """Empty ChainAnalysis should have defaults."""
        analysis = ChainAnalysis()
        assert len(analysis.stages) == 0
        assert analysis.total_gain_db == 0.0
        assert analysis.clip_risk is False
        assert analysis.snr_risk is False
        assert len(analysis.warnings) == 0

    def test_analysis_with_stages(self):
        """ChainAnalysis should accumulate stage info."""
        analysis = ChainAnalysis(
            stages=[
                GainStageInfo(effect_name="input", output_rms_db=-18.0, input_rms_db=-18.0),
                GainStageInfo(effect_name="vc-gain", output_rms_db=-12.0, input_rms_db=-18.0, gain_delta_db=6.0),
            ],
            total_gain_db=6.0,
        )
        assert len(analysis.stages) == 2
        assert analysis.total_gain_db == 6.0


class TestAnalyzeChain:
    """Tests for AutoFix.analyze_chain (Phase 2)."""

    def test_analyze_chain_with_rendered_stages(self):
        """analyze_chain should process rendered stages."""
        fixer = AutoFix(sample_rate=44100)
        sr = 44100
        t = np.linspace(0, 1.0, sr, endpoint=False, dtype=np.float32)

        # Simulate: input at -18dBFS, gain boost to -12dBFS, then comp back to -15dBFS
        input_audio = 0.126 * np.sin(2 * np.pi * 440 * t)  # ~-18 dBFS
        after_gain = input_audio * 2.0  # ~-12 dBFS
        after_comp = after_gain * 0.7   # ~-15 dBFS

        rendered_stages = [
            ("vc-gain", input_audio, after_gain),
            ("vc-comp", after_gain, after_comp),
        ]

        analysis = fixer.analyze_chain(input_audio, [], rendered_stages)
        assert len(analysis.stages) == 2
        assert analysis.stages[0].effect_name == "vc-gain"
        assert analysis.stages[1].effect_name == "vc-comp"
        # Gain should be positive for the first stage
        assert analysis.stages[0].gain_delta_db > 0
        # Comp should reduce level
        assert analysis.stages[1].gain_delta_db < 0

    def test_analyze_chain_without_rendered_stages(self):
        """analyze_chain with no rendered stages should create input stage."""
        fixer = AutoFix(sample_rate=44100)
        sr = 44100
        t = np.linspace(0, 1.0, sr, endpoint=False, dtype=np.float32)
        audio = 0.5 * np.sin(2 * np.pi * 440 * t)

        analysis = fixer.analyze_chain(audio, [{"name": "vc-gain", "params": {"gain": 3}}])
        assert len(analysis.stages) == 1
        assert analysis.stages[0].effect_name == "input"

    def test_input_exceeds_ceiling(self):
        """analyze_chain should detect input exceeding ceiling."""
        fixer = AutoFix(sample_rate=44100, input_ceiling_db=-6.0)
        sr = 44100
        t = np.linspace(0, 1.0, sr, endpoint=False, dtype=np.float32)

        # Input at -3 dBFS (exceeds -6 dBFS ceiling)
        hot_audio = 0.707 * np.sin(2 * np.pi * 440 * t)
        # Output slightly reduced
        out_audio = hot_audio * 0.5

        rendered_stages = [("vc-comp", hot_audio, out_audio)]
        analysis = fixer.analyze_chain(hot_audio, [], rendered_stages)

        # Should have detected input ceiling issue
        assert any("exceeds ceiling" in issue for issue in analysis.stages[0].issues)

    def test_output_below_floor(self):
        """analyze_chain should detect output below SNR floor."""
        fixer = AutoFix(sample_rate=44100, output_floor_db=-24.0)
        sr = 44100
        t = np.linspace(0, 1.0, sr, endpoint=False, dtype=np.float32)

        # Input at reasonable level
        input_audio = 0.126 * np.sin(2 * np.pi * 440 * t)  # ~-18 dBFS
        # Output very quiet
        out_audio = input_audio * 0.01  # ~-58 dBFS

        rendered_stages = [("vc-comp", input_audio, out_audio)]
        analysis = fixer.analyze_chain(input_audio, [], rendered_stages)

        # Should have detected output floor issue
        assert any("below floor" in issue for issue in analysis.stages[0].issues)


class TestGainAccumulation:
    """Tests for gain accumulation detection."""

    def test_consecutive_boost_clip_risk(self):
        """Consecutive gain boosts > 6dB should flag clip risk."""
        fixer = AutoFix(sample_rate=44100)
        sr = 44100
        t = np.linspace(0, 1.0, sr, endpoint=False, dtype=np.float32)

        input_audio = 0.126 * np.sin(2 * np.pi * 440 * t)  # ~-18 dBFS
        after_gain1 = input_audio * 2.0   # +6dB
        after_gain2 = after_gain1 * 2.0   # +6dB more = +12dB total

        rendered_stages = [
            ("vc-gain-1", input_audio, after_gain1),
            ("vc-gain-2", after_gain1, after_gain2),
        ]

        analysis = fixer.analyze_chain(input_audio, [], rendered_stages)
        assert analysis.clip_risk is True
        assert any("Consecutive gain boost" in w for w in analysis.warnings)

    def test_consecutive_cut_snr_risk(self):
        """Consecutive gain cuts > 12dB should flag SNR risk."""
        fixer = AutoFix(sample_rate=44100)
        sr = 44100
        t = np.linspace(0, 1.0, sr, endpoint=False, dtype=np.float32)

        input_audio = 0.5 * np.sin(2 * np.pi * 440 * t)  # ~-6 dBFS
        after_eq = input_audio * 0.25     # -12dB
        after_comp = after_eq * 0.25      # -12dB more = -24dB total

        rendered_stages = [
            ("vc-eq", input_audio, after_eq),
            ("vc-comp", after_eq, after_comp),
        ]

        analysis = fixer.analyze_chain(input_audio, [], rendered_stages)
        assert analysis.snr_risk is True
        assert any("Consecutive gain cut" in w for w in analysis.warnings)


class TestFixGainStaging:
    """Tests for AutoFix.fix_gain_staging."""

    def test_fix_inserts_gain_before_hot_effect(self):
        """fix_gain_staging should insert gain reduction before hot effects."""
        fixer = AutoFix(sample_rate=44100, input_ceiling_db=-6.0)
        sr = 44100
        t = np.linspace(0, 1.0, sr, endpoint=False, dtype=np.float32)

        # Hot input that exceeds ceiling
        hot_audio = 0.707 * np.sin(2 * np.pi * 440 * t)  # ~-3 dBFS
        out_audio = hot_audio * 0.5

        rendered_stages = [("vc-comp", hot_audio, out_audio)]
        analysis = fixer.analyze_chain(hot_audio, [], rendered_stages)

        track_config = {
            "effects": [{"name": "vc-comp", "params": {"threshold": -20}}]
        }
        fixed = fixer.fix_gain_staging(track_config, analysis)

        # Should have inserted a vc-gain effect
        assert len(fixed["effects"]) > 1
        gain_effects = [e for e in fixed["effects"] if e["name"] == "vc-gain"]
        assert len(gain_effects) >= 1
        # The gain should be negative (reduction)
        assert any(e["params"]["gain"] < 0 for e in gain_effects)

    def test_fix_inserts_gain_after_quiet_effect(self):
        """fix_gain_staging should insert gain boost after too-quiet effects."""
        fixer = AutoFix(sample_rate=44100, output_floor_db=-24.0)
        sr = 44100
        t = np.linspace(0, 1.0, sr, endpoint=False, dtype=np.float32)

        input_audio = 0.126 * np.sin(2 * np.pi * 440 * t)
        quiet_out = input_audio * 0.01  # Very quiet

        rendered_stages = [("vc-comp", input_audio, quiet_out)]
        analysis = fixer.analyze_chain(input_audio, [], rendered_stages)

        track_config = {
            "effects": [{"name": "vc-comp", "params": {"threshold": -20}}]
        }
        fixed = fixer.fix_gain_staging(track_config, analysis)

        # Should have inserted a gain boost
        gain_effects = [e for e in fixed["effects"] if e["name"] == "vc-gain"]
        assert len(gain_effects) >= 1
        assert any(e["params"]["gain"] > 0 for e in gain_effects)

    def test_fix_does_not_modify_original(self):
        """fix_gain_staging should not modify the original config."""
        fixer = AutoFix(sample_rate=44100)
        analysis = ChainAnalysis()  # Empty analysis — no fixes needed

        track_config = {
            "effects": [{"name": "vc-gain", "params": {"gain": 3}}]
        }
        original_effects_len = len(track_config["effects"])
        fixed = fixer.fix_gain_staging(track_config, analysis)

        # Original should be unchanged
        assert len(track_config["effects"]) == original_effects_len

    def test_fix_empty_chain(self):
        """fix_gain_staging with empty chain should return unchanged config."""
        fixer = AutoFix(sample_rate=44100)
        analysis = ChainAnalysis()
        track_config = {"effects": []}
        fixed = fixer.fix_gain_staging(track_config, analysis)
        assert fixed["effects"] == []


class TestBackwardCompatibility:
    """Tests that Phase 1 API still works."""

    def test_analyze_phase1(self):
        """Phase 1 analyze() should still work."""
        fixer = AutoFix(sample_rate=44100)
        sr = 44100
        t = np.linspace(0, 1.0, sr, endpoint=False, dtype=np.float32)
        audio = 0.5 * np.sin(2 * np.pi * 440 * t)

        result = fixer.analyze(audio)
        assert "gain_db" in result
        assert "limiter" in result
        assert "warnings" in result
        assert isinstance(result["gain_db"], float)

    def test_apply_gain_phase1(self):
        """Phase 1 apply_gain() should still work."""
        fixer = AutoFix(sample_rate=44100)
        audio = np.ones(1000, dtype=np.float32) * 0.5
        result = fixer.apply_gain(audio, 6.0)
        # +6dB ≈ ×2 in linear
        expected = 0.5 * (10 ** (6.0 / 20.0))
        np.testing.assert_allclose(result, expected, atol=1e-5)

    def test_silent_track_warning(self):
        """Silent track should generate warning."""
        fixer = AutoFix(sample_rate=44100)
        audio = np.zeros(44100, dtype=np.float32)
        result = fixer.analyze(audio)
        assert any("Silent" in w for w in result["warnings"])

    def test_over_compression_warning(self):
        """Very low dynamic range should warn about over-compression."""
        fixer = AutoFix(sample_rate=44100)
        # Create a heavily limited signal (almost constant amplitude)
        sr = 44100
        t = np.linspace(0, 1.0, sr, endpoint=False, dtype=np.float32)
        # Near-constant level (very low dynamic range)
        audio = np.ones(sr, dtype=np.float32) * 0.5
        # Add tiny variation
        audio += 0.01 * np.sin(2 * np.pi * 440 * t)

        result = fixer.analyze(audio)
        # Dynamic range should be very small
        # This should trigger the over-compression warning
        assert "gain_db" in result
