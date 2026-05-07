"""
detector.py — BPM detection from audio for VCMix.

Uses librosa.beat.beat_track to estimate tempo from audio.
Includes slow-song correction:
    - librosa sometimes reports half-tempo for fast songs
    - if detected BPM < 80, double it
    - if detected BPM > 160, halve it
    - This keeps BPM in the standard 80-160 range

Usage:
    from vcmix.bpm.detector import detect_bpm
    bpm = detect_bpm("vocal.wav")
    bpm = detect_bpm(audio_array, sr=44100)

Dependencies: librosa>=0.10.0, numpy
"""

from __future__ import annotations

from pathlib import Path
from typing import Union

import numpy as np


def detect_bpm(
    source: Union[str, Path, np.ndarray],
    sr: int = 44100,
) -> float:
    """
    Detect BPM from an audio file or array.

    Args:
        source: Path to audio file, or numpy audio array.
        sr: Sample rate (used when source is a numpy array).

    Returns:
        Detected BPM as float, normalized to 80-160 range.

    Raises:
        ImportError: If librosa is not installed.
        FileNotFoundError: If audio file path doesn't exist.
    """
    try:
        import librosa
    except ImportError:
        raise ImportError(
            "librosa is required for BPM detection. "
            "Install with: pip install librosa"
        )

    # Load audio
    if isinstance(source, (str, Path)):
        source = Path(source)
        if not source.exists():
            raise FileNotFoundError(f"Audio file not found: {source}")
        y, _ = librosa.load(str(source), sr=sr)
    else:
        y = source.astype(np.float32)
        if y.ndim == 2:
            y = y[0] if y.shape[0] < y.shape[1] else y[:, 0]

    # Ensure mono
    if y.ndim > 1:
        y = y[0]

    # Detect tempo
    tempo, _ = librosa.beat.beat_track(y=y, sr=sr)
    # Handle librosa returning ndarray (newer versions)
    if isinstance(tempo, np.ndarray):
        bpm = float(tempo.flat[0])
    else:
        bpm = float(tempo)

    # Normalize: slow songs get doubled, fast songs get halved
    if bpm < 80:
        bpm *= 2.0
    elif bpm > 160:
        bpm /= 2.0

    return round(bpm, 1)
