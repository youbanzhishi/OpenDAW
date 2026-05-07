"""
template_applier.py — Apply arrangement templates to generate VCMix YAML (Phase 12).

Takes an ArrangementTemplate + BPM + key and produces a complete
VCMix YAML project configuration with:
    - Track list (with instrument assignments)
    - Effect chains (with mix preset parameters)
    - Section markers (with per-track entry/exit times)
    - Volume/pan automation
    - Energy curve automation

Usage:
    from vcmix.arrangement.template_applier import TemplateApplier
    from vcmix.arrangement.templates import get_template

    tmpl = get_template("pop-standard")
    applier = TemplateApplier()
    yaml_str = applier.apply(tmpl, bpm=120, key="C")
    # or get dict:
    config = applier.apply_to_dict(tmpl, bpm=120, key="C")
"""

from __future__ import annotations

from typing import Any

import yaml

from vcmix.arrangement.templates import ArrangementTemplate, Section, TrackSpec
from vcmix.presets.mix_presets import get_mix_preset, list_mix_presets


class TemplateApplier:
    """Apply an arrangement template to generate a full VCMix YAML config.

    The applier resolves:
        1. Track list from all unique TrackSpecs across sections.
        2. Effect chains from track type + associated mix preset.
        3. Section markers with bar/time offsets.
        4. Automation points for volume and pan based on energy curves.
    """

    # Volume mapping: energy level → dB offset
    _ENERGY_VOLUME_MAP: dict[str, float] = {
        "low": -6.0,
        "medium": -3.0,
        "high": 0.0,
        "peak": 2.0,
    }

    def apply(self, template: ArrangementTemplate, bpm: float = 120.0, key: str = "C") -> str:
        """Apply template and return YAML string.

        Args:
            template: ArrangementTemplate to apply.
            bpm: Tempo in BPM.
            key: Musical key (e.g. "C", "Am").

        Returns:
            Complete VCMix YAML config as string.
        """
        config = self.apply_to_dict(template, bpm=bpm, key=key)
        return yaml.dump(config, default_flow_style=False, allow_unicode=True, sort_keys=False)

    def apply_to_dict(self, template: ArrangementTemplate, bpm: float = 120.0, key: str = "C") -> dict[str, Any]:
        """Apply template and return config dict.

        Args:
            template: ArrangementTemplate to apply.
            bpm: Tempo in BPM.
            key: Musical key.

        Returns:
            Complete VCMix config dict.
        """
        # Collect unique tracks across all sections
        unique_tracks = self._collect_tracks(template)
        # Build track configs with effects from mix preset
        track_configs = self._build_track_configs(unique_tracks, template.genre)
        # Build section markers
        sections = self._build_sections(template, bpm)
        # Build automation
        automation = self._build_automation(template, bpm)

        config: dict[str, Any] = {
            "name": f"{template.name} - {key} @ {bpm} BPM",
            "bpm": bpm,
            "key": key,
            "genre": template.genre,
            "tracks": track_configs,
            "arrangement": {
                "template": template.name,
                "sections": sections,
                "total_bars": template.total_bars,
            },
            "automation": automation,
        }

        # Add recommended mix preset
        mix_preset = self._recommend_mix_preset(template.genre)
        if mix_preset:
            config["recommended_mix_preset"] = mix_preset

        return config

    def _collect_tracks(self, template: ArrangementTemplate) -> dict[str, TrackSpec]:
        """Collect all unique tracks across sections.

        Returns:
            Dict mapping track name → TrackSpec.
        """
        seen: dict[str, TrackSpec] = {}
        for section in template.structure:
            for track in section.tracks:
                if track.name not in seen:
                    seen[track.name] = track
        return seen

    def _build_track_configs(
        self, tracks: dict[str, TrackSpec], genre: str
    ) -> list[dict[str, Any]]:
        """Build VCMix track configs from TrackSpecs.

        Applies genre-appropriate mix preset effects if available.
        """
        # Try to get genre mix preset
        mix_preset = self._recommend_mix_preset_obj(genre)

        configs: list[dict[str, Any]] = []
        for name, spec in tracks.items():
            track_cfg: dict[str, Any] = {
                "name": name,
                "type": spec.type,
            }
            if spec.instrument:
                track_cfg["instrument"] = spec.instrument

            # Merge template effects with mix preset effects
            effects = list(spec.effects)
            if mix_preset:
                # Find matching track type in mix preset
                preset_effects = self._get_mix_preset_effects(spec, mix_preset)
                if preset_effects and not effects:
                    effects = preset_effects
                elif preset_effects and effects:
                    # Merge: template effects take precedence, fill gaps
                    existing_plugins = {e.get("name") for e in effects}
                    for pe in preset_effects:
                        if pe.get("name") not in existing_plugins:
                            effects.append(pe)

            if effects:
                track_cfg["effects"] = effects

            # Set volume/pan from mix preset
            if mix_preset:
                vol, pan = self._get_mix_preset_volume_pan(spec, mix_preset)
                if vol is not None:
                    track_cfg["volume_db"] = vol
                if pan is not None:
                    track_cfg["pan"] = pan

            # For audio tracks, add placeholder file
            if spec.type == "audio":
                track_cfg["file"] = f"{name.lower().replace(' ', '_')}.wav"
            elif spec.type == "midi":
                track_cfg["midi_file"] = f"{name.lower().replace(' ', '_')}.mid"
            elif spec.type == "sampler":
                track_cfg["midi_file"] = f"{name.lower().replace(' ', '_')}.mid"
                track_cfg["zones"] = [{"sample": f"{name.lower().replace(' ', '_')}.wav"}]

            configs.append(track_cfg)

        return configs

    def _build_sections(self, template: ArrangementTemplate, bpm: float) -> list[dict[str, Any]]:
        """Build section markers with bar/time offsets."""
        beat_duration = 60.0 / bpm  # seconds per beat
        bar_duration = beat_duration * 4  # assuming 4/4 time

        sections: list[dict[str, Any]] = []
        bar_offset = 0
        for section in template.structure:
            start_bar = bar_offset
            end_bar = bar_offset + section.duration_bars
            start_sec = round(start_bar * bar_duration, 2)
            end_sec = round(end_bar * bar_duration, 2)

            sec_dict: dict[str, Any] = {
                "name": section.name,
                "start_bar": start_bar,
                "end_bar": end_bar,
                "start_sec": start_sec,
                "end_sec": end_sec,
                "duration_bars": section.duration_bars,
                "energy": section.energy,
                "active_tracks": [t.name for t in section.tracks],
            }
            sections.append(sec_dict)
            bar_offset = end_bar

        return sections

    def _build_automation(self, template: ArrangementTemplate, bpm: float) -> dict[str, Any]:
        """Build automation points for volume and energy curve."""
        beat_duration = 60.0 / bpm
        bar_duration = beat_duration * 4

        # Energy curve: points at each section boundary
        energy_points: list[dict[str, Any]] = []
        volume_points: list[dict[str, Any]] = []
        bar_offset = 0
        for section in template.structure:
            # Start of section
            time_sec = round(bar_offset * bar_duration, 2)
            energy_points.append({
                "time_sec": time_sec,
                "bar": bar_offset,
                "value": section.energy,
                "section": section.name,
            })
            # Volume automation: map energy to dB (chorus louder, bridge softer)
            vol_db = self._energy_to_db(section.energy)
            volume_points.append({
                "time_sec": time_sec,
                "bar": bar_offset,
                "value_db": vol_db,
                "section": section.name,
            })
            bar_offset += section.duration_bars

        # Add final point
        final_time = round(bar_offset * bar_duration, 2)
        energy_points.append({
            "time_sec": final_time,
            "bar": bar_offset,
            "value": 0.0,
            "section": "end",
        })
        volume_points.append({
            "time_sec": final_time,
            "bar": bar_offset,
            "value_db": -60.0,
            "section": "end",
        })

        # Per-track mute automation (enter/exit sections)
        track_automation: dict[str, list[dict[str, Any]]] = {}
        for section in template.structure:
            for track in section.tracks:
                if track.name not in track_automation:
                    track_automation[track.name] = []
                sec_start = round(
                    sum(s.duration_bars for s in template.structure[:template.structure.index(section)]) * bar_duration, 2
                )
                track_automation[track.name].append({
                    "section": section.name,
                    "active": True,
                    "time_sec": sec_start,
                })

        return {
            "energy_curve": energy_points,
            "master_volume": volume_points,
            "track_mute": track_automation,
        }

    @staticmethod
    def _energy_to_db(energy: float) -> float:
        """Map energy level (0-1) to dB offset."""
        # energy 0.0 → -12dB, 0.5 → -3dB, 1.0 → 0dB (quadratic)
        return round(12.0 * (energy ** 1.5) - 12.0, 1)

    @staticmethod
    def _recommend_mix_preset(genre: str) -> str | None:
        """Recommend a mix preset name for a genre."""
        genre_preset_map: dict[str, str] = {
            "pop": "clean-pop",
            "edm": "punchy-edm",
            "rock": "warm-vintage",
            "hiphop": "tight-hiphop",
            "rnb": "airy-ballad",
            "progressive": "punchy-edm",
            "lofi": "lofi-chill",
            "orchestral": "warm-vintage",
        }
        return genre_preset_map.get(genre)

    @classmethod
    def _recommend_mix_preset_obj(cls, genre: str):
        """Get the MixPreset object for a genre."""
        from vcmix.presets.mix_presets import MixPreset
        name = cls._recommend_mix_preset(genre)
        if name:
            return get_mix_preset(name)
        return None

    @staticmethod
    def _get_mix_preset_effects(spec: TrackSpec, mix_preset) -> list[dict[str, Any]]:
        """Extract effects for a track spec from a mix preset."""
        from vcmix.presets.mix_presets import MixPreset
        if not isinstance(mix_preset, MixPreset):
            return []

        # Map track spec to preset track type
        track_type_map = {
            "vocal": "vocals",
            "vox": "vocals",
            "voice": "vocals",
            "drum": "drums",
            "bass": "bass",
            "guitar": "guitar",
            "key": "keys",
            "piano": "keys",
            "rhodes": "keys",
            "synth": "synth",
            "string": "strings",
            "pad": "synth",
            "fx": "synth",
        }
        spec_type_lower = spec.name.lower() + spec.instrument.lower()
        matched_type = None
        for keyword, preset_type in track_type_map.items():
            if keyword in spec_type_lower:
                matched_type = preset_type
                break
        if matched_type is None:
            matched_type = "synth"  # default

        # Find the matching track preset
        for tp in mix_preset.tracks:
            if tp.track_type == matched_type:
                return [e.to_dict() for e in tp.effects]
        return []

    @staticmethod
    def _get_mix_preset_volume_pan(spec: TrackSpec, mix_preset):
        """Get volume and pan from mix preset for a track spec."""
        from vcmix.presets.mix_presets import MixPreset
        if not isinstance(mix_preset, MixPreset):
            return None, None

        track_type_map = {
            "vocal": "vocals",
            "vox": "vocals",
            "drum": "drums",
            "bass": "bass",
            "guitar": "guitar",
            "key": "keys",
            "piano": "keys",
            "rhodes": "keys",
            "synth": "synth",
            "string": "strings",
            "pad": "synth",
            "fx": "synth",
        }
        spec_type_lower = spec.name.lower() + spec.instrument.lower()
        matched_type = None
        for keyword, preset_type in track_type_map.items():
            if keyword in spec_type_lower:
                matched_type = preset_type
                break
        if matched_type is None:
            matched_type = "synth"

        for tp in mix_preset.tracks:
            if tp.track_type == matched_type:
                return tp.volume_db, tp.pan
        return None, None
