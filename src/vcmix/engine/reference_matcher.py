"""
reference_matcher.py — Reference track matching engine for VCMix (Phase 6).

Analyzes a reference audio track's spectral and dynamic characteristics,
then computes the difference between the current mix and the reference,
generating EQ, compression, and level adjustment suggestions.

Pipeline:
    1. analyze_reference()  — Extract spectral/dynamic features from reference
    2. compute_match()      — Compute difference between current mix and reference
    3. generate_adjustments() — Generate EQ/Comp/Level adjustment suggestions

Reference features extracted:
    - Per-band spectral energy (sub, low, mid, high_mid, high, air)
    - RMS and peak levels
    - Dynamic range
    - Spectral centroid
    - Loudness ratio between frequency bands

Usage:
    from vcmix.engine.reference_matcher import ReferenceMatcher
    matcher = ReferenceMatcher(sample_rate=44100)
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

# ── Data structures ─────────────────────────────────────────────────────────

@dataclass
class SpectralFeatures:
    """
    Spectral and dynamic features of an audio signal.

    Attributes:
        bands: Per-band energy (sub, low, mid, high_mid, high, air).
        rms_db: Overall RMS level in dBFS.
        peak_db: Overall peak level in dBFS.
        dynamic_range_db: Peak - RMS in dB.
        spectral_centroid_hz: Weighted average frequency.
        band_ratios: Normalized band energy ratios (each band / total).
    """

    bands: dict[str, float] = field(default_factory=dict)
    rms_db: float = -120.0
    peak_db: float = -120.0
    dynamic_range_db: float = 0.0
    spectral_centroid_hz: float = 0.0
    band_ratios: dict[str, float] = field(default_factory=dict)


@dataclass
class MatchDiff:
    """
    Difference between current mix and reference track.

    Attributes:
        rms_delta_db: RMS level difference (current - reference).
        peak_delta_db: Peak level difference.
        dr_delta_db: Dynamic range difference.
        band_deltas: Per-band energy ratio differences (current - reference).
        centroid_delta_hz: Spectral centroid frequency difference.
        needs_eq: Whether EQ adjustments are recommended.
        needs_comp: Whether compression adjustments are recommended.
        needs_level: Whether level adjustments are recommended.
        summary: Human-readable summary of the match quality.
    """

    rms_delta_db: float = 0.0
    peak_delta_db: float = 0.0
    dr_delta_db: float = 0.0
    band_deltas: dict[str, float] = field(default_factory=dict)
    centroid_delta_hz: float = 0.0
    needs_eq: bool = False
    needs_comp: bool = False
    needs_level: bool = False
    summary: str = ""


@dataclass
class ReferenceAdjustment:
    """
    A single adjustment suggestion derived from reference matching.

    Attributes:
        target: Where to apply — "track:<name>" or "master".
        category: "eq", "comp", or "level".
        params: Adjustment parameters.
        reason: Human-readable reason.
    """

    target: str = ""
    category: str = ""
    params: dict[str, Any] = field(default_factory=dict)
    reason: str = ""


# ── Thresholds ──────────────────────────────────────────────────────────────

_EQ_BAND_THRESHOLD = 0.05     # Band ratio delta above this -> EQ adjustment
_LEVEL_THRESHOLD_DB = 2.0     # Level delta above this -> level adjustment
_DR_THRESHOLD_DB = 3.0        # Dynamic range delta above this -> comp adjustment
_CENTROID_THRESHOLD_HZ = 500  # Centroid delta above this -> brightness adjustment


class ReferenceMatcher:
    """
    Reference track matching engine.

    Analyzes a reference audio track's spectral and dynamic profile,
    then computes differences and generates adjustment suggestions
    to make the current mix sound closer to the reference.

    Args:
        sample_rate: Audio sample rate for analysis.
    """

    def __init__(self, sample_rate: int = 44100) -> None:
        self.sample_rate = sample_rate
        self._analyzer = Analyzer(sample_rate=sample_rate)

    def analyze_reference(self, audio: np.ndarray, sr: int | None = None) -> SpectralFeatures:
        """
        Analyze a reference audio track and extract spectral/dynamic features.

        Args:
            audio: Audio buffer (1D mono or 2D multi-channel).
            sr: Sample rate (defaults to self.sample_rate).

        Returns:
            SpectralFeatures with per-band energy, levels, and ratios.
        """
        if sr is not None:
            self._analyzer = Analyzer(sample_rate=sr)
            self.sample_rate = sr

        # Flatten to mono
        if audio.ndim == 2:
            mono = audio[0] if audio.shape[0] <= audio.shape[1] else audio[:, 0]
        else:
            mono = audio

        # Compute spectral bands
        bands = self._analyzer.compute_spectrum(mono)

        # Compute levels
        rms = self._analyzer.compute_rms(mono)
        peak = self._analyzer.compute_peak(mono)
        rms_db = 20.0 * np.log10(rms) if rms > 1e-10 else -120.0
        peak_db = 20.0 * np.log10(peak) if peak > 1e-10 else -120.0
        dynamic_range_db = round(peak_db - rms_db, 2) if rms > 1e-10 else 0.0

        # Compute band ratios
        total_energy = sum(bands.values()) if bands else 0.0
        if total_energy < 1e-10:
            total_energy = 1.0
        band_ratios = {name: energy / total_energy for name, energy in bands.items()}

        # Compute spectral centroid
        spectral_centroid_hz = self._compute_spectral_centroid(mono)

        return SpectralFeatures(
            bands=bands,
            rms_db=round(float(rms_db), 2),
            peak_db=round(float(peak_db), 2),
            dynamic_range_db=round(float(dynamic_range_db), 2),
            spectral_centroid_hz=round(float(spectral_centroid_hz), 1),
            band_ratios=band_ratios,
        )

    def compute_match(
        self,
        current: SpectralFeatures,
        reference: SpectralFeatures,
    ) -> MatchDiff:
        """
        Compute the difference between current mix and reference.

        Compares spectral band ratios, levels, and dynamic range
        to determine what adjustments are needed.

        Args:
            current: SpectralFeatures of the current mix.
            reference: SpectralFeatures of the reference track.

        Returns:
            MatchDiff with deltas and flags for needed adjustment types.
        """
        # Level deltas
        rms_delta = current.rms_db - reference.rms_db
        peak_delta = current.peak_db - reference.peak_db
        dr_delta = current.dynamic_range_db - reference.dynamic_range_db

        # Band ratio deltas
        all_bands = set(list(current.band_ratios.keys()) + list(reference.band_ratios.keys()))
        band_deltas: dict[str, float] = {}
        for band in all_bands:
            cur_ratio = current.band_ratios.get(band, 0.0)
            ref_ratio = reference.band_ratios.get(band, 0.0)
            band_deltas[band] = round(cur_ratio - ref_ratio, 4)

        # Centroid delta
        centroid_delta = current.spectral_centroid_hz - reference.spectral_centroid_hz

        # Determine needs
        needs_eq = any(abs(delta) > _EQ_BAND_THRESHOLD for delta in band_deltas.values())
        needs_level = abs(rms_delta) > _LEVEL_THRESHOLD_DB
        needs_comp = abs(dr_delta) > _DR_THRESHOLD_DB

        # Generate summary
        summary_parts: list[str] = []
        if needs_level:
            direction = "louder" if rms_delta < 0 else "quieter"
            summary_parts.append(
                f"Level: mix is {abs(rms_delta):.1f} dB {direction} than reference"
            )
        if needs_eq:
            problem_bands = [b for b, d in band_deltas.items() if abs(d) > _EQ_BAND_THRESHOLD]
            summary_parts.append(
                f"EQ: spectral mismatch in {', '.join(problem_bands)}"
            )
        if needs_comp:
            direction = "more" if dr_delta > 0 else "less"
            summary_parts.append(
                f"Dynamics: mix needs {direction} compression (delta {dr_delta:.1f} dB)"
            )
        if not summary_parts:
            summary_parts.append("Mix closely matches reference")

        summary = "; ".join(summary_parts)

        return MatchDiff(
            rms_delta_db=round(rms_delta, 2),
            peak_delta_db=round(peak_delta, 2),
            dr_delta_db=round(dr_delta, 2),
            band_deltas=band_deltas,
            centroid_delta_hz=round(centroid_delta, 1),
            needs_eq=needs_eq,
            needs_comp=needs_comp,
            needs_level=needs_level,
            summary=summary,
        )

    def generate_adjustments(
        self,
        diff: MatchDiff,
        target: str = "master",
    ) -> list[ReferenceAdjustment]:
        """
        Generate EQ, compression, and level adjustments from match difference.

        Transforms spectral/dynamic deltas into concrete parameter
        adjustments for the VCMix effect chain.

        Args:
            diff: MatchDiff from compute_match().
            target: Where to apply adjustments (default: "master").

        Returns:
            List of ReferenceAdjustment suggestions.
        """
        adjustments: list[ReferenceAdjustment] = []

        # ── Level adjustment ───────────────────────────────────────────────
        if diff.needs_level and abs(diff.rms_delta_db) > _LEVEL_THRESHOLD_DB:
            gain_db = -diff.rms_delta_db  # Negative delta -> positive gain
            adjustments.append(ReferenceAdjustment(
                target=target,
                category="level",
                params={"gain_db": round(gain_db, 1)},
                reason=(
                    f"Mix RMS is {diff.rms_delta_db:+.1f} dB vs reference - "
                    f"adjusting by {gain_db:+.1f} dB"
                ),
            ))

        # ── EQ adjustments ─────────────────────────────────────────────────
        if diff.needs_eq:
            eq_params: dict[str, Any] = {}

            # Low-frequency buildup
            low_delta = diff.band_deltas.get("low", 0.0) + diff.band_deltas.get("sub", 0.0)
            if low_delta > _EQ_BAND_THRESHOLD:
                eq_params["low_cut"] = 100
                eq_params["low_cut_reason"] = "reduce low-frequency buildup"
            elif low_delta < -_EQ_BAND_THRESHOLD:
                eq_params["low_cut"] = 40
                eq_params["low_cut_reason"] = "add low-frequency weight"

            # Mid-range
            mid_delta = diff.band_deltas.get("mid", 0.0)
            if mid_delta > _EQ_BAND_THRESHOLD:
                eq_params["peak_freq"] = 500
                eq_params["peak_gain"] = -round(mid_delta * 20, 1)
                eq_params["peak_q"] = 1.2
            elif mid_delta < -_EQ_BAND_THRESHOLD:
                eq_params["peak_freq"] = 500
                eq_params["peak_gain"] = round(abs(mid_delta) * 15, 1)
                eq_params["peak_q"] = 1.2

            # High-mid / presence
            hm_delta = diff.band_deltas.get("high_mid", 0.0)
            if hm_delta > _EQ_BAND_THRESHOLD:
                eq_params["presence_freq"] = 3000
                eq_params["presence_gain"] = -round(hm_delta * 15, 1)
            elif hm_delta < -_EQ_BAND_THRESHOLD:
                eq_params["presence_freq"] = 3000
                eq_params["presence_gain"] = round(abs(hm_delta) * 12, 1)

            # High / air
            high_delta = diff.band_deltas.get("high", 0.0) + diff.band_deltas.get("air", 0.0)
            if high_delta > _EQ_BAND_THRESHOLD:
                eq_params["high_shelf"] = 8000
                eq_params["high_shelf_gain"] = -2
            elif high_delta < -_EQ_BAND_THRESHOLD:
                eq_params["high_shelf"] = 10000
                eq_params["high_shelf_gain"] = 2

            # Centroid-based brightness adjustment
            if abs(diff.centroid_delta_hz) > _CENTROID_THRESHOLD_HZ:
                if diff.centroid_delta_hz < -_CENTROID_THRESHOLD_HZ:
                    eq_params.setdefault("high_shelf", 10000)
                    eq_params.setdefault("high_shelf_gain", 2)
                    eq_params["brightness_note"] = (
                        f"Centroid {diff.centroid_delta_hz:+.0f} Hz - mix is darker"
                    )
                else:
                    eq_params.setdefault("high_shelf", 6000)
                    eq_params.setdefault("high_shelf_gain", -1.5)
                    eq_params["brightness_note"] = (
                        f"Centroid {diff.centroid_delta_hz:+.0f} Hz - mix is brighter"
                    )

            if eq_params:
                adjustments.append(ReferenceAdjustment(
                    target=target,
                    category="eq",
                    params=eq_params,
                    reason=f"Spectral balance adjustment - {diff.summary}",
                ))

        # ── Compression adjustment ─────────────────────────────────────────
        if diff.needs_comp:
            if diff.dr_delta_db > _DR_THRESHOLD_DB:
                comp_params = {
                    "threshold_db": -18,
                    "ratio": 2,
                    "attack_ms": 10,
                    "release_ms": 80,
                }
                reason = (
                    f"Mix dynamic range is {diff.dr_delta_db:+.1f} dB wider than "
                    f"reference - adding compression"
                )
            else:
                comp_params = {
                    "action": "reduce",
                    "ratio_adjust": -1,
                }
                reason = (
                    f"Mix dynamic range is {diff.dr_delta_db:+.1f} dB narrower than "
                    f"reference - reducing compression"
                )

            adjustments.append(ReferenceAdjustment(
                target=target,
                category="comp",
                params=comp_params,
                reason=reason,
            ))

        return adjustments

    # ── Private helpers ────────────────────────────────────────────────────

    def _compute_spectral_centroid(self, audio: np.ndarray) -> float:
        """
        Compute spectral centroid (weighted mean frequency) of audio.

        The spectral centroid indicates the "brightness" of a signal.
        Higher centroid = brighter signal.

        Args:
            audio: Mono audio buffer.

        Returns:
            Spectral centroid in Hz.
        """
        if audio.ndim == 2:
            audio = audio[0] if audio.shape[0] <= audio.shape[1] else audio[:, 0]

        n_fft = min(4096, len(audio))
        if n_fft < 2:
            return 0.0

        windowed = audio[:n_fft].astype(np.float64) * np.hanning(n_fft)
        fft_data = np.fft.rfft(windowed, n=n_fft)
        magnitudes = np.abs(fft_data)
        freqs = np.fft.rfftfreq(n_fft, 1.0 / self.sample_rate)

        total_mag = np.sum(magnitudes)
        if total_mag < 1e-10:
            return 0.0

        centroid = float(np.sum(freqs * magnitudes) / total_mag)
        return centroid
