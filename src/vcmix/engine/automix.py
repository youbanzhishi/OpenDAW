"""
automix.py — Intelligent auto-mixing engine for VCMix.

Analyzes dry vocal audio and automatically generates:
    - Effect chain configuration
    - Per-effect parameter values
    - Complete VCMix YAML project configuration

Analysis pipeline:
    1. RMS/Peak → gain staging needs
    2. Spectrum → EQ frequency adjustment needs
    3. Sibilance ratio → DeEsser needs
    4. Dynamic range → compression needs
    5. Tail energy → reverb needs

Usage:
    from vcmix.engine.automix import AutoMixer
    mixer = AutoMixer()
    analysis = mixer.analyze_dry_vocal(audio, sr)
    chain = mixer.generate_chain(analysis)
    yaml_config = mixer.generate_yaml("vocal", "vocal.wav", analysis)

Dependencies: numpy, vcmix.engine.analyzer
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

from vcmix.engine.analyzer import Analyzer


# ── Analysis thresholds ────────────────────────────────────────────────────

_RMS_TARGET_DB = -18.0            # Target RMS for gain staging
_PEAK_HEADROOM_DB = -1.0         # Maximum allowed peak
_SIBILANCE_THRESHOLD = 0.12      # Above this → DeEsser needed
_DYNAMIC_RANGE_LOW = 6.0         # Below this → light compression
_DYNAMIC_RANGE_HIGH = 18.0       # Above this → heavy compression
_TAIL_ENERGY_THRESHOLD = 0.01    # Relative energy for reverb suggestion
_LOW_FREQ_BOOST_THRESHOLD = 0.3  # Band energy ratio for low-freq presence
_HIGH_FREQ_CUT_THRESHOLD = 0.25  # Band energy ratio for harsh high-freq


class AutoMixer:
    """
    Intelligent auto-mixing engine.

    Analyzes dry vocal characteristics and generates appropriate
    effect chains with tuned parameters.
    """

    def __init__(self, sample_rate: int = 44100, bpm: float = 120.0) -> None:
        self.sample_rate = sample_rate
        self.bpm = bpm
        self._analyzer = Analyzer(sample_rate=sample_rate)

    def analyze_dry_vocal(self, audio: np.ndarray, sr: int | None = None) -> dict[str, Any]:
        """
        Analyze dry vocal audio and return feature dict.

        Args:
            audio: Audio buffer (1D mono or 2D multi-channel).
            sr: Sample rate (defaults to self.sample_rate).

        Returns:
            Dict with analysis results:
                - rms_db, peak_db, true_peak_db: Level metrics
                - dynamic_range_db: Peak - RMS
                - gain_needed_db: Gain to hit target RMS
                - sibilance_ratio: Sibilance energy ratio
                - needs_deesser: Whether DeEsser is needed
                - spectrum: Frequency band energy distribution
                - eq_needs: Recommended EQ adjustments
                - compression_needs: Compression parameters
                - reverb_suggestion: Reverb type and amount
        """
        if sr is not None:
            self._analyzer = Analyzer(sample_rate=sr)
            self.sample_rate = sr

        # Flatten to mono for analysis
        if audio.ndim == 2:
            mono = audio[0] if audio.shape[0] <= audio.shape[1] else audio[:, 0]
        else:
            mono = audio

        # 1. Level analysis
        rms = self._analyzer.compute_rms(mono)
        peak = self._analyzer.compute_peak(mono)
        true_peak = self._analyzer.compute_true_peak(mono)

        rms_db = 20 * np.log10(rms) if rms > 1e-10 else -120.0
        peak_db = 20 * np.log10(peak) if peak > 1e-10 else -120.0
        true_peak_db = 20 * np.log10(true_peak) if true_peak > 1e-10 else -120.0

        # Gain needed to hit target RMS
        gain_needed_db = round(_RMS_TARGET_DB - rms_db, 2) if rms > 1e-10 else 0.0

        # 2. Dynamic range
        dynamic_range_db = round(peak_db - rms_db, 2) if rms > 1e-10 else 0.0

        # 3. Sibilance
        sibilance_ratio = self._analyzer.compute_sibilance(mono)
        needs_deesser = sibilance_ratio > _SIBILANCE_THRESHOLD

        # 4. Spectrum analysis
        spectrum = self._analyzer.compute_spectrum(mono)

        # 5. Tail energy (for reverb estimation)
        tail_energy = self._compute_tail_energy(mono)

        # 6. EQ needs based on spectrum
        eq_needs = self._analyze_eq_needs(spectrum)

        # 7. Compression needs based on dynamic range
        compression_needs = self._analyze_compression(dynamic_range_db, rms_db)

        # 8. Reverb suggestion based on tail energy
        reverb_suggestion = self._analyze_reverb(tail_energy, sibilance_ratio)

        return {
            "rms_db": round(float(rms_db), 2),
            "peak_db": round(float(peak_db), 2),
            "true_peak_db": round(float(true_peak_db), 2),
            "dynamic_range_db": round(float(dynamic_range_db), 2),
            "gain_needed_db": float(gain_needed_db),
            "sibilance_ratio": round(float(sibilance_ratio), 4),
            "needs_deesser": bool(needs_deesser),
            "spectrum": spectrum,
            "tail_energy": round(float(tail_energy), 4),
            "eq_needs": eq_needs,
            "compression_needs": compression_needs,
            "reverb_suggestion": reverb_suggestion,
        }

    def generate_chain(self, analysis: dict[str, Any]) -> list[dict[str, Any]]:
        """
        Generate effect chain based on analysis results.

        Args:
            analysis: Output from analyze_dry_vocal().

        Returns:
            List of effect config dicts with name + params.
        """
        chain: list[dict[str, Any]] = []

        # 1. Gain staging (always first)
        gain_db = analysis.get("gain_needed_db", 0.0)
        if abs(gain_db) > 0.5:
            chain.append({
                "name": "vc-gain",
                "params": {"gain": round(gain_db, 1)},
            })

        # 2. DeEsser (if sibilance detected)
        if analysis.get("needs_deesser", False):
            sib_ratio = analysis.get("sibilance_ratio", 0.0)
            # More sibilance → more aggressive threshold
            threshold = -40 if sib_ratio > 0.2 else -35
            reduction = -8 if sib_ratio > 0.2 else -6
            chain.append({
                "name": "vc-deesser",
                "params": {"threshold": threshold, "reduction": reduction},
            })

        # 3. EQ (based on spectral analysis)
        eq_needs = analysis.get("eq_needs", {})
        eq_params: dict[str, Any] = {}

        low_cut = eq_needs.get("low_cut_hz", 80)
        if low_cut > 0:
            eq_params["low_cut"] = low_cut

        high_shelf = eq_needs.get("high_shelf_hz", 0)
        high_shelf_gain = eq_needs.get("high_shelf_gain_db", 0)
        if high_shelf > 0:
            eq_params["high_shelf"] = high_shelf
            if high_shelf_gain != 0:
                eq_params["high_shelf_gain"] = high_shelf_gain

        peak_freq = eq_needs.get("peak_freq_hz", 0)
        peak_gain = eq_needs.get("peak_gain_db", 0)
        if peak_freq > 0 and peak_gain != 0:
            eq_params["peak_freq"] = peak_freq
            eq_params["peak_gain"] = round(peak_gain, 1)
            eq_params["peak_q"] = 1.5

        if eq_params:
            # Ensure minimal params for vc-eq
            if "low_cut" not in eq_params:
                eq_params["low_cut"] = 80
            if "high_shelf" not in eq_params:
                eq_params["high_shelf"] = 8000
            if "peak_freq" not in eq_params:
                eq_params["peak_freq"] = 2500
                eq_params["peak_gain"] = -2
                eq_params["peak_q"] = 1.5
            chain.append({"name": "vc-eq", "params": eq_params})

        # 4. Compressor (based on dynamic range)
        comp = analysis.get("compression_needs", {})
        if comp.get("needed", False):
            chain.append({
                "name": "vc-comp",
                "params": {
                    "threshold": comp.get("threshold_db", -24),
                    "ratio": comp.get("ratio", 3),
                    "attack": comp.get("attack_ms", 5),
                    "release": comp.get("release_ms", 50),
                },
            })

        # 5. Reverb (based on tail energy)
        reverb = analysis.get("reverb_suggestion", {})
        if reverb.get("needed", False):
            chain.append({
                "name": "vc-reverb",
                "params": {
                    "room": reverb.get("room", 35),
                    "decay": reverb.get("decay", 30),
                    "damping": reverb.get("damping", 50),
                    "mix": reverb.get("mix", 10),
                    "predelay": reverb.get("predelay", 40),
                    "wetlpf": reverb.get("wetlpf", 5000),
                },
            })

        # 6. Limiter (always at end for safety)
        chain.append({
            "name": "vc-limiter",
            "params": {"ceiling": -1},
        })

        return chain

    def generate_yaml(
        self,
        track_name: str,
        audio_path: str,
        analysis: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Generate a complete VCMix YAML project configuration.

        Args:
            track_name: Name for the track (e.g. "vocal").
            audio_path: Path to the dry vocal audio file.
            analysis: Output from analyze_dry_vocal().

        Returns:
            Dict representing a complete VCMix project YAML structure.
        """
        chain = self.generate_chain(analysis)

        # Determine vocal level based on RMS
        rms_db = analysis.get("rms_db", -18.0)
        gain_db = analysis.get("gain_needed_db", 0.0)
        # Target: vocal should be about -14 LUFS in the final mix
        # If gain is already compensated, use 1.0; otherwise calculate
        if abs(gain_db) < 0.5:
            vocal_level = 1.0
        else:
            # After gain staging, the track should be near target RMS
            vocal_level = 1.0

        config: dict[str, Any] = {
            "name": f"automix_{track_name}",
            "bpm": self.bpm,
            "sample_rate": self.sample_rate,
            "tracks": [
                {
                    "name": track_name,
                    "file": audio_path,
                    "effects": chain,
                }
            ],
            "master": {
                "levels": {track_name: vocal_level},
                "effects": [],
                "output": f"output_{track_name}.wav",
            },
        }

        return config

    # ── Private helpers ────────────────────────────────────────────────────

    def _compute_tail_energy(self, audio: np.ndarray) -> float:
        """Compute relative energy in the last 10% of the audio."""
        tail_start = int(len(audio) * 0.9)
        if tail_start >= len(audio):
            return 0.0

        total_energy = float(np.mean(audio.astype(np.float64) ** 2))
        if total_energy < 1e-10:
            return 0.0

        tail_energy = float(np.mean(audio[tail_start:].astype(np.float64) ** 2))
        return tail_energy / total_energy

    def _analyze_eq_needs(self, spectrum: dict[str, float]) -> dict[str, Any]:
        """
        Determine EQ needs from spectrum bands.

        Returns dict with:
            - low_cut_hz: High-pass filter cutoff
            - high_shelf_hz: High shelf frequency
            - high_shelf_gain_db: High shelf gain (positive = boost)
            - peak_freq_hz: Notch/bell frequency
            - peak_gain_db: Notch/bell gain (negative = cut)
        """
        total = sum(spectrum.values()) if spectrum else 1.0
        if total < 1e-10:
            total = 1.0

        sub_ratio = spectrum.get("sub", 0.0) / total
        low_ratio = spectrum.get("low", 0.0) / total
        mid_ratio = spectrum.get("mid", 0.0) / total
        high_mid_ratio = spectrum.get("high_mid", 0.0) / total
        high_ratio = spectrum.get("high", 0.0) / total
        air_ratio = spectrum.get("air", 0.0) / total

        eq_needs: dict[str, Any] = {
            "low_cut_hz": 80,
            "high_shelf_hz": 0,
            "high_shelf_gain_db": 0,
            "peak_freq_hz": 0,
            "peak_gain_db": 0,
        }

        # Low cut: reduce sub-bass rumble
        if sub_ratio > 0.05:
            eq_needs["low_cut_hz"] = 100
        elif sub_ratio > 0.02:
            eq_needs["low_cut_hz"] = 80
        else:
            eq_needs["low_cut_hz"] = 60

        # High shelf: boost air if needed, cut harshness
        if air_ratio < 0.02:
            eq_needs["high_shelf_hz"] = 10000
            eq_needs["high_shelf_gain_db"] = 2
        elif high_ratio > _HIGH_FREQ_CUT_THRESHOLD:
            eq_needs["high_shelf_hz"] = 6000
            eq_needs["high_shelf_gain_db"] = -2

        # Presence peak: cut if high-mid energy is dominant
        if high_mid_ratio > 0.3:
            eq_needs["peak_freq_hz"] = 3000
            eq_needs["peak_gain_db"] = -3
        elif high_mid_ratio > 0.2:
            eq_needs["peak_freq_hz"] = 2500
            eq_needs["peak_gain_db"] = -1.5
        elif mid_ratio > 0.5:
            # Boxy — cut around 400-600Hz
            eq_needs["peak_freq_hz"] = 500
            eq_needs["peak_gain_db"] = -2

        return eq_needs

    def _analyze_compression(self, dynamic_range_db: float, rms_db: float) -> dict[str, Any]:
        """
        Determine compression needs from dynamic range.

        Returns dict with:
            - needed: Whether compression is needed
            - threshold_db: Compressor threshold
            - ratio: Compression ratio
            - attack_ms: Attack time
            - release_ms: Release time
        """
        if dynamic_range_db < _DYNAMIC_RANGE_LOW:
            # Already very compressed — light touch
            return {
                "needed": True,
                "threshold_db": -24,
                "ratio": 2,
                "attack_ms": 10,
                "release_ms": 80,
            }
        elif dynamic_range_db < _DYNAMIC_RANGE_HIGH:
            # Moderate dynamics — standard compression
            # Lower RMS → lower threshold
            threshold = -24 if rms_db < -18 else -20
            return {
                "needed": True,
                "threshold_db": threshold,
                "ratio": 3,
                "attack_ms": 5,
                "release_ms": 50,
            }
        else:
            # High dynamics — stronger compression
            return {
                "needed": True,
                "threshold_db": -26,
                "ratio": 4,
                "attack_ms": 2,
                "release_ms": 30,
            }

    def _analyze_reverb(self, tail_energy: float, sibilance: float) -> dict[str, Any]:
        """
        Determine reverb needs from tail energy and sibilance.

        High tail energy → less reverb needed (room already has reflections).
        High sibilance → more damping needed.
        """
        if tail_energy > 0.1:
            # Already has significant room reverb — minimal addition
            return {
                "needed": True,
                "room": 20,
                "decay": 15,
                "damping": 70,
                "mix": 5,
                "predelay": 20,
                "wetlpf": 4000,
            }
        elif tail_energy > _TAIL_ENERGY_THRESHOLD:
            # Moderate tail — standard reverb
            damping = 60 if sibilance > _SIBILANCE_THRESHOLD else 50
            wetlpf = 4000 if sibilance > _SIBILANCE_THRESHOLD else 5500
            return {
                "needed": True,
                "room": 35,
                "decay": 30,
                "damping": damping,
                "mix": 10,
                "predelay": 40,
                "wetlpf": wetlpf,
            }
        else:
            # Very dry — generous reverb
            damping = 65 if sibilance > _SIBILANCE_THRESHOLD else 45
            wetlpf = 4500 if sibilance > _SIBILANCE_THRESHOLD else 6000
            return {
                "needed": True,
                "room": 50,
                "decay": 45,
                "damping": damping,
                "mix": 15,
                "predelay": 60,
                "wetlpf": wetlpf,
            }
