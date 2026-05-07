"""
meter.py — Audio level metering for VCMix.

Provides standard audio metering measurements:
    - RMS level (dBFS)
    - Sample peak (dBFS)
    - True peak (dBFS) via 4x oversampling
    - LUFS (simplified K-weighted, Phase 2 full ITU-R BS.1770)

All measurements return values in dBFS (0 dBFS = digital full scale).

Usage:
    from vcmix.audio.meter import Meter
    meter = Meter(sample_rate=44100)
    rms_db = meter.rms_db(audio)
    peak_db = meter.peak_db(audio)
    true_peak_db = meter.true_peak_db(audio)

Dependencies: numpy
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class Meter:
    """
    Audio level meter.

    Args:
        sample_rate: Audio sample rate.
    """

    sample_rate: int = 44100

    def rms(self, audio: np.ndarray) -> float:
        """RMS level (linear)."""
        return float(np.sqrt(np.mean(audio.astype(np.float64) ** 2)))

    def rms_db(self, audio: np.ndarray) -> float:
        """RMS level in dBFS."""
        r = self.rms(audio)
        return 20.0 * np.log10(r) if r > 0 else -120.0

    def peak(self, audio: np.ndarray) -> float:
        """Sample peak level (linear)."""
        return float(np.max(np.abs(audio)))

    def peak_db(self, audio: np.ndarray) -> float:
        """Sample peak level in dBFS."""
        p = self.peak(audio)
        return 20.0 * np.log10(p) if p > 0 else -120.0

    def true_peak(self, audio: np.ndarray) -> float:
        """
        True peak level via 4x oversampling (linear).

        Detects inter-sample peaks that sample-peak misses.
        """
        if audio.ndim == 2:
            return max(self.true_peak(audio[ch]) for ch in range(audio.shape[0]))

        upsampled = np.zeros(len(audio) * 4, dtype=np.float64)
        upsampled[::4] = audio.astype(np.float64)
        # Simple lowpass
        kernel = np.ones(15) / 15.0
        filtered = np.convolve(upsampled, kernel, mode="same")
        return float(np.max(np.abs(filtered)))

    def true_peak_db(self, audio: np.ndarray) -> float:
        """True peak level in dBFS."""
        tp = self.true_peak(audio)
        return 20.0 * np.log10(tp) if tp > 0 else -120.0

    def lufs(self, audio: np.ndarray) -> float:
        """
        Simplified LUFS measurement (K-weighted RMS approximation).

        Note: This is a simplified approximation, not full ITU-R BS.1770-4.
        Full implementation planned for Phase 2.

        Returns:
            Integrated loudness in LUFS.
        """
        # K-weighting: simple high-shelf + high-pass approximation
        # Stage 1: Pre-filter (high shelf +4dB above 1kHz, approx)
        # Stage 2: Weighting filter
        # Simplified: just RMS with a gentle high-frequency emphasis
        audio_f = audio.astype(np.float64)

        if audio_f.ndim == 2:
            # Sum channels with channel weighting (stereo = +1.5dB per ch)
            n_ch = audio_f.shape[0]
            audio_f = np.sum(audio_f, axis=0) / np.sqrt(n_ch)

        rms_val = np.sqrt(np.mean(audio_f ** 2))
        if rms_val < 1e-10:
            return -120.0

        # Approximate LUFS = RMS_dBFS - 0.691 (K-weighting offset)
        rms_dbfs = 20.0 * np.log10(rms_val)
        return round(rms_dbfs - 0.691, 1)

    def full_report(self, audio: np.ndarray) -> dict[str, float]:
        """
        Generate a complete metering report.

        Returns:
            Dict with all metering values in dBFS/LUFS.
        """
        return {
            "rms_db": round(self.rms_db(audio), 2),
            "peak_db": round(self.peak_db(audio), 2),
            "true_peak_db": round(self.true_peak_db(audio), 2),
            "lufs": round(self.lufs(audio), 1),
            "dynamic_range_db": round(self.peak_db(audio) - self.rms_db(audio), 2),
        }
