"""
io.py — Audio file reading and writing for VCMix.

Wraps soundfile for cross-platform audio I/O:
    - read_audio(): Read any soundfile-supported format to numpy array
    - write_audio(): Write numpy array to WAV/FLAC/OGG

Always returns float32 numpy arrays with sample rate.
Supports mono and multi-channel files.

Usage:
    from vcmix.audio.io import read_audio, write_audio
    audio, sr = read_audio("vocal.wav")
    write_audio(audio, "output.wav", sr)

Dependencies: numpy, soundfile>=0.12.0
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import soundfile as sf


def read_audio(path: str | Path) -> tuple[np.ndarray, int]:
    """
    Read an audio file into a numpy float32 array.

    Args:
        path: Path to audio file (WAV, FLAC, OGG, etc.).

    Returns:
        Tuple of (audio_array, sample_rate).
        audio_array shape: (samples,) for mono, (samples, channels) for multi-channel.

    Raises:
        FileNotFoundError: If the file does not exist.
    """
    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(f"Audio file not found: {file_path}")

    audio, sample_rate = sf.read(str(file_path), dtype="float32")
    return audio, sample_rate


def write_audio(audio: np.ndarray, path: str | Path, sample_rate: int,
                subtype: str = "FLOAT") -> None:
    """
    Write a numpy array to an audio file.

    Args:
        audio: Audio buffer (float32 numpy array).
        path: Output file path. Format inferred from extension.
        sample_rate: Sample rate in Hz.
        subtype: Soundfile subtype (default FLOAT for 32-bit WAV).

    Raises:
        ValueError: If audio is empty or path has unsupported extension.
    """
    file_path = Path(path)
    file_path.parent.mkdir(parents=True, exist_ok=True)

    if audio.size == 0:
        raise ValueError("Cannot write empty audio buffer")

    sf.write(str(file_path), audio, sample_rate, subtype=subtype)
