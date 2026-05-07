"""
test_bpm.py — Tests for vcmix.bpm module.

Tests BPM detection and sync calculations:
    - calc_stretch_ratio: Correct ratio for known BPM pairs
    - calc_beat_grid: Grid positions match expected sample offsets
    - quantize_to_grid: Nearest beat snapping works
    - detect_bpm: Returns a value within valid range

Usage:
    pytest tests/test_bpm.py -v

Dependencies: pytest, numpy
"""

from __future__ import annotations

import numpy as np
import pytest

from vcmix.bpm.sync import calc_stretch_ratio, calc_beat_grid, quantize_to_grid
from vcmix.bpm.detector import detect_bpm


class TestCalcStretchRatio:
    """Tests for calc_stretch_ratio()."""

    def test_same_bpm(self) -> None:
        """Same BPM should return ratio 1.0."""
        assert calc_stretch_ratio(120, 120) == 1.0

    def test_double_bpm(self) -> None:
        """Half the target BPM should return ratio 0.5."""
        assert calc_stretch_ratio(60, 120) == 0.5

    def test_half_bpm(self) -> None:
        """Double the target BPM should return ratio 2.0."""
        assert calc_stretch_ratio(120, 60) == 2.0

    def test_zero_bpm_raises(self) -> None:
        """Zero BPM should raise ValueError."""
        with pytest.raises(ValueError):
            calc_stretch_ratio(0, 120)


class TestCalcBeatGrid:
    """Tests for calc_beat_grid()."""

    def test_grid_spacing(self) -> None:
        """Beat grid spacing should match samples_per_beat."""
        bpm = 120
        sr = 44100
        grid = calc_beat_grid(bpm, sample_rate=sr, duration_sec=10.0)
        samples_per_beat = int(sr * 60.0 / bpm)
        # Check consecutive differences
        diffs = np.diff(grid)
        assert all(d == samples_per_beat for d in diffs)

    def test_grid_starts_at_zero(self) -> None:
        """First beat should be at sample 0."""
        grid = calc_beat_grid(120, sample_rate=44100, duration_sec=10.0)
        assert grid[0] == 0


class TestQuantizeToGrid:
    """Tests for quantize_to_grid()."""

    def test_exact_on_beat(self) -> None:
        """Position exactly on a beat should not move."""
        grid = calc_beat_grid(120, sample_rate=44100, duration_sec=10.0)
        result = quantize_to_grid(int(grid[5]), grid)
        assert result == grid[5]

    def test_near_beat_snaps(self) -> None:
        """Position near a beat should snap to it."""
        grid = calc_beat_grid(120, sample_rate=44100, duration_sec=10.0)
        offset = int(grid[5]) + 10  # 10 samples off
        result = quantize_to_grid(offset, grid)
        assert result == grid[5]


class TestDetectBPM:
    """Tests for detect_bpm()."""

    def test_returns_float_in_range(self) -> None:
        """BPM detection should return a value in the valid range."""
        # Generate a simple click track at 120 BPM
        sr = 44100
        duration = 10.0
        audio = np.zeros(int(sr * duration), dtype=np.float32)
        beat_interval = int(sr * 60.0 / 120)
        for i in range(0, len(audio), beat_interval):
            audio[i] = 1.0
        bpm = detect_bpm(audio, sample_rate=sr)
        assert 60 <= bpm <= 200
