"""
automix.py — Intelligent auto-mixing engine for VCMix (Phase 6).

Phase 4: Dry-vocal analysis → effect chain generation.
Phase 6: DataStream closed-loop control for project-level auto-mixing.

Closed-loop pipeline:
    render → DataStream events → AutoMixer.analyze() → mixing state
           → AutoMixer.suggest() → adjustment suggestions
           → AutoMixer.apply() → new YAML config (original untouched)
           → re-render → new DataStream events → loop again

Phase 4 API (preserved):
    - AutoMixer.analyze_dry_vocal()  — Analyze dry vocal features
    - AutoMixer.generate_chain()     — Generate effect chain from analysis
    - AutoMixer.generate_yaml()      — Generate full VCMix YAML config

Phase 6 API (new):
    - AutoMixer.analyze()   — Extract mixing state from DataStream events
    - AutoMixer.suggest()   — Generate parameter adjustment suggestions
    - AutoMixer.apply()     — Apply suggestions to YAML config (new file)

Mixing rules (Phase 6):
    - Target RMS: -18 dBFS (vocal), -24 dBFS (accompaniment)
    - Spectral balance: avoid low-frequency buildup, clear mid-high
    - Dynamic range: 6-12 dB (vocal), 3-6 dB (master)
    - True peak: ≤ -1 dBFS
    - Sibilance: trigger DeEsser when threshold exceeded

Usage:
    # Phase 4 (dry vocal analysis)
    from vcmix.engine.automix import AutoMixer
    mixer = AutoMixer()
    analysis = mixer.analyze_dry_vocal(audio, sr)
    chain = mixer.generate_chain(analysis)

    # Phase 6 (DataStream closed-loop)
    from vcmix.engine.automix import AutoMixer
    from vcmix.stream.emitter import DataStream
    mixer = AutoMixer()
    state = mixer.analyze(stream_events)
    suggestions = mixer.suggest(state)
    new_config = mixer.apply(original_config, suggestions)

Dependencies: numpy, vcmix.engine.analyzer, vcmix.stream.emitter
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from vcmix.engine.analyzer import Analyzer
from vcmix.stream.emitter import StreamEvent

# ── Phase 4: Analysis thresholds (preserved) ────────────────────────────────

_RMS_TARGET_DB = -18.0            # Target RMS for gain staging
_PEAK_HEADROOM_DB = -1.0         # Maximum allowed peak
_SIBILANCE_THRESHOLD = 0.12      # Above this → DeEsser needed
_DYNAMIC_RANGE_LOW = 6.0         # Below this → light compression
_DYNAMIC_RANGE_HIGH = 18.0       # Above this → heavy compression
_TAIL_ENERGY_THRESHOLD = 0.01    # Relative energy for reverb suggestion
_LOW_FREQ_BOOST_THRESHOLD = 0.3  # Band energy ratio for low-freq presence
_HIGH_FREQ_CUT_THRESHOLD = 0.25  # Band energy ratio for harsh high-freq

# ── Phase 6: Closed-loop mixing thresholds ──────────────────────────────────

_VOCAL_RMS_TARGET_DB = -18.0     # Target RMS for vocal tracks
_ACCOMP_RMS_TARGET_DB = -24.0    # Target RMS for accompaniment tracks
_MASTER_RMS_TARGET_DB = -16.0    # Target RMS for master bus
_VOCAL_DR_MIN = 6.0              # Minimum vocal dynamic range (dB)
_VOCAL_DR_MAX = 12.0             # Maximum vocal dynamic range (dB)
_MASTER_DR_MIN = 3.0             # Minimum master dynamic range (dB)
_MASTER_DR_MAX = 6.0             # Maximum master dynamic range (dB)
_TRUE_PEAK_CEILING = -1.0        # Maximum true peak (dBFS)
_LOW_FREQ_BUILDUP_RATIO = 0.15   # Sub+Low band energy ratio threshold
_SIBILANCE_TRIGGER_DB = -20.0    # Sibilance trigger threshold (dB)

# ── Vocal-like track name heuristics ────────────────────────────────────────
_VOCAL_NAME_PATTERNS = ("vocal", "vox", "voice", "lead", "bgv", "choir", "chant")


# ── Phase 6 data structures ─────────────────────────────────────────────────

@dataclass
class TrackMixState:
    """
    Per-track mixing state extracted from DataStream events.

    Attributes:
        name: Track name.
        rms_db: Current RMS level in dBFS.
        peak_db: Current peak level in dBFS.
        true_peak_db: Current true peak level in dBFS.
        dynamic_range_db: Peak - RMS in dB.
        warnings: List of warning strings from DataStream.
        sibilance_exceeds: Whether sibilance exceeds threshold.
        is_vocal: Whether this track is detected as a vocal track.
    """

    name: str = ""
    rms_db: float = -120.0
    peak_db: float = -120.0
    true_peak_db: float = -120.0
    dynamic_range_db: float = 0.0
    warnings: list[str] = field(default_factory=list)
    sibilance_exceeds: bool = False
    is_vocal: bool = False


@dataclass
class MasterMixState:
    """
    Master bus mixing state extracted from DataStream events.

    Attributes:
        rms_db: Current master RMS level in dBFS.
        peak_db: Current master peak level in dBFS.
        true_peak_db: Current master true peak level in dBFS.
        dynamic_range_db: Peak - RMS in dB.
        warnings: List of warning strings from DataStream.
    """

    rms_db: float = -120.0
    peak_db: float = -120.0
    true_peak_db: float = -120.0
    dynamic_range_db: float = 0.0
    warnings: list[str] = field(default_factory=list)


@dataclass
class MixingState:
    """
    Complete mixing state extracted from DataStream event stream.

    Attributes:
        tracks: Per-track mixing states.
        master: Master bus mixing state.
        effect_deltas: Per-track effect delta summaries.
        has_clipping: Whether any clipping was detected.
        has_low_snr: Whether any low-SNR was detected.
        has_sibilance: Whether any sibilance was detected.
    """

    tracks: dict[str, TrackMixState] = field(default_factory=dict)
    master: MasterMixState = field(default_factory=MasterMixState)
    effect_deltas: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    has_clipping: bool = False
    has_low_snr: bool = False
    has_sibilance: bool = False


@dataclass
class AdjustmentSuggestion:
    """
    A single parameter adjustment suggestion.

    Attributes:
        target: Where to apply — "track:<name>", "track:<name>:effect:<idx>",
                "master", "master:effect:<idx>".
        action: Type of action — "gain", "eq", "compressor", "limiter",
                "deesser", "level".
        params: Parameters for the adjustment.
        reason: Human-readable reason for this suggestion.
        priority: Priority level (1=critical, 2=important, 3=suggested).
    """

    target: str = ""
    action: str = ""
    params: dict[str, Any] = field(default_factory=dict)
    reason: str = ""
    priority: int = 3


# ── AutoMixer class ─────────────────────────────────────────────────────────

class AutoMixer:
    """
    Intelligent auto-mixing engine.

    Phase 4: Analyzes dry vocal characteristics and generates appropriate
    effect chains with tuned parameters.

    Phase 6: Provides DataStream closed-loop control — analyzes streaming
    events from the rendering pipeline, generates adjustment suggestions,
    and applies them to produce new YAML configurations.
    """

    def __init__(self, sample_rate: int = 44100, bpm: float = 120.0) -> None:
        self.sample_rate = sample_rate
        self.bpm = bpm
        self._analyzer = Analyzer(sample_rate=sample_rate)

    # ── Phase 4 API (fully preserved) ──────────────────────────────────────

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

        analysis.get("rms_db", -18.0)
        gain_db = analysis.get("gain_needed_db", 0.0)
        if abs(gain_db) < 0.5:
            vocal_level = 1.0
        else:
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

    # ── Phase 6 API: DataStream closed-loop control ────────────────────────

    def analyze(self, events: list[StreamEvent]) -> MixingState:
        """
        Extract mixing state from DataStream events.

        Processes the stream of events emitted during rendering and
        consolidates them into a structured MixingState for the
        suggestion engine.

        Args:
            events: List of StreamEvent objects from DataStream.

        Returns:
            MixingState with per-track and master mixing state,
            warning flags, and effect delta summaries.
        """
        state = MixingState()

        for event in events:
            if event.event_type == "track_level":
                name = event.track
                is_vocal = self._is_vocal_track(name)
                ts = TrackMixState(
                    name=name,
                    rms_db=event.data.get("rms_db", -120.0),
                    peak_db=event.data.get("peak_db", -120.0),
                    true_peak_db=event.data.get("true_peak_db", -120.0),
                    dynamic_range_db=round(
                        event.data.get("peak_db", -120.0) - event.data.get("rms_db", -120.0), 2
                    ),
                    is_vocal=is_vocal,
                )
                # Update with latest reading (events may have multiple)
                state.tracks[name] = ts

            elif event.event_type == "master_level":
                state.master = MasterMixState(
                    rms_db=event.data.get("rms_db", -120.0),
                    peak_db=event.data.get("peak_db", -120.0),
                    true_peak_db=event.data.get("true_peak_db", -120.0),
                    dynamic_range_db=round(
                        event.data.get("peak_db", -120.0) - event.data.get("rms_db", -120.0), 2
                    ),
                )

            elif event.event_type == "effect_delta":
                track_name = event.track
                if track_name not in state.effect_deltas:
                    state.effect_deltas[track_name] = []
                state.effect_deltas[track_name].append({
                    "effect": event.data.get("effect", ""),
                    "before_rms_db": event.data.get("before_rms_db", -120.0),
                    "after_rms_db": event.data.get("after_rms_db", -120.0),
                    "before_peak_db": event.data.get("before_peak_db", -120.0),
                    "after_peak_db": event.data.get("after_peak_db", -120.0),
                    "delta_db": event.data.get("delta_db", 0.0),
                })

            elif event.event_type == "warning":
                track_name = event.track
                warning_type = event.data.get("warning_type", "")
                message = event.data.get("message", "")

                if track_name == "master":
                    state.master.warnings.append(message)
                elif track_name in state.tracks:
                    state.tracks[track_name].warnings.append(message)

                if warning_type == "clipping":
                    state.has_clipping = True
                elif warning_type == "low_snr":
                    state.has_low_snr = True
                elif warning_type == "sibilance":
                    state.has_sibilance = True
                    if track_name in state.tracks:
                        state.tracks[track_name].sibilance_exceeds = True

            elif event.event_type == "sibilance":
                track_name = event.track
                exceeds = event.data.get("exceeds", False)
                if exceeds:
                    state.has_sibilance = True
                    if track_name in state.tracks:
                        state.tracks[track_name].sibilance_exceeds = True

        return state

    def suggest(self, state: MixingState) -> list[AdjustmentSuggestion]:
        """
        Generate parameter adjustment suggestions based on mixing state.

        Applies the following rules:
            1. RMS targeting: vocal → -18 dBFS, accompaniment → -24 dBFS
            2. Spectral balance: avoid low-frequency buildup
            3. Dynamic range: vocal 6-12 dB, master 3-6 dB
            4. True peak: ≤ -1 dBFS
            5. Sibilance: trigger DeEsser when threshold exceeded

        Args:
            state: MixingState from analyze().

        Returns:
            List of AdjustmentSuggestion, sorted by priority (1=most critical).
        """
        suggestions: list[AdjustmentSuggestion] = []

        # ── Rule 1: Per-track RMS targeting ────────────────────────────────
        for name, ts in state.tracks.items():
            target_rms = _VOCAL_RMS_TARGET_DB if ts.is_vocal else _ACCOMP_RMS_TARGET_DB
            rms_delta = target_rms - ts.rms_db

            # Only suggest if more than 1 dB off target
            if abs(rms_delta) > 1.0:
                suggestions.append(AdjustmentSuggestion(
                    target=f"track:{name}",
                    action="gain",
                    params={"gain_db": round(rms_delta, 1)},
                    reason=(
                        f"Track '{name}' RMS {ts.rms_db:.1f} dBFS — "
                        f"target {target_rms:.0f} dBFS "
                        f"({'vocal' if ts.is_vocal else 'accomp'})"
                    ),
                    priority=1 if abs(rms_delta) > 6 else 2,
                ))

        # ── Rule 2: True peak ceiling ─────────────────────────────────────
        for name, ts in state.tracks.items():
            if ts.true_peak_db > _TRUE_PEAK_CEILING:
                excess = ts.true_peak_db - _TRUE_PEAK_CEILING
                suggestions.append(AdjustmentSuggestion(
                    target=f"track:{name}",
                    action="limiter",
                    params={"ceiling": _TRUE_PEAK_CEILING},
                    reason=(
                        f"Track '{name}' true peak {ts.true_peak_db:.1f} dBFS "
                        f"exceeds ceiling {_TRUE_PEAK_CEILING:.1f} dBFS "
                        f"(+{excess:.1f} dB)"
                    ),
                    priority=1,
                ))

        # ── Rule 3: Dynamic range control ─────────────────────────────────
        for name, ts in state.tracks.items():
            if ts.is_vocal:
                if ts.dynamic_range_db < _VOCAL_DR_MIN:
                    # Too compressed — suggest reducing compression
                    suggestions.append(AdjustmentSuggestion(
                        target=f"track:{name}",
                        action="compressor",
                        params={"action": "reduce", "ratio_adjust": -1},
                        reason=(
                            f"Vocal '{name}' dynamic range {ts.dynamic_range_db:.1f} dB "
                            f"below minimum {_VOCAL_DR_MIN:.0f} dB — over-compressed"
                        ),
                        priority=2,
                    ))
                elif ts.dynamic_range_db > _VOCAL_DR_MAX:
                    # Too dynamic — suggest compression
                    suggestions.append(AdjustmentSuggestion(
                        target=f"track:{name}",
                        action="compressor",
                        params={
                            "threshold_db": -20,
                            "ratio": 3,
                            "attack_ms": 5,
                            "release_ms": 50,
                        },
                        reason=(
                            f"Vocal '{name}' dynamic range {ts.dynamic_range_db:.1f} dB "
                            f"above maximum {_VOCAL_DR_MAX:.0f} dB — needs compression"
                        ),
                        priority=2,
                    ))

        # Master dynamic range
        if state.master.dynamic_range_db < _MASTER_DR_MIN:
            suggestions.append(AdjustmentSuggestion(
                target="master",
                action="compressor",
                params={"action": "reduce", "ratio_adjust": -1},
                reason=(
                    f"Master dynamic range {state.master.dynamic_range_db:.1f} dB "
                    f"below minimum {_MASTER_DR_MIN:.0f} dB — over-compressed"
                ),
                priority=2,
            ))
        elif state.master.dynamic_range_db > _MASTER_DR_MAX:
            suggestions.append(AdjustmentSuggestion(
                target="master",
                action="compressor",
                params={
                    "threshold_db": -14,
                    "ratio": 2,
                    "attack_ms": 10,
                    "release_ms": 100,
                },
                reason=(
                    f"Master dynamic range {state.master.dynamic_range_db:.1f} dB "
                    f"above maximum {_MASTER_DR_MAX:.0f} dB — needs compression"
                ),
                priority=2,
            ))

        # ── Rule 4: Master true peak ──────────────────────────────────────
        if state.master.true_peak_db > _TRUE_PEAK_CEILING:
            excess = state.master.true_peak_db - _TRUE_PEAK_CEILING
            suggestions.append(AdjustmentSuggestion(
                target="master",
                action="limiter",
                params={"ceiling": _TRUE_PEAK_CEILING},
                reason=(
                    f"Master true peak {state.master.true_peak_db:.1f} dBFS "
                    f"exceeds ceiling {_TRUE_PEAK_CEILING:.1f} dBFS"
                ),
                priority=1,
            ))

        # ── Rule 5: Sibilance → DeEsser ───────────────────────────────────
        for name, ts in state.tracks.items():
            if ts.sibilance_exceeds:
                suggestions.append(AdjustmentSuggestion(
                    target=f"track:{name}",
                    action="deesser",
                    params={"threshold": -35, "reduction": -6},
                    reason=(
                        f"Track '{name}' sibilance exceeds threshold — "
                        f"DeEsser recommended"
                    ),
                    priority=2,
                ))

        # ── Rule 6: Spectral balance (low-frequency buildup) ──────────────
        # Use effect deltas to detect excessive low-frequency gain
        for name, deltas in state.effect_deltas.items():
            for delta in deltas:
                effect_name = delta.get("effect", "")
                delta_db = delta.get("delta_db", 0.0)
                # If any effect adds more than 6 dB of gain, flag it
                if delta_db > 6.0:
                    suggestions.append(AdjustmentSuggestion(
                        target=f"track:{name}",
                        action="gain",
                        params={"gain_db": -round(delta_db - 3.0, 1)},
                        reason=(
                            f"Effect '{effect_name}' on '{name}' adds "
                            f"+{delta_db:.1f} dB — risk of clipping"
                        ),
                        priority=2,
                    ))

        # Sort by priority (1 = most critical)
        suggestions.sort(key=lambda s: s.priority)
        return suggestions

    def apply(
        self,
        config: dict[str, Any],
        suggestions: list[AdjustmentSuggestion],
    ) -> dict[str, Any]:
        """
        Apply adjustment suggestions to a YAML config, producing a new config.

        The original config is never modified — a deep copy is created first.

        Suggestion targets are mapped to config locations:
            - "track:<name>"          → track volume/effects
            - "track:<name>:effect:N" → specific effect params
            - "master"                → master effects/levels
            - "master:effect:N"       → specific master effect params

        Args:
            config: Original YAML config dict (ProjectConfig as dict).
            suggestions: List of AdjustmentSuggestion from suggest().

        Returns:
            New config dict with adjustments applied.
        """
        new_config = copy.deepcopy(config)
        tracks = new_config.get("tracks", [])
        master = new_config.get("master", {})

        for suggestion in suggestions:
            target = suggestion.target
            action = suggestion.action
            params = suggestion.params

            if target.startswith("track:"):
                parts = target.split(":")
                track_name = parts[1] if len(parts) > 1 else ""

                # Find the track in config
                track_cfg = None
                for t in tracks:
                    if t.get("name") == track_name:
                        track_cfg = t
                        break

                if track_cfg is None:
                    continue

                # Check for specific effect target
                effect_idx = None
                if len(parts) >= 4 and parts[2] == "effect":
                    try:
                        effect_idx = int(parts[3])
                    except ValueError:
                        pass

                if effect_idx is not None:
                    # Apply to specific effect
                    effects = track_cfg.get("effects", [])
                    if 0 <= effect_idx < len(effects):
                        self._apply_to_effect(effects[effect_idx], action, params)
                else:
                    # Apply to track level
                    self._apply_to_track(track_cfg, action, params, master)

            elif target == "master" or target.startswith("master:"):
                parts = target.split(":")
                effect_idx = None
                if len(parts) >= 3 and parts[1] == "effect":
                    try:
                        effect_idx = int(parts[2])
                    except ValueError:
                        pass

                if effect_idx is not None:
                    effects = master.get("effects", [])
                    if 0 <= effect_idx < len(effects):
                        self._apply_to_effect(effects[effect_idx], action, params)
                else:
                    self._apply_to_master(master, action, params)

        return new_config

    # ── Private helpers ────────────────────────────────────────────────────

    @staticmethod
    def _is_vocal_track(name: str) -> bool:
        """Heuristic: determine if a track name suggests a vocal track."""
        name_lower = name.lower()
        return any(pattern in name_lower for pattern in _VOCAL_NAME_PATTERNS)

    def _apply_to_track(
        self,
        track_cfg: dict[str, Any],
        action: str,
        params: dict[str, Any],
        master_cfg: dict[str, Any],
    ) -> None:
        """Apply an action to a track configuration (in-place on the copy)."""
        if action == "gain":
            gain_db = params.get("gain_db", 0.0)
            effects = track_cfg.get("effects", [])

            # Look for existing vc-gain effect
            gain_effect = None
            for eff in effects:
                if eff.get("name") == "vc-gain":
                    gain_effect = eff
                    break

            if gain_effect is not None:
                # Adjust existing gain
                old_gain = gain_effect.get("params", {}).get("gain", 0.0)
                gain_effect.setdefault("params", {})["gain"] = round(old_gain + gain_db, 1)
            else:
                # Insert gain at the beginning
                effects.insert(0, {
                    "name": "vc-gain",
                    "params": {"gain": round(gain_db, 1)},
                })
            track_cfg["effects"] = effects

        elif action == "limiter":
            effects = track_cfg.get("effects", [])
            # Check if limiter already exists
            has_limiter = any(eff.get("name") == "vc-limiter" for eff in effects)
            if not has_limiter:
                effects.append({
                    "name": "vc-limiter",
                    "params": {"ceiling": params.get("ceiling", -1)},
                })
            track_cfg["effects"] = effects

        elif action == "compressor":
            # Handle reduce compression
            if params.get("action") == "reduce":
                effects = track_cfg.get("effects", [])
                for eff in effects:
                    if eff.get("name") == "vc-comp":
                        ratio = eff.get("params", {}).get("ratio", 3)
                        eff.setdefault("params", {})["ratio"] = max(
                            1, ratio + params.get("ratio_adjust", -1)
                        )
            else:
                # Add compressor if not present
                effects = track_cfg.get("effects", [])
                has_comp = any(eff.get("name") == "vc-comp" for eff in effects)
                if not has_comp:
                    effects.append({
                        "name": "vc-comp",
                        "params": {
                            "threshold": params.get("threshold_db", -20),
                            "ratio": params.get("ratio", 3),
                            "attack": params.get("attack_ms", 5),
                            "release": params.get("release_ms", 50),
                        },
                    })
                track_cfg["effects"] = effects

        elif action == "deesser":
            effects = track_cfg.get("effects", [])
            has_deesser = any(eff.get("name") == "vc-deesser" for eff in effects)
            if not has_deesser:
                # Insert after gain, before other effects
                insert_idx = 0
                for i, eff in enumerate(effects):
                    if eff.get("name") == "vc-gain":
                        insert_idx = i + 1
                        break
                effects.insert(insert_idx, {
                    "name": "vc-deesser",
                    "params": {
                        "threshold": params.get("threshold", -35),
                        "reduction": params.get("reduction", -6),
                    },
                })
            track_cfg["effects"] = effects

        elif action == "level":
            # Adjust master level for this track
            track_name = track_cfg.get("name", "")
            levels = master_cfg.get("levels", {})
            current_level = levels.get(track_name, 1.0)
            level_delta = params.get("level_delta", 0.0)
            levels[track_name] = round(current_level * (10.0 ** (level_delta / 20.0)), 4)
            master_cfg["levels"] = levels

    @staticmethod
    def _apply_to_effect(
        effect_cfg: dict[str, Any],
        action: str,
        params: dict[str, Any],
    ) -> None:
        """Apply an action to a specific effect configuration (in-place on the copy)."""
        effect_params = effect_cfg.setdefault("params", {})

        if action == "gain":
            old_gain = effect_params.get("gain", 0.0)
            effect_params["gain"] = round(old_gain + params.get("gain_db", 0.0), 1)

        elif action == "compressor":
            if params.get("action") == "reduce":
                ratio = effect_params.get("ratio", 3)
                effect_params["ratio"] = max(1, ratio + params.get("ratio_adjust", -1))
            else:
                for key, val in params.items():
                    if key in ("threshold_db", "ratio", "attack_ms", "release_ms"):
                        effect_params[key] = val

        elif action == "eq":
            for key, val in params.items():
                effect_params[key] = val

    @staticmethod
    def _apply_to_master(
        master_cfg: dict[str, Any],
        action: str,
        params: dict[str, Any],
    ) -> None:
        """Apply an action to master configuration (in-place on the copy)."""
        effects = master_cfg.get("effects", [])

        if action == "limiter":
            has_limiter = any(eff.get("name") == "vc-limiter" for eff in effects)
            if has_limiter:
                for eff in effects:
                    if eff.get("name") == "vc-limiter":
                        eff.setdefault("params", {})["ceiling"] = params.get("ceiling", -1)
            else:
                effects.append({
                    "name": "vc-limiter",
                    "params": {"ceiling": params.get("ceiling", -1)},
                })
            master_cfg["effects"] = effects

        elif action == "compressor":
            if params.get("action") == "reduce":
                for eff in effects:
                    if eff.get("name") == "vc-comp":
                        ratio = eff.get("params", {}).get("ratio", 3)
                        eff.setdefault("params", {})["ratio"] = max(
                            1, ratio + params.get("ratio_adjust", -1)
                        )
            else:
                has_comp = any(eff.get("name") == "vc-comp" for eff in effects)
                if not has_comp:
                    effects.append({
                        "name": "vc-comp",
                        "params": {
                            "threshold": params.get("threshold_db", -14),
                            "ratio": params.get("ratio", 2),
                            "attack": params.get("attack_ms", 10),
                            "release": params.get("release_ms", 100),
                        },
                    })
                master_cfg["effects"] = effects

        elif action == "gain":
            has_limiter = any(eff.get("name") == "vc-limiter" for eff in effects)
            if not has_limiter:
                effects.append({
                    "name": "vc-limiter",
                    "params": {"ceiling": -1},
                })
            # Adjust all master levels proportionally
            gain_db = params.get("gain_db", 0.0)
            levels = master_cfg.get("levels", {})
            for name in levels:
                levels[name] = round(levels[name] * (10.0 ** (gain_db / 20.0)), 4)
            master_cfg["levels"] = levels

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
        spectrum.get("low", 0.0) / total
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

        if sub_ratio > 0.05:
            eq_needs["low_cut_hz"] = 100
        elif sub_ratio > 0.02:
            eq_needs["low_cut_hz"] = 80
        else:
            eq_needs["low_cut_hz"] = 60

        if air_ratio < 0.02:
            eq_needs["high_shelf_hz"] = 10000
            eq_needs["high_shelf_gain_db"] = 2
        elif high_ratio > _HIGH_FREQ_CUT_THRESHOLD:
            eq_needs["high_shelf_hz"] = 6000
            eq_needs["high_shelf_gain_db"] = -2

        if high_mid_ratio > 0.3:
            eq_needs["peak_freq_hz"] = 3000
            eq_needs["peak_gain_db"] = -3
        elif high_mid_ratio > 0.2:
            eq_needs["peak_freq_hz"] = 2500
            eq_needs["peak_gain_db"] = -1.5
        elif mid_ratio > 0.5:
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
            return {
                "needed": True,
                "threshold_db": -24,
                "ratio": 2,
                "attack_ms": 10,
                "release_ms": 80,
            }
        elif dynamic_range_db < _DYNAMIC_RANGE_HIGH:
            threshold = -24 if rms_db < -18 else -20
            return {
                "needed": True,
                "threshold_db": threshold,
                "ratio": 3,
                "attack_ms": 5,
                "release_ms": 50,
            }
        else:
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
