"""
sync.py — BPM synchronization and beat grid calculations for VCMix.

Provides utilities for aligning audio clips to a project BPM:
    - calc_stretch_ratio(): Time-stretch ratio between source and target BPM
    - calc_beat_grid(): Sample positions of beats at a given BPM
    - quantize_to_grid(): Snap events to nearest beat grid position

Usage:
    from vcmix.bpm.sync import calc_stretch_ratio, calc_beat_grid
    ratio = calc_stretch_ratio(source_bpm=128, target_bpm=120)
    grid = calc_beat_grid(bpm=120, sample_rate=44100, duration_sec=180)

Dependencies: numpy
"""

from __future__ import annotations

import numpy as np


def calc_stretch_ratio(source_bpm: float, target_bpm: float) -> float:
    """
    Calculate time-stretch ratio to convert from source to target BPM.

    Args:
        source_bpm: Original BPM of the audio.
        target_bpm: Desired target BPM.

    Returns:
        Stretch ratio (1.0 = no change, >1.0 = slow down, <1.0 = speed up).
    """
    if source_bpm <= 0 or target_bpm <= 0:
        raise ValueError("BPM values must be positive")
    return source_bpm / target_bpm


def calc_beat_grid(bpm: float, sample_rate: int = 44100,
                   duration_sec: float = 180.0,
                   time_signature: str = "4/4") -> np.ndarray:
    """
    Calculate sample positions of beats for a given BPM.

    Args:
        bpm: Beats per minute.
        sample_rate: Sample rate in Hz.
        duration_sec: Duration of the project in seconds.
        time_signature: Time signature string (e.g., "4/4").

    Returns:
        Array of sample positions where beats occur.
    """
    if bpm <= 0:
        raise ValueError("BPM must be positive")

    samples_per_beat = int(sample_rate * 60.0 / bpm)
    total_samples = int(duration_sec * sample_rate)
    n_beats = total_samples // samples_per_beat

    return np.arange(n_beats) * samples_per_beat


def quantize_to_grid(position_samples: int, beat_grid: np.ndarray) -> int:
    """
    Snap a sample position to the nearest beat grid position.

    Args:
        position_samples: Sample position to quantize.
        beat_grid: Array of beat grid positions.

    Returns:
        Nearest beat grid position as integer sample offset.
    """
    if len(beat_grid) == 0:
        return position_samples

    idx = np.argmin(np.abs(beat_grid - position_samples))
    return int(beat_grid[idx])
