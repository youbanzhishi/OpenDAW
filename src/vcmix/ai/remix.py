"""
remix.py — One-click Remix engine for VCMix (Phase 17).

Combines reference track analysis with new素材 to automatically
generate a remix. Pipeline:

    1. Analyze reference (separation + reverse analysis)
    2. If genre/bpm specified, adjust arrangement template
    3. Replace reference stems with new素材
    4. Auto-mix new素材 to blend with reference style
    5. Render output

Usage:
    from vcmix.ai.remix import RemixEngine
    engine = RemixEngine()
    result = engine.remix("reference.wav", new_stems={"vocals": "new_vocals.wav"})
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from vcmix.ai.transcription import AITranscription, TranscriptionResult
from vcmix.ai.style_transfer import StyleTransfer, StyleTransferResult
from vcmix.ai.reference_matcher_v2 import ReferenceMatcherV2


# ── Data structures ─────────────────────────────────────────────────────

@dataclass
class RemixResult:
    """Result of a remix operation."""
    output_path: str = ""
    output_yaml: str = ""
    transcription: dict[str, Any] = field(default_factory=dict)
    style_transfer: dict[str, Any] = field(default_factory=dict)
    replaced_stems: list[str] = field(default_factory=list)
    kept_stems: list[str] = field(default_factory=list)
    final_config: dict[str, Any] = field(default_factory=dict)
    remix_time_sec: float = 0.0
    status: str = "success"

    def to_dict(self) -> dict[str, Any]:
        return {
            "output_path": self.output_path,
            "output_yaml": self.output_yaml,
            "replaced_stems": self.replaced_stems,
            "kept_stems": self.kept_stems,
            "final_config_keys": list(self.final_config.keys()) if self.final_config else [],
            "remix_time_sec": round(self.remix_time_sec, 3),
            "status": self.status,
        }


# ── Remix Engine ────────────────────────────────────────────────────────

class RemixEngine:
    """One-click Remix engine.

    Analyzes a reference track, replaces specified stems with new素材,
    and auto-mixes everything together in the reference's style.
    """

    def __init__(self, sample_rate: int = 44100) -> None:
        self.sample_rate = sample_rate
        self._transcriber = AITranscription(sample_rate=sample_rate)
        self._style_transfer = StyleTransfer(sample_rate=sample_rate)
        self._style_matcher = ReferenceMatcherV2(sample_rate=sample_rate)

    def remix(
        self,
        reference_path: str,
        new_stems: dict[str, str],
        genre: str | None = None,
        bpm: float | None = None,
        output_dir: str | None = None,
        separate_fn: Any | None = None,
    ) -> RemixResult:
        """
        One-click Remix pipeline.

        Args:
            reference_path: Path to reference audio file.
            new_stems: Dict mapping stem names to new audio file paths.
                       e.g. {"vocals": "new_vocals.wav", "bass": "new_bass.wav"}
            genre: Override genre for the remix (optional).
            bpm: Override BPM for the remix (optional).
            output_dir: Output directory (defaults to ./remix_output).
            separate_fn: Custom separation function.

        Returns:
            RemixResult with output paths and analysis details.
        """
        start_time = time.time()
        result = RemixResult()

        if output_dir is None:
            output_dir = "./remix_output"

        out_path = Path(output_dir)
        out_path.mkdir(parents=True, exist_ok=True)

        try:
            # Step 1: Transcribe reference
            transcription = self._transcriber.transcribe(
                reference_path, str(out_path / "reference_analysis"),
                separate_fn=separate_fn,
            )
            result.transcription = transcription.to_dict()

            # Step 2: Get style features (optional genre/bpm override)
            ref_audio = self._load_audio(reference_path)
            style_result = self._style_matcher.match_style(reference_audio=ref_audio)

            effective_genre = genre or style_result.features.genre
            effective_bpm = bpm or style_result.features.bpm

            # Step 3: Load reference project config
            project_config = self._build_remix_config(
                transcription, effective_genre, effective_bpm, new_stems
            )

            # Step 4: Track which stems are replaced vs kept
            ref_stems = set(transcription.stems.keys())
            new_stem_names = set(new_stems.keys())
            result.replaced_stems = list(ref_stems & new_stem_names)
            result.kept_stems = list(ref_stems - new_stem_names)

            # Step 5: Apply style transfer
            reference_stems: dict[str, np.ndarray] = {}
            for stem_name, stem_path in transcription.stems.items():
                audio = self._load_audio(stem_path)
                if audio is not None:
                    reference_stems[stem_name] = audio

            style_transfer_result = self._style_transfer.transfer(
                reference_path=reference_path,
                project_yaml=str(out_path / "remix_project.yaml"),
                output_yaml=str(out_path / "remix_styled.yaml"),
                reference_stems=reference_stems,
            )
            result.style_transfer = style_transfer_result.to_dict()

            # Step 6: Finalize config with new stems and style
            final_config = self._finalize_remix(
                project_config, new_stems, style_transfer_result, effective_bpm
            )
            result.final_config = final_config

            # Write final config
            final_yaml = str(out_path / "remix_final.yaml")
            self._write_yaml(final_config, final_yaml)
            result.output_yaml = final_yaml

        except Exception as e:
            result.status = "failed"
            result.final_config = {"error": str(e)}

        result.remix_time_sec = time.time() - start_time
        return result

    # ── Build Remix Config ───────────────────────────────────────────────

    def _build_remix_config(
        self,
        transcription: TranscriptionResult,
        genre: str,
        bpm: float,
        new_stems: dict[str, str],
    ) -> dict[str, Any]:
        """Build the remix project config from transcription + overrides."""
        config: dict[str, Any] = {
            "name": f"Remix ({genre} style)",
            "bpm": bpm,
            "key": transcription.key_info.root,
            "scale": transcription.key_info.scale_type,
            "genre": genre,
            "sample_rate": self.sample_rate,
            "tracks": [],
            "arrangement": transcription.arrangement,
            "master": {
                "target_lufs": -14.0,
                "true_peak_ceiling": -1.0,
                "effects": [{"name": "vc-limiter", "params": {"ceiling": -1.0}}],
            },
        }

        # Build track list: reference stems + new stems
        track_names_seen: set[str] = set()

        for stem_name, stem_path in transcription.stems.items():
            if stem_name in new_stems:
                # This stem will be replaced
                track = {
                    "name": stem_name,
                    "type": "audio",
                    "file": new_stems[stem_name],
                    "source": "new",
                    "volume": 0.7,
                    "effects": self._default_effects_for_stem(stem_name),
                }
            else:
                # Keep reference stem
                analysis = transcription.stem_analyses.get(stem_name, {})
                track = {
                    "name": stem_name,
                    "type": "audio",
                    "file": stem_path,
                    "source": "reference",
                    "volume": self._rms_to_volume(analysis.get("rms_db", -18.0)),
                    "effects": self._analysis_to_effects(analysis, stem_name),
                }

            config["tracks"].append(track)
            track_names_seen.add(stem_name)

        # Add new stems not in reference
        for stem_name, stem_path in new_stems.items():
            if stem_name not in track_names_seen:
                track = {
                    "name": stem_name,
                    "type": "audio",
                    "file": stem_path,
                    "source": "new",
                    "volume": 0.7,
                    "effects": self._default_effects_for_stem(stem_name),
                }
                config["tracks"].append(track)

        return config

    def _default_effects_for_stem(self, stem_name: str) -> list[dict[str, Any]]:
        """Return default effects for a new stem."""
        effects: list[dict[str, Any]] = []

        name_lower = stem_name.lower()
        if any(p in name_lower for p in ("vocal", "vox", "voice")):
            effects = [
                {"name": "vc-eq", "params": {"low_cut_hz": 80}},
                {"name": "vc-comp", "params": {"threshold": -18, "ratio": 3, "attack": 5}},
                {"name": "vc-reverb", "params": {"wet": 0.2, "room_size": 0.5}},
                {"name": "vc-limiter", "params": {"ceiling": -1}},
            ]
        elif any(p in name_lower for p in ("drum", "kick", "snare", "hihat")):
            effects = [
                {"name": "vc-eq", "params": {"low_cut_hz": 30}},
                {"name": "vc-comp", "params": {"threshold": -12, "ratio": 4, "attack": 1}},
                {"name": "vc-limiter", "params": {"ceiling": -1}},
            ]
        elif any(p in name_lower for p in ("bass", "808")):
            effects = [
                {"name": "vc-eq", "params": {"low_shelf_db": 2}},
                {"name": "vc-comp", "params": {"threshold": -15, "ratio": 4, "attack": 10}},
                {"name": "vc-limiter", "params": {"ceiling": -1}},
            ]
        else:
            effects = [
                {"name": "vc-eq", "params": {}},
                {"name": "vc-limiter", "params": {"ceiling": -1}},
            ]

        return effects

    def _rms_to_volume(self, rms_db: float) -> float:
        """Convert RMS dB to volume (0.0-1.0)."""
        if rms_db <= -60.0:
            return 0.0
        volume = (rms_db + 60.0) / 60.0
        return round(max(0.0, min(1.0, volume)), 4)

    def _analysis_to_effects(
        self, analysis: dict[str, Any], stem_name: str
    ) -> list[dict[str, Any]]:
        """Convert reverse analysis to effects (simplified)."""
        effects: list[dict[str, Any]] = []

        eq_bands = analysis.get("eq_curve", {}).get("bands", [])
        if eq_bands:
            eq_params: dict[str, Any] = {}
            for band in eq_bands:
                freq = band.get("freq", 1000)
                gain = band.get("gain_db", 0)
                if freq < 200:
                    eq_params["low_shelf_db"] = gain
                elif freq < 2000:
                    eq_params["peak_gain"] = gain
                else:
                    eq_params["high_shelf_db"] = gain
            effects.append({"name": "vc-eq", "params": eq_params})

        comp = analysis.get("compression", {})
        if comp.get("ratio", 1.0) > 1.5:
            effects.append({
                "name": "vc-comp",
                "params": {
                    "threshold": comp.get("threshold_db", -20),
                    "ratio": comp.get("ratio", 2.0),
                },
            })

        effects.append({"name": "vc-limiter", "params": {"ceiling": -1.0}})
        return effects

    # ── Finalize Remix ───────────────────────────────────────────────────

    def _finalize_remix(
        self,
        project_config: dict[str, Any],
        new_stems: dict[str, str],
        style_result: StyleTransferResult,
        bpm: float,
    ) -> dict[str, Any]:
        """Finalize the remix config with style transfer applied."""
        import copy
        config = copy.deepcopy(project_config)

        # Ensure BPM is set
        config["bpm"] = bpm

        # Apply style transfer adjustments to tracks
        for track in config.get("tracks", []):
            track_name = track.get("name", "")

            # Apply EQ from style transfer
            if track_name in style_result.eq_transfers:
                eq_params = style_result.eq_transfers[track_name].get("params", {})
                effects = track.setdefault("effects", [])
                for e in effects:
                    if e.get("name") == "vc-eq":
                        e.setdefault("params", {}).update(eq_params)
                        break

            # Apply compression from style transfer
            if track_name in style_result.comp_transfers:
                comp_params = style_result.comp_transfers[track_name].get("params", {})
                effects = track.setdefault("effects", [])
                for e in effects:
                    if e.get("name") == "vc-comp":
                        e.setdefault("params", {}).update(comp_params)
                        break

            # Apply reverb from style transfer
            if track_name in style_result.reverb_transfers:
                reverb_params = style_result.reverb_transfers[track_name].get("params", {})
                effects = track.setdefault("effects", [])
                for e in effects:
                    if e.get("name") == "vc-reverb":
                        e.setdefault("params", {}).update(reverb_params)
                        break

            # Apply gain adjustments
            if track_name in style_result.gain_adjustments:
                gain_db = style_result.gain_adjustments[track_name]
                current_vol = track.get("volume", 0.7)
                new_vol = current_vol * (10.0 ** (gain_db / 20.0))
                track["volume"] = round(max(0.0, min(1.0, new_vol)), 4)

        return config

    # ── Audio Loading ────────────────────────────────────────────────────

    def _load_audio(self, path: str) -> np.ndarray | None:
        """Load audio from file path."""
        try:
            import soundfile as sf
            audio, sr = sf.read(path)
            if audio.ndim == 1:
                audio = audio.reshape(1, -1)
            elif audio.ndim == 2:
                audio = audio.T
            return audio.astype(np.float64)
        except (ImportError, FileNotFoundError, RuntimeError):
            return None

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
