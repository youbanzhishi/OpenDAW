"""
analyzer.py — Audio data analysis engine for VCMix.

Provides real-time and post-render analysis of audio signals:
    - RMS level (per-channel and overall)
    - Peak level (sample-peak and true-peak)
    - LUFS (integrated, short-term, momentary) — Phase 2
    - Spectrum analysis (FFT magnitude, spectral centroid)
    - Dynamic range estimation

Usage:
    from vcmix.engine.analyzer import Analyzer
    analyzer = Analyzer(sample_rate=44100)
    rms = analyzer.rms(audio_buffer)
    peak = analyzer.peak(audio_buffer)
    spectrum = analyzer.spectrum(audio_buffer)

Dependencies: numpy, librosa (optional, for advanced features)
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class Analyzer:
    """
    Audio analysis engine.

    Args:
        sample_rate: Sample rate of the audio to analyze.
    """

    sample_rate: int = 44100

    def rms(self, audio: np.ndarray) -> float:
        """
        Calculate RMS level of audio buffer.

        Args:
            audio: Audio buffer (1D or 2D numpy array).

        Returns:
            RMS value as float.
        """
        return float(np.sqrt(np.mean(audio.astype(np.float64) ** 2)))

    def peak(self, audio: np.ndarray) -> float:
        """
        Calculate peak level of audio buffer.

        Args:
            audio: Audio buffer (1D or 2D numpy array).

        Returns:
            Peak absolute value as float.
        """
        return float(np.max(np.abs(audio)))

    def spectrum(self, audio: np.ndarray, n_fft: int = 2048) -> tuple[np.ndarray, np.ndarray]:
        """
        Compute magnitude spectrum via FFT.

        Args:
            audio: Mono audio buffer (1D numpy array).
            n_fft: FFT window size.

        Returns:
            Tuple of (frequencies, magnitudes) numpy arrays.
        """
        windowed = audio[:n_fft] * np.hanning(min(len(audio), n_fft))
        fft_data = np.fft.rfft(windowed, n=n_fft)
        magnitudes = np.abs(fft_data)
        frequencies = np.fft.rfftfreq(n_fft, 1.0 / self.sample_rate)
        return frequencies, magnitudes

    def dynamic_range(self, audio: np.ndarray) -> float:
        """
        Estimate dynamic range (difference between peak and RMS in dB).

        Args:
            audio: Audio buffer.

        Returns:
            Dynamic range in dB.
        """
        rms_val = self.rms(audio)
        peak_val = self.peak(audio)
        if rms_val <= 0:
            return 0.0
        return float(20 * np.log10(peak_val / rms_val))
