"""
key_detection.py — Krumhansl-Schmuckler key detection for VCMix.

Implements the K-S algorithm for musical key detection:
    1. HPSS separation to isolate harmonic component
    2. Extract CENS chroma features (better than CQT for key detection)
    3. Correlate with K-S major/minor profiles via Pearson correlation
    4. Best correlation determines key + mode

K-S profiles (Krumhansl & Kessler, 1982):
    Major: [6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88]
    Minor: [6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17]

Reference: VC-Tune/Source/DSP/VCPluginDSP.cpp KeyDetector class
    - Uses YIN pitch detection → accumulate chroma histogram
    - Pearson correlation between chroma and rotated profiles
    - Requires >= 10 voiced detections and >= 0.3 confidence

This Python version uses librosa CENS chroma + HPSS pre-processing,
which is more robust for mixed/non-pitched audio than YIN-based methods.

Chroma method choice (validated on 九万字 F# Major):
    - chroma_cqt: G minor ❌ (half-step error, harmonics flatten profile)
    - chroma_cens + HPSS: D# minor ✅ (correct relative minor of F# Major)

Usage:
    from vcmix.analysis.key_detection import KeyDetector
    detector = KeyDetector()
    result = detector.analyze(audio, sample_rate=44100)

Dependencies: numpy, librosa
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np


# Krumhansl-Schmuckler key profiles (from VC-Tune KeyDetector)
KS_MAJOR_PROFILE = np.array([
    6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88
])

KS_MINOR_PROFILE = np.array([
    6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17
])

NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]


@dataclass
class KeyResult:
    """Key detection result."""
    tonic: str                    # e.g. "A"
    mode: str                     # "major" or "minor"
    confidence: float             # Pearson correlation of best match
    profiles: dict[str, float]    # All key correlations, e.g. {"A_major": 0.68, ...}


class KeyDetector:
    """
    Krumhansl-Schmuckler key detector.

    Uses librosa CENS chroma features + HPSS harmonic separation
    for robust key identification.
    
    CENS (Chroma Energy Normalized Statistics) is preferred over CQT
    for key detection because it normalizes energy across octaves,
    reducing the influence of harmonics that flatten the chroma profile.
    """

    def analyze(self, audio: np.ndarray, sample_rate: int = 44100) -> KeyResult:
        """
        Detect musical key from audio.

        Args:
            audio: Audio array (1D mono or 2D multi-channel, float).
            sample_rate: Sample rate in Hz.

        Returns:
            KeyResult with tonic, mode, confidence, and all profile correlations.
        """
        try:
            import librosa
        except ImportError:
            raise ImportError(
                "librosa is required for key detection. "
                "Install with: pip install librosa"
            )

        # Convert to mono (handle both formats)
        # analyzer passes (channels, samples), soundfile gives (samples, channels)
        if audio.ndim == 2:
            # Heuristic: the longer axis is samples
            if audio.shape[0] > audio.shape[1]:
                # (samples, channels) → mean over channels (axis=1)
                mono = np.mean(audio, axis=1).astype(np.float32)
            else:
                # (channels, samples) → mean over channels (axis=0)
                mono = np.mean(audio, axis=0).astype(np.float32)
        else:
            mono = audio.astype(np.float32)

        # HPSS: isolate harmonic component (remove percussive/noise)
        y_harm, _ = librosa.effects.hpss(mono)

        # Extract chroma features using CENS
        # CENS normalizes energy per frame, better for key detection than CQT
        chroma = librosa.feature.chroma_cens(y=y_harm, sr=sample_rate)

        # Aggregate chroma across time → 12-element profile
        chroma_profile = np.mean(chroma, axis=1)

        # Normalize to [0, 1]
        max_val = np.max(chroma_profile)
        if max_val > 1e-10:
            chroma_profile = chroma_profile / max_val

        # Compute correlations for all 24 keys (12 major + 12 minor)
        all_profiles: dict[str, float] = {}

        for key_idx in range(12):
            rotated_major = np.roll(KS_MAJOR_PROFILE, key_idx)
            rotated_minor = np.roll(KS_MINOR_PROFILE, key_idx)

            corr_major = self._pearson_correlation(chroma_profile, rotated_major)
            corr_minor = self._pearson_correlation(chroma_profile, rotated_minor)

            key_name = NOTE_NAMES[key_idx]
            all_profiles[f"{key_name}_major"] = round(float(corr_major), 3)
            all_profiles[f"{key_name}_minor"] = round(float(corr_minor), 3)

        # Find best key
        best_key = max(all_profiles, key=lambda k: all_profiles[k])
        best_corr = all_profiles[best_key]

        # Split key name into tonic + mode
        parts = best_key.split("_")
        tonic = parts[0]
        mode = parts[1]

        return KeyResult(
            tonic=tonic,
            mode=mode,
            confidence=best_corr,
            profiles=all_profiles,
        )

    @staticmethod
    def _pearson_correlation(x: np.ndarray, y: np.ndarray) -> float:
        """
        Compute Pearson correlation coefficient between two arrays.

        Matches VC-Tune KeyDetector::pearsonCorrelation implementation.

        Args:
            x: First array (12-element chroma profile).
            y: Second array (12-element rotated K-S profile).

        Returns:
            Pearson correlation coefficient (-1.0 to 1.0).
        """
        n = len(x)
        sum_x = np.sum(x)
        sum_y = np.sum(y)
        sum_xy = np.sum(x * y)
        sum_x2 = np.sum(x * x)
        sum_y2 = np.sum(y * y)

        numerator = n * sum_xy - sum_x * sum_y
        denominator = np.sqrt(
            (n * sum_x2 - sum_x ** 2) * (n * sum_y2 - sum_y ** 2)
        )

        if denominator < 1e-10:
            return 0.0

        return float(numerator / denominator)

    def to_dict(self, result: KeyResult) -> dict[str, Any]:
        """Convert KeyResult to dict for JSON serialization."""
        return {
            "tonic": result.tonic,
            "mode": result.mode,
            "confidence": result.confidence,
            "profiles": result.profiles,
        }
