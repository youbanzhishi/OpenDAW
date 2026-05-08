"""
spectrum.py — 1/3-octave spectrum analysis for VCMix.

Implements:
    - 1/3-octave band spectrum (31 bands: 20Hz-20kHz)
    - Peak/dip band annotation
    - Spectral balance scoring (low/mid/high/air energy ratios)

Standard 1/3-octave center frequencies (31 bands):
    20, 25, 31.5, 40, 50, 63, 80, 100, 125, 160,
    200, 250, 315, 400, 500, 630, 800, 1000, 1250, 1600,
    2000, 2500, 3150, 4000, 5000, 6300, 8000, 10000, 12500, 16000, 20000

Usage:
    from vcmix.analysis.spectrum import SpectrumAnalyzer
    analyzer = SpectrumAnalyzer(sample_rate=44100)
    result = analyzer.analyze(audio)

Dependencies: numpy, scipy.signal
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
from scipy.signal import welch


# Standard 1/3-octave center frequencies (ISO 266)
THIRD_OCTAVE_CENTER_FREQS = [
    20, 25, 31.5, 40, 50, 63, 80, 100, 125, 160,
    200, 250, 315, 400, 500, 630, 800, 1000, 1250, 1600,
    2000, 2500, 3150, 4000, 5000, 6300, 8000, 10000, 12500, 16000, 20000,
]

# Nice display labels for band keys
BAND_LABELS = {
    20: "20", 25: "25", 31.5: "31.5", 40: "40", 50: "50",
    63: "63", 80: "80", 100: "100", 125: "125", 160: "160",
    200: "200", 250: "250", 315: "315", 400: "400", 500: "500",
    630: "630", 800: "800", 1000: "1k", 1250: "1.25k", 1600: "1.6k",
    2000: "2k", 2500: "2.5k", 3150: "3.15k", 4000: "4k", 5000: "5k",
    6300: "6.3k", 8000: "8k", 10000: "10k", 12500: "12.5k", 16000: "16k", 20000: "20k",
}


@dataclass
class SpectrumResult:
    """1/3-octave spectrum analysis result."""
    bands: dict[str, float]          # label -> level in dB
    peak_band: str                   # band with highest energy
    dip_band: str                    # band with lowest energy (excluding edges)
    balance: dict[str, float]        # low/mid/high/air energy ratios


class SpectrumAnalyzer:
    """
    1/3-octave spectrum analyzer.

    Args:
        sample_rate: Audio sample rate in Hz.
    """

    # Spectral balance band definitions
    LOW_RANGE = (20, 250)       # Sub + Low
    MID_RANGE = (250, 2000)     # Mid
    HIGH_RANGE = (2000, 6000)   # High
    AIR_RANGE = (6000, 20000)   # Air/Presence

    def __init__(self, sample_rate: int = 44100) -> None:
        self.sample_rate = sample_rate
        nyquist = sample_rate / 2.0
        self.center_freqs = [f for f in THIRD_OCTAVE_CENTER_FREQS if f < nyquist]

    def _compute_band_edges(self, center: float) -> tuple[float, float]:
        """Compute 1/3-octave band edge frequencies. Factor = 2^(1/6)."""
        factor = 2.0 ** (1.0 / 6.0)
        return center / factor, center * factor

    def analyze(self, audio: np.ndarray) -> SpectrumResult:
        """
        Perform 1/3-octave spectrum analysis.

        Args:
            audio: Audio array (1D mono or 2D multi-channel, float).

        Returns:
            SpectrumResult with band levels, peak/dip, and balance.
        """
        if audio.ndim == 2:
            mono = np.mean(audio.astype(np.float64), axis=0)
        else:
            mono = audio.astype(np.float64)

        sr = self.sample_rate

        # Compute PSD using Welch's method
        nperseg = min(8192, len(mono))
        freqs, psd = welch(mono, fs=sr, nperseg=nperseg, noverlap=nperseg // 2)

        # Map PSD to 1/3-octave bands
        band_levels = {}
        band_levels_hz = {}  # For peak/dip detection using numeric keys

        for fc in self.center_freqs:
            lo, hi = self._compute_band_edges(fc)
            mask = (freqs >= lo) & (freqs < hi)
            label = BAND_LABELS.get(fc, str(fc))

            if np.any(mask):
                band_energy = np.mean(psd[mask])
                if band_energy > 1e-20:
                    level_db = round(float(10.0 * np.log10(band_energy)), 1)
                else:
                    level_db = -120.0
            else:
                level_db = -120.0

            band_levels[label] = level_db
            band_levels_hz[fc] = level_db

        # Find peak and dip bands (excluding extreme edges < 50Hz and > 16kHz)
        inner_bands = {
            k: v for k, v in band_levels_hz.items()
            if 50.0 <= k <= 16000.0
        }

        if inner_bands:
            peak_fc = max(inner_bands, key=lambda k: inner_bands[k])
            dip_fc = min(inner_bands, key=lambda k: inner_bands[k])
            peak_band = BAND_LABELS.get(peak_fc, str(peak_fc))
            dip_band = BAND_LABELS.get(dip_fc, str(dip_fc))
        else:
            peak_band = list(band_levels.keys())[0] if band_levels else "N/A"
            dip_band = peak_band

        # Compute spectral balance (energy ratios)
        balance = self._compute_balance(freqs, psd)

        return SpectrumResult(
            bands=band_levels,
            peak_band=peak_band,
            dip_band=dip_band,
            balance=balance,
        )

    def _compute_balance(self, freqs: np.ndarray, psd: np.ndarray) -> dict[str, float]:
        """
        Compute spectral balance: energy ratios for low/mid/high/air.

        Returns ratios that sum to 1.0.
        """
        def band_energy(lo: float, hi: float) -> float:
            mask = (freqs >= lo) & (freqs < hi)
            if np.any(mask):
                return float(np.sum(psd[mask]))
            return 0.0

        low_e = band_energy(*self.LOW_RANGE)
        mid_e = band_energy(*self.MID_RANGE)
        high_e = band_energy(*self.HIGH_RANGE)
        air_e = band_energy(*self.AIR_RANGE)

        total = low_e + mid_e + high_e + air_e
        if total < 1e-20:
            return {"low": 0.25, "mid": 0.25, "high": 0.25, "air": 0.25}

        return {
            "low": round(low_e / total, 2),
            "mid": round(mid_e / total, 2),
            "high": round(high_e / total, 2),
            "air": round(air_e / total, 2),
        }

    def to_dict(self, result: SpectrumResult) -> dict[str, Any]:
        """Convert SpectrumResult to dict for JSON serialization."""
        return {
            "bands": result.bands,
            "peak_band": result.peak_band,
            "dip_band": result.dip_band,
            "balance": result.balance,
        }
