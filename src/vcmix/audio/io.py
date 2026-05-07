"""
io.py — Cross-platform audio file I/O for VCMix.

Provides unified read/write for:
    - WAV  (via soundfile, native support)
    - FLAC (via soundfile, native support)
    - MP3  (via ffmpeg subprocess, cross-platform)

All paths use pathlib.Path. All text encoding is UTF-8.

Audio format conventions:
    - Internal representation: numpy float32 array
    - Mono: 1D array (samples,)
    - Stereo/Multi-channel: 2D array (channels, samples)
    - Sample values: -1.0 to 1.0 (float32)

Usage:
    from vcmix.audio.io import read_audio, write_audio
    audio, sr = read_audio("vocal.wav")
    write_audio(audio, "output.wav", sr, format="WAV")

Dependencies: numpy, soundfile, subprocess (ffmpeg for MP3)
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Tuple

import numpy as np
import soundfile as sf


def read_audio(
    path: Path | str,
    dtype: str = "float32",
) -> Tuple[np.ndarray, int]:
    """
    Read an audio file into a numpy array.

    For WAV/FLAC: uses soundfile directly.
    For MP3: converts to temp WAV via ffmpeg, then reads with soundfile.

    Args:
        path: Path to audio file (WAV, FLAC, or MP3).
        dtype: Numpy dtype for output (default float32).

    Returns:
        Tuple of (audio_array, sample_rate).
        - Mono: shape (samples,)
        - Stereo: shape (channels, samples)

    Raises:
        FileNotFoundError: If file doesn't exist.
        RuntimeError: If ffmpeg conversion fails for MP3.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Audio file not found: {path}")

    suffix = path.suffix.lower()

    if suffix in (".mp3", ".m4a", ".aac", ".ogg"):
        return _read_via_ffmpeg(path, dtype)
    else:
        # WAV, FLAC — soundfile native
        data, sr = sf.read(str(path), dtype=dtype, always_2d=False)

        # Normalize shape: soundfile returns (samples, channels)
        # We want (channels, samples) for multi-channel, (samples,) for mono
        if data.ndim == 2:
            data = data.T  # (channels, samples)

        return data, sr


def _read_via_ffmpeg(path: Path, dtype: str = "float32") -> Tuple[np.ndarray, int]:
    """
    Read audio via ffmpeg conversion to temp WAV.

    Args:
        path: Source audio file path.
        dtype: Target numpy dtype.

    Returns:
        Tuple of (audio_array, sample_rate).
    """
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise RuntimeError(
            "ffmpeg not found. Install ffmpeg for MP3/M4A support. "
            "On Ubuntu: apt install ffmpeg. On macOS: brew install ffmpeg."
        )

    with tempfile.TemporaryDirectory(prefix="vcmix_io_") as tmpdir:
        tmp_wav = Path(tmpdir) / "temp.wav"
        cmd = [
            ffmpeg, "-y", "-i", str(path),
            "-acodec", "pcm_f32le",
            "-ar", "44100",
            str(tmp_wav),
        ]
        result = subprocess.run(
            cmd, capture_output=True, text=True, encoding="utf-8"
        )
        if result.returncode != 0:
            raise RuntimeError(f"ffmpeg conversion failed: {result.stderr[:500]}")

        data, sr = sf.read(str(tmp_wav), dtype=dtype, always_2d=False)
        if data.ndim == 2:
            data = data.T
        return data, sr


def write_audio(
    audio: np.ndarray,
    path: Path | str,
    sample_rate: int,
    format: str = "WAV",
    subtype: str = "FLOAT",
) -> Path:
    """
    Write a numpy array to an audio file.

    For WAV/FLAC: uses soundfile directly.
    For MP3: writes temp WAV then converts via ffmpeg.

    Args:
        audio: Audio array. Mono: (samples,), Stereo: (channels, samples).
        path: Output file path.
        sample_rate: Sample rate in Hz.
        format: Soundfile format string (default "WAV").
        subtype: Soundfile subtype (default "FLOAT" for 32-bit float WAV).

    Returns:
        Path to the written file.

    Raises:
        RuntimeError: If write fails or ffmpeg conversion fails.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    # Normalize to (samples, channels) for soundfile
    if audio.ndim == 1:
        data = audio
    else:
        data = audio.T  # (channels, samples) -> (samples, channels)

    suffix = path.suffix.lower()

    if suffix in (".mp3", ".m4a", ".aac", ".ogg"):
        return _write_via_ffmpeg(data, path, sample_rate)
    else:
        sf.write(str(path), data, sample_rate, format=format, subtype=subtype)
        return path


def _write_via_ffmpeg(data: np.ndarray, path: Path, sample_rate: int) -> Path:
    """
    Write audio via temp WAV -> ffmpeg conversion.

    Args:
        data: Audio in (samples, channels) format.
        path: Target output path (determines format).
        sample_rate: Sample rate.

    Returns:
        Path to the output file.
    """
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise RuntimeError("ffmpeg not found. Install ffmpeg for MP3 support.")

    with tempfile.TemporaryDirectory(prefix="vcmix_io_") as tmpdir:
        tmp_wav = Path(tmpdir) / "temp.wav"
        sf.write(str(tmp_wav), data, sample_rate, format="WAV", subtype="FLOAT")

        cmd = [ffmpeg, "-y", "-i", str(tmp_wav), str(path)]
        result = subprocess.run(
            cmd, capture_output=True, text=True, encoding="utf-8"
        )
        if result.returncode != 0:
            raise RuntimeError(f"ffmpeg encoding failed: {result.stderr[:500]}")

    return path
