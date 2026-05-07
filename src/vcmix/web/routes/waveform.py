"""
waveform.py — Waveform & Spectrum API endpoints for VCMix (Phase 13).

Provides:
    GET /api/v1/waveform/{project_id}/{track} — Get track waveform peak data
    GET /api/v1/spectrum/{project_id}/{track}  — Get track FFT spectrum data
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from vcmix.web.project_manager import ProjectManager

router = APIRouter()

# ── Shared project manager ───────────────────────────────────────────────

_pm = ProjectManager()


# ── Models ───────────────────────────────────────────────────────────────

class WaveformResponse(BaseModel):
    """Response for waveform peak data."""
    peaks: list[float] = Field(default_factory=list, description="Downsampled peak amplitude array [0..1]")
    sample_count: int = Field(default=0, description="Total number of audio samples")
    sample_rate: int = Field(default=44100, description="Sample rate in Hz")
    duration_s: float = Field(default=0.0, description="Duration in seconds")
    channels: int = Field(default=1, description="Number of audio channels")


class SpectrumResponse(BaseModel):
    """Response for FFT spectrum data."""
    frequencies: list[float] = Field(default_factory=list, description="Frequency bin centers (Hz)")
    magnitudes: list[float] = Field(default_factory=list, description="Magnitude values")
    sample_rate: int = Field(default=44100, description="Sample rate in Hz")
    fft_size: int = Field(default=2048, description="FFT window size")
    rms_db: float = Field(default=-120.0, description="RMS level in dB")
    peak_db: float = Field(default=-120.0, description="Peak level in dB")
    lufs: float = Field(default=-120.0, description="LUFS approximation")


# ── Helpers ──────────────────────────────────────────────────────────────

def _generate_waveform_peaks(audio: np.ndarray, num_peaks: int = 2000) -> list[float]:
    """Downsample audio to a fixed number of peak values.

    Splits the audio into num_peaks bins and takes the max absolute value
    in each bin, normalized to [0, 1].

    Args:
        audio: Audio samples (1D float numpy array).
        num_peaks: Number of output peak values.

    Returns:
        List of normalized peak values.
    """
    if len(audio) == 0:
        return []

    # Mono downmix if stereo
    if audio.ndim == 2:
        audio = np.mean(audio, axis=0)

    # Take absolute values
    abs_audio = np.abs(audio.astype(np.float64))
    peak_val = np.max(abs_audio)
    if peak_val == 0:
        return [0.0] * min(num_peaks, len(abs_audio))

    # Downsample by binning
    total_samples = len(abs_audio)
    if total_samples <= num_peaks:
        return [float(v / peak_val) for v in abs_audio]

    bins = np.array_split(abs_audio, num_peaks)
    peaks = [float(np.max(bin) / peak_val) for bin in bins]
    return peaks


def _compute_fft_spectrum(audio: np.ndarray, sr: int = 44100, fft_size: int = 2048) -> dict[str, Any]:
    """Compute FFT magnitude spectrum from audio data.

    Args:
        audio: Audio samples (1D float numpy array).
        sr: Sample rate.
        fft_size: FFT window size.

    Returns:
        Dict with frequencies, magnitudes, rms_db, peak_db, lufs.
    """
    if len(audio) == 0:
        return {
            "frequencies": [],
            "magnitudes": [],
            "rms_db": -120.0,
            "peak_db": -120.0,
            "lufs": -120.0,
        }

    # Mono downmix
    if audio.ndim == 2:
        audio = np.mean(audio, axis=0)

    # Pad or truncate to fft_size
    if len(audio) < fft_size:
        audio = np.pad(audio, (0, fft_size - len(audio)))
    else:
        audio = audio[:fft_size]

    # Apply Hann window
    window = np.hanning(fft_size)
    windowed = audio * window

    # FFT
    spectrum = np.fft.rfft(windowed)
    magnitudes = np.abs(spectrum)

    # Frequency bins
    freqs = np.fft.rfftfreq(fft_size, d=1.0 / sr)

    # Compute levels
    rms = float(np.sqrt(np.mean(audio.astype(np.float64) ** 2)))
    peak = float(np.max(np.abs(audio.astype(np.float64))))
    rms_db = 20.0 * np.log10(rms) if rms > 0 else -120.0
    peak_db = 20.0 * np.log10(peak) if peak > 0 else -120.0

    # LUFS approximation (simplified K-weighting)
    lufs = rms_db - 0.691  # simplified offset

    return {
        "frequencies": freqs.tolist(),
        "magnitudes": magnitudes.tolist(),
        "rms_db": round(rms_db, 2),
        "peak_db": round(peak_db, 2),
        "lufs": round(lufs, 1),
    }


# ── Endpoints ────────────────────────────────────────────────────────────

@router.get("/waveform/{project_id}/{track}", response_model=WaveformResponse)
async def get_waveform(
    project_id: str,
    track: str,
    num_peaks: int = Query(default=2000, ge=100, le=10000, description="Number of output peaks"),
):
    """
    Get waveform peak data for a track.

    Reads the track's audio file, downsamples to a fixed number of peaks,
    and returns the normalized peak array suitable for Canvas rendering.
    """
    filepath = _pm.get_filepath(project_id)
    if filepath is None:
        raise HTTPException(status_code=404, detail=f"Project not found: {project_id}")

    # Parse project to find the track
    import yaml
    try:
        content = filepath.read_text(encoding="utf-8")
        config = yaml.safe_load(content)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read project: {e}")

    tracks = config.get("tracks", [])
    track_config = None
    for t in tracks:
        if t.get("name") == track:
            track_config = t
            break

    if track_config is None:
        raise HTTPException(status_code=404, detail=f"Track '{track}' not found in project")

    # Read audio file
    track_file = track_config.get("file", "")
    audio_path = filepath.parent / track_file

    if not audio_path.exists():
        # Return synthetic waveform based on track config
        duration = track_config.get("duration", 10)
        sr = config.get("sample_rate", 44100)
        num_samples = int(duration * sr)
        t = np.linspace(0, duration, num_samples)
        # Generate a simple sine-based waveform for visualization
        audio = np.sin(2 * np.pi * 440 * t) * 0.5 * np.exp(-t / duration)
        peaks = _generate_waveform_peaks(audio, num_peaks)
        return WaveformResponse(
            peaks=peaks,
            sample_count=num_samples,
            sample_rate=sr,
            duration_s=duration,
            channels=1,
        )

    try:
        from vcmix.audio.io import read_audio
        audio, file_sr = read_audio(audio_path)
        sr = file_sr or config.get("sample_rate", 44100)
        num_samples = audio.shape[-1] if audio.ndim > 0 else len(audio)
        duration = num_samples / sr
        channels = audio.shape[0] if audio.ndim == 2 else 1

        peaks = _generate_waveform_peaks(audio, num_peaks)
        return WaveformResponse(
            peaks=peaks,
            sample_count=num_samples,
            sample_rate=sr,
            duration_s=round(duration, 3),
            channels=channels,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read audio: {e}")


@router.get("/spectrum/{project_id}/{track}", response_model=SpectrumResponse)
async def get_spectrum(
    project_id: str,
    track: str,
    fft_size: int = Query(default=2048, ge=256, le=16384, description="FFT window size"),
):
    """
    Get FFT spectrum data for a track.

    Computes the magnitude spectrum of the track's audio data
    using FFT with a Hann window. Returns frequency bins and
    magnitude values suitable for spectrum visualization.
    """
    filepath = _pm.get_filepath(project_id)
    if filepath is None:
        raise HTTPException(status_code=404, detail=f"Project not found: {project_id}")

    import yaml
    try:
        content = filepath.read_text(encoding="utf-8")
        config = yaml.safe_load(content)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read project: {e}")

    tracks = config.get("tracks", [])
    track_config = None
    for t in tracks:
        if t.get("name") == track:
            track_config = t
            break

    if track_config is None:
        raise HTTPException(status_code=404, detail=f"Track '{track}' not found in project")

    track_file = track_config.get("file", "")
    audio_path = filepath.parent / track_file

    if not audio_path.exists():
        # Generate synthetic spectrum
        sr = config.get("sample_rate", 44100)
        t = np.linspace(0, 2.0, int(2.0 * sr))
        audio = np.sin(2 * np.pi * 440 * t) * 0.5 * np.exp(-t)
        result = _compute_fft_spectrum(audio, sr, fft_size)
        return SpectrumResponse(
            frequencies=result["frequencies"],
            magnitudes=result["magnitudes"],
            sample_rate=sr,
            fft_size=fft_size,
            rms_db=result["rms_db"],
            peak_db=result["peak_db"],
            lufs=result["lufs"],
        )

    try:
        from vcmix.audio.io import read_audio
        audio, file_sr = read_audio(audio_path)
        sr = file_sr or config.get("sample_rate", 44100)
        result = _compute_fft_spectrum(audio, sr, fft_size)
        return SpectrumResponse(
            frequencies=result["frequencies"],
            magnitudes=result["magnitudes"],
            sample_rate=sr,
            fft_size=fft_size,
            rms_db=result["rms_db"],
            peak_db=result["peak_db"],
            lufs=result["lufs"],
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to analyze audio: {e}")
