"""
loudness.py — EBU R128 loudness analysis for VCMix.

Implements EBU R128 loudness measurement:
    - Integrated LUFS (BS.1770-4 with gating, via pyloudnorm)
    - RMS (overall + per-second)
    - True Peak detection
    - Dynamic Range (DR = True Peak - RMS)
    - Loudness Range (LRA, via pyloudnorm)

Uses pyloudnorm for BS.1770-4 compliant LUFS/LRA measurement,
which includes the proper gating algorithm. Falls back to
simplified K-weighted RMS when pyloudnorm is unavailable.

K-weighting filter chain (biquad implementation, for fallback):
    Stage 1: High-shelf +4dB at 1500Hz (head-related acoustic model)
    Stage 2: High-pass at 38Hz (RLB revised low-frequency B-weighting)

References:
    - ITU-R BS.1770-4
    - EBU R128
    - pyloudnorm (Brechtmann, 2021)

Usage:
    from vcmix.analysis.loudness import LoudnessAnalyzer
    analyzer = LoudnessAnalyzer(sample_rate=44100)
    result = analyzer.analyze(audio)

Dependencies: numpy, scipy.signal, pyloudnorm (recommended)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
from scipy.signal import lfilter


@dataclass
class LoudnessResult:
    """Loudness analysis result."""
    integrated_lufs: float
    rms_dbfs: float
    rms_per_second: list[float]
    true_peak_dbfs: float
    dynamic_range_db: float
    loudness_range_lu: float


class LoudnessAnalyzer:
    """
    EBU R128 loudness analyzer.

    Uses pyloudnorm for BS.1770-4 compliant LUFS/LRA with gating.
    Falls back to simplified K-weighted RMS when pyloudnorm unavailable.

    Args:
        sample_rate: Audio sample rate in Hz.
    """

    def __init__(self, sample_rate: int = 44100) -> None:
        self.sample_rate = sample_rate
        self._b_shelf, self._a_shelf = self._design_high_shelf(
            G=4.0, fc=1500.0, Q=1.0 / np.sqrt(2), rate=sample_rate
        )
        self._b_hp, self._a_hp = self._design_high_pass(
            fc=38.0, Q=0.5, rate=sample_rate
        )

    @staticmethod
    def _design_high_shelf(
        G: float, fc: float, Q: float, rate: float
    ) -> tuple[np.ndarray, np.ndarray]:
        """Design high-shelf biquad filter (Audio EQ Cookbook / RBJ)."""
        A = 10.0 ** (G / 40.0)
        w0 = 2.0 * np.pi * (fc / rate)
        alpha = np.sin(w0) / (2.0 * Q)

        b0 = A * ((A + 1) + (A - 1) * np.cos(w0) + 2 * np.sqrt(A) * alpha)
        b1 = -2 * A * ((A - 1) + (A + 1) * np.cos(w0))
        b2 = A * ((A + 1) + (A - 1) * np.cos(w0) - 2 * np.sqrt(A) * alpha)
        a0 = (A + 1) - (A - 1) * np.cos(w0) + 2 * np.sqrt(A) * alpha
        a1 = 2 * ((A - 1) - (A + 1) * np.cos(w0))
        a2 = (A + 1) - (A - 1) * np.cos(w0) - 2 * np.sqrt(A) * alpha

        b = np.array([b0, b1, b2]) / a0
        a = np.array([a0, a1, a2]) / a0
        return b, a

    @staticmethod
    def _design_high_pass(
        fc: float, Q: float, rate: float
    ) -> tuple[np.ndarray, np.ndarray]:
        """Design high-pass biquad filter (Audio EQ Cookbook / RBJ)."""
        w0 = 2.0 * np.pi * (fc / rate)
        alpha = np.sin(w0) / (2.0 * Q)

        b0 = (1 + np.cos(w0)) / 2
        b1 = -(1 + np.cos(w0))
        b2 = (1 + np.cos(w0)) / 2
        a0 = 1 + alpha
        a1 = -2 * np.cos(w0)
        a2 = 1 - alpha

        b = np.array([b0, b1, b2]) / a0
        a = np.array([a0, a1, a2]) / a0
        return b, a

    def _k_weight(self, audio: np.ndarray) -> np.ndarray:
        """Apply K-weighting filter chain (for fallback/advanced use)."""
        x = audio.astype(np.float64)
        x = lfilter(self._b_shelf, self._a_shelf, x)
        x = lfilter(self._b_hp, self._a_hp, x)
        return x

    def _compute_lufs_pyloudnorm(self, audio: np.ndarray) -> tuple[float, float]:
        """
        Compute LUFS and LRA using pyloudnorm (BS.1770-4 compliant).

        Args:
            audio: Mono audio signal (1D float64 array).

        Returns:
            Tuple of (integrated_lufs, loudness_range_lu).
        """
        try:
            import pyloudnorm as pyln
            mono = audio.astype(np.float64)
            meter = pyln.Meter(self.sample_rate)
            # pyloudnorm requires audio longer than block size (0.4s)
            min_samples = int(meter.block_size * self.sample_rate) + 1
            if len(mono) < min_samples:
                # Too short for pyloudnorm, use fallback
                return self._compute_lufs_simplified(mono)

            lufs = meter.integrated_loudness(mono)
            lra = meter.loudness_range(mono)

            if np.isnan(lufs) or np.isinf(lufs):
                lufs = -120.0
            if np.isnan(lra) or np.isinf(lra):
                lra = 0.0
            return round(float(lufs), 1), round(float(lra), 1)
        except (ImportError, ValueError):
            return self._compute_lufs_simplified(audio)

    def _compute_lufs_simplified(self, audio: np.ndarray) -> tuple[float, float]:
        """
        Compute simplified LUFS and LRA (fallback).

        Note: Without BS.1770-4 gating, this gives lower LUFS
        for material with silence gaps.
        """
        k_weighted = self._k_weight(audio)
        mean_sq = np.mean(k_weighted ** 2)
        if mean_sq < 1e-20:
            lufs = -120.0
        else:
            lufs = -0.691 + 10.0 * np.log10(mean_sq)
            lufs = round(float(lufs), 1)

        # Simplified LRA
        sr = self.sample_rate
        block_size = int(3.0 * sr)
        hop_size = int(1.0 * sr)

        if len(k_weighted) < block_size:
            return lufs, 0.0

        short_term_lufs = []
        for start in range(0, len(k_weighted) - block_size + 1, hop_size):
            block = k_weighted[start:start + block_size]
            ms = np.mean(block ** 2)
            if ms > 1e-20:
                short_term_lufs.append(-0.691 + 10.0 * np.log10(ms))

        if len(short_term_lufs) < 2:
            return lufs, 0.0

        arr = np.array(short_term_lufs)
        p10 = np.percentile(arr, 10)
        p95 = np.percentile(arr, 95)
        lra = max(0.0, p95 - p10)

        return lufs, round(float(lra), 1)

    def _compute_rms_dbfs(self, audio: np.ndarray) -> float:
        """Compute overall RMS in dBFS."""
        rms = np.sqrt(np.mean(audio.astype(np.float64) ** 2))
        if rms < 1e-20:
            return -120.0
        return round(float(20.0 * np.log10(rms)), 2)

    def _compute_rms_per_second(self, audio: np.ndarray) -> list[float]:
        """Compute RMS for each 1-second block."""
        sr = self.sample_rate
        n_samples = len(audio)
        n_seconds = max(1, n_samples // sr)
        results = []
        for i in range(n_seconds):
            start = i * sr
            end = min(start + sr, n_samples)
            if start >= n_samples:
                break
            block = audio[start:end].astype(np.float64)
            rms = np.sqrt(np.mean(block ** 2))
            if rms < 1e-20:
                results.append(-120.0)
            else:
                results.append(round(float(20.0 * np.log10(rms)), 2))
        return results

    def _compute_true_peak(self, audio: np.ndarray) -> float:
        """Compute true peak via 4x oversampling."""
        if audio.ndim == 2:
            return max(self._compute_true_peak(audio[ch]) for ch in range(audio.shape[0]))

        upsampled = np.zeros(len(audio) * 4, dtype=np.float64)
        upsampled[::4] = audio.astype(np.float64)
        kernel = np.ones(15) / 15.0
        filtered = np.convolve(upsampled, kernel, mode="same")
        tp = np.max(np.abs(filtered))
        if tp < 1e-20:
            return -120.0
        return round(float(20.0 * np.log10(tp)), 2)

    def _compute_sample_peak_dbfs(self, audio: np.ndarray) -> float:
        """Compute sample peak in dBFS."""
        if audio.ndim == 2:
            peak = np.max(np.abs(audio))
        else:
            peak = np.max(np.abs(audio))
        if peak < 1e-20:
            return -120.0
        return round(float(20.0 * np.log10(peak)), 2)

    def analyze(self, audio: np.ndarray) -> LoudnessResult:
        """
        Perform complete loudness analysis.

        Args:
            audio: Audio array (1D mono or 2D multi-channel, float).

        Returns:
            LoudnessResult with all loudness metrics.
        """
        # Convert to mono for analysis
        if audio.ndim == 2:
            mono = np.mean(audio.astype(np.float64), axis=0)
        else:
            mono = audio.astype(np.float64)

        integrated_lufs, loudness_range = self._compute_lufs_pyloudnorm(mono)
        rms_dbfs = self._compute_rms_dbfs(mono)
        rms_per_second = self._compute_rms_per_second(mono)
        true_peak_dbfs = self._compute_true_peak(audio)
        # DR = Sample Peak - RMS (using mono for consistency)
        sample_peak_dbfs = self._compute_sample_peak_dbfs(mono)
        dynamic_range = round(sample_peak_dbfs - rms_dbfs, 2)

        return LoudnessResult(
            integrated_lufs=integrated_lufs,
            rms_dbfs=rms_dbfs,
            rms_per_second=rms_per_second,
            true_peak_dbfs=true_peak_dbfs,
            dynamic_range_db=dynamic_range,
            loudness_range_lu=loudness_range,
        )

    def to_dict(self, result: LoudnessResult) -> dict[str, Any]:
        """Convert LoudnessResult to dict for JSON serialization."""
        return {
            "integrated_lufs": result.integrated_lufs,
            "rms_dbfs": result.rms_dbfs,
            "rms_per_second": result.rms_per_second,
            "true_peak_dbfs": result.true_peak_dbfs,
            "dynamic_range_db": result.dynamic_range_db,
            "loudness_range_lu": result.loudness_range_lu,
        }
