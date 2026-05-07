"""
test_bpm.py — Tests for vcmix.bpm module.

Tests BPM note-value conversion and BPM detection:
    - note_to_ms: Musical note values → milliseconds
    - resolve_bpm_times: Batch resolve note values in param dicts
    - detect_bpm: BPM detection from audio

Usage:
    pytest tests/test_bpm.py -v

Dependencies: pytest, numpy
"""

from __future__ import annotations

import numpy as np
import pytest

from vcmix.bpm.sync import note_to_ms, resolve_bpm_times


class TestNoteToMs:
    """Tests for note_to_ms()."""

    def test_quarter_note_120(self) -> None:
        assert note_to_ms(120, "1/4") == 500.0

    def test_eighth_note_120(self) -> None:
        assert note_to_ms(120, "1/8") == 250.0

    def test_dotted_eighth_120(self) -> None:
        assert note_to_ms(120, "1/8d") == 375.0

    def test_triplet_eighth_120(self) -> None:
        assert abs(note_to_ms(120, "1/8t") - 166.7) < 0.1

    def test_bpm62_dotted_eighth(self) -> None:
        """九万字 @BPM62: 1/8d ≈ 725.8ms (key test case)."""
        assert abs(note_to_ms(62, "1/8d") - 725.8) < 0.2

    def test_whole_note(self) -> None:
        assert note_to_ms(120, "1/1") == 2000.0

    def test_sixteenth_note(self) -> None:
        assert note_to_ms(120, "1/16") == 125.0

    def test_plain_number_passthrough(self) -> None:
        assert note_to_ms(120, 250) == 250.0

    def test_string_number_passthrough(self) -> None:
        assert note_to_ms(120, "250") == 250.0

    def test_invalid_note_value_raises(self) -> None:
        with pytest.raises(ValueError):
            note_to_ms(120, "invalid")


class TestResolveBpmTimes:
    """Tests for resolve_bpm_times()."""

    def test_resolves_time_note_value(self) -> None:
        result = resolve_bpm_times({"time": "1/8d", "feedback": 12}, bpm=120)
        assert result["time"] == 375.0
        assert result["feedback"] == 12

    def test_resolves_predelay(self) -> None:
        result = resolve_bpm_times({"predelay": "1/4", "mix": 50}, bpm=120)
        assert result["predelay"] == 500.0
        assert result["mix"] == 50

    def test_leaves_numbers_unchanged(self) -> None:
        result = resolve_bpm_times({"time": 181, "feedback": 12}, bpm=62)
        assert result["time"] == 181
        assert result["feedback"] == 12

    def test_bpm62_jiuwanzi_delay(self) -> None:
        """九万字 delay params: time=1/8d → 725.8ms @BPM62."""
        result = resolve_bpm_times(
            {"time": "1/8d", "feedback": 12, "mix": 5}, bpm=62
        )
        assert abs(result["time"] - 725.8) < 0.2


class TestDetectBPM:
    """Tests for detect_bpm()."""

    def test_returns_float_in_range(self) -> None:
        from vcmix.bpm.detector import detect_bpm
        sr = 44100
        duration = 10.0
        audio = np.zeros(int(sr * duration), dtype=np.float32)
        beat_interval = int(sr * 60.0 / 120)
        for i in range(0, len(audio), beat_interval):
            audio[i] = 1.0
        bpm = detect_bpm(audio, sr=sr)
        assert 60 <= bpm <= 200
