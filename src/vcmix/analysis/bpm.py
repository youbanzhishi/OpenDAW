"""
bpm.py — BPM detection for VCMix analysis module.

Uses librosa onset detection + autocorrelation for robust tempo estimation.
Includes slow-song correction (BPM < 80 → double, BPM > 160 → halve).

Usage:
    from vcmix.analysis.bpm import BPMDetector
    detector = BPMDetector()
    result = detector.analyze(audio, sample_rate=44100)

Dependencies: numpy, librosa
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import warnings

import numpy as np


@dataclass
class BPMResult:
    """BPM detection result."""
    value: float
    confidence: float


class BPMDetector:
    """
    BPM detector using librosa onset detection + beat tracking.

    Provides confidence score based on onset strength autocorrelation
    peak prominence.
    """

    def analyze(self, audio: np.ndarray, sample_rate: int = 44100) -> BPMResult:
        """
        Detect BPM from audio.

        Args:
            audio: Audio array (1D mono or 2D multi-channel, float).
            sample_rate: Sample rate in Hz.

        Returns:
            BPMResult with BPM value and confidence.
        """
        try:
            import librosa
            warnings.filterwarnings("ignore", message=".*n_fft.*is too large.*")
        except ImportError:
            raise ImportError(
                "librosa is required for BPM detection. "
                "Install with: pip install librosa"
            )

        # Convert to mono
        if audio.ndim == 2:
            mono = np.mean(audio.astype(np.float32), axis=0)
        else:
            mono = audio.astype(np.float32)

        # Detect tempo using librosa
        tempo, beat_frames = librosa.beat.beat_track(y=mono, sr=sample_rate)

        # Handle librosa returning ndarray (newer versions)
        if isinstance(tempo, np.ndarray):
            bpm = float(tempo.flat[0])
        else:
            bpm = float(tempo)

        # Guard against zero BPM
        if bpm <= 0 or np.isnan(bpm) or np.isinf(bpm):
            return BPMResult(value=0.0, confidence=0.0)

        # Compute confidence from onset autocorrelation
        confidence = self._compute_confidence(mono, sample_rate, bpm)

        # Normalize BPM to 80-160 range
        if bpm < 80:
            bpm *= 2.0
        elif bpm > 160:
            bpm /= 2.0

        return BPMResult(
            value=round(bpm, 1),
            confidence=round(confidence, 3),
        )

    def _compute_confidence(
        self, audio: np.ndarray, sr: int, bpm: float
    ) -> float:
        """
        Compute BPM confidence from onset strength autocorrelation.

        Args:
            audio: Mono audio signal.
            sr: Sample rate.
            bpm: Detected BPM.

        Returns:
            Confidence value between 0.0 and 1.0.
        """
        try:
            import librosa
            warnings.filterwarnings("ignore", message=".*n_fft.*is too large.*")
        except ImportError:
            return 0.5

        if bpm <= 0:
            return 0.0

        # Get onset envelope
        onset_env = librosa.onset.onset_strength(y=audio, sr=sr)

        if len(onset_env) < 10:
            return 0.3

        # Autocorrelation of onset envelope
        onset_centered = onset_env - np.mean(onset_env)
        autocorr = np.correlate(onset_centered, onset_centered, mode="full")
        autocorr = autocorr[len(autocorr) // 2:]  # Positive lags only

        if autocorr[0] < 1e-10:
            return 0.3

        autocorr_norm = autocorr / autocorr[0]

        # Expected lag for the detected BPM
        hop_length = 512  # librosa default
        if bpm <= 0:
            return 0.3
        expected_lag = int(60.0 * sr / (hop_length * bpm))

        if expected_lag <= 0 or expected_lag >= len(autocorr_norm):
            return 0.3

        # Confidence = autocorrelation value at expected lag
        confidence = float(np.clip(autocorr_norm[expected_lag], 0.0, 1.0))

        # Boost low confidence slightly to avoid zero
        confidence = max(confidence, 0.1)

        return confidence

    def to_dict(self, result: BPMResult) -> dict[str, Any]:
        """Convert BPMResult to dict for JSON serialization."""
        return {
            "value": result.value,
            "confidence": result.confidence,
        }
