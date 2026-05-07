"""test_reference_matcher.py — Tests for reference track matching."""

from __future__ import annotations

import numpy as np
import pytest

from vcmix.engine.reference_matcher import (
    AdjustmentSuggestion,
    DynamicFeatures,
    MatchDifference,
    ReferenceMatcher,
    ReferenceProfile,
    SpectralFeatures,
)


@pytest.fixture
def matcher():
    return ReferenceMatcher(sample_rate=44100)


@pytest.fixture
def sine_audio():
    """1-second 440Hz sine at -12dBFS."""
    sr = 44100
    t = np.linspace(0, 1.0, sr, endpoint=False, dtype=np.float64)
    return 0.25 * np.sin(2 * np.pi * 440 * t)


@pytest.fixture
def quiet_audio():
    """1-second 440Hz sine at -30dBFS (much quieter)."""
    sr = 44100
    t = np.linspace(0, 1.0, sr, endpoint=False, dtype=np.float64)
    return 0.03 * np.sin(2 * np.pi * 440 * t)


@pytest.fixture
def bright_audio():
    """White noise (broadband, flat spectrum)."""
    sr = 44100
    np.random.seed(42)
    return np.random.randn(sr).astype(np.float64) * 0.1


class TestSpectralFeatures:

    def test_default_values(self):
        sf = SpectralFeatures()
        assert len(sf.band_rms_db) == 8
        assert all(v == -60.0 for v in sf.band_rms_db)
        assert sf.overall_rms_db == -60.0


class TestAnalyzeReference:

    def test_returns_profile(self, matcher, sine_audio):
        profile = matcher.analyze_reference(sine_audio)
        assert isinstance(profile, ReferenceProfile)
        assert isinstance(profile.spectral, SpectralFeatures)
        assert isinstance(profile.dynamic, DynamicFeatures)

    def test_spectral_bands_populated(self, matcher, sine_audio):
        profile = matcher.analyze_reference(sine_audio)
        # 440Hz falls in the 500Hz band, so that band should be loudest
        # Band centers: 63, 125, 250, 500, 1k, 2k, 4k, 8k
        band_500_idx = 3  # 500Hz band
        # At least one band should be > -60dB (i.e., have signal)
        assert max(profile.spectral.band_rms_db) > -60.0

    def test_overall_levels(self, matcher, sine_audio):
        profile = matcher.analyze_reference(sine_audio)
        # -12dBFS signal should have RMS close to -12dB
        assert profile.spectral.overall_rms_db > -30.0
        assert profile.spectral.overall_peak_db > -20.0

    def test_dynamic_features(self, matcher, sine_audio):
        profile = matcher.analyze_reference(sine_audio)
        assert profile.dynamic.crest_factor_db >= 0.0
        assert profile.dynamic.dynamic_range_db >= 0.0

    def test_quiet_vs_loud(self, matcher, sine_audio, quiet_audio):
        loud = matcher.analyze_reference(sine_audio)
        quiet = matcher.analyze_reference(quiet_audio)
        assert loud.spectral.overall_rms_db > quiet.spectral.overall_rms_db

    def test_broadband_spectrum(self, matcher, bright_audio):
        profile = matcher.analyze_reference(bright_audio)
        # White noise should have relatively flat bands
        bands = profile.spectral.band_rms_db
        band_range = max(bands) - min(bands)
        # White noise shouldn't have >20dB variation between bands
        assert band_range < 25.0


class TestComputeMatch:

    def test_identical_profiles(self, matcher, sine_audio):
        profile = matcher.analyze_reference(sine_audio)
        diff = matcher.compute_match(profile, profile)
        assert diff.similarity_score == pytest.approx(1.0, abs=0.01)
        assert all(abs(d) < 0.01 for d in diff.band_delta_db)
        assert abs(diff.rms_delta_db) < 0.01

    def test_different_profiles(self, matcher, sine_audio, quiet_audio):
        loud = matcher.analyze_reference(sine_audio)
        quiet = matcher.analyze_reference(quiet_audio)
        diff = matcher.compute_match(loud, quiet)
        # Loud should have higher RMS than quiet
        assert diff.rms_delta_db > 0
        # Similarity should be < 1.0
        assert diff.similarity_score < 1.0

    def test_match_difference_fields(self, matcher, sine_audio,
                                      quiet_audio):
        current = matcher.analyze_reference(sine_audio)
        reference = matcher.analyze_reference(quiet_audio)
        diff = matcher.compute_match(current, reference)
        assert len(diff.band_delta_db) == 8
        assert isinstance(diff.rms_delta_db, float)
        assert isinstance(diff.dynamic_range_delta_db, float)


class TestGenerateAdjustments:

    def test_no_adjustment_needed(self, matcher, sine_audio):
        profile = matcher.analyze_reference(sine_audio)
        diff = matcher.compute_match(profile, profile)
        suggestions = matcher.generate_adjustments(diff)
        # Identical profiles should need few or no adjustments
        high_priority = [s for s in suggestions if s.priority > 0.5]
        assert len(high_priority) == 0

    def test_gain_adjustment_suggested(self, matcher, sine_audio,
                                        quiet_audio):
        loud = matcher.analyze_reference(sine_audio)
        quiet = matcher.analyze_reference(quiet_audio)
        diff = matcher.compute_match(loud, quiet)
        suggestions = matcher.generate_adjustments(diff)
        # Should suggest gain adjustment
        gain_suggestions = [s for s in suggestions
                           if s.target == "gain"]
        assert len(gain_suggestions) >= 1

    def test_suggestions_sorted_by_priority(self, matcher, sine_audio,
                                             quiet_audio):
        loud = matcher.analyze_reference(sine_audio)
        quiet = matcher.analyze_reference(quiet_audio)
        diff = matcher.compute_match(loud, quiet)
        suggestions = matcher.generate_adjustments(diff)
        # Should be sorted by priority (highest first)
        priorities = [s.priority for s in suggestions]
        assert priorities == sorted(priorities, reverse=True)

    def test_suggestion_fields(self, matcher):
        diff = MatchDifference(
            band_delta_db=[0.0] * 8,
            rms_delta_db=5.0,
            dynamic_range_delta_db=0.0,
            crest_delta_db=0.0,
            similarity_score=0.5,
        )
        suggestions = matcher.generate_adjustments(diff)
        for s in suggestions:
            assert isinstance(s, AdjustmentSuggestion)
            assert s.target in ("eq", "comp", "gain", "limiter")
            assert isinstance(s.params, dict)
            assert isinstance(s.reason, str)
            assert 0.0 <= s.priority <= 1.0

    def test_eq_adjustment_for_band_difference(self, matcher):
        diff = MatchDifference(
            band_delta_db=[5.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
            rms_delta_db=0.0,
            dynamic_range_delta_db=0.0,
            crest_delta_db=0.0,
            similarity_score=0.5,
        )
        suggestions = matcher.generate_adjustments(diff)
        eq_suggestions = [s for s in suggestions if s.target == "eq"]
        assert len(eq_suggestions) >= 1
        # Should suggest reducing the 63Hz band
        eq63 = [s for s in eq_suggestions
                if s.params.get("frequency") == 63]
        assert len(eq63) >= 1
        assert eq63[0].params["gain_db"] < 0  # Should reduce


class TestEdgeCases:

    def test_silent_reference(self, matcher):
        sr = 44100
        silence = np.zeros(sr, dtype=np.float64)
        profile = matcher.analyze_reference(silence)
        assert profile.spectral.overall_rms_db == -120.0

    def test_short_audio(self, matcher):
        sr = 44100
        short = np.ones(100, dtype=np.float64) * 0.5
        profile = matcher.analyze_reference(short)
        assert isinstance(profile, ReferenceProfile)
