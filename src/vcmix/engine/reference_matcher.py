"""
reference_matcher.py — Reference track matching for VCMix.

Analyzes a reference (target) audio track's spectral and dynamic
characteristics, then computes the difference between the current
mix and the reference, generating EQ/Comp/Level adjustment suggestions.

Part of VCMix Phase 6: AutoMix intelligent mixing engine.

Usage:
    from vcmix.engine.reference_matcher import ReferenceMatcher

    matcher = ReferenceMatcher()
    ref_features = matcher.analyze_reference(ref_audio, sr)
    diff = matcher.compute_match(current_features, ref_features)
    adjustments = matcher.generate_adjustments(diff)

Dependencies: numpy, vcmix.engine.analyzer
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

from vcmix.engine.analyzer import Analyzer


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class SpectralFeatures:
    """Spectral characteristics of an audio signal."""
    # Octave band RMS values (dBFS), 8 bands
    # Band centers: 63, 125, 250, 500, 1k, 2k, 4k, 8k Hz
    band_rms_db: list[float] = field(default_factory=lambda: [
        -60.0] * 8)
    overall_rms_db: float = -60.0
    overall_peak_db: float = -60.0


@dataclass
class DynamicFeatures:
    """Dynamic characteristics of an audio signal."""
    dynamic_range_db: float = 0.0  # RMS to peak distance
    crest_factor_db: float = 0.0   # Peak to RMS ratio
    lra_db: float = 0.0            # Loudness range (approx)


@dataclass
class ReferenceProfile:
    """Combined spectral + dynamic profile of a reference track."""
    spectral: SpectralFeatures = field(
        default_factory=SpectralFeatures)
    dynamic: DynamicFeatures = field(
        default_factory=DynamicFeatures)


@dataclass
class MatchDifference:
    """Difference between current mix and reference."""
    band_delta_db: list[float] = field(default_factory=list)
    rms_delta_db: float = 0.0
    dynamic_range_delta_db: float = 0.0
    crest_delta_db: float = 0.0
    similarity_score: float = 1.0  # 0=completely different, 1=identical


@dataclass
class AdjustmentSuggestion:
    """Suggested parameter adjustment."""
    target: str          # "eq", "comp", "gain", "limiter"
    params: dict[str, Any] = field(default_factory=dict)
    reason: str = ""
    priority: float = 0.0  # 0=low, 1=critical


# ---------------------------------------------------------------------------
# Octave band center frequencies
# ---------------------------------------------------------------------------

_BAND_CENTERS = [63, 125, 250, 500, 1000, 2000, 4000, 8000]
_BAND_EDGES = [44, 88, 177, 354, 707, 1414, 2828, 5657, 11314]


# ---------------------------------------------------------------------------
# ReferenceMatcher
# ---------------------------------------------------------------------------

class ReferenceMatcher:
    """Analyze reference tracks and compute matching adjustments.

    Algorithm:
        1. Analyze reference track → SpectralFeatures + DynamicFeatures
        2. Analyze current mix → same features
        3. Compute per-band delta (dB) between current and reference
        4. Generate EQ/Comp/Level adjustment suggestions
    """

    def __init__(self, sample_rate: int = 44100) -> None:
        self.sr = sample_rate

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def analyze_reference(self, audio: np.ndarray,
                          sr: int | None = None) -> ReferenceProfile:
        """Analyze a reference audio track.

        Parameters
        ----------
        audio : np.ndarray
            Mono or stereo audio signal.
        sr : int, optional
            Sample rate (defaults to self.sr).

        Returns
        -------
        ReferenceProfile
        """
        sr = sr or self.sr
        audio = np.asarray(audio, dtype=np.float64).ravel()

        spectral = self._compute_spectral(audio, sr)
        dynamic = self._compute_dynamic(audio, sr)

        return ReferenceProfile(spectral=spectral, dynamic=dynamic)

    def compute_match(self, current: ReferenceProfile,
                      reference: ReferenceProfile) -> MatchDifference:
        """Compute the difference between current mix and reference.

        Parameters
        ----------
        current : ReferenceProfile
            Current mix profile.
        reference : ReferenceProfile
            Reference track profile.

        Returns
        -------
        MatchDifference
        """
        band_delta = [
            c - r for c, r in zip(
                current.spectral.band_rms_db,
                reference.spectral.band_rms_db,
            )
        ]
        rms_delta = current.spectral.overall_rms_db - \
            reference.spectral.overall_rms_db
        dr_delta = current.dynamic.dynamic_range_db - \
            reference.dynamic.dynamic_range_db
        crest_delta = current.dynamic.crest_factor_db - \
            reference.dynamic.crest_factor_db

        # Similarity score (1 - mean absolute band delta / 20)
        mean_band_delta = float(
            np.mean(np.abs(band_delta))) if band_delta else 0.0
        similarity = max(0.0, 1.0 - mean_band_delta / 20.0)

        return MatchDifference(
            band_delta_db=band_delta,
            rms_delta_db=rms_delta,
            dynamic_range_delta_db=dr_delta,
            crest_delta_db=crest_delta,
            similarity_score=similarity,
        )

    def generate_adjustments(
        self, diff: MatchDifference,
    ) -> list[AdjustmentSuggestion]:
        """Generate parameter adjustment suggestions.

        Parameters
        ----------
        diff : MatchDifference
            Difference between current and reference.

        Returns
        -------
        list[AdjustmentSuggestion]
        """
        suggestions: list[AdjustmentSuggestion] = []

        # 1. Per-band EQ adjustments
        for i, delta in enumerate(diff.band_delta_db):
            if abs(delta) > 1.5:  # Only suggest if >1.5dB difference
                freq = _BAND_CENTERS[i]
                suggestions.append(AdjustmentSuggestion(
                    target="eq",
                    params={
                        "frequency": freq,
                        "gain_db": round(-delta * 0.5, 1),
                        "q": 1.0,
                    },
                    reason=f"Band {freq}Hz: current is "
                           f"{delta:+.1f}dB vs reference",
                    priority=min(1.0, abs(delta) / 12.0),
                ))

        # 2. Overall level adjustment
        if abs(diff.rms_delta_db) > 2.0:
            suggestions.append(AdjustmentSuggestion(
                target="gain",
                params={"gain_db": round(-diff.rms_delta_db * 0.5, 1)},
                reason=f"Overall level: current is "
                       f"{diff.rms_delta_db:+.1f}dB vs reference",
                priority=min(1.0, abs(diff.rms_delta_db) / 10.0),
            ))

        # 3. Compression adjustment
        if abs(diff.dynamic_range_delta_db) > 3.0:
            if diff.dynamic_range_delta_db > 0:
                # Current has more dynamic range → compress more
                suggestions.append(AdjustmentSuggestion(
                    target="comp",
                    params={
                        "threshold": -18,
                        "ratio": min(6.0, 2.0 + abs(
                            diff.dynamic_range_delta_db) / 5.0),
                    },
                    reason=f"Dynamic range: current is "
                           f"{diff.dynamic_range_delta_db:+.1f}dB wider "
                           f"→ compress more",
                    priority=0.5,
                ))
            else:
                # Current has less dynamic range → reduce compression
                suggestions.append(AdjustmentSuggestion(
                    target="comp",
                    params={
                        "threshold": -24,
                        "ratio": max(1.5, 2.0 - abs(
                            diff.dynamic_range_delta_db) / 5.0),
                    },
                    reason=f"Dynamic range: current is "
                           f"{diff.dynamic_range_delta_db:+.1f}dB narrower "
                           f"→ compress less",
                    priority=0.5,
                ))

        # Sort by priority (highest first)
        suggestions.sort(key=lambda s: s.priority, reverse=True)
        return suggestions

    # ------------------------------------------------------------------
    # Internal methods
    # ------------------------------------------------------------------

    def _compute_spectral(self, audio: np.ndarray,
                          sr: int) -> SpectralFeatures:
        """Compute octave-band spectral features."""
        analyzer = Analyzer(sample_rate=sr)

        # Overall levels
        overall_rms = analyzer.compute_rms(audio)
        overall_peak = analyzer.compute_peak(audio)

        overall_rms_db = 20 * np.log10(overall_rms) if overall_rms > 0 else -120.0
        overall_peak_db = 20 * \
            np.log10(overall_peak) if overall_peak > 0 else -120.0

        # Per-band RMS via FFT
        n_fft = min(len(audio), sr * 4)  # 4 seconds max
        spectrum = np.fft.rfft(audio[:n_fft])
        freqs = np.fft.rfftfreq(n_fft, 1.0 / sr)
        magnitudes = np.abs(spectrum)

        band_rms_db: list[float] = []
        for i in range(len(_BAND_CENTERS)):
            lo = _BAND_EDGES[i]
            hi = _BAND_EDGES[i + 1]
            mask = (freqs >= lo) & (freqs < hi)
            if np.any(mask):
                band_mag = np.mean(magnitudes[mask] ** 2)
                band_db = 10 * np.log10(band_mag + 1e-20) - \
                    10 * np.log10(n_fft)
            else:
                band_db = -120.0
            band_rms_db.append(round(band_db, 2))

        return SpectralFeatures(
            band_rms_db=band_rms_db,
            overall_rms_db=round(overall_rms_db, 2),
            overall_peak_db=round(overall_peak_db, 2),
        )

    def _compute_dynamic(self, audio: np.ndarray,
                         sr: int) -> DynamicFeatures:
        """Compute dynamic range features."""
        analyzer = Analyzer(sample_rate=sr)

        rms = analyzer.compute_rms(audio)
        peak = analyzer.compute_peak(audio)

        rms_db = 20 * np.log10(rms) if rms > 0 else -120.0
        peak_db = 20 * np.log10(peak) if peak > 0 else -120.0

        dynamic_range = peak_db - rms_db
        crest_factor = peak_db - rms_db

        # Approximate LRA: RMS variation across 400ms windows
        win_samples = int(sr * 0.4)
        if len(audio) > win_samples:
            n_windows = len(audio) // win_samples
            window_rms = []
            for w in range(n_windows):
                seg = audio[w * win_samples:(w + 1) * win_samples]
                r = float(np.sqrt(np.mean(seg ** 2)))
                if r > 0:
                    window_rms.append(20 * np.log10(r))
            if len(window_rms) >= 2:
                lra = float(np.percentile(window_rms, 95) -
                            np.percentile(window_rms, 10))
            else:
                lra = 0.0
        else:
            lra = 0.0

        return DynamicFeatures(
            dynamic_range_db=round(dynamic_range, 2),
            crest_factor_db=round(crest_factor, 2),
            lra_db=round(lra, 2),
        )
