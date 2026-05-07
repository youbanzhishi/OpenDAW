"""
vcmix.bpm — BPM detection and sync utilities.

This subpackage provides:
    - detector: BPM detection from audio via librosa
    - sync:     BPM note-value to millisecond conversion

Usage:
    from vcmix.bpm.detector import detect_bpm
    from vcmix.bpm.sync import note_to_ms, resolve_bpm_times

Dependencies: librosa (optional, for detection), numpy
"""

from vcmix.bpm.sync import note_to_ms, resolve_bpm_times

__all__ = ["note_to_ms", "resolve_bpm_times"]
