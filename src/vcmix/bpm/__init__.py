"""
vcmix.bpm — BPM detection and synchronization utilities.

This subpackage provides:
    - detector: Tempo/BPM detection from audio signals
    - sync: BPM sync calculations (time-stretch ratio, beat alignment)

Usage:
    from vcmix.bpm import detect_bpm, calc_stretch_ratio

Dependencies: numpy, librosa (optional for beat tracking)
"""

from vcmix.bpm.detector import detect_bpm
from vcmix.bpm.sync import calc_stretch_ratio, calc_beat_grid

__all__ = ["detect_bpm", "calc_stretch_ratio", "calc_beat_grid"]
