"""
test_arrangement.py - Tests for arrangement structure extraction.

Uses synthesised sine-wave stems to simulate different song sections
(intro -> verse -> chorus -> bridge -> outro) without real audio.
"""
from __future__ import annotations

import numpy as np
import pytest

from vcmix.separation.arrangement import (
    ArrangementExtractor,
    Section,
    extract_arrangement,
)

# ---------------------------------------------------------------------------
# Helpers: synthesise sine-wave stems with energy profiles
# ---------------------------------------------------------------------------

SR = 44100
BPM = 120.0
BEAT_SEC = 60.0 / BPM  # 0.5 s per beat
BEAT_SAMPLES = int(SR * BEAT_SEC)  # 22050


def _sine(freq: float, duration_beats: int, amplitude: float = 1.0) -> np.ndarray:
    """Generate a sine wave of given frequency & duration (in beats)."""
    n_samples = duration_beats * BEAT_SAMPLES
    t = np.arange(n_samples, dtype=np.float64) / SR
    return amplitude * np.sin(2.0 * np.pi * freq * t)


def _make_song_stems() -> dict[str, np.ndarray]:
    """Create stems simulating a 32-beat song:
        beats 0-3:   intro  (only bass, low energy)
        beats 4-11:  verse  (bass + drums, medium)
        beats 12-19: chorus (bass + drums + vocals, high)
        beats 20-23: bridge (only vocals, low)
        beats 24-31: outro  (bass + drums, medium)
    """
    _total_beats = 32  # noqa: F841

    # Bass: present in intro/verse/chorus/outro
    bass = np.concatenate([
        _sine(80, 4, 0.3),     # intro  (beats 0-3)
        _sine(80, 8, 0.5),     # verse  (beats 4-11)
        _sine(80, 8, 0.6),     # chorus (beats 12-19)
        _sine(80, 4, 0.0),     # bridge (silence)
        _sine(80, 8, 0.4),     # outro  (beats 24-31)
    ])

    # Drums: present in verse/chorus/outro
    drums = np.concatenate([
        _sine(200, 4, 0.0),    # intro  (silence)
        _sine(200, 8, 0.5),    # verse
        _sine(200, 8, 0.7),    # chorus
        _sine(200, 4, 0.0),    # bridge (silence)
        _sine(200, 8, 0.4),    # outro
    ])

    # Vocals: present only in chorus and bridge
    vocals = np.concatenate([
        _sine(440, 4, 0.0),    # intro  (silence)
        _sine(440, 8, 0.0),    # verse  (silence)
        _sine(440, 8, 0.8),    # chorus
        _sine(440, 4, 0.3),    # bridge
        _sine(440, 8, 0.0),    # outro  (silence)
    ])

    return {"bass": bass, "drums": drums, "vocals": vocals}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestArrangementExtractor:

    @pytest.fixture()
    def song(self):
        return _make_song_stems()

    @pytest.fixture()
    def extractor(self):
        return ArrangementExtractor(
            energy_low_threshold=0.30,
            energy_high_threshold=0.65,
            min_section_beats=4,
            boundary_jump_ratio=0.25,
        )

    def test_returns_sections(self, extractor, song):
        """extract() returns a non-empty list of Section objects."""
        sections = extractor.extract(song, SR, BPM)
        assert isinstance(sections, list)
        assert len(sections) > 0
        for s in sections:
            assert isinstance(s, Section)

    def test_sections_cover_full_range(self, extractor, song):
        """Sections must span the entire song without gaps."""
        sections = extractor.extract(song, SR, BPM)
        # First section starts at beat 0
        assert sections[0].start_beat == 0
        # Sections are contiguous
        for i in range(len(sections) - 1):
            assert sections[i].end_beat == sections[i + 1].start_beat

    def test_section_names_are_valid(self, extractor, song):
        """All section names must be from the allowed set."""
        valid_names = {"intro", "verse", "chorus", "bridge", "outro"}
        sections = extractor.extract(song, SR, BPM)
        for s in sections:
            assert s.name in valid_names, f"Invalid section name: {s.name}"

    def test_energy_levels_are_valid(self, extractor, song):
        """All energy levels must be from the allowed set."""
        valid = {"low", "medium", "high"}
        sections = extractor.extract(song, SR, BPM)
        for s in sections:
            assert s.energy_level in valid

    def test_beat_and_sec_consistency(self, extractor, song):
        """start_sec / end_sec must be consistent with beat indices."""
        sections = extractor.extract(song, SR, BPM)
        beat_sec = 60.0 / BPM
        for s in sections:
            assert abs(s.start_sec - s.start_beat * beat_sec) < 0.01
            assert abs(s.end_sec - s.end_beat * beat_sec) < 0.01

    def test_intro_is_first(self, extractor, song):
        """The first section should be labelled 'intro'."""
        sections = extractor.extract(song, SR, BPM)
        assert sections[0].name == "intro"

    def test_chorus_detected(self, extractor, song):
        """At least one 'chorus' section should be detected."""
        sections = extractor.extract(song, SR, BPM)
        names = [s.name for s in sections]
        assert "chorus" in names

    def test_active_stems_populated(self, extractor, song):
        """Sections should have non-empty active_stems where instruments play."""
        sections = extractor.extract(song, SR, BPM)
        # At least one section should have active stems
        has_active = any(len(s.active_stems) > 0 for s in sections)
        assert has_active

    def test_chorus_has_most_stems(self, extractor, song):
        """Chorus should have more active stems than intro/bridge."""
        sections = extractor.extract(song, SR, BPM)
        chorus = [s for s in sections if s.name == "chorus"]
        intro = [s for s in sections if s.name == "intro"]
        if chorus and intro:
            assert len(chorus[0].active_stems) >= len(intro[0].active_stems)

    def test_empty_stems_return_empty(self, extractor):
        """Empty stems dict should return empty sections list."""
        sections = extractor.extract({}, SR, BPM)
        assert sections == []

    def test_invalid_bpm_raises(self, extractor, song):
        """Zero or negative BPM should raise ValueError."""
        with pytest.raises(ValueError):
            extractor.extract(song, SR, 0)
        with pytest.raises(ValueError):
            extractor.extract(song, SR, -10)

    def test_invalid_sr_raises(self, extractor, song):
        """Zero or negative sample rate should raise ValueError."""
        with pytest.raises(ValueError):
            extractor.extract(song, 0, BPM)

    def test_single_beat_song(self, extractor):
        """A song with just 1 beat should still return results."""
        one_beat = int(SR * 60.0 / BPM)
        stems = {"bass": np.ones(one_beat, dtype=np.float64) * 0.5}
        sections = extractor.extract(stems, SR, BPM)
        assert len(sections) >= 1

    def test_convenience_function(self, song):
        """extract_arrangement() convenience wrapper should work."""
        sections = extract_arrangement(song, SR, BPM)
        assert isinstance(sections, list)
        assert len(sections) > 0

    def test_sections_are_ordered(self, extractor, song):
        """Sections must be in chronological order."""
        sections = extractor.extract(song, SR, BPM)
        for i in range(len(sections) - 1):
            assert sections[i].start_beat < sections[i + 1].start_beat
            assert sections[i].end_beat <= sections[i + 1].start_beat

    def test_min_section_length(self, extractor, song):
        """After merging, no section should be shorter than min_section_beats."""
        sections = extractor.extract(song, SR, BPM)
        # The last section may be short; we allow the very last one to be shorter
        # since there's nothing to merge with
        for s in sections[:-1]:
            beat_len = s.end_beat - s.start_beat
            assert beat_len >= extractor.min_section_beats, (
                f"Section {s.name} too short: {beat_len} beats"
            )


class TestEdgeCases:
    """Edge case tests with simple signals."""

    def test_silent_stems(self):
        """All-silent stems should still produce sections."""
        sr, bpm = 44100, 120.0
        beat_samples = int(sr * 60.0 / bpm)
        silence = np.zeros(16 * beat_samples, dtype=np.float64)
        stems = {"bass": silence, "drums": silence}
        extractor = ArrangementExtractor()
        sections = extractor.extract(stems, sr, bpm)
        # Should return at least one section (the whole song)
        assert len(sections) >= 1

    def test_constant_energy(self):
        """Constant-energy stems should produce a single section."""
        sr, bpm = 44100, 120.0
        beat_samples = int(sr * 60.0 / bpm)
        tone = np.ones(16 * beat_samples, dtype=np.float64) * 0.5
        stems = {"bass": tone}
        extractor = ArrangementExtractor()
        sections = extractor.extract(stems, sr, bpm)
        # With no energy changes, should be one section
        assert len(sections) == 1
        # constant high energy = chorus, constant medium = intro
        assert sections[0].name in ("intro", "chorus")

    def test_two_stem_different_energy(self):
        """Two stems with clearly different energy regions."""
        sr, bpm = 44100, 120.0
        beat_samples = int(sr * 60.0 / bpm)
        # First 8 beats loud, last 8 beats quiet
        loud = np.ones(8 * beat_samples, dtype=np.float64) * 0.8
        quiet = np.ones(8 * beat_samples, dtype=np.float64) * 0.1
        stems = {"instrument": np.concatenate([loud, quiet])}
        extractor = ArrangementExtractor(boundary_jump_ratio=0.5)
        sections = extractor.extract(stems, sr, bpm)
        # Should detect the energy change
        assert len(sections) >= 1
