"""
style_transfer.py — Style transfer engine for VCMix (Phase 17).

Transfers the mixing style from a reference track to a target project.
Analyzes the reference's EQ curves, compression settings, reverb/delay
parameters, and gain balance, then applies them to the target project.

Pipeline:
    1. Analyze reference mixing style (via ReverseMixAnalyzer)
    2. Read target project current parameters
    3. Transfer EQ settings
    4. Transfer compression settings
    5. Transfer reverb settings
    6. Adjust gain balance
    7. Output new YAML configuration

Usage:
    from vcmix.ai.style_transfer import StyleTransfer
    st = StyleTransfer()
    result = st.transfer("reference.wav", "project.yaml", "output.yaml")
"""

from __future__ import annotations

import copy
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from vcmix.separation.reverse_analyzer import ReverseMixAnalyzer
from vcmix.ai.reference_matcher_v2 import ReferenceMatcherV2, StyleFeatures


# ── Data structures ─────────────────────────────────────────────────────

@dataclass
class StyleTransferResult:
    """Result of style transfer operation."""
    output_yaml: str = ""
    reference_analysis: dict[str, Any] = field(default_factory=dict)
    transferred_params: dict[str, Any] = field(default_factory=dict)
    eq_transfers: dict[str, dict[str, Any]] = field(default_factory=dict)
    comp_transfers: dict[str, dict[str, Any]] = field(default_factory=dict)
    reverb_transfers: dict[str, dict[str, Any]] = field(default_factory=dict)
    gain_adjustments: dict[str, float] = field(default_factory=dict)
    transfer_time_sec: float = 0.0
    status: str = "success"

    def to_dict(self) -> dict[str, Any]:
        return {
            "output_yaml": self.output_yaml,
            "reference_analysis": self.reference_analysis,
            "transferred_params": self.transferred_params,
            "eq_transfers": self.eq_transfers,
            "comp_transfers": self.comp_transfers,
            "reverb_transfers": self.reverb_transfers,
            "gain_adjustments": {k: round(v, 2) for k, v in self.gain_adjustments.items()},
            "transfer_time_sec": round(self.transfer_time_sec, 3),
            "status": self.status,
        }


# ── Track name pattern matching ─────────────────────────────────────────

_VOCAL_PATTERNS = ("vocal", "vox", "voice", "lead", "bgv", "choir")
_DRUM_PATTERNS = ("drum", "kick", "snare", "hihat", "cymbal", "perc")
_BASS_PATTERNS = ("bass", "808", "sub")
_INSTRUMENT_PATTERNS = ("guitar", "piano", "keys", "synth", "strings", "rhodes")


def _match_category(track_name: str) -> str:
    """Match a track name to a stem category."""
    name_lower = track_name.lower()
    if any(p in name_lower for p in _VOCAL_PATTERNS):
        return "vocals"
    elif any(p in name_lower for p in _DRUM_PATTERNS):
        return "drums"
    elif any(p in name_lower for p in _BASS_PATTERNS):
        return "bass"
    else:
        return "other"


# ── Style Transfer Engine ───────────────────────────────────────────────

class StyleTransfer:
    """Style transfer engine.

    Transfers the mixing style from a reference track to a target project.
    """

    def __init__(self, sample_rate: int = 44100) -> None:
        self.sample_rate = sample_rate
        self._reverse_analyzer = ReverseMixAnalyzer(sample_rate=sample_rate)
        self._style_matcher = ReferenceMatcherV2(sample_rate=sample_rate)

    def transfer(
        self,
        reference_path: str,
        project_yaml: str,
        output_yaml: str,
        reference_audio: np.ndarray | None = None,
        reference_stems: dict[str, np.ndarray] | None = None,
    ) -> StyleTransferResult:
        """
        Transfer mixing style from reference to target project.

        Args:
            reference_path: Path to reference audio file.
            project_yaml: Path to target project YAML.
            output_yaml: Path for output YAML.
            reference_audio: Pre-loaded reference audio (alternative).
            reference_stems: Pre-separated reference stems (alternative).

        Returns:
            StyleTransferResult with transferred parameters and output config.
        """
        start_time = time.time()
        result = StyleTransferResult(output_yaml=output_yaml)

        try:
            # Step 1: Analyze reference mixing style
            ref_analysis = self._analyze_reference(
                reference_path, reference_audio, reference_stems
            )
            result.reference_analysis = ref_analysis

            # Step 2: Load target project
            target_config = self._load_project(project_yaml)
            target_tracks = self._extract_tracks(target_config)

            # Step 3: Transfer EQ settings
            result.eq_transfers = self._transfer_eq(ref_analysis, target_tracks)

            # Step 4: Transfer compression settings
            result.comp_transfers = self._transfer_compression(ref_analysis, target_tracks)

            # Step 5: Transfer reverb settings
            result.reverb_transfers = self._transfer_reverb(ref_analysis, target_tracks)

            # Step 6: Adjust gain balance
            result.gain_adjustments = self._balance_gain(ref_analysis, target_tracks)

            # Step 7: Apply transfers to target config
            modified_config = self._apply_transfers(
                target_config, result
            )

            # Step 8: Write output
            self._write_yaml(modified_config, output_yaml)

            result.transferred_params = {
                "eq_tracks": list(result.eq_transfers.keys()),
                "comp_tracks": list(result.comp_transfers.keys()),
                "reverb_tracks": list(result.reverb_transfers.keys()),
                "gain_tracks": list(result.gain_adjustments.keys()),
            }

        except Exception as e:
            result.status = "failed"
            result.reference_analysis = {"error": str(e)}

        result.transfer_time_sec = time.time() - start_time
        return result

    # ── Reference Analysis ───────────────────────────────────────────────

    def _analyze_reference(
        self,
        reference_path: str,
        reference_audio: np.ndarray | None,
        reference_stems: dict[str, np.ndarray] | None,
    ) -> dict[str, Any]:
        """Analyze reference track mixing style."""
        analysis: dict[str, Any] = {
            "stem_analyses": {},
            "style_features": {},
        }

        # Analyze stems if provided
        if reference_stems:
            for stem_name, audio in reference_stems.items():
                stem_analysis = self._reverse_analyzer.analyze_stem(audio, stem_name)
                analysis["stem_analyses"][stem_name] = stem_analysis.to_dict()
        else:
            # Load and analyze from path
            audio = self._load_audio(reference_path, reference_audio)
            if audio is not None:
                # Analyze full mix as single stem
                stem_analysis = self._reverse_analyzer.analyze_stem(audio, "full_mix")
                analysis["stem_analyses"]["full_mix"] = stem_analysis.to_dict()

        # Get style features
        audio = self._load_audio(reference_path, reference_audio)
        if audio is not None:
            style_result = self._style_matcher.match_style(reference_audio=audio)
            analysis["style_features"] = style_result.features.to_dict()

        return analysis

    def _load_audio(
        self,
        reference_path: str | None,
        reference_audio: np.ndarray | None,
    ) -> np.ndarray | None:
        """Load audio from path or use provided array."""
        if reference_audio is not None:
            return reference_audio.astype(np.float64)

        if reference_path is not None:
            try:
                import soundfile as sf
                audio, sr = sf.read(reference_path)
                if audio.ndim == 1:
                    audio = audio.reshape(1, -1)
                elif audio.ndim == 2:
                    audio = audio.T
                return audio.astype(np.float64)
            except (ImportError, FileNotFoundError):
                pass

        return None

    # ── Target Project Loading ───────────────────────────────────────────

    def _load_project(self, project_yaml: str) -> dict[str, Any]:
        """Load VCMix project from YAML."""
        path = Path(project_yaml)
        if not path.exists():
            # Try parsing as inline YAML string
            try:
                import yaml
                return yaml.safe_load(project_yaml)
            except Exception:
                return {"tracks": [], "master": {}}

        try:
            import yaml
            with open(path, "r", encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
        except ImportError:
            return {"tracks": [], "master": {}}

    def _extract_tracks(self, config: dict[str, Any]) -> dict[str, dict[str, Any]]:
        """Extract tracks from project config as dict keyed by name."""
        tracks: dict[str, dict[str, Any]] = {}
        for track in config.get("tracks", []):
            name = track.get("name", "unknown")
            tracks[name] = track
        return tracks

    # ── EQ Transfer ──────────────────────────────────────────────────────

    def _transfer_eq(
        self,
        ref_analysis: dict[str, Any],
        target_tracks: dict[str, dict[str, Any]],
    ) -> dict[str, dict[str, Any]]:
        """Transfer EQ settings from reference to target tracks.

        Maps reference stem EQ curves to target tracks by category
        (vocals→vocals, drums→drums, etc.).
        """
        transfers: dict[str, dict[str, Any]] = {}

        # Get reference EQ curves by category
        ref_eq_by_category: dict[str, dict[str, Any]] = {}
        for stem_name, stem_data in ref_analysis.get("stem_analyses", {}).items():
            category = _match_category(stem_name)
            eq_curve = stem_data.get("eq_curve", {})
            ref_eq_by_category[category] = eq_curve

        # Apply to target tracks
        for track_name, track_data in target_tracks.items():
            category = _match_category(track_name)
            ref_eq = ref_eq_by_category.get(category) or ref_eq_by_category.get("other")

            if ref_eq and ref_eq.get("bands"):
                eq_params = self._eq_bands_to_params(ref_eq.get("bands", []))
                transfers[track_name] = {
                    "category": category,
                    "params": eq_params,
                }

        return transfers

    def _eq_bands_to_params(self, bands: list[dict[str, Any]]) -> dict[str, Any]:
        """Convert EQ band list to VCMix EQ parameters."""
        params: dict[str, Any] = {}
        for band in bands:
            freq = band.get("freq", 1000)
            gain = band.get("gain_db", 0)
            q = band.get("q", 1.0)

            if freq < 200:
                params["low_shelf_db"] = gain
                params["low_shelf_hz"] = freq
            elif freq < 2000:
                params["peak_freq"] = freq
                params["peak_gain"] = gain
                params["peak_q"] = q
            else:
                params["high_shelf_db"] = gain
                params["high_shelf_hz"] = freq

        return params

    # ── Compression Transfer ─────────────────────────────────────────────

    def _transfer_compression(
        self,
        ref_analysis: dict[str, Any],
        target_tracks: dict[str, dict[str, Any]],
    ) -> dict[str, dict[str, Any]]:
        """Transfer compression settings from reference to target tracks."""
        transfers: dict[str, dict[str, Any]] = {}

        ref_comp_by_category: dict[str, dict[str, Any]] = {}
        for stem_name, stem_data in ref_analysis.get("stem_analyses", {}).items():
            category = _match_category(stem_name)
            comp = stem_data.get("compression", {})
            if comp.get("ratio", 1.0) > 1.5:
                ref_comp_by_category[category] = comp

        for track_name, track_data in target_tracks.items():
            category = _match_category(track_name)
            ref_comp = ref_comp_by_category.get(category) or ref_comp_by_category.get("other")

            if ref_comp:
                transfers[track_name] = {
                    "category": category,
                    "params": {
                        "threshold": ref_comp.get("threshold_db", -20),
                        "ratio": ref_comp.get("ratio", 2.0),
                        "attack": ref_comp.get("attack_ms", 10),
                        "release": ref_comp.get("release_ms", 100),
                    },
                }

        return transfers

    # ── Reverb Transfer ──────────────────────────────────────────────────

    def _transfer_reverb(
        self,
        ref_analysis: dict[str, Any],
        target_tracks: dict[str, dict[str, Any]],
    ) -> dict[str, dict[str, Any]]:
        """Transfer reverb settings from reference to target tracks."""
        transfers: dict[str, dict[str, Any]] = {}

        ref_reverb_by_category: dict[str, dict[str, Any]] = {}
        for stem_name, stem_data in ref_analysis.get("stem_analyses", {}).items():
            category = _match_category(stem_name)
            reverb = stem_data.get("reverb", {})
            if reverb.get("wet_ratio", 0) > 0.03:
                ref_reverb_by_category[category] = reverb

        for track_name, track_data in target_tracks.items():
            category = _match_category(track_name)
            ref_reverb = ref_reverb_by_category.get(category) or ref_reverb_by_category.get("other")

            if ref_reverb:
                transfers[track_name] = {
                    "category": category,
                    "params": {
                        "wet": round(min(0.5, ref_reverb.get("wet_ratio", 0.2)), 3),
                        "room_size": round(min(1.0, ref_reverb.get("rt60_ms", 500) / 3000.0), 3),
                    },
                }

        return transfers

    # ── Gain Balance ─────────────────────────────────────────────────────

    def _balance_gain(
        self,
        ref_analysis: dict[str, Any],
        target_tracks: dict[str, dict[str, Any]],
    ) -> dict[str, float]:
        """Adjust gain balance to match reference loudness distribution.

        Computes the loudness ratio between stems in the reference,
        then adjusts target track volumes to match.
        """
        # Get reference RMS levels by category
        ref_rms_by_category: dict[str, float] = {}
        for stem_name, stem_data in ref_analysis.get("stem_analyses", {}).items():
            category = _match_category(stem_name)
            rms_db = stem_data.get("rms_db", -60.0)
            if category not in ref_rms_by_category or rms_db > ref_rms_by_category[category]:
                ref_rms_by_category[category] = rms_db

        if not ref_rms_by_category:
            return {}

        # Compute reference level ratios relative to loudest category
        max_rms = max(ref_rms_by_category.values())
        ref_ratios: dict[str, float] = {}
        for cat, rms in ref_rms_by_category.items():
            ref_ratios[cat] = 10.0 ** ((rms - max_rms) / 20.0)

        # Adjust target track volumes
        adjustments: dict[str, float] = {}
        for track_name, track_data in target_tracks.items():
            category = _match_category(track_name)
            target_ratio = ref_ratios.get(category, 1.0)
            current_volume = track_data.get("volume", 0.7)

            # Scale volume by the ratio
            adjusted_volume = current_volume * target_ratio
            adjusted_volume = max(0.0, min(1.0, adjusted_volume))

            if adjusted_volume != current_volume:
                gain_db = 20 * np.log10(adjusted_volume / current_volume) if current_volume > 0 else 0.0
                adjustments[track_name] = round(float(gain_db), 2)

        return adjustments

    # ── Apply Transfers ──────────────────────────────────────────────────

    def _apply_transfers(
        self,
        config: dict[str, Any],
        result: StyleTransferResult,
    ) -> dict[str, Any]:
        """Apply all transfers to the target project config."""
        modified = copy.deepcopy(config)

        for track in modified.get("tracks", []):
            track_name = track.get("name", "")

            # Apply EQ
            if track_name in result.eq_transfers:
                eq_params = result.eq_transfers[track_name]["params"]
                effects = track.setdefault("effects", [])
                has_eq = any(e.get("name") == "vc-eq" for e in effects)
                if has_eq:
                    for e in effects:
                        if e.get("name") == "vc-eq":
                            e.setdefault("params", {}).update(eq_params)
                else:
                    effects.append({"name": "vc-eq", "params": eq_params})

            # Apply compression
            if track_name in result.comp_transfers:
                comp_params = result.comp_transfers[track_name]["params"]
                effects = track.setdefault("effects", [])
                has_comp = any(e.get("name") == "vc-comp" for e in effects)
                if has_comp:
                    for e in effects:
                        if e.get("name") == "vc-comp":
                            e.setdefault("params", {}).update(comp_params)
                else:
                    effects.append({"name": "vc-comp", "params": comp_params})

            # Apply reverb
            if track_name in result.reverb_transfers:
                reverb_params = result.reverb_transfers[track_name]["params"]
                effects = track.setdefault("effects", [])
                has_reverb = any(e.get("name") == "vc-reverb" for e in effects)
                if has_reverb:
                    for e in effects:
                        if e.get("name") == "vc-reverb":
                            e.setdefault("params", {}).update(reverb_params)
                else:
                    effects.append({"name": "vc-reverb", "params": reverb_params})

            # Apply gain adjustment
            if track_name in result.gain_adjustments:
                gain_db = result.gain_adjustments[track_name]
                current_vol = track.get("volume", 0.7)
                new_vol = current_vol * (10.0 ** (gain_db / 20.0))
                track["volume"] = round(max(0.0, min(1.0, new_vol)), 4)

        return modified

    # ── YAML Writing ─────────────────────────────────────────────────────

    def _write_yaml(self, config: dict[str, Any], path: str) -> None:
        """Write project config as YAML file."""
        try:
            import yaml
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                yaml.dump(config, f, allow_unicode=True, default_flow_style=False)
        except ImportError:
            import json
            json_path = path.replace(".yaml", ".json")
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(config, f, indent=2, ensure_ascii=False)
