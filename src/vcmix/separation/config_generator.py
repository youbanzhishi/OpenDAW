"""
config_generator.py — Generate VCMix YAML configuration from analysis results.

Takes the output of reverse mix analysis and arrangement analysis,
and produces a complete VCMix YAML config that can be rendered with
``vcmix render``.

Usage:
    from vcmix.separation.config_generator import VCMixConfigGenerator

    generator = VCMixConfigGenerator()
    yaml_str = generator.generate(stem_analyses, arrangement, bpm=120)
    # Or save directly:
    generator.generate_to_file(stem_analyses, arrangement, bpm=120, path="mix.yaml")
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import yaml

from vcmix.separation.arrangement_analyzer import ArrangementTimeline
from vcmix.separation.reverse_analyzer import StemMixAnalysis

# ── Default effect parameters per stem type ───────────────────────────

_STEM_DEFAULT_EFFECTS: dict[str, list[dict[str, Any]]] = {
    "vocals": [
        {"name": "vc-eq", "params": {"low_cut": 80, "high_shelf": 8000}},
        {"name": "vc-comp", "params": {"threshold": -18, "ratio": 3.0, "attack": 5, "release": 50}},
        {"name": "vc-limiter", "params": {"ceiling": -1}},
    ],
    "drums": [
        {"name": "vc-eq", "params": {"low_cut": 30, "high_shelf": 8000}},
        {"name": "vc-comp", "params": {"threshold": -18, "ratio": 2.5, "attack": 1, "release": 20}},
        {"name": "vc-limiter", "params": {"ceiling": -1}},
    ],
    "bass": [
        {"name": "vc-eq", "params": {"low_cut": 30, "high_shelf": 5000}},
        {"name": "vc-comp", "params": {"threshold": -20, "ratio": 3.0, "attack": 10, "release": 80}},
        {"name": "vc-limiter", "params": {"ceiling": -1}},
    ],
    "other": [
        {"name": "vc-eq", "params": {"low_cut": 60, "high_shelf": 8000}},
        {"name": "vc-limiter", "params": {"ceiling": -1}},
    ],
}


def _sanitize_for_yaml(obj: Any) -> Any:
    """Convert numpy types to native Python types for YAML serialization."""
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        return float(obj)
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, dict):
        return {k: _sanitize_for_yaml(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_sanitize_for_yaml(v) for v in obj]
    return obj


class VCMixConfigGenerator:
    """Generate VCMix YAML configuration from analysis results.

    Parameters
    ----------
    sample_rate : int
        Target sample rate for the config.
    stem_dir : str
        Directory containing separated stem WAV files.
    """

    def __init__(
        self,
        sample_rate: int = 44100,
        stem_dir: str = "./stems/",
    ):
        self.sample_rate = sample_rate
        self.stem_dir = stem_dir

    def generate(
        self,
        stem_analyses: dict[str, StemMixAnalysis],
        arrangement: ArrangementTimeline | None = None,
        bpm: float = 120.0,
    ) -> str:
        """Generate VCMix YAML configuration string.

        Parameters
        ----------
        stem_analyses : dict[str, StemMixAnalysis]
            Per-stem analysis results from ReverseMixAnalyzer.
        arrangement : ArrangementTimeline or None
            Arrangement structure (optional).
        bpm : float
            Tempo in BPM.

        Returns
        -------
        str
            Complete YAML config string.
        """
        config = self._build_config(stem_analyses, arrangement, bpm)
        config = _sanitize_for_yaml(config)
        return yaml.dump(config, default_flow_style=False, allow_unicode=True, sort_keys=False)

    def generate_to_file(
        self,
        stem_analyses: dict[str, StemMixAnalysis],
        arrangement: ArrangementTimeline | None,
        bpm: float,
        path: str | Path,
    ) -> Path:
        """Generate and save VCMix YAML config to file.

        Returns the path to the saved file.
        """
        path = Path(path)
        yaml_str = self.generate(stem_analyses, arrangement, bpm)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(yaml_str, encoding="utf-8")
        return path

    def _build_config(
        self,
        stem_analyses: dict[str, StemMixAnalysis],
        arrangement: ArrangementTimeline | None,
        bpm: float,
    ) -> dict[str, Any]:
        """Build the config dict structure."""
        tracks = []
        levels: dict[str, float] = {}

        for stem_name, analysis in stem_analyses.items():
            track = self._build_track(stem_name, analysis)
            tracks.append(track)

            # Compute level from RMS
            level = min(1.0, max(0.1, 10 ** (analysis.rms_db / 20) * 5))
            levels[stem_name] = round(level, 2)

        config: dict[str, Any] = {
            "name": "demucs_analysis",
            "bpm": round(bpm, 1),
            "sample_rate": self.sample_rate,
            "tracks": tracks,
            "master": {
                "levels": levels,
                "effects": [],
                "output": "demucs_mix.wav",
            },
        }

        # Add arrangement sections if available
        if arrangement and arrangement.sections:
            config["arrangement"] = self._build_arrangement(arrangement)

        return config

    def _build_track(
        self, stem_name: str, analysis: StemMixAnalysis,
    ) -> dict[str, Any]:
        """Build a track config entry from analysis results."""
        effects = self._build_effects(stem_name, analysis)
        return {
            "name": stem_name,
            "file": f"{self.stem_dir}{stem_name}.wav",
            "effects": effects,
        }

    def _build_effects(
        self, stem_name: str, analysis: StemMixAnalysis,
    ) -> list[dict[str, Any]]:
        """Build effects chain from analysis results.

        Uses the detected parameters from reverse analysis when available,
        falling back to stem-type defaults.
        """
        effects: list[dict[str, Any]] = []

        # EQ from analysis
        eq_effect = self._build_eq_effect(analysis)
        if eq_effect:
            effects.append(eq_effect)

        # Compression from analysis
        comp_effect = self._build_comp_effect(analysis)
        if comp_effect:
            effects.append(comp_effect)

        # Reverb from analysis (if detected)
        reverb_effect = self._build_reverb_effect(analysis)
        if reverb_effect:
            effects.append(reverb_effect)

        # Delay from analysis (if detected)
        delay_effect = self._build_delay_effect(analysis)
        if delay_effect:
            effects.append(delay_effect)

        # Always add limiter
        effects.append({"name": "vc-limiter", "params": {"ceiling": -1}})

        return effects

    @staticmethod
    def _build_eq_effect(analysis: StemMixAnalysis) -> dict[str, Any] | None:
        """Build EQ effect from detected EQ curve."""
        bands = analysis.eq_curve.bands
        if not bands:
            # Use defaults
            defaults = _STEM_DEFAULT_EFFECTS.get(analysis.track_name, [])
            for e in defaults:
                if e["name"] == "vc-eq":
                    return e
            return None

        params: dict[str, Any] = {}
        for i, band in enumerate(bands[:8]):
            params[f"band{i+1}_freq"] = int(band.freq)
            params[f"band{i+1}_gain"] = round(band.gain_db, 1)
            params[f"band{i+1}_q"] = round(band.q, 2)

        return {"name": "vc-eq", "params": params}

    @staticmethod
    def _build_comp_effect(analysis: StemMixAnalysis) -> dict[str, Any] | None:
        """Build compressor effect from detected compression."""
        comp = analysis.compression
        if comp.ratio <= 1.0:
            return None

        return {
            "name": "vc-comp",
            "params": {
                "threshold": round(comp.threshold_db, 1),
                "ratio": round(comp.ratio, 1),
                "attack": round(comp.attack_ms, 1),
                "release": round(comp.release_ms, 1),
            },
        }

    @staticmethod
    def _build_reverb_effect(analysis: StemMixAnalysis) -> dict[str, Any] | None:
        """Build reverb effect from detected reverb parameters."""
        rev = analysis.reverb
        if rev.rt60_ms < 100:
            return None  # No significant reverb detected

        return {
            "name": "vc-reverb",
            "params": {
                "room_size": round(min(rev.rt60_ms / 3000.0, 1.0), 2),
                "damping": 0.5,
                "wet": round(rev.wet_ratio, 3),
                "pre_delay": round(rev.pre_delay_ms, 1),
            },
        }

    @staticmethod
    def _build_delay_effect(analysis: StemMixAnalysis) -> dict[str, Any] | None:
        """Build delay effect from detected delay parameters."""
        delay = analysis.delay
        if delay.delay_ms < 10 or delay.tap_count < 1:
            return None

        return {
            "name": "vc-delay",
            "params": {
                "delay_ms": round(delay.delay_ms, 1),
                "feedback": round(delay.feedback, 3),
                "mix": round(min(delay.feedback + 0.1, 0.5), 3),
            },
        }

    @staticmethod
    def _build_arrangement(arrangement: ArrangementTimeline) -> list[dict[str, Any]]:
        """Build arrangement section entries for the config."""
        sections = []
        for s in arrangement.sections:
            section_dict: dict[str, Any] = {
                "name": s.name,
                "start_beat": s.start_beat,
                "end_beat": s.end_beat,
                "energy_level": s.energy_level,
            }
            active = s.active_stems()
            if active:
                section_dict["active_stems"] = active
            sections.append(section_dict)
        return sections
