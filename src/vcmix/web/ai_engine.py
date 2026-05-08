"""
ai_engine.py — AI mixing decision engine for VCMix Agent API (Phase 11).

Provides AI-driven mixing suggestions based on audio analysis data.
Implements a closed-loop pipeline:

    analyze → diagnose → suggest → apply → verify

Two modes:
    - One-shot ("one_click"): Auto-apply all suggestions
    - Step-by-step ("step"): Return suggestions for human review

Decision logs record every reasoning step for transparency.

Usage:
    from vcmix.web.ai_engine import AIEngine
    engine = AIEngine()
    result = engine.mix(analysis_data, mode="step")
    result = engine.master(analysis_data, mode="one_click")
"""

from __future__ import annotations

import copy
import time
from dataclasses import dataclass, field
from typing import Any

from vcmix.audio.meter import Meter
from vcmix.engine.analyzer import Analyzer
from vcmix.engine.automix import AutoMixer

# ── Target thresholds ────────────────────────────────────────────────────────

_MASTER_TARGET_LUFS = -14.0
_MASTER_PEAK_CEILING = -1.0
_VOCAL_TARGET_RMS_DB = -18.0
_ACCOMP_TARGET_RMS_DB = -24.0
_SIBILANCE_THRESHOLD = 0.12
_DYNAMIC_RANGE_MIN = 3.0
_DYNAMIC_RANGE_MAX = 18.0
_LOW_FREQ_BUILDUP = 0.15


@dataclass
class DecisionLog:
    """A single AI decision step with reasoning."""

    step: str
    target: str
    action: str
    params: dict[str, Any]
    reason: str
    confidence: float = 1.0
    timestamp: float = field(default_factory=time.time)


@dataclass
class MixResult:
    """Result of an AI mixing decision."""

    mode: str
    suggestions: list[dict[str, Any]]
    decision_log: list[dict[str, Any]]
    summary: str
    applied: bool = False
    updated_config: dict[str, Any | None] = None


class AIEngine:
    """
    AI mixing decision engine.

    Analyzes audio data and generates mixing/mastering suggestions
    with full decision logging for transparency.
    """

    def __init__(self, sample_rate: int = 44100) -> None:
        self._sr = sample_rate
        self._analyzer = Analyzer(sample_rate=sample_rate)
        self._meter = Meter(sample_rate=sample_rate)
        self._automixer = AutoMixer(sample_rate=sample_rate)

    # ── AI Mix ─────────────────────────────────────────────────────────────

    def mix(
        self,
        analysis: dict[str, Any],
        mode: str = "step",
        config: dict[str, Any | None] = None,
    ) -> MixResult:
        """
        Generate AI mixing suggestions based on analysis data.

        Args:
            analysis: Project analysis data from AnalysisService.
            mode: "step" (suggestions only) or "one_click" (auto-apply).
            config: Original YAML config dict (required for one_click mode).

        Returns:
            MixResult with suggestions and decision log.
        """
        log: list[DecisionLog] = []
        suggestions: list[dict[str, Any]] = []

        tracks = analysis.get("tracks", [])
        master = analysis.get("master", {})

        # ── Step 1: Analyze ────────────────────────────────────────────────
        log.append(DecisionLog(
            step="analyze", target="project", action="scan",
            params={"track_count": len(tracks)},
            reason=f"Scanning {len(tracks)} tracks for mixing issues",
        ))

        # ── Step 2: Diagnose per-track ─────────────────────────────────────
        for track in tracks:
            track_name = track.get("name", "unknown")
            track_suggestions = self._diagnose_track(track_name, track, log)
            suggestions.extend(track_suggestions)

        # ── Step 3: Diagnose master ────────────────────────────────────────
        master_suggestions = self._diagnose_master(master, log)
        suggestions.extend(master_suggestions)

        # ── Step 4: Prioritize ─────────────────────────────────────────────
        suggestions.sort(key=lambda s: s.get("priority", 3))
        log.append(DecisionLog(
            step="prioritize", target="project", action="sort",
            params={"total_suggestions": len(suggestions)},
            reason=f"Prioritized {len(suggestions)} suggestions by severity",
        ))

        # ── Step 5: Apply or return ────────────────────────────────────────
        applied = False
        updated_config = None
        if mode == "one_click" and config is not None:
            updated_config = self._apply_suggestions(config, suggestions, log)
            applied = True
            log.append(DecisionLog(
                step="apply", target="project", action="one_click",
                params={"applied_count": len(suggestions)},
                reason="Applied all suggestions in one-click mode",
            ))

        # Build summary
        critical = sum(1 for s in suggestions if s.get("priority") == 1)
        important = sum(1 for s in suggestions if s.get("priority") == 2)
        suggested = sum(1 for s in suggestions if s.get("priority") == 3)
        summary = (
            f"Found {len(suggestions)} suggestions: "
            f"{critical} critical, {important} important, {suggested} suggested"
        )

        return MixResult(
            mode=mode,
            suggestions=suggestions,
            decision_log=[self._log_to_dict(d) for d in log],
            summary=summary,
            applied=applied,
            updated_config=updated_config,
        )

    # ── AI Master ──────────────────────────────────────────────────────────

    def master(
        self,
        analysis: dict[str, Any],
        mode: str = "step",
        config: dict[str, Any | None] = None,
    ) -> MixResult:
        """
        Generate AI mastering suggestions.

        Focuses on the master bus: loudness normalization, true peak
        limiting, and final spectral balance.

        Args:
            analysis: Project analysis data.
            mode: "step" or "one_click".
            config: Original YAML config dict.

        Returns:
            MixResult with mastering suggestions.
        """
        log: list[DecisionLog] = []
        suggestions: list[dict[str, Any]] = []

        master = analysis.get("master", {})

        # ── Step 1: Analyze master bus ─────────────────────────────────────
        log.append(DecisionLog(
            step="analyze", target="master", action="scan",
            params={"status": master.get("status", "unknown")},
            reason="Analyzing master bus for mastering decisions",
        ))

        # ── Step 2: Loudness ───────────────────────────────────────────────
        lufs = master.get("lufs", -120.0)
        if lufs > -120.0:  # Valid measurement
            lufs_delta = round(_MASTER_TARGET_LUFS - lufs, 1)
            if abs(lufs_delta) > 1.0:
                suggestions.append({
                    "target": "master",
                    "action": "loudness_normalize",
                    "params": {"lufs_delta_db": lufs_delta, "target_lufs": _MASTER_TARGET_LUFS},
                    "reason": f"Master LUFS={lufs}, target={_MASTER_TARGET_LUFS}, delta={lufs_delta}dB",
                    "priority": 1,
                })
                log.append(DecisionLog(
                    step="diagnose", target="master", action="loudness",
                    params={"current_lufs": lufs, "target_lufs": _MASTER_TARGET_LUFS},
                    reason=f"Loudness normalization needed: {lufs_delta}dB adjustment",
                ))

        # ── Step 3: True peak ──────────────────────────────────────────────
        true_peak_db = master.get("true_peak_db", -120.0)
        if true_peak_db > -120.0 and true_peak_db > _MASTER_PEAK_CEILING:
            suggestions.append({
                "target": "master",
                "action": "limiter",
                "params": {"ceiling": _MASTER_PEAK_CEILING, "true_peak_db": true_peak_db},
                "reason": f"True peak ({true_peak_db}dB) exceeds ceiling ({_MASTER_PEAK_CEILING}dB)",
                "priority": 1,
            })
            log.append(DecisionLog(
                step="diagnose", target="master", action="true_peak",
                params={"true_peak_db": true_peak_db},
                reason=f"True peak limiting needed: current={true_peak_db}dB",
            ))

        # ── Step 4: Dynamic range ──────────────────────────────────────────
        dr = master.get("dynamic_range_db", 0.0)
        if dr > 0:
            if dr < _DYNAMIC_RANGE_MIN:
                suggestions.append({
                    "target": "master",
                    "action": "reduce_compression",
                    "params": {"dynamic_range_db": dr, "target_min": _DYNAMIC_RANGE_MIN},
                    "reason": f"Master dynamic range ({dr}dB) too low — over-compressed",
                    "priority": 2,
                })
            elif dr > _DYNAMIC_RANGE_MAX:
                suggestions.append({
                    "target": "master",
                    "action": "compressor",
                    "params": {
                        "threshold_db": -14,
                        "ratio": 2,
                        "attack_ms": 10,
                        "release_ms": 100,
                    },
                    "reason": f"Master dynamic range ({dr}dB) too high — needs compression",
                    "priority": 2,
                })

        # ── Step 5: Spectral balance ───────────────────────────────────────
        spectrum = master.get("spectrum", {})
        if spectrum:
            total = sum(spectrum.values()) if spectrum else 1.0
            if total > 0:
                low_energy = (spectrum.get("sub", 0) + spectrum.get("low", 0)) / total
                if low_energy > _LOW_FREQ_BUILDUP:
                    suggestions.append({
                        "target": "master",
                        "action": "eq",
                        "params": {"low_cut_hz": 40, "low_shelf_db": -2},
                        "reason": f"Low frequency buildup detected ({low_energy:.1%} of total energy)",
                        "priority": 2,
                    })
                    log.append(DecisionLog(
                        step="diagnose", target="master", action="spectral",
                        params={"low_energy_ratio": round(low_energy, 3)},
                        reason="Low frequency buildup needs EQ correction",
                    ))

        # ── Step 6: Ensure limiter ─────────────────────────────────────────
        has_limiter_suggestion = any(
            s["action"] == "limiter" for s in suggestions
        )
        if not has_limiter_suggestion:
            suggestions.append({
                "target": "master",
                "action": "limiter",
                "params": {"ceiling": -1.0},
                "reason": "Master bus should have a limiter for safety",
                "priority": 3,
            })

        # ── Apply if one_click ─────────────────────────────────────────────
        applied = False
        updated_config = None
        if mode == "one_click" and config is not None:
            updated_config = self._apply_suggestions(config, suggestions, log)
            applied = True
            log.append(DecisionLog(
                step="apply", target="master", action="one_click",
                params={"applied_count": len(suggestions)},
                reason="Applied all mastering suggestions in one-click mode",
            ))

        summary = (
            f"Mastering analysis: {len(suggestions)} suggestions "
            f"for loudness={lufs} LUFS, peak={true_peak_db}dB"
        )

        return MixResult(
            mode=mode,
            suggestions=suggestions,
            decision_log=[self._log_to_dict(d) for d in log],
            summary=summary,
            applied=applied,
            updated_config=updated_config,
        )

    # ── Per-track diagnosis ────────────────────────────────────────────────

    def _diagnose_track(
        self, name: str, track: dict[str, Any], log: list[DecisionLog]
    ) -> list[dict[str, Any]]:
        """Diagnose issues for a single track."""
        suggestions: list[dict[str, Any]] = []
        rms_db = track.get("rms_db", -120.0)
        track.get("peak_db", -120.0)
        true_peak_db = track.get("true_peak_db", -120.0)
        dr = track.get("dynamic_range_db", 0.0)
        sibilance = track.get("sibilance_ratio", 0.0)
        spectrum = track.get("spectrum", {})
        is_vocal = any(
            p in name.lower() for p in ("vocal", "vox", "voice", "lead", "bgv")
        )
        target_rms = _VOCAL_TARGET_RMS_DB if is_vocal else _ACCOMP_TARGET_RMS_DB

        # Gain staging
        if rms_db > -120.0:
            gain_needed = round(target_rms - rms_db, 1)
            if abs(gain_needed) > 2.0:
                suggestions.append({
                    "target": f"track:{name}",
                    "action": "gain",
                    "params": {"gain_db": gain_needed},
                    "reason": f"Track RMS={rms_db}dB, target={target_rms}dB, needs {gain_needed:+.1f}dB",
                    "priority": 1 if abs(gain_needed) > 6 else 2,
                })
                log.append(DecisionLog(
                    step="diagnose", target=f"track:{name}", action="gain",
                    params={"rms_db": rms_db, "target_rms_db": target_rms, "gain_db": gain_needed},
                    reason=f"Gain staging needed: {gain_needed:+.1f}dB",
                ))

        # True peak
        if true_peak_db > -120.0 and true_peak_db > _MASTER_PEAK_CEILING:
            suggestions.append({
                "target": f"track:{name}",
                "action": "limiter",
                "params": {"ceiling": _MASTER_PEAK_CEILING},
                "reason": f"Track true peak ({true_peak_db}dB) exceeds ceiling",
                "priority": 1,
            })

        # Sibilance
        if sibilance > _SIBILANCE_THRESHOLD:
            suggestions.append({
                "target": f"track:{name}",
                "action": "deesser",
                "params": {"threshold": -35, "reduction": -6},
                "reason": f"Sibilance ratio ({sibilance:.2f}) exceeds threshold ({_SIBILANCE_THRESHOLD})",
                "priority": 2,
            })
            log.append(DecisionLog(
                step="diagnose", target=f"track:{name}", action="deesser",
                params={"sibilance_ratio": sibilance},
                reason="De-essing recommended",
            ))

        # Dynamic range
        if dr > 0:
            if dr > _DYNAMIC_RANGE_MAX and is_vocal:
                suggestions.append({
                    "target": f"track:{name}",
                    "action": "compressor",
                    "params": {"threshold_db": -20, "ratio": 3, "attack_ms": 5, "release_ms": 50},
                    "reason": f"Vocal dynamic range ({dr}dB) too high — needs compression",
                    "priority": 2,
                })
            elif dr < _DYNAMIC_RANGE_MIN:
                suggestions.append({
                    "target": f"track:{name}",
                    "action": "reduce_compression",
                    "params": {"dynamic_range_db": dr},
                    "reason": f"Track dynamic range ({dr}dB) too low — over-compressed",
                    "priority": 2,
                })

        # Low frequency buildup
        if spectrum:
            total = sum(spectrum.values()) if spectrum else 1.0
            if total > 0:
                low_ratio = (spectrum.get("sub", 0) + spectrum.get("low", 0)) / total
                if low_ratio > _LOW_FREQ_BUILDUP:
                    suggestions.append({
                        "target": f"track:{name}",
                        "action": "eq",
                        "params": {"low_cut_hz": 80},
                        "reason": f"Low frequency buildup ({low_ratio:.1%}) — needs HPF",
                        "priority": 3,
                    })

        return suggestions

    # ── Master diagnosis ───────────────────────────────────────────────────

    def _diagnose_master(
        self, master: dict[str, Any], log: list[DecisionLog]
    ) -> list[dict[str, Any]]:
        """Diagnose master bus issues."""
        # Master diagnosis is handled in the master() method
        # This is for the mix() method's master analysis
        suggestions: list[dict[str, Any]] = []
        lufs = master.get("lufs", -120.0)
        true_peak_db = master.get("true_peak_db", -120.0)

        if lufs > -120.0:
            lufs_delta = round(_MASTER_TARGET_LUFS - lufs, 1)
            if abs(lufs_delta) > 2.0:
                suggestions.append({
                    "target": "master",
                    "action": "gain",
                    "params": {"gain_db": lufs_delta},
                    "reason": f"Master LUFS={lufs}, needs {lufs_delta:+.1f}dB to reach target",
                    "priority": 1 if abs(lufs_delta) > 6 else 2,
                })

        if true_peak_db > _MASTER_PEAK_CEILING and true_peak_db > -120.0:
            suggestions.append({
                "target": "master",
                "action": "limiter",
                "params": {"ceiling": _MASTER_PEAK_CEILING},
                "reason": f"Master peak ({true_peak_db}dB) exceeds ceiling",
                "priority": 1,
            })

        return suggestions

    # ── Apply suggestions ──────────────────────────────────────────────────

    def _apply_suggestions(
        self,
        config: dict[str, Any],
        suggestions: list[dict[str, Any]],
        log: list[DecisionLog],
    ) -> dict[str, Any]:
        """Apply suggestions to config dict, returning a new copy."""
        new_config = copy.deepcopy(config)

        for s in suggestions:
            target = s["target"]
            action = s["action"]
            params = s.get("params", {})

            if target == "master":
                self._apply_to_master(new_config, action, params)
            elif target.startswith("track:"):
                track_name = target.split(":", 1)[1]
                self._apply_to_track(new_config, track_name, action, params)

            log.append(DecisionLog(
                step="apply", target=target, action=action,
                params=params,
                reason=f"Applied {action} to {target}",
                confidence=0.9,
            ))

        return new_config

    @staticmethod
    def _apply_to_master(
        config: dict[str, Any], action: str, params: dict[str, Any]
    ) -> None:
        """Apply an action to the master config (in-place)."""
        master = config.setdefault("master", {})
        effects = master.setdefault("effects", [])

        if action == "limiter":
            # Check if limiter exists
            for eff in effects:
                if eff.get("name") == "vc-limiter":
                    eff.setdefault("params", {})["ceiling"] = params.get("ceiling", -1)
                    return
            effects.append({"name": "vc-limiter", "params": {"ceiling": params.get("ceiling", -1)}})

        elif action == "gain":
            # Adjust all master levels
            gain_db = params.get("gain_db", 0.0)
            levels = master.setdefault("levels", {})
            for name in levels:
                levels[name] = round(levels[name] * (10.0 ** (gain_db / 20.0)), 4)

        elif action == "compressor":
            for eff in effects:
                if eff.get("name") == "vc-comp":
                    return  # Already has compressor
            effects.append({
                "name": "vc-comp",
                "params": {
                    "threshold": params.get("threshold_db", -14),
                    "ratio": params.get("ratio", 2),
                    "attack": params.get("attack_ms", 10),
                    "release": params.get("release_ms", 100),
                },
            })

        elif action == "reduce_compression":
            for eff in effects:
                if eff.get("name") == "vc-comp":
                    ratio = eff.get("params", {}).get("ratio", 3)
                    eff.setdefault("params", {})["ratio"] = max(1, ratio - 1)

        elif action == "eq":
            for eff in effects:
                if eff.get("name") == "vc-eq":
                    return
            effects.append({
                "name": "vc-eq",
                "params": {
                    "low_cut_hz": params.get("low_cut_hz", 40),
                    "low_shelf_db": params.get("low_shelf_db", 0),
                },
            })

        elif action == "loudness_normalize":
            gain_db = params.get("lufs_delta_db", 0.0)
            levels = master.setdefault("levels", {})
            for name in levels:
                levels[name] = round(levels[name] * (10.0 ** (gain_db / 20.0)), 4)

    @staticmethod
    def _apply_to_track(
        config: dict[str, Any], track_name: str, action: str, params: dict[str, Any]
    ) -> None:
        """Apply an action to a specific track (in-place)."""
        tracks = config.setdefault("tracks", [])
        track_cfg = None
        for t in tracks:
            if t.get("name") == track_name:
                track_cfg = t
                break

        if track_cfg is None:
            return

        effects = track_cfg.setdefault("effects", [])

        if action == "gain":
            gain_db = params.get("gain_db", 0.0)
            # Look for existing gain effect
            gain_effect = None
            for eff in effects:
                if eff.get("name") == "vc-gain":
                    gain_effect = eff
                    break
            if gain_effect is not None:
                old = gain_effect.get("params", {}).get("gain", 0.0)
                gain_effect.setdefault("params", {})["gain"] = round(old + gain_db, 1)
            else:
                effects.insert(0, {"name": "vc-gain", "params": {"gain": round(gain_db, 1)}})

        elif action == "limiter":
            for eff in effects:
                if eff.get("name") == "vc-limiter":
                    return
            effects.append({"name": "vc-limiter", "params": {"ceiling": params.get("ceiling", -1)}})

        elif action == "compressor":
            for eff in effects:
                if eff.get("name") == "vc-comp":
                    return
            effects.append({
                "name": "vc-comp",
                "params": {
                    "threshold": params.get("threshold_db", -20),
                    "ratio": params.get("ratio", 3),
                    "attack": params.get("attack_ms", 5),
                    "release": params.get("release_ms", 50),
                },
            })

        elif action == "reduce_compression":
            for eff in effects:
                if eff.get("name") == "vc-comp":
                    ratio = eff.get("params", {}).get("ratio", 3)
                    eff.setdefault("params", {})["ratio"] = max(1, ratio - 1)

        elif action == "deesser":
            for eff in effects:
                if eff.get("name") == "vc-deesser":
                    return
            effects.insert(0, {
                "name": "vc-deesser",
                "params": {
                    "threshold": params.get("threshold", -35),
                    "reduction": params.get("reduction", -6),
                },
            })

        elif action == "eq":
            for eff in effects:
                if eff.get("name") == "vc-eq":
                    eff.setdefault("params", {}).update(params)
                    return
            effects.append({
                "name": "vc-eq",
                "params": params,
            })

    # ── Helpers ────────────────────────────────────────────────────────────

    @staticmethod
    def _log_to_dict(log: DecisionLog) -> dict[str, Any]:
        """Convert DecisionLog to dict for JSON serialization."""
        return {
            "step": log.step,
            "target": log.target,
            "action": log.action,
            "params": log.params,
            "reason": log.reason,
            "confidence": log.confidence,
            "timestamp": round(log.timestamp, 3),
        }


    # ── Phase 12: Arrangement & Mix Preset Suggestions ──────────────────

    def suggest_arrangement(
        self,
        genre: str,
        duration: float | None = None,
        mood: str = "neutral",
    ) -> dict[str, Any]:
        """Suggest an arrangement template based on genre, duration, and mood.

        Args:
            genre: Target genre (pop/rock/edm/hiphop/rnb/progressive/lofi/orchestral).
            duration: Optional target duration in seconds.
            mood: Mood hint (neutral/upbeat/mellow/dark/epic).

        Returns:
            Dict with recommended template, suggested BPM, and key.
        """
        from vcmix.arrangement.templates import (
            TEMPLATE_REGISTRY,
            list_templates,
            list_templates_by_genre,
        )

        # Find best matching template
        genre_templates = list_templates_by_genre(genre)
        if not genre_templates:
            # Fuzzy match: try partial genre
            genre_lower = genre.lower()
            for key in list_templates():
                tmpl = TEMPLATE_REGISTRY[key]
                if genre_lower in tmpl.genre or tmpl.genre in genre_lower:
                    genre_templates.append(key)

        if not genre_templates:
            genre_templates = list_templates()[:1]  # Default to first

        # Pick template based on mood
        template_key = genre_templates[0]
        if mood == "epic" and "progressive" in [k for k in genre_templates]:
            template_key = "progressive"
        elif mood == "mellow" and "lofi" in genre_templates:
            template_key = "lofi"
        elif mood == "dark" and "orchestral" in genre_templates:
            template_key = "orchestral"

        template = TEMPLATE_REGISTRY[template_key]

        # Suggest BPM based on genre and mood
        bpm_low, bpm_high = template.bpm_range
        suggested_bpm = (bpm_low + bpm_high) / 2
        if mood == "upbeat":
            suggested_bpm = bpm_high
        elif mood == "mellow":
            suggested_bpm = bpm_low

        # Suggest key based on mood
        key_suggestions = {
            "neutral": template.default_key,
            "upbeat": "C" if "m" not in template.default_key.lower() else "C",
            "mellow": "Fm" if "m" not in template.default_key.lower() else template.default_key,
            "dark": "Dm",
            "epic": "Em",
        }
        suggested_key = key_suggestions.get(mood, template.default_key)

        result: dict[str, Any] = {
            "template_key": template_key,
            "template_name": template.name,
            "genre": template.genre,
            "suggested_bpm": suggested_bpm,
            "suggested_key": suggested_key,
            "sections": template.section_names,
            "total_bars": template.total_bars,
            "bpm_range": list(template.bpm_range),
            "description": template.description,
        }

        # If duration specified, calculate bar scaling
        if duration and suggested_bpm > 0:
            bar_duration = (60.0 / suggested_bpm) * 4
            target_bars = int(duration / bar_duration)
            if target_bars > 0 and template.total_bars > 0:
                scale = target_bars / template.total_bars
                result["duration_scaling"] = round(scale, 2)
                result["target_bars"] = target_bars

        return result

    def suggest_mix_preset(
        self,
        genre: str,
        track_types: list[str | None] = None,
    ) -> dict[str, Any]:
        """Suggest a mix preset based on genre and track types.

        Args:
            genre: Target genre.
            track_types: Optional list of track types present.

        Returns:
            Dict with recommended preset details.
        """
        from vcmix.presets.mix_presets import (
            MIX_PRESET_REGISTRY,
        )
        from vcmix.presets.mix_presets import (
            suggest_mix_preset as _suggest,
        )

        preset = _suggest(genre, track_types)
        if preset is None:
            return {"error": "No matching preset found", "genre": genre}

        result: dict[str, Any] = {
            "preset_key": None,
            "name": preset.name,
            "genre": preset.genre,
            "description": preset.description,
            "track_types": preset.track_types,
            "master_target_lufs": preset.master.target_lufs,
            "tracks": [],
        }

        # Find the registry key
        for key, val in MIX_PRESET_REGISTRY.items():
            if val is preset:
                result["preset_key"] = key
                break

        for tp in preset.tracks:
            result["tracks"].append({
                "track_type": tp.track_type,
                "effect_count": len(tp.effects),
                "volume_db": tp.volume_db,
                "pan": tp.pan,
                "effect_names": [e.plugin for e in tp.effects],
            })

        return result
