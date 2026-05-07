"""
test_arrangement_strategy.py — Tests for arrangement-aware mixing strategy.

Tests the Phase 7 ArrangementStrategy and SectionMixParams classes:
    - from_sections() factory method
    - get_params_at_beat() query with crossfade
    - to_yaml_overrides() YAML export
    - Default parameter mapping per section type
    - Crossfade interpolation between sections
    - Outro fade handling
    - Edge cases (single section, empty, etc.)

Usage:
    pytest tests/test_arrangement_strategy.py -v

Dependencies: pytest, numpy, pyyaml
"""

from __future__ import annotations

import yaml

import pytest

from vcmix.separation.arrangement import Section
from vcmix.engine.arrangement_strategy import (
    ArrangementStrategy,
    SectionMixParams,
    _SECTION_DEFAULTS,
    _interpolate_params,
)


# ---------------------------------------------------------------------------
# Helper: create Section objects
# ---------------------------------------------------------------------------

def _make_sections() -> list[Section]:
    """Create a typical 5-section song arrangement (32 beats)."""
    beat_sec = 0.5  # 120 BPM
    return [
        Section(name="intro",  start_beat=0,  end_beat=4,
                start_sec=0.0,  end_sec=2.0,  active_stems=["bass"],
                energy_level="low"),
        Section(name="verse",  start_beat=4,  end_beat=12,
                start_sec=2.0,  end_sec=6.0,  active_stems=["bass", "drums"],
                energy_level="medium"),
        Section(name="chorus", start_beat=12, end_beat=20,
                start_sec=6.0,  end_sec=10.0, active_stems=["bass", "drums", "vocals"],
                energy_level="high"),
        Section(name="bridge", start_beat=20, end_beat=24,
                start_sec=10.0, end_sec=12.0, active_stems=["vocals"],
                energy_level="low"),
        Section(name="outro",  start_beat=24, end_beat=32,
                start_sec=12.0, end_sec=16.0, active_stems=["bass", "drums"],
                energy_level="medium"),
    ]


# ---------------------------------------------------------------------------
# Tests: SectionMixParams
# ---------------------------------------------------------------------------

class TestSectionMixParams:

    def test_default_values(self):
        """SectionMixParams should have sensible defaults."""
        p = SectionMixParams(section_name="test")
        assert p.section_name == "test"
        assert p.reverb_mix == 0.0
        assert p.delay_mix == 0.0
        assert p.compression_ratio == 1.0
        assert p.gain_db == 0.0
        assert p.crossfade_beats == 2

    def test_custom_values(self):
        """SectionMixParams should accept custom values."""
        p = SectionMixParams(
            section_name="chorus",
            reverb_mix=0.20,
            delay_mix=0.20,
            compression_ratio=3.0,
            gain_db=2.0,
            crossfade_beats=4,
        )
        assert p.reverb_mix == 0.20
        assert p.compression_ratio == 3.0
        assert p.gain_db == 2.0


# ---------------------------------------------------------------------------
# Tests: ArrangementStrategy.from_sections()
# ---------------------------------------------------------------------------

class TestFromSections:

    def test_creates_strategy(self):
        """from_sections() should return a valid ArrangementStrategy."""
        sections = _make_sections()
        strategy = ArrangementStrategy.from_sections(sections)
        assert isinstance(strategy, ArrangementStrategy)
        assert len(strategy.sections) == 5
        assert strategy.total_beats == 32

    def test_section_map_populated(self):
        """section_map should map start_beats to section indices."""
        sections = _make_sections()
        strategy = ArrangementStrategy.from_sections(sections)
        assert 0 in strategy.section_map
        assert 4 in strategy.section_map
        assert 12 in strategy.section_map
        assert strategy.section_map[0] == 0
        assert strategy.section_map[4] == 1

    def test_intro_params(self):
        """Intro section should have low reverb, low delay, 1.5:1 compression."""
        sections = _make_sections()
        strategy = ArrangementStrategy.from_sections(sections)
        intro = strategy.sections[0]
        assert intro.section_name == "intro"
        assert intro.reverb_mix == pytest.approx(0.05)
        assert intro.delay_mix == pytest.approx(0.05)
        assert intro.compression_ratio == pytest.approx(1.5)

    def test_verse_params(self):
        """Verse section should have medium reverb, 2:1 compression."""
        sections = _make_sections()
        strategy = ArrangementStrategy.from_sections(sections)
        verse = strategy.sections[1]
        assert verse.section_name == "verse"
        assert verse.reverb_mix == pytest.approx(0.10)
        assert verse.compression_ratio == pytest.approx(2.0)

    def test_chorus_params(self):
        """Chorus should have high reverb, 3:1 compression, +2dB gain."""
        sections = _make_sections()
        strategy = ArrangementStrategy.from_sections(sections)
        chorus = strategy.sections[2]
        assert chorus.section_name == "chorus"
        assert chorus.reverb_mix == pytest.approx(0.20)
        assert chorus.compression_ratio == pytest.approx(3.0)
        assert chorus.gain_db == pytest.approx(2.0)

    def test_bridge_params(self):
        """Bridge should have high reverb, low compression."""
        sections = _make_sections()
        strategy = ArrangementStrategy.from_sections(sections)
        bridge = strategy.sections[3]
        assert bridge.section_name == "bridge"
        assert bridge.reverb_mix == pytest.approx(0.25)
        assert bridge.compression_ratio == pytest.approx(1.5)

    def test_outro_params(self):
        """Outro should have reduced parameters (fade applied)."""
        sections = _make_sections()
        strategy = ArrangementStrategy.from_sections(sections)
        outro = strategy.sections[4]
        assert outro.section_name == "outro"
        assert outro.gain_db < 0  # gain reduction applied

    def test_overrides_applied(self):
        """Custom overrides should override default values."""
        sections = _make_sections()
        strategy = ArrangementStrategy.from_sections(
            sections, overrides={"chorus": {"reverb_mix": 0.35, "gain_db": 3.0}}
        )
        chorus = strategy.sections[2]
        assert chorus.reverb_mix == pytest.approx(0.35)
        assert chorus.gain_db == pytest.approx(3.0)

    def test_unknown_section_uses_verse_defaults(self):
        """Unknown section names should fall back to verse defaults."""
        sections = [Section(
            name="breakdown", start_beat=0, end_beat=8,
            start_sec=0.0, end_sec=4.0,
        )]
        strategy = ArrangementStrategy.from_sections(sections)
        assert strategy.sections[0].reverb_mix == pytest.approx(0.10)  # verse default

    def test_empty_sections(self):
        """Empty sections list should produce empty strategy."""
        strategy = ArrangementStrategy.from_sections([])
        assert len(strategy.sections) == 0
        assert strategy.total_beats == 0


# ---------------------------------------------------------------------------
# Tests: ArrangementStrategy.get_params_at_beat()
# ---------------------------------------------------------------------------

class TestGetParamsAtBeat:

    def test_returns_params_in_section(self):
        """Beat within a section returns that section's params."""
        sections = _make_sections()
        strategy = ArrangementStrategy.from_sections(sections)
        # Beat 2 is in intro (beats 0-4)
        params = strategy.get_params_at_beat(2)
        assert params.section_name == "intro"

    def test_returns_chorus_params(self):
        """Beat within chorus returns chorus params."""
        sections = _make_sections()
        strategy = ArrangementStrategy.from_sections(sections)
        # Beat 15 is in chorus (beats 12-20), outside crossfade zone
        params = strategy.get_params_at_beat(15)
        assert params.section_name == "chorus"

    def test_crossfade_at_section_start(self):
        """Beats at section start should be crossfaded from previous."""
        sections = _make_sections()
        strategy = ArrangementStrategy.from_sections(sections)
        # Verse starts at beat 4, crossfade_beats=2
        # Beat 4 is at progress 0.0 — should be close to intro params
        params = strategy.get_params_at_beat(4)
        # The interpolation at progress=0 should be very close to intro
        intro_params = strategy.sections[0]
        assert params.reverb_mix == pytest.approx(intro_params.reverb_mix)

    def test_crossfade_completed(self):
        """Beats past crossfade zone should have pure section params."""
        sections = _make_sections()
        strategy = ArrangementStrategy.from_sections(sections)
        # Verse starts at beat 4, crossfade=2 beats
        # Beat 7 is past crossfade (4+2=6)
        params = strategy.get_params_at_beat(7)
        verse_params = strategy.sections[1]
        assert params.reverb_mix == pytest.approx(verse_params.reverb_mix)

    def test_negative_beat_raises(self):
        """Negative beat should raise ValueError."""
        sections = _make_sections()
        strategy = ArrangementStrategy.from_sections(sections)
        with pytest.raises(ValueError):
            strategy.get_params_at_beat(-1)

    def test_beat_beyond_song_returns_last_section(self):
        """Beat beyond song length returns last section's params."""
        sections = _make_sections()
        strategy = ArrangementStrategy.from_sections(sections)
        params = strategy.get_params_at_beat(100)
        assert params.section_name == "outro"

    def test_first_section_no_crossfade(self):
        """Beat in first section with no previous section — no crossfade."""
        sections = _make_sections()
        strategy = ArrangementStrategy.from_sections(sections)
        # Beat 0 is in intro — no previous section for crossfade
        params = strategy.get_params_at_beat(0)
        assert params.section_name == "intro"
        assert params.reverb_mix == pytest.approx(0.05)

    def test_single_section_strategy(self):
        """Strategy with one section should work without crossfade."""
        sections = [Section(
            name="verse", start_beat=0, end_beat=16,
            start_sec=0.0, end_sec=8.0,
        )]
        strategy = ArrangementStrategy.from_sections(sections)
        params = strategy.get_params_at_beat(5)
        assert params.section_name == "verse"
        assert params.reverb_mix == pytest.approx(0.10)


# ---------------------------------------------------------------------------
# Tests: ArrangementStrategy.to_yaml_overrides()
# ---------------------------------------------------------------------------

class TestToYamlOverrides:

    def test_produces_valid_yaml(self):
        """to_yaml_overrides() should produce valid YAML."""
        sections = _make_sections()
        strategy = ArrangementStrategy.from_sections(sections)
        yaml_str = strategy.to_yaml_overrides()
        parsed = yaml.safe_load(yaml_str)
        assert "arrangement_strategy" in parsed

    def test_contains_all_sections(self):
        """YAML should contain entries for all sections."""
        sections = _make_sections()
        strategy = ArrangementStrategy.from_sections(sections)
        yaml_str = strategy.to_yaml_overrides()
        parsed = yaml.safe_load(yaml_str)
        strat = parsed["arrangement_strategy"]
        assert len(strat) == 5

    def test_section_keys_named_correctly(self):
        """Section keys should follow pattern section_{idx}_{name}."""
        sections = _make_sections()
        strategy = ArrangementStrategy.from_sections(sections)
        yaml_str = strategy.to_yaml_overrides()
        parsed = yaml.safe_load(yaml_str)
        strat = parsed["arrangement_strategy"]
        assert "section_0_intro" in strat
        assert "section_2_chorus" in strat

    def test_each_section_has_required_fields(self):
        """Each section entry should have all required parameter fields."""
        required_fields = {
            "start_beat", "section_name", "reverb_mix",
            "delay_mix", "compression_ratio", "gain_db", "crossfade_beats",
        }
        sections = _make_sections()
        strategy = ArrangementStrategy.from_sections(sections)
        yaml_str = strategy.to_yaml_overrides()
        parsed = yaml.safe_load(yaml_str)
        for key, val in parsed["arrangement_strategy"].items():
            assert required_fields.issubset(set(val.keys())), (
                f"Missing fields in {key}: {required_fields - set(val.keys())}"
            )

    def test_empty_strategy_yaml(self):
        """Empty strategy should produce valid YAML with empty sections."""
        strategy = ArrangementStrategy()
        yaml_str = strategy.to_yaml_overrides()
        parsed = yaml.safe_load(yaml_str)
        assert "arrangement_strategy" in parsed
        assert len(parsed["arrangement_strategy"]) == 0


# ---------------------------------------------------------------------------
# Tests: _interpolate_params()
# ---------------------------------------------------------------------------

class TestInterpolation:

    def test_at_zero_returns_prev(self):
        """At progress=0, interpolation should return prev params."""
        prev = SectionMixParams(section_name="intro", reverb_mix=0.05, gain_db=0.0)
        curr = SectionMixParams(section_name="verse", reverb_mix=0.10, gain_db=1.0)
        result = _interpolate_params(prev, curr, 0.0)
        assert result.reverb_mix == pytest.approx(0.05)
        assert result.gain_db == pytest.approx(0.0)

    def test_at_one_returns_curr(self):
        """At progress=1, interpolation should return curr params."""
        prev = SectionMixParams(section_name="intro", reverb_mix=0.05, gain_db=0.0)
        curr = SectionMixParams(section_name="verse", reverb_mix=0.10, gain_db=1.0)
        result = _interpolate_params(prev, curr, 1.0)
        assert result.reverb_mix == pytest.approx(0.10)
        assert result.gain_db == pytest.approx(1.0)

    def test_at_half_returns_midpoint(self):
        """At progress=0.5, interpolation should return midpoints."""
        prev = SectionMixParams(section_name="intro", reverb_mix=0.0, compression_ratio=1.0)
        curr = SectionMixParams(section_name="chorus", reverb_mix=0.20, compression_ratio=3.0)
        result = _interpolate_params(prev, curr, 0.5)
        assert result.reverb_mix == pytest.approx(0.10)
        assert result.compression_ratio == pytest.approx(2.0)

    def test_section_name_transitions(self):
        """Section name should be prev at progress<0.5 and curr at >=0.5."""
        prev = SectionMixParams(section_name="intro")
        curr = SectionMixParams(section_name="chorus")
        assert _interpolate_params(prev, curr, 0.3).section_name == "intro"
        assert _interpolate_params(prev, curr, 0.5).section_name == "chorus"
        assert _interpolate_params(prev, curr, 0.7).section_name == "chorus"


# ---------------------------------------------------------------------------
# Tests: Section defaults consistency
# ---------------------------------------------------------------------------

class TestSectionDefaults:

    def test_all_section_types_have_defaults(self):
        """All 5 section types should have default parameters."""
        for name in ("intro", "verse", "chorus", "bridge", "outro"):
            assert name in _SECTION_DEFAULTS

    def test_chorus_has_highest_reverb(self):
        """Chorus should have the highest default reverb (before bridge)."""
        chorus_reverb = _SECTION_DEFAULTS["chorus"]["reverb_mix"]
        intro_reverb = _SECTION_DEFAULTS["intro"]["reverb_mix"]
        verse_reverb = _SECTION_DEFAULTS["verse"]["reverb_mix"]
        assert chorus_reverb > intro_reverb
        assert chorus_reverb > verse_reverb

    def test_intro_has_lowest_compression(self):
        """Intro should have the lowest compression ratio."""
        intro_comp = _SECTION_DEFAULTS["intro"]["compression_ratio"]
        chorus_comp = _SECTION_DEFAULTS["chorus"]["compression_ratio"]
        assert intro_comp < chorus_comp

    def test_chorus_has_positive_gain(self):
        """Chorus should have +2dB gain."""
        assert _SECTION_DEFAULTS["chorus"]["gain_db"] == 2.0

    def test_outro_has_negative_gain(self):
        """Outro should have negative gain (fade out)."""
        assert _SECTION_DEFAULTS["outro"]["gain_db"] < 0


# ---------------------------------------------------------------------------
# Tests: Integration with ArrangementExtractor (round-trip)
# ---------------------------------------------------------------------------

class TestArrangementIntegration:
    """Integration tests with ArrangementExtractor from Phase 5."""

    def test_round_trip_with_extractor(self):
        """Sections from ArrangementExtractor should produce valid strategy."""
        import numpy as np

        sr, bpm = 44100, 120.0
        beat_samples = int(sr * 60.0 / bpm)

        def _sine(freq, beats, amp=1.0):
            t = np.arange(beats * beat_samples, dtype=np.float64) / sr
            return amp * np.sin(2.0 * np.pi * freq * t)

        stems = {
            "bass": np.concatenate([
                _sine(80, 4, 0.3), _sine(80, 8, 0.5),
                _sine(80, 8, 0.6), _sine(80, 4, 0.0), _sine(80, 8, 0.4),
            ]),
            "drums": np.concatenate([
                _sine(200, 4, 0.0), _sine(200, 8, 0.5),
                _sine(200, 8, 0.7), _sine(200, 4, 0.0), _sine(200, 8, 0.4),
            ]),
            "vocals": np.concatenate([
                _sine(440, 4, 0.0), _sine(440, 8, 0.0),
                _sine(440, 8, 0.8), _sine(440, 4, 0.3), _sine(440, 8, 0.0),
            ]),
        }

        from vcmix.separation.arrangement import ArrangementExtractor
        extractor = ArrangementExtractor()
        sections = extractor.extract(stems, sr, bpm)

        strategy = ArrangementStrategy.from_sections(sections)
        assert len(strategy.sections) > 0
        assert strategy.total_beats > 0

        # Should be able to query any beat
        for beat in range(0, strategy.total_beats, 4):
            params = strategy.get_params_at_beat(beat)
            assert isinstance(params, SectionMixParams)

    def test_yaml_export_round_trip(self):
        """Strategy -> YAML -> parse should preserve key parameters."""
        sections = _make_sections()
        strategy = ArrangementStrategy.from_sections(sections)
        yaml_str = strategy.to_yaml_overrides()
        parsed = yaml.safe_load(yaml_str)

        # Verify chorus params in YAML match strategy
        chorus_data = parsed["arrangement_strategy"]["section_2_chorus"]
        assert chorus_data["reverb_mix"] == pytest.approx(0.20, abs=0.01)
        assert chorus_data["compression_ratio"] == pytest.approx(3.0)
        assert chorus_data["gain_db"] == pytest.approx(2.0)
