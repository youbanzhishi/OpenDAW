"""
sibilance.py — Sibilance detection for VCMix.

Detects excessive sibilance in audio (especially vocals):
    - 6-8kHz energy ratio (sibilance frequency range)
    - Sibilance index (0-1 normalized)
    - Peak sibilance frequency

Sibilance index interpretation:
    - < 0.10: Low sibilance, no treatment needed
    - 0.10-0.20: Moderate sibilance, consider light de-essing
    - > 0.20: High sibilance, de-essing recommended

Usage:
    from vcmix.analysis.sibilance import SibilanceDetector
    detector = SibilanceDetector(sample_rate=44100)
    result = detector.analyze(audio)

Dependencies: numpy
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np


@dataclass
class SibilanceResult:
    """Sibilance detection result."""
    index: float          # Sibilance index (0-1)
    peak_freq: int        # Peak sibilance frequency in Hz
    energy_ratio: float   # 6-8kHz / total energy ratio


class SibilanceDetector:
    """
    Sibilance detector based on high-frequency energy analysis.

    Args:
        sample_rate: Audio sample rate in Hz.
        sibilance_low: Lower bound of sibilance frequency range (Hz).
        sibilance_high: Upper bound of sibilance frequency range (Hz).
    """

    def __init__(
        self,
        sample_rate: int = 44100,
        sibilance_low: float = 6000.0,
        sibilance_high: float = 8000.0,
    ) -> None:
        self.sample_rate = sample_rate
        self.sibilance_low = sibilance_low
        self.sibilance_high = sibilance_high

    def analyze(self, audio: np.ndarray) -> SibilanceResult:
        """
        Detect sibilance in audio.

        Args:
            audio: Audio array (1D mono or 2D multi-channel, float).

        Returns:
            SibilanceResult with sibilance index, peak frequency, and energy ratio.
        """
        # Convert to mono
        if audio.ndim == 2:
            mono = np.mean(audio.astype(np.float64), axis=0)
        else:
            mono = audio.astype(np.float64)

        sr = self.sample_rate
        n_fft = min(8192, len(mono))

        # Compute FFT
        windowed = mono[:n_fft] * np.hanning(n_fft)
        fft_data = np.fft.rfft(windowed, n=n_fft)
        magnitudes = np.abs(fft_data)
        freqs = np.fft.rfftfreq(n_fft, 1.0 / sr)

        # Total energy
        total_energy = np.sum(magnitudes ** 2)
        if total_energy < 1e-20:
            return SibilanceResult(index=0.0, peak_freq=0, energy_ratio=0.0)

        # Sibilance band energy (6-8kHz)
        sib_mask = (freqs >= self.sibilance_low) & (freqs < self.sibilance_high)
        sib_energy = np.sum(magnitudes[sib_mask] ** 2)

        # Energy ratio
        energy_ratio = float(sib_energy / total_energy)

        # Find peak frequency in sibilance band
        if np.any(sib_mask):
            sib_freqs = freqs[sib_mask]
            sib_mags = magnitudes[sib_mask]
            peak_idx = np.argmax(sib_mags)
            peak_freq = int(round(sib_freqs[peak_idx]))
        else:
            peak_freq = 0

        # Compute sibilance index (0-1)
        # Typical dry vocal: energy_ratio ~0.05-0.15
        # Map energy_ratio to 0-1 index using a sigmoid-like mapping
        # index = 1 - exp(-k * ratio) where k adjusts sensitivity
        k = 8.0  # Sensitivity factor
        sibilance_index = float(1.0 - np.exp(-k * energy_ratio))
        sibilance_index = round(np.clip(sibilance_index, 0.0, 1.0), 2)

        return SibilanceResult(
            index=sibilance_index,
            peak_freq=peak_freq,
            energy_ratio=round(energy_ratio, 2),
        )

    def to_dict(self, result: SibilanceResult) -> dict[str, Any]:
        """Convert SibilanceResult to dict for JSON serialization."""
        return {
            "index": result.index,
            "peak_freq": result.peak_freq,
            "energy_ratio": result.energy_ratio,
        }
