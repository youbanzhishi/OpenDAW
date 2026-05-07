"""
detector.py — Tempo/BPM detection from audio signals.

Provides BPM detection using onset-based analysis:
    - detect_bpm(): Estimate BPM from an audio buffer
    - Uses librosa's beat tracker when available
    - Falls back to a simple onset autocorrelation method

Usage:
    from vcmix.bpm.detector import detect_bpm
    bpm = detect_bpm(audio, sample_rate=44100)

Dependencies: numpy, librosa (optional, recommended)
"""

from __future__ import annotations

import numpy as np


def detect_bpm(audio: np.ndarray, sample_rate: int = 44100,
               min_bpm: float = 60.0, max_bpm: float = 200.0) -> float:
    """
    Detect the tempo (BPM) of an audio signal.

    Tries librosa's beat tracker first; falls back to a simple
    onset autocorrelation method if librosa is unavailable.

    Args:
        audio: Mono audio buffer (1D numpy array).
        sample_rate: Sample rate in Hz.
        min_bpm: Minimum BPM to consider.
        max_bpm: Maximum BPM to consider.

    Returns:
        Detected BPM as float.
    """
    try:
        return _detect_with_librosa(audio, sample_rate, min_bpm, max_bpm)
    except ImportError:
        return _detect_autocorr(audio, sample_rate, min_bpm, max_bpm)


def _detect_with_librosa(audio: np.ndarray, sample_rate: int,
                          min_bpm: float, max_bpm: float) -> float:
    """Detect BPM using librosa's beat tracker."""
    import librosa

    tempo, _ = librosa.beat.beat_track(
        y=audio.astype(np.float32),
        sr=sample_rate,
        bpm=min_bpm,
    )
    # librosa may return array or scalar depending on version
    bpm = float(tempo) if np.ndim(tempo) == 0 else float(tempo[0])
    return max(min_bpm, min(bpm, max_bpm))


def _detect_autocorr(audio: np.ndarray, sample_rate: int,
                      min_bpm: float, max_bpm: float) -> float:
    """
    Simple BPM detection via onset strength autocorrelation.

    This is a fallback method — less accurate than librosa
    but requires no external dependencies beyond numpy.
    """
    # Compute onset strength envelope
    frame_size = 1024
    hop_size = 512
    n_frames = (len(audio) - frame_size) // hop_size

    if n_frames < 10:
        return 120.0  # Not enough audio, return default

    onset_env = np.zeros(n_frames)
    for i in range(n_frames):
        frame = audio[i * hop_size : i * hop_size + frame_size]
        onset_env[i] = np.sum(frame.astype(np.float64) ** 2)

    # Onset diff (half-wave rectified)
    onset_diff = np.diff(onset_env)
    onset_diff = np.maximum(onset_diff, 0)

    # Autocorrelation
    corr = np.correlate(onset_diff, onset_diff, mode="full")
    corr = corr[len(corr) // 2 :]

    # Convert BPM range to lag range
    frame_rate = sample_rate / hop_size
    min_lag = int(frame_rate * 60.0 / max_bpm)
    max_lag = int(frame_rate * 60.0 / min_bpm)

    if max_lag >= len(corr) or min_lag >= max_lag:
        return 120.0

    # Find peak in autocorrelation within BPM range
    search_region = corr[min_lag:max_lag]
    if len(search_region) == 0:
        return 120.0

    peak_lag = np.argmax(search_region) + min_lag
    bpm = frame_rate * 60.0 / peak_lag
    return float(bpm)
