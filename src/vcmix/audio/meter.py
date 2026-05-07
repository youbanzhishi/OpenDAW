"""
meter.py — RMS/Peak/spectrum metering for VCMix.

Provides metering utilities for visual feedback and analysis:
    - RMS level (momentary and integrated)
    - Peak level (sample peak)
    - Spectrum (FFT magnitude for frequency display)

All values returned in linear scale; convert to dBFS in the caller
using 20 * log10(value) if needed.

Usage:
    from vcmix.audio.meter import Meter
    meter = Meter(sample_rate=44100)
    rms = meter.rms(audio)
    peak = meter.peak(audio)
    freqs, mags = meter.spectrum(audio)

Dependencies: numpy
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class Meter:
    """
    Audio metering utility.

    Args:
        sample_rate: Sample rate of the audio.
        window_ms: RMS window size in milliseconds (default 400ms = K-weighted).
    """

    sample_rate: int = 44100
    window_ms: float = 400.0

    @property
    def window_samples(self) -> int:
        """Calculate window size in samples."""
        return int(self.sample_rate * self.window_ms / 1000)

    def rms(self, audio: np.ndarray) -> float:
        """
        Calculate RMS level of audio buffer.

        Args:
            audio: Audio buffer.

        Returns:
            RMS value (linear scale).
        """
        return float(np.sqrt(np.mean(audio.astype(np.float64) ** 2)))

    def rms_windowed(self, audio: np.ndarray) -> np.ndarray:
        """
        Calculate RMS for each windowed segment.

        Args:
            audio: Audio buffer.

        Returns:
            Array of RMS values, one per window.
        """
        win = self.window_samples
        n_windows = len(audio) // win
        if n_windows == 0:
            return np.array([self.rms(audio)])

        results = []
        for i in range(n_windows):
            segment = audio[i * win : (i + 1) * win]
            results.append(np.sqrt(np.mean(segment.astype(np.float64) ** 2)))
        return np.array(results)

    def peak(self, audio: np.ndarray) -> float:
        """
        Calculate peak level of audio buffer.

        Args:
            audio: Audio buffer.

        Returns:
            Peak absolute value (linear scale).
        """
        return float(np.max(np.abs(audio)))

    def spectrum(self, audio: np.ndarray, n_fft: int = 2048) -> tuple[np.ndarray, np.ndarray]:
        """
        Compute magnitude spectrum via FFT.

        Args:
            audio: Mono audio buffer.
            n_fft: FFT window size.

        Returns:
            Tuple of (frequencies, magnitudes).
        """
        windowed = audio[:n_fft] * np.hanning(min(len(audio), n_fft))
        fft_data = np.fft.rfft(windowed, n=n_fft)
        magnitudes = np.abs(fft_data)
        frequencies = np.fft.rfftfreq(n_fft, 1.0 / self.sample_rate)
        return frequencies, magnitudes
