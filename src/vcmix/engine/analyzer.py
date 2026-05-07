"""
analyzer.py — Audio data analysis engine for VCMix.

Provides comprehensive audio signal analysis:
    - compute_rms()          — RMS level (per-channel or overall)
    - compute_peak()         — Sample peak level
    - compute_true_peak()    — True peak via 4x oversampling
    - compute_spectrum()     — FFT magnitude spectrum with band energy
    - compute_sibilance()    — Sibilant energy ratio in 5-9kHz band
    - compute_rt60()         — Reverb decay time estimation

All methods accept numpy arrays (1D mono or 2D multi-channel).
Used by Renderer in --report mode to emit per-step analysis.

Usage:
    from vcmix.engine.analyzer import Analyzer
    analyzer = Analyzer(sample_rate=44100)
    rms = analyzer.compute_rms(audio)
    spectrum = analyzer.compute_spectrum(audio)

Dependencies: numpy
"""

from __future__ import annotations

import numpy as np
from dataclasses import dataclass


@dataclass
class Analyzer:
    """
    Audio analysis engine.

    Args:
        sample_rate: Sample rate of the audio to analyze.
    """

    sample_rate: int = 44100

    def compute_rms(self, audio: np.ndarray) -> float:
        """
        Calculate RMS level of audio buffer.

        Args:
            audio: Audio buffer (1D or 2D numpy array, float).

        Returns:
            RMS value as float (linear scale).
        """
        return float(np.sqrt(np.mean(audio.astype(np.float64) ** 2)))

    def compute_peak(self, audio: np.ndarray) -> float:
        """
        Calculate sample peak level.

        Args:
            audio: Audio buffer.

        Returns:
            Maximum absolute sample value.
        """
        return float(np.max(np.abs(audio)))

    def compute_true_peak(self, audio: np.ndarray) -> float:
        """
        Estimate true peak level via 4x oversampling.

        Uses simple sinc interpolation (4x upsampling) to detect
        inter-sample peaks that sample-peak misses.

        Args:
            audio: Audio buffer (mono 1D or multi-channel 2D).

        Returns:
            Estimated true peak value.
        """
        if audio.ndim == 2:
            # Process each channel, return max
            peaks = [self.compute_true_peak(audio[ch]) for ch in range(audio.shape[0])]
            return max(peaks)

        # Simple 4x oversampling via zero-insertion + lowpass
        upsampled = np.zeros(len(audio) * 4, dtype=np.float64)
        upsampled[::4] = audio.astype(np.float64)

        # Simple moving-average lowpass (order 15)
        kernel_size = 15
        kernel = np.ones(kernel_size) / kernel_size
        filtered = np.convolve(upsampled, kernel, mode="same")

        return float(np.max(np.abs(filtered)))

    def compute_spectrum(self, audio: np.ndarray, n_fft: int = 4096) -> dict[str, float]:
        """
        Compute frequency band energy distribution.

        Splits the spectrum into standard mixing bands:
            sub (20-60Hz), low (60-250Hz), mid (250-2kHz),
            high-mid (2k-6kHz), high (6k-16kHz), air (16k+Hz)

        Args:
            audio: Mono audio buffer (1D).
            n_fft: FFT window size.

        Returns:
            Dict of band_name -> energy (linear RMS of band).
        """
        if audio.ndim == 2:
            audio = audio[0] if audio.shape[0] <= audio.shape[1] else audio[:, 0]

        # Ensure enough samples
        if len(audio) < n_fft:
            n_fft = len(audio)

        windowed = audio[:n_fft].astype(np.float64) * np.hanning(n_fft)
        fft_data = np.fft.rfft(windowed, n=n_fft)
        magnitudes = np.abs(fft_data)
        freqs = np.fft.rfftfreq(n_fft, 1.0 / self.sample_rate)

        # Define mixing bands
        bands = {
            "sub":      (20,   60),
            "low":      (60,   250),
            "mid":      (250,  2000),
            "high_mid": (2000, 6000),
            "high":     (6000, 16000),
            "air":      (16000, self.sample_rate // 2),
        }

        result: dict[str, float] = {}
        for name, (lo, hi) in bands.items():
            mask = (freqs >= lo) & (freqs < hi)
            if np.any(mask):
                band_energy = float(np.sqrt(np.mean(magnitudes[mask] ** 2)))
            else:
                band_energy = 0.0
            result[name] = round(band_energy, 6)

        return result

    def compute_sibilance(self, audio: np.ndarray) -> float:
        """
        Compute sibilance ratio — energy in 5-9kHz relative to total.

        High sibilance ratio (>0.15) indicates need for de-essing.

        Args:
            audio: Audio buffer.

        Returns:
            Sibilance energy ratio (0.0 to 1.0+).
        """
        if audio.ndim == 2:
            audio = audio[0] if audio.shape[0] <= audio.shape[1] else audio[:, 0]

        n_fft = min(4096, len(audio))
        windowed = audio[:n_fft].astype(np.float64) * np.hanning(n_fft)
        fft_data = np.fft.rfft(windowed, n=n_fft)
        magnitudes = np.abs(fft_data)
        freqs = np.fft.rfftfreq(n_fft, 1.0 / self.sample_rate)

        total_energy = np.sum(magnitudes ** 2)
        if total_energy < 1e-10:
            return 0.0

        sib_mask = (freqs >= 5000) & (freqs < 9000)
        sib_energy = np.sum(magnitudes[sib_mask] ** 2)

        return float(sib_energy / total_energy)

    def compute_rt60(self, audio: np.ndarray) -> float:
        """
        Estimate RT60 reverb decay time from audio tail.

        Finds the decay curve from peak level to noise floor and
        extrapolates the time for 60dB of decay.

        Args:
            audio: Audio buffer (mono 1D preferred).

        Returns:
            Estimated RT60 in seconds. Returns 0.0 if decay too short.
        """
        if audio.ndim == 2:
            audio = audio[0] if audio.shape[0] <= audio.shape[1] else audio[:, 0]

        # Compute energy envelope (100ms windows)
        win_samples = int(self.sample_rate * 0.01)  # 10ms windows
        n_windows = len(audio) // win_samples
        if n_windows < 10:
            return 0.0

        envelope = np.array([
            np.sqrt(np.mean(audio[i * win_samples:(i + 1) * win_samples] ** 2))
            for i in range(n_windows)
        ])

        # Find peak
        peak_idx = np.argmax(envelope)
        if peak_idx >= n_windows - 1:
            return 0.0

        peak_val = envelope[peak_idx]
        if peak_val < 1e-10:
            return 0.0

        # Find where level drops 60dB below peak
        target = peak_val * (10 ** (-60 / 20))
        decay_envelope = envelope[peak_idx:]
        below_idx = np.where(decay_envelope <= target)[0]

        if len(below_idx) == 0:
            # Estimate from available decay
            end_val = decay_envelope[-1]
            if end_val < peak_val and end_val > 0:
                db_decay = 20 * np.log10(end_val / peak_val)
                if db_decay < -5:
                    time_to_end = (len(decay_envelope) * win_samples) / self.sample_rate
                    return round(time_to_end * (-60.0 / db_decay), 3)
            return 0.0

        rt60_samples = below_idx[0] * win_samples
        return round(rt60_samples / self.sample_rate, 3)

    def compare(self, before: np.ndarray, after: np.ndarray) -> dict[str, Any]:
        """
        Compare audio before/after processing and return diff report.

        Args:
            before: Audio before processing.
            after: Audio after processing.

        Returns:
            Dict with before/after metrics and deltas.
        """
        from typing import Any

        b_rms = self.compute_rms(before)
        a_rms = self.compute_rms(after)
        b_peak = self.compute_peak(before)
        a_peak = self.compute_peak(after)

        return {
            "rms_db_before": round(20 * np.log10(b_rms) if b_rms > 0 else -120.0, 2),
            "rms_db_after":  round(20 * np.log10(a_rms) if a_rms > 0 else -120.0, 2),
            "rms_delta_db":  round(20 * np.log10(a_rms / b_rms) if b_rms > 0 and a_rms > 0 else 0.0, 2),
            "peak_db_before": round(20 * np.log10(b_peak) if b_peak > 0 else -120.0, 2),
            "peak_db_after":  round(20 * np.log10(a_peak) if a_peak > 0 else -120.0, 2),
        }
