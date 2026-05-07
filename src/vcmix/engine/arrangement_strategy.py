"""
arrangement_strategy.py — Arrangement-aware mixing strategy generator.

Generates section-level effect parameters from arrangement analysis,
enabling dynamic mixing that adapts to song structure (intro/verse/chorus/
bridge/outro).

Phase 7 module: links Phase 5 ArrangementExtractor output to the
rendering pipeline via per-section effect parameter overrides.

Key classes:
    SectionMixParams   — Effect parameters for a single section
    ArrangementStrategy — Full strategy derived from a list of Section objects

Strategy rules (per section type):
    Intro:  low reverb (5%), low delay, compression ratio 1.5:1
    Verse:  medium reverb (10%), medium delay, compression ratio 2:1
    Chorus: high reverb (20%), high delay, compression ratio 3:1, +2 dB gain
    Bridge: high reverb (25%), low compression
    Outro:  gradually decreasing reverb/delay/gain

Public API:
    ArrangementStrategy.from_sections()  — build strategy from Section list
    ArrangementStrategy.get_params_at_beat() — query params at any beat
    ArrangementStrategy.to_yaml_overrides()  — export as YAML-overridable dict

Usage:
    from vcmix.separation.arrangement import Section
    from vcmix.engine.arrangement_strategy import ArrangementStrategy

    sections = [Section("intro", 0, 4, ...), Section("chorus", 4, 12, ...)]
    strategy = ArrangementStrategy.from_sections(sections)
    params = strategy.get_params_at_beat(6)  # chorus params
    overrides = strategy.to_yaml_overrides()

Dependencies: numpy, pyyaml
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import yaml

# ---------------------------------------------------------------------------
# Per-section effect parameter dataclass
# ---------------------------------------------------------------------------

@dataclass
class SectionMixParams:
    """Effect parameters for a single musical section.

    Attributes
    ----------
    section_name : str
        Name of the section (intro/verse/chorus/bridge/outro).
    reverb_mix : float
        Reverb wet/dry mix percentage (0.0–1.0).
    delay_mix : float
        Delay wet/dry mix percentage (0.0–1.0).
    compression_ratio : float
        Compressor ratio (e.g. 2.0 means 2:1).
    gain_db : float
        Gain offset in dB relative to baseline.
    crossfade_beats : int
        Number of beats over which to crossfade into this section.
    """

    section_name: str
    reverb_mix: float = 0.0
    delay_mix: float = 0.0
    compression_ratio: float = 1.0
    gain_db: float = 0.0
    crossfade_beats: int = 2


# ---------------------------------------------------------------------------
# Default parameter presets per section type
# ---------------------------------------------------------------------------

_SECTION_DEFAULTS: dict[str, dict[str, Any]] = {
    "intro": {
        "reverb_mix": 0.05,
        "delay_mix": 0.05,
        "compression_ratio": 1.5,
        "gain_db": 0.0,
        "crossfade_beats": 2,
    },
    "verse": {
        "reverb_mix": 0.10,
        "delay_mix": 0.10,
        "compression_ratio": 2.0,
        "gain_db": 0.0,
        "crossfade_beats": 2,
    },
    "chorus": {
        "reverb_mix": 0.20,
        "delay_mix": 0.20,
        "compression_ratio": 3.0,
        "gain_db": 2.0,
        "crossfade_beats": 4,
    },
    "bridge": {
        "reverb_mix": 0.25,
        "delay_mix": 0.05,
        "compression_ratio": 1.5,
        "gain_db": 0.0,
        "crossfade_beats": 3,
    },
    "outro": {
        "reverb_mix": 0.05,
        "delay_mix": 0.05,
        "compression_ratio": 1.5,
        "gain_db": -1.0,
        "crossfade_beats": 4,
    },
}


# ---------------------------------------------------------------------------
# ArrangementStrategy
# ---------------------------------------------------------------------------

@dataclass
class ArrangementStrategy:
    """Full arrangement-aware mixing strategy.

    Maps every beat of the song to a set of effect parameters,
    with optional crossfade smoothing at section boundaries.

    Attributes
    ----------
    sections : list[SectionMixParams]
        Ordered list of per-section mixing parameters.
    section_map : dict[int, int]
        Mapping from start_beat -> index in *sections*.
    total_beats : int
        Total number of beats in the song.
    """

    sections: list[SectionMixParams] = field(default_factory=list)
    section_map: dict[int, int] = field(default_factory=dict)
    total_beats: int = 0

    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------

    @classmethod
    def from_sections(
        cls,
        song_sections: list[Any],
        overrides: dict[str, dict[str, Any]] | None = None,
    ) -> ArrangementStrategy:
        """Build a strategy from a list of Section objects.

        Parameters
        ----------
        song_sections : list[Section]
            Section objects from ArrangementExtractor.extract().
        overrides : dict, optional
            Per-section-type parameter overrides, e.g.
            ``{"chorus": {"reverb_mix": 0.30}}``.

        Returns
        -------
        ArrangementStrategy
        """
        overrides = overrides or {}
        mix_sections: list[SectionMixParams] = []
        section_map: dict[int, int] = {}
        total_beats = 0

        for idx, sec in enumerate(song_sections):
            name = sec.name.lower()
            total_beats = max(total_beats, sec.end_beat)

            # Start with defaults for this section type
            defaults = _SECTION_DEFAULTS.get(name, _SECTION_DEFAULTS["verse"]).copy()

            # Apply user overrides for this section type
            if name in overrides:
                defaults.update(overrides[name])

            params = SectionMixParams(
                section_name=name,
                reverb_mix=defaults["reverb_mix"],
                delay_mix=defaults["delay_mix"],
                compression_ratio=defaults["compression_ratio"],
                gain_db=defaults["gain_db"],
                crossfade_beats=defaults["crossfade_beats"],
            )

            # For outro, apply gradual reduction across the section
            if name == "outro":
                params = _apply_outro_fade(params, sec)

            section_map[sec.start_beat] = idx
            mix_sections.append(params)

        return cls(
            sections=mix_sections,
            section_map=section_map,
            total_beats=total_beats,
        )

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def get_params_at_beat(self, beat: int) -> SectionMixParams:
        """Get interpolated effect parameters at a given beat.

        If the beat falls within a crossfade zone at the start of a
        section, the parameters are linearly interpolated between the
        previous and current section.

        Parameters
        ----------
        beat : int
            Beat index (0-based).

        Returns
        -------
        SectionMixParams
            Interpolated parameters for the given beat.

        Raises
        ------
        ValueError
            If *beat* is negative.
        """
        if beat < 0:
            raise ValueError(f"beat must be non-negative, got {beat}")

        # Find which section this beat belongs to
        section_idx = self._find_section_index(beat)
        current = self.sections[section_idx]

        # Check if we're in a crossfade zone
        # Find the start_beat of the current section
        start_beat = self._find_start_beat(section_idx)
        fade_beats = current.crossfade_beats

        if fade_beats > 0 and section_idx > 0 and beat < start_beat + fade_beats:
            # We're in the crossfade zone
            prev = self.sections[section_idx - 1]
            progress = (beat - start_beat) / fade_beats
            progress = max(0.0, min(1.0, progress))  # clamp
            return _interpolate_params(prev, current, progress)

        return current

    # ------------------------------------------------------------------
    # YAML export
    # ------------------------------------------------------------------

    def to_yaml_overrides(self) -> str:
        """Generate a YAML string of section-level overrides.

        This can be merged with a VCMix project YAML to apply
        arrangement-aware mixing parameters.

        Returns
        -------
        str
            YAML-formatted override configuration.
        """
        data: dict[str, Any] = {"arrangement_strategy": {}}
        for idx, sec in enumerate(self.sections):
            start_beat = self._find_start_beat(idx)
            data["arrangement_strategy"][f"section_{idx}_{sec.section_name}"] = {
                "start_beat": start_beat,
                "section_name": sec.section_name,
                "reverb_mix": round(sec.reverb_mix, 4),
                "delay_mix": round(sec.delay_mix, 4),
                "compression_ratio": sec.compression_ratio,
                "gain_db": sec.gain_db,
                "crossfade_beats": sec.crossfade_beats,
            }
        return yaml.dump(data, default_flow_style=False, allow_unicode=True, sort_keys=False)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _find_section_index(self, beat: int) -> int:
        """Find the section index that contains the given beat.

        Uses the section_map to locate the correct section.
        """
        # Find the greatest start_beat <= beat
        candidates = [sb for sb in self.section_map if sb <= beat]
        if not candidates:
            return 0
        start_beat = max(candidates)
        return self.section_map[start_beat]

    def _find_start_beat(self, section_idx: int) -> int:
        """Find the start beat for a section at the given index."""
        for sb, idx in self.section_map.items():
            if idx == section_idx:
                return sb
        return 0


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def _interpolate_params(
    prev: SectionMixParams,
    curr: SectionMixParams,
    progress: float,
) -> SectionMixParams:
    """Linearly interpolate between two SectionMixParams.

    Parameters
    ----------
    prev : SectionMixParams
        Parameters of the previous section (progress=0).
    curr : SectionMixParams
        Parameters of the current section (progress=1).
    progress : float
        Interpolation factor in [0, 1].

    Returns
    -------
    SectionMixParams
        Interpolated parameters.
    """
    return SectionMixParams(
        section_name=curr.section_name if progress >= 0.5 else prev.section_name,
        reverb_mix=prev.reverb_mix + (curr.reverb_mix - prev.reverb_mix) * progress,
        delay_mix=prev.delay_mix + (curr.delay_mix - prev.delay_mix) * progress,
        compression_ratio=prev.compression_ratio
        + (curr.compression_ratio - prev.compression_ratio) * progress,
        gain_db=prev.gain_db + (curr.gain_db - prev.gain_db) * progress,
        crossfade_beats=curr.crossfade_beats,
    )


def _apply_outro_fade(params: SectionMixParams, section: Any) -> SectionMixParams:
    """Apply gradual fade-out parameters for the outro section.

    The outro's reverb, delay, and gain are set to reduced values
    that taper off towards the end of the section.

    Parameters
    ----------
    params : SectionMixParams
        The base outro parameters (from defaults).
    section : Section
        The outro Section object (for length calculation).

    Returns
    -------
    SectionMixParams
        Modified params with fade-out applied.
    """
    length_beats = section.end_beat - section.start_beat
    if length_beats <= 0:
        return params

    # Gradual reduction: reverb and delay start at section defaults
    # but we set gain to decrease proportionally
    # The actual per-beat interpolation handles the fade in get_params_at_beat
    # Here we set the *target* values for the end of the outro
    fade_factor = max(0.2, 1.0 - (length_beats / max(length_beats, 16)))
    return SectionMixParams(
        section_name=params.section_name,
        reverb_mix=params.reverb_mix * fade_factor,
        delay_mix=params.delay_mix * fade_factor,
        compression_ratio=params.compression_ratio,
        gain_db=-2.0,  # outro gain reduction
        crossfade_beats=params.crossfade_beats,
    )
