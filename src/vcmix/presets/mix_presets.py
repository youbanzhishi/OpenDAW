"""
mix_presets.py — Genre/scene-based complete mix presets (Phase 12).

Provides full mixing presets organized by genre and scene, including
per-track-type effect chains, volume, pan, and master bus settings.

Built-in presets (6):
    - Clean Pop    — Bright vocals + compression + short reverb
    - Warm Vintage — Warm EQ + tape saturation + long reverb
    - Punchy EDM   — Multiband comp + sidechain + big reverb
    - Tight Hip-Hop — HPF + heavy comp + short delay
    - Airy Ballad  — Air band boost + light comp + hall reverb
    - Lo-fi Chill  — Low-pass filter + noise + tape wobble

Usage:
    from vcmix.presets.mix_presets import get_mix_preset, list_mix_presets

    for name in list_mix_presets():
        preset = get_mix_preset(name)
        print(f"{preset.name}: {len(preset.tracks)} track presets")
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# ── Data Models ──────────────────────────────────────────────────────────

@dataclass
class EffectPreset:
    """Single effect preset with plugin name and parameters.

    Attributes:
        plugin: Plugin name (e.g. "VC-EQ", "VC-Comp", "VC-Reverb").
        params: Plugin parameters dict.
        enabled: Whether the effect is active.
    """

    plugin: str
    params: dict[str, Any] = field(default_factory=dict)
    enabled: bool = True

    def to_dict(self) -> dict[str, Any]:
        """Serialize to plain dict (VCMix effects format)."""
        result: dict[str, Any] = {"name": self.plugin.lower().replace("vc-", "vc-")}
        # Normalize plugin name for VCMix
        name = self.plugin
        if name.startswith("VC-"):
            name = "vc-" + name[3:].lower()
        elif not name.startswith("vc-"):
            name = "vc-" + name.lower()
        result["name"] = name
        if self.params:
            result["params"] = dict(self.params)
        if not self.enabled:
            result["enabled"] = False
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EffectPreset:
        """Deserialize from plain dict."""
        plugin = data.get("name", data.get("plugin", ""))
        return cls(
            plugin=plugin,
            params=data.get("params", {}),
            enabled=data.get("enabled", True),
        )


@dataclass
class TrackMixPreset:
    """Per-track-type mixing preset.

    Attributes:
        track_type: Track type (vocals/drums/bass/guitar/keys/synth/strings).
        effects: Ordered list of effect presets.
        volume_db: Volume in dB.
        pan: Pan position (-1.0 left to 1.0 right).
    """

    track_type: str
    effects: list[EffectPreset] = field(default_factory=list)
    volume_db: float = 0.0
    pan: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """Serialize to plain dict."""
        return {
            "track_type": self.track_type,
            "effects": [e.to_dict() for e in self.effects],
            "volume_db": self.volume_db,
            "pan": self.pan,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TrackMixPreset:
        """Deserialize from plain dict."""
        effects = [EffectPreset.from_dict(e) for e in data.get("effects", [])]
        return cls(
            track_type=data["track_type"],
            effects=effects,
            volume_db=data.get("volume_db", 0.0),
            pan=data.get("pan", 0.0),
        )


@dataclass
class MasterMixPreset:
    """Master bus mixing preset.

    Attributes:
        effects: Master bus effect chain.
        volume_db: Master volume.
        target_lufs: Target LUFS level.
    """

    effects: list[EffectPreset] = field(default_factory=list)
    volume_db: float = 0.0
    target_lufs: float = -14.0

    def to_dict(self) -> dict[str, Any]:
        """Serialize to plain dict."""
        return {
            "effects": [e.to_dict() for e in self.effects],
            "volume_db": self.volume_db,
            "target_lufs": self.target_lufs,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MasterMixPreset:
        """Deserialize from plain dict."""
        effects = [EffectPreset.from_dict(e) for e in data.get("effects", [])]
        return cls(
            effects=effects,
            volume_db=data.get("volume_db", 0.0),
            target_lufs=data.get("target_lufs", -14.0),
        )


@dataclass
class MixPreset:
    """Complete mix preset with per-track and master settings.

    Attributes:
        name: Preset name.
        genre: Genre tag.
        description: Human-readable description.
        tracks: List of per-track-type presets.
        master: Master bus preset.
    """

    name: str
    genre: str
    description: str = ""
    tracks: list[TrackMixPreset] = field(default_factory=list)
    master: MasterMixPreset = field(default_factory=MasterMixPreset)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to plain dict."""
        return {
            "name": self.name,
            "genre": self.genre,
            "description": self.description,
            "tracks": [t.to_dict() for t in self.tracks],
            "master": self.master.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MixPreset:
        """Deserialize from plain dict."""
        tracks = [TrackMixPreset.from_dict(t) for t in data.get("tracks", [])]
        master = MasterMixPreset.from_dict(data.get("master", {}))
        return cls(
            name=data["name"],
            genre=data.get("genre", "pop"),
            description=data.get("description", ""),
            tracks=tracks,
            master=master,
        )

    @property
    def track_types(self) -> list[str]:
        """List of track types covered by this preset."""
        return [t.track_type for t in self.tracks]


# ── Pre-defined Mix Presets ──────────────────────────────────────────────

_CLEAN_POP = MixPreset(
    name="Clean Pop",
    genre="pop",
    description="Bright vocals + compression + short reverb. Clean, modern pop sound.",
    tracks=[
        TrackMixPreset("vocals", [
            EffectPreset("VC-EQ", {"high_shelf_db": 3, "low_cut_hz": 80}),
            EffectPreset("VC-Comp", {"threshold": -18, "ratio": 3, "attack": 5, "release": 50}),
            EffectPreset("VC-Reverb", {"wet": 0.15, "room_size": 0.3, "damping": 0.7}),
            EffectPreset("VC-Limiter", {"ceiling": -1}),
        ], volume_db=-3.0, pan=0.0),
        TrackMixPreset("drums", [
            EffectPreset("VC-EQ", {"low_cut_hz": 40, "high_shelf_db": 1}),
            EffectPreset("VC-Comp", {"threshold": -10, "ratio": 4, "attack": 3, "release": 30}),
        ], volume_db=-6.0, pan=0.0),
        TrackMixPreset("bass", [
            EffectPreset("VC-EQ", {"low_shelf_db": 2, "high_cut_hz": 200}),
            EffectPreset("VC-Comp", {"threshold": -12, "ratio": 4, "attack": 10, "release": 80}),
        ], volume_db=-6.0, pan=0.0),
        TrackMixPreset("guitar", [
            EffectPreset("VC-EQ", {"high_shelf_db": 1}),
            EffectPreset("VC-Reverb", {"wet": 0.2, "room_size": 0.4}),
        ], volume_db=-9.0, pan=-0.2),
        TrackMixPreset("keys", [
            EffectPreset("VC-EQ", {"high_shelf_db": 2}),
            EffectPreset("VC-Reverb", {"wet": 0.25, "room_size": 0.5}),
        ], volume_db=-9.0, pan=0.2),
        TrackMixPreset("synth", [
            EffectPreset("VC-EQ", {}),
            EffectPreset("VC-Delay", {"time_ms": 250, "feedback": 0.2}),
            EffectPreset("VC-Reverb", {"wet": 0.2, "room_size": 0.4}),
        ], volume_db=-9.0, pan=0.1),
        TrackMixPreset("strings", [
            EffectPreset("VC-EQ", {"high_shelf_db": -1}),
            EffectPreset("VC-Reverb", {"wet": 0.3, "room_size": 0.7}),
        ], volume_db=-12.0, pan=0.0),
    ],
    master=MasterMixPreset([
        EffectPreset("VC-EQ", {"high_shelf_db": 1}),
        EffectPreset("VC-Comp", {"threshold": -14, "ratio": 2, "attack": 10, "release": 100}),
        EffectPreset("VC-Limiter", {"ceiling": -1}),
    ], volume_db=0.0, target_lufs=-14.0),
)

_WARM_VINTAGE = MixPreset(
    name="Warm Vintage",
    genre="rock",
    description="Warm EQ + tape saturation + long reverb. Vintage analog warmth.",
    tracks=[
        TrackMixPreset("vocals", [
            EffectPreset("VC-EQ", {"low_shelf_db": 2, "high_shelf_db": -2, "low_cut_hz": 80}),
            EffectPreset("VC-Comp", {"threshold": -20, "ratio": 3, "attack": 10, "release": 80}),
            EffectPreset("VC-Reverb", {"wet": 0.25, "room_size": 0.6, "damping": 0.4}),
            EffectPreset("VC-Limiter", {"ceiling": -1}),
        ], volume_db=-3.0, pan=0.0),
        TrackMixPreset("drums", [
            EffectPreset("VC-EQ", {"low_shelf_db": 3, "high_shelf_db": -2}),
            EffectPreset("VC-Comp", {"threshold": -8, "ratio": 3, "attack": 5, "release": 60}),
        ], volume_db=-6.0, pan=0.0),
        TrackMixPreset("bass", [
            EffectPreset("VC-EQ", {"low_shelf_db": 3}),
            EffectPreset("VC-Comp", {"threshold": -10, "ratio": 4, "attack": 15, "release": 100}),
        ], volume_db=-6.0, pan=0.0),
        TrackMixPreset("guitar", [
            EffectPreset("VC-EQ", {"low_shelf_db": 1, "high_shelf_db": -1}),
            EffectPreset("VC-Reverb", {"wet": 0.3, "room_size": 0.6, "damping": 0.3}),
        ], volume_db=-8.0, pan=-0.3),
        TrackMixPreset("keys", [
            EffectPreset("VC-EQ", {"low_shelf_db": 2}),
            EffectPreset("VC-Reverb", {"wet": 0.3, "room_size": 0.7}),
        ], volume_db=-10.0, pan=0.3),
        TrackMixPreset("synth", [
            EffectPreset("VC-EQ", {"low_shelf_db": 2, "high_shelf_db": -2}),
            EffectPreset("VC-Reverb", {"wet": 0.25, "room_size": 0.5, "damping": 0.4}),
        ], volume_db=-10.0, pan=0.0),
        TrackMixPreset("strings", [
            EffectPreset("VC-EQ", {"low_shelf_db": 2, "high_shelf_db": -3}),
            EffectPreset("VC-Reverb", {"wet": 0.4, "room_size": 0.8, "damping": 0.3}),
        ], volume_db=-12.0, pan=0.0),
    ],
    master=MasterMixPreset([
        EffectPreset("VC-EQ", {"low_shelf_db": 2, "high_shelf_db": -1}),
        EffectPreset("VC-Comp", {"threshold": -12, "ratio": 2, "attack": 20, "release": 150}),
        EffectPreset("VC-Limiter", {"ceiling": -1}),
    ], volume_db=0.0, target_lufs=-14.0),
)

_PUNCHY_EDM = MixPreset(
    name="Punchy EDM",
    genre="edm",
    description="Multiband comp + sidechain + big reverb. Punchy, club-ready sound.",
    tracks=[
        TrackMixPreset("vocals", [
            EffectPreset("VC-EQ", {"high_shelf_db": 4, "low_cut_hz": 100}),
            EffectPreset("VC-Comp", {"threshold": -15, "ratio": 4, "attack": 2, "release": 30}),
            EffectPreset("VC-Reverb", {"wet": 0.1, "room_size": 0.3}),
            EffectPreset("VC-Delay", {"time_ms": 125, "feedback": 0.15}),
            EffectPreset("VC-Limiter", {"ceiling": -1}),
        ], volume_db=-3.0, pan=0.0),
        TrackMixPreset("drums", [
            EffectPreset("VC-EQ", {"low_cut_hz": 30, "high_shelf_db": 2}),
            EffectPreset("VC-Comp", {"threshold": -6, "ratio": 5, "attack": 1, "release": 20}),
            EffectPreset("VC-Limiter", {"ceiling": -0.5}),
        ], volume_db=-3.0, pan=0.0),
        TrackMixPreset("bass", [
            EffectPreset("VC-EQ", {"low_shelf_db": 3, "high_cut_hz": 150}),
            EffectPreset("VC-Comp", {"threshold": -8, "ratio": 6, "attack": 2, "release": 40}),
        ], volume_db=-4.0, pan=0.0),
        TrackMixPreset("guitar", [
            EffectPreset("VC-EQ", {"low_cut_hz": 150}),
            EffectPreset("VC-Delay", {"time_ms": 250, "feedback": 0.3}),
            EffectPreset("VC-Reverb", {"wet": 0.15, "room_size": 0.5}),
        ], volume_db=-12.0, pan=0.0),
        TrackMixPreset("keys", [
            EffectPreset("VC-EQ", {"low_cut_hz": 120, "high_shelf_db": 2}),
            EffectPreset("VC-Reverb", {"wet": 0.2, "room_size": 0.6}),
        ], volume_db=-9.0, pan=0.0),
        TrackMixPreset("synth", [
            EffectPreset("VC-EQ", {"low_cut_hz": 100}),
            EffectPreset("VC-Delay", {"time_ms": 375, "feedback": 0.25}),
            EffectPreset("VC-Reverb", {"wet": 0.25, "room_size": 0.7}),
        ], volume_db=-6.0, pan=0.0),
        TrackMixPreset("strings", [
            EffectPreset("VC-EQ", {"high_shelf_db": -2}),
            EffectPreset("VC-Reverb", {"wet": 0.3, "room_size": 0.8}),
        ], volume_db=-15.0, pan=0.0),
    ],
    master=MasterMixPreset([
        EffectPreset("VC-EQ", {"low_shelf_db": 1, "high_shelf_db": 2}),
        EffectPreset("VC-Comp", {"threshold": -10, "ratio": 3, "attack": 5, "release": 50}),
        EffectPreset("VC-Limiter", {"ceiling": -1}),
    ], volume_db=0.0, target_lufs=-14.0),
)

_TIGHT_HIPHOP = MixPreset(
    name="Tight Hip-Hop",
    genre="hiphop",
    description="HPF + heavy comp + short delay. Tight, punchy hip-hop sound.",
    tracks=[
        TrackMixPreset("vocals", [
            EffectPreset("VC-EQ", {"low_cut_hz": 100, "high_shelf_db": 3}),
            EffectPreset("VC-Comp", {"threshold": -16, "ratio": 4, "attack": 3, "release": 40}),
            EffectPreset("VC-Delay", {"time_ms": 125, "feedback": 0.1}),
            EffectPreset("VC-Limiter", {"ceiling": -1}),
        ], volume_db=-3.0, pan=0.0),
        TrackMixPreset("drums", [
            EffectPreset("VC-EQ", {"low_cut_hz": 30, "high_shelf_db": 2}),
            EffectPreset("VC-Comp", {"threshold": -8, "ratio": 5, "attack": 1, "release": 25}),
        ], volume_db=-4.0, pan=0.0),
        TrackMixPreset("bass", [
            EffectPreset("VC-EQ", {"low_shelf_db": 4}),
            EffectPreset("VC-Comp", {"threshold": -10, "ratio": 6, "attack": 5, "release": 50}),
        ], volume_db=-5.0, pan=0.0),
        TrackMixPreset("guitar", [
            EffectPreset("VC-EQ", {"low_cut_hz": 200}),
            EffectPreset("VC-Delay", {"time_ms": 250, "feedback": 0.2}),
        ], volume_db=-12.0, pan=-0.3),
        TrackMixPreset("keys", [
            EffectPreset("VC-EQ", {"low_cut_hz": 120, "high_shelf_db": 1}),
            EffectPreset("VC-Reverb", {"wet": 0.1, "room_size": 0.3}),
        ], volume_db=-10.0, pan=0.2),
        TrackMixPreset("synth", [
            EffectPreset("VC-EQ", {"low_cut_hz": 100}),
            EffectPreset("VC-Delay", {"time_ms": 250, "feedback": 0.2}),
            EffectPreset("VC-Reverb", {"wet": 0.1, "room_size": 0.3}),
        ], volume_db=-8.0, pan=0.0),
        TrackMixPreset("strings", [
            EffectPreset("VC-EQ", {"low_cut_hz": 200, "high_shelf_db": -2}),
            EffectPreset("VC-Reverb", {"wet": 0.15, "room_size": 0.4}),
        ], volume_db=-14.0, pan=0.0),
    ],
    master=MasterMixPreset([
        EffectPreset("VC-EQ", {"low_shelf_db": 2, "high_shelf_db": 1}),
        EffectPreset("VC-Comp", {"threshold": -12, "ratio": 3, "attack": 5, "release": 60}),
        EffectPreset("VC-Limiter", {"ceiling": -1}),
    ], volume_db=0.0, target_lufs=-14.0),
)

_AIRY_BALLAD = MixPreset(
    name="Airy Ballad",
    genre="rnb",
    description="Air band boost + light comp + hall reverb. Airy, emotional ballad sound.",
    tracks=[
        TrackMixPreset("vocals", [
            EffectPreset("VC-EQ", {"high_shelf_db": 4, "low_cut_hz": 60}),
            EffectPreset("VC-Comp", {"threshold": -22, "ratio": 2, "attack": 10, "release": 80}),
            EffectPreset("VC-Reverb", {"wet": 0.3, "room_size": 0.8, "damping": 0.5}),
            EffectPreset("VC-Limiter", {"ceiling": -1}),
        ], volume_db=-2.0, pan=0.0),
        TrackMixPreset("drums", [
            EffectPreset("VC-EQ", {"low_cut_hz": 50, "high_shelf_db": -1}),
            EffectPreset("VC-Comp", {"threshold": -15, "ratio": 2, "attack": 10, "release": 80}),
        ], volume_db=-9.0, pan=0.0),
        TrackMixPreset("bass", [
            EffectPreset("VC-EQ", {"low_shelf_db": 1}),
            EffectPreset("VC-Comp", {"threshold": -14, "ratio": 3, "attack": 15, "release": 100}),
        ], volume_db=-8.0, pan=0.0),
        TrackMixPreset("guitar", [
            EffectPreset("VC-EQ", {"high_shelf_db": 2}),
            EffectPreset("VC-Reverb", {"wet": 0.35, "room_size": 0.8}),
        ], volume_db=-9.0, pan=-0.2),
        TrackMixPreset("keys", [
            EffectPreset("VC-EQ", {"high_shelf_db": 3}),
            EffectPreset("VC-Reverb", {"wet": 0.4, "room_size": 0.9}),
        ], volume_db=-7.0, pan=0.2),
        TrackMixPreset("synth", [
            EffectPreset("VC-EQ", {"high_shelf_db": 2}),
            EffectPreset("VC-Reverb", {"wet": 0.3, "room_size": 0.7}),
        ], volume_db=-10.0, pan=0.0),
        TrackMixPreset("strings", [
            EffectPreset("VC-EQ", {"high_shelf_db": 2}),
            EffectPreset("VC-Reverb", {"wet": 0.45, "room_size": 0.9, "damping": 0.4}),
        ], volume_db=-9.0, pan=0.0),
    ],
    master=MasterMixPreset([
        EffectPreset("VC-EQ", {"high_shelf_db": 1}),
        EffectPreset("VC-Comp", {"threshold": -16, "ratio": 2, "attack": 15, "release": 120}),
        EffectPreset("VC-Limiter", {"ceiling": -1}),
    ], volume_db=0.0, target_lufs=-14.0),
)

_LOFI_CHILL = MixPreset(
    name="Lo-fi Chill",
    genre="lofi",
    description="Low-pass filter + noise + tape wobble. Warm, nostalgic lo-fi sound.",
    tracks=[
        TrackMixPreset("vocals", [
            EffectPreset("VC-EQ", {"high_shelf_db": -4, "low_shelf_db": 2, "low_cut_hz": 100}),
            EffectPreset("VC-Comp", {"threshold": -20, "ratio": 3, "attack": 15, "release": 100}),
            EffectPreset("VC-Reverb", {"wet": 0.2, "room_size": 0.4, "damping": 0.3}),
            EffectPreset("VC-Limiter", {"ceiling": -1}),
        ], volume_db=-4.0, pan=0.0),
        TrackMixPreset("drums", [
            EffectPreset("VC-EQ", {"high_shelf_db": -6, "low_shelf_db": 3}),
            EffectPreset("VC-Comp", {"threshold": -12, "ratio": 3, "attack": 5, "release": 60}),
        ], volume_db=-7.0, pan=0.0),
        TrackMixPreset("bass", [
            EffectPreset("VC-EQ", {"low_shelf_db": 4, "high_shelf_db": -4}),
            EffectPreset("VC-Comp", {"threshold": -10, "ratio": 4, "attack": 10, "release": 80}),
        ], volume_db=-6.0, pan=0.0),
        TrackMixPreset("guitar", [
            EffectPreset("VC-EQ", {"high_shelf_db": -5, "low_shelf_db": 2}),
            EffectPreset("VC-Reverb", {"wet": 0.25, "room_size": 0.5, "damping": 0.3}),
        ], volume_db=-8.0, pan=-0.2),
        TrackMixPreset("keys", [
            EffectPreset("VC-EQ", {"high_shelf_db": -3, "low_shelf_db": 2}),
            EffectPreset("VC-Reverb", {"wet": 0.3, "room_size": 0.5, "damping": 0.3}),
        ], volume_db=-6.0, pan=0.1),
        TrackMixPreset("synth", [
            EffectPreset("VC-EQ", {"high_shelf_db": -4, "low_shelf_db": 1}),
            EffectPreset("VC-Reverb", {"wet": 0.2, "room_size": 0.4, "damping": 0.3}),
        ], volume_db=-10.0, pan=0.0),
        TrackMixPreset("strings", [
            EffectPreset("VC-EQ", {"high_shelf_db": -5, "low_shelf_db": 2}),
            EffectPreset("VC-Reverb", {"wet": 0.35, "room_size": 0.6, "damping": 0.3}),
        ], volume_db=-12.0, pan=0.0),
    ],
    master=MasterMixPreset([
        EffectPreset("VC-EQ", {"high_shelf_db": -2, "low_shelf_db": 2}),
        EffectPreset("VC-Comp", {"threshold": -14, "ratio": 2, "attack": 20, "release": 150}),
        EffectPreset("VC-Limiter", {"ceiling": -1}),
    ], volume_db=0.0, target_lufs=-16.0),
)


# ── Registry ─────────────────────────────────────────────────────────────

MIX_PRESET_REGISTRY: dict[str, MixPreset] = {
    "clean-pop": _CLEAN_POP,
    "warm-vintage": _WARM_VINTAGE,
    "punchy-edm": _PUNCHY_EDM,
    "tight-hiphop": _TIGHT_HIPHOP,
    "airy-ballad": _AIRY_BALLAD,
    "lofi-chill": _LOFI_CHILL,
}


def get_mix_preset(name: str) -> MixPreset | None:
    """Get a mix preset by registry key.

    Args:
        name: Preset registry key (e.g. "clean-pop").

    Returns:
        MixPreset or None if not found.
    """
    return MIX_PRESET_REGISTRY.get(name)


def list_mix_presets() -> list[str]:
    """List all available mix preset registry keys."""
    return sorted(MIX_PRESET_REGISTRY.keys())


def list_mix_presets_by_genre(genre: str) -> list[str]:
    """List mix preset keys filtered by genre.

    Args:
        genre: Genre tag to filter by.

    Returns:
        List of matching preset keys.
    """
    return sorted(k for k, v in MIX_PRESET_REGISTRY.items() if v.genre == genre)


def suggest_mix_preset(genre: str, track_types: list[str] | None = None) -> MixPreset | None:
    """Suggest a mix preset based on genre and track types.

    Args:
        genre: Primary genre.
        track_types: Optional list of track types to match.

    Returns:
        Best matching MixPreset or None.
    """
    # Direct genre match first
    genre_matches = list_mix_presets_by_genre(genre)
    if genre_matches:
        return MIX_PRESET_REGISTRY[genre_matches[0]]

    # Fallback: check track type coverage
    if track_types:
        best_key = None
        best_score = -1
        for key, preset in MIX_PRESET_REGISTRY.items():
            preset_types = set(preset.track_types)
            requested_types = set(track_types)
            overlap = len(preset_types & requested_types)
            if overlap > best_score:
                best_score = overlap
                best_key = key
        if best_key:
            return MIX_PRESET_REGISTRY[best_key]

    # Default fallback
    return MIX_PRESET_REGISTRY.get("clean-pop")
