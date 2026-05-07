"""
test_reference_matcher.py — Tests for vcmix.engine.reference_matcher (Phase 6).

Tests the reference track matching engine:
    - analyze_reference() — Extract spectral/dynamic features
    - compute_match() — Compute difference between current and reference
    - generate_adjustments() — Generate EQ/Comp/Level suggestions
    - Integration: full pipeline from audio to adjustments

Usage:
    pytest tests/test_reference_matcher.py -v

Dependencies: pytest, numpy
"""

from __future__ import annotations

import numpy as np
import pytest

from vcmix.engine.reference_matcher import (
    MatchDiff,
    ReferenceAdjustment,
    ReferenceMatcher,
    SpectralFeatures,
)


class TestSpectralFeatures:
    """Tests for SpectralFeatures dataclass."""

    def test_default_values(self) -> None:
        """Default SpectralFeatures should have -120 dBFS levels."""
        features = SpectralFeatures()
        assert features.rms_db == -120.0
        assert features.peak_db == -120.0
        assert features.dynamic_range_db == 0.0
        assert features.spectral_centroid_hz == 0.0


class TestAnalyzeReference:
    """Tests for ReferenceMatcher.analyze_reference()."""

    def test_analyze_sine_wave(self) -> None:
        """Analyzing a 440Hz sine should return reasonable features."""
        sr = 44100
        t = np.linspace(0, 1.0, sr, endpoint=False, dtype=np.float32)
        audio = 0.5 * np.sin(2 * np.pi * 440 * t)

        matcher = ReferenceMatcher(sample_rate=sr)
        features = matcher.analyze_reference(audio)

        assert features.rms_db > -120.0
        assert features.peak_db > -120.0
        assert features.dynamic_range_db > 0
        assert len(features.bands) > 0
        assert "mid" in features.bands

    def test_analyze_stereo_audio(self) -> None:
        """Should handle stereo audio (2D array)."""
        sr = 44100
        t = np.linspace(0, 1.0, sr, endpoint=False, dtype=np.float32)
        left = 0.5 * np.sin(2 * np.pi * 440 * t)
        right = 0.3 * np.sin(2 * np.pi * 880 * t)
        stereo = np.stack([left, right])

        matcher = ReferenceMatcher(sample_rate=sr)
        features = matcher.analyze_reference(stereo)

        assert features.rms_db > -120.0

    def test_analyze_silence(self) -> None:
        """Silent audio should return -120 dBFS."""
        sr = 44100
        audio = np.zeros(sr, dtype=np.float32)

        matcher = ReferenceMatcher(sample_rate=sr)
        features = matcher.analyze_reference(audio)

        assert features.rms_db <= -100.0
        assert features.peak_db <= -100.0

    def test_band_ratios_sum_approximately_one(self) -> None:
        """Band ratios should sum to approximately 1.0."""
        sr = 44100
        t = np.linspace(0, 1.0, sr, endpoint=False, dtype=np.float32)
        audio = 0.5 * np.sin(2 * np.pi * 440 * t)

        matcher = ReferenceMatcher(sample_rate=sr)
        features = matcher.analyze_reference(audio)

        total = sum(features.band_ratios.values())
        assert 0.9 < total < 1.1

    def test_spectral_centroid_of_sine(self) -> None:
        """440Hz sine should have spectral centroid near 440Hz."""
        sr = 44100
        t = np.linspace(0, 1.0, sr, endpoint=False, dtype=np.float32)
        audio = 0.5 * np.sin(2 * np.pi * 440 * t)

        matcher = ReferenceMatcher(sample_rate=sr)
        features = matcher.analyze_reference(audio)

        # Spectral centroid should be in the mid frequency range
        assert features.spectral_centroid_hz > 100
        assert features.spectral_centroid_hz < 5000

    def test_high_frequency_audio_has_higher_centroid(self) -> None:
        """High-frequency audio should have higher spectral centroid."""
        sr = 44100
        t = np.linspace(0, 1.0, sr, endpoint=False, dtype=np.float32)
        low_audio = 0.5 * np.sin(2 * np.pi * 200 * t)
        high_audio = 0.5 * np.sin(2 * np.pi * 5000 * t)

        matcher = ReferenceMatcher(sample_rate=sr)
        low_features = matcher.analyze_reference(low_audio)
        high_features = matcher.analyze_reference(high_audio)

        assert high_features.spectral_centroid_hz > low_features.spectral_centroid_hz

    def test_sample_rate_override(self) -> None:
        """Passing sr parameter should override the default sample rate."""
        sr = 48000
        t = np.linspace(0, 1.0, sr, endpoint=False, dtype=np.float32)
        audio = 0.5 * np.sin(2 * np.pi * 440 * t)

        matcher = ReferenceMatcher(sample_rate=44100)
        features = matcher.analyze_reference(audio, sr=sr)

        # Should not crash and should return valid features
        assert features.rms_db > -120.0


class TestComputeMatch:
    """Tests for ReferenceMatcher.compute_match()."""

    def test_identical_features(self) -> None:
        """Identical current and reference should produce near-zero deltas."""
        features = SpectralFeatures(
            bands={"sub": 0.01, "low": 0.05, "mid": 0.30, "high_mid": 0.25, "high": 0.20, "air": 0.05},
            rms_db=-16.0,
            peak_db=-4.0,
            dynamic_range_db=12.0,
            spectral_centroid_hz=2000.0,
            band_ratios={"sub": 0.013, "low": 0.065, "mid": 0.39, "high_mid": 0.325, "high": 0.26, "air": 0.065},
        )

        matcher = ReferenceMatcher()
        diff = matcher.compute_match(features, features)

        assert diff.rms_delta_db == 0.0
        assert diff.peak_delta_db == 0.0
        assert diff.dr_delta_db == 0.0
        assert not diff.needs_level
        assert not diff.needs_comp

    def test_level_mismatch(self) -> None:
        """Different RMS levels should flag needs_level."""
        current = SpectralFeatures(rms_db=-20.0, peak_db=-8.0, dynamic_range_db=12.0)
        reference = SpectralFeatures(rms_db=-14.0, peak_db=-3.0, dynamic_range_db=11.0)

        matcher = ReferenceMatcher()
        diff = matcher.compute_match(current, reference)

        assert diff.rms_delta_db == -6.0
        assert diff.needs_level is True

    def test_dynamic_range_mismatch(self) -> None:
        """Different dynamic ranges should flag needs_comp."""
        current = SpectralFeatures(rms_db=-16.0, peak_db=-4.0, dynamic_range_db=12.0)
        reference = SpectralFeatures(rms_db=-16.0, peak_db=-4.0, dynamic_range_db=6.0)

        matcher = ReferenceMatcher()
        diff = matcher.compute_match(current, reference)

        assert diff.dr_delta_db == 6.0
        assert diff.needs_comp is True

    def test_spectral_mismatch(self) -> None:
        """Different band ratios should flag needs_eq."""
        current = SpectralFeatures(
            rms_db=-16.0,
            peak_db=-4.0,
            dynamic_range_db=12.0,
            band_ratios={"sub": 0.1, "low": 0.2, "mid": 0.30, "high_mid": 0.15, "high": 0.15, "air": 0.1},
        )
        reference = SpectralFeatures(
            rms_db=-16.0,
            peak_db=-4.0,
            dynamic_range_db=12.0,
            band_ratios={"sub": 0.01, "low": 0.05, "mid": 0.30, "high_mid": 0.30, "high": 0.25, "air": 0.09},
        )

        matcher = ReferenceMatcher()
        diff = matcher.compute_match(current, reference)

        assert diff.needs_eq is True
        assert "sub" in diff.band_deltas
        assert "low" in diff.band_deltas

    def test_match_summary(self) -> None:
        """Match should include a human-readable summary."""
        current = SpectralFeatures(rms_db=-20.0, peak_db=-8.0, dynamic_range_db=12.0)
        reference = SpectralFeatures(rms_db=-14.0, peak_db=-3.0, dynamic_range_db=6.0)

        matcher = ReferenceMatcher()
        diff = matcher.compute_match(current, reference)

        assert len(diff.summary) > 0

    def test_close_match_summary(self) -> None:
        """Close match should report closely matches."""
        features = SpectralFeatures(
            rms_db=-16.0,
            peak_db=-4.0,
            dynamic_range_db=12.0,
            band_ratios={"sub": 0.02, "low": 0.06, "mid": 0.35, "high_mid": 0.28, "high": 0.22, "air": 0.07},
        )
        reference = SpectralFeatures(
            rms_db=-16.0,
            peak_db=-4.0,
            dynamic_range_db=12.0,
            band_ratios={"sub": 0.02, "low": 0.06, "mid": 0.35, "high_mid": 0.28, "high": 0.22, "air": 0.07},
        )

        matcher = ReferenceMatcher()
        diff = matcher.compute_match(features, reference)

        assert "closely matches" in diff.summary.lower()


class TestGenerateAdjustments:
    """Tests for ReferenceMatcher.generate_adjustments()."""

    def test_no_adjustments_for_close_match(self) -> None:
        """Close match should produce no adjustments."""
        diff = MatchDiff(
            rms_delta_db=0.5,
            peak_delta_db=0.3,
            dr_delta_db=1.0,
            band_deltas={"mid": 0.01},
            needs_eq=False,
            needs_comp=False,
            needs_level=False,
            summary="Close match",
        )

        matcher = ReferenceMatcher()
        adjustments = matcher.generate_adjustments(diff)

        assert len(adjustments) == 0

    def test_level_adjustment(self) -> None:
        """Level mismatch should produce gain adjustment."""
        diff = MatchDiff(
            rms_delta_db=-6.0,
            peak_delta_db=-5.0,
            dr_delta_db=1.0,
            band_deltas={},
            needs_level=True,
            needs_comp=False,
            needs_eq=False,
            summary="Level mismatch",
        )

        matcher = ReferenceMatcher()
        adjustments = matcher.generate_adjustments(diff)

        level_adj = [a for a in adjustments if a.category == "level"]
        assert len(level_adj) >= 1
        assert level_adj[0].params["gain_db"] > 0  # Need to boost

    def test_eq_adjustment_for_low_buildup(self) -> None:
        """Low-frequency buildup should produce EQ adjustment."""
        diff = MatchDiff(
            rms_delta_db=0.5,
            peak_delta_db=0.3,
            dr_delta_db=1.0,
            band_deltas={"sub": 0.1, "low": 0.08, "high_mid": -0.1},
            needs_eq=True,
            needs_comp=False,
            needs_level=False,
            summary="Low-frequency buildup",
        )

        matcher = ReferenceMatcher()
        adjustments = matcher.generate_adjustments(diff)

        eq_adj = [a for a in adjustments if a.category == "eq"]
        assert len(eq_adj) >= 1
        assert "low_cut" in eq_adj[0].params

    def test_comp_adjustment_too_dynamic(self) -> None:
        """Mix more dynamic than reference should produce compression."""
        diff = MatchDiff(
            rms_delta_db=0.5,
            peak_delta_db=0.3,
            dr_delta_db=5.0,
            band_deltas={},
            needs_eq=False,
            needs_comp=True,
            needs_level=False,
            summary="Too dynamic",
        )

        matcher = ReferenceMatcher()
        adjustments = matcher.generate_adjustments(diff)

        comp_adj = [a for a in adjustments if a.category == "comp"]
        assert len(comp_adj) >= 1
        # Should add compression
        assert "threshold_db" in comp_adj[0].params or "ratio" in comp_adj[0].params

    def test_comp_adjustment_over_compressed(self) -> None:
        """Mix less dynamic than reference should reduce compression."""
        diff = MatchDiff(
            rms_delta_db=0.5,
            peak_delta_db=0.3,
            dr_delta_db=-5.0,
            band_deltas={},
            needs_eq=False,
            needs_comp=True,
            needs_level=False,
            summary="Over-compressed",
        )

        matcher = ReferenceMatcher()
        adjustments = matcher.generate_adjustments(diff)

        comp_adj = [a for a in adjustments if a.category == "comp"]
        assert len(comp_adj) >= 1
        assert comp_adj[0].params.get("action") == "reduce"

    def test_centroid_brightness_adjustment(self) -> None:
        """Centroid delta should produce brightness EQ adjustment."""
        diff = MatchDiff(
            rms_delta_db=0.5,
            peak_delta_db=0.3,
            dr_delta_db=1.0,
            band_deltas={"high_mid": -0.08, "high": -0.06, "air": -0.05},
            centroid_delta_hz=-800.0,
            needs_eq=True,
            needs_comp=False,
            needs_level=False,
            summary="Darker than reference",
        )

        matcher = ReferenceMatcher()
        adjustments = matcher.generate_adjustments(diff)

        eq_adj = [a for a in adjustments if a.category == "eq"]
        assert len(eq_adj) >= 1
        # Should boost high shelf (brighten)
        assert eq_adj[0].params.get("high_shelf_gain", 0) > 0

    def test_custom_target(self) -> None:
        """Adjustments should use the specified target."""
        diff = MatchDiff(
            rms_delta_db=-6.0,
            peak_delta_db=-5.0,
            dr_delta_db=1.0,
            band_deltas={},
            needs_level=True,
            needs_comp=False,
            needs_eq=False,
            summary="Level mismatch",
        )

        matcher = ReferenceMatcher()
        adjustments = matcher.generate_adjustments(diff, target="track:vocal")

        for adj in adjustments:
            assert adj.target == "track:vocal"


class TestReferenceMatcherIntegration:
    """Integration tests: audio -> features -> match -> adjustments."""

    def test_full_pipeline_different_audio(self) -> None:
        """Full pipeline with different audio should produce adjustments."""
        sr = 44100
        t = np.linspace(0, 1.0, sr, endpoint=False, dtype=np.float32)

        # Reference: bright 440Hz sine
        ref_audio = 0.5 * np.sin(2 * np.pi * 440 * t)
        # Current: darker 200Hz sine (lower volume)
        cur_audio = 0.2 * np.sin(2 * np.pi * 200 * t)

        matcher = ReferenceMatcher(sample_rate=sr)
        ref_features = matcher.analyze_reference(ref_audio)
        cur_features = matcher.analyze_reference(cur_audio)

        diff = matcher.compute_match(cur_features, ref_features)
        adjustments = matcher.generate_adjustments(diff)

        # Should detect level difference (0.2 vs 0.5 amplitude)
        assert diff.needs_level is True
        assert len(adjustments) > 0

    def test_full_pipeline_same_audio(self) -> None:
        """Same audio for current and reference should produce minimal adjustments."""
        sr = 44100
        t = np.linspace(0, 1.0, sr, endpoint=False, dtype=np.float32)
        audio = 0.5 * np.sin(2 * np.pi * 440 * t)

        matcher = ReferenceMatcher(sample_rate=sr)
        features = matcher.analyze_reference(audio)

        diff = matcher.compute_match(features, features)
        adjustments = matcher.generate_adjustments(diff)

        assert len(adjustments) == 0

    def test_realistic_mixing_scenario(self) -> None:
        """Simulate a realistic mixing scenario with multiple band differences."""
        sr = 44100
        t = np.linspace(0, 2.0, int(sr * 2), endpoint=False, dtype=np.float32)

        # Reference: balanced mix
        ref_audio = (
            0.2 * np.sin(2 * np.pi * 100 * t)   # Low
            + 0.3 * np.sin(2 * np.pi * 500 * t)  # Mid
            + 0.2 * np.sin(2 * np.pi * 3000 * t) # High-mid
            + 0.1 * np.sin(2 * np.pi * 8000 * t) # High
        )

        # Current: bass-heavy, quiet highs
        cur_audio = (
            0.4 * np.sin(2 * np.pi * 100 * t)   # Too much low
            + 0.3 * np.sin(2 * np.pi * 500 * t)  # Same mid
            + 0.1 * np.sin(2 * np.pi * 3000 * t) # Less high-mid
            + 0.05 * np.sin(2 * np.pi * 8000 * t) # Much less high
        )

        matcher = ReferenceMatcher(sample_rate=sr)
        ref_features = matcher.analyze_reference(ref_audio)
        cur_features = matcher.analyze_reference(cur_audio)

        diff = matcher.compute_match(cur_features, ref_features)

        # Should detect spectral mismatch
        assert diff.needs_eq is True

        adjustments = matcher.generate_adjustments(diff)
        assert len(adjustments) > 0

        # Should have EQ adjustment
        eq_adj = [a for a in adjustments if a.category == "eq"]
        assert len(eq_adj) >= 1
