"""
templates.py — Pre-defined arrangement structure templates (Phase 12).

Provides genre-specific arrangement templates with section sequences,
track specifications, energy curves, and recommended BPM ranges.

Built-in templates (8):
    - Pop Standard
    - EDM Drop
    - Rock
    - Hip-Hop
    - R&B Ballad
    - Progressive
    - Lo-fi
    - Orchestral

Usage:
    from vcmix.arrangement.templates import get_template, list_templates

    for name in list_templates():
        tmpl = get_template(name)
        print(f"{tmpl.name}: {len(tmpl.structure)} sections, BPM {tmpl.bpm_range}")
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# ── Data Models ──────────────────────────────────────────────────────────

@dataclass
class TrackSpec:
    """Track specification within an arrangement section.

    Attributes:
        name: Track display name (e.g. "Lead Vocal").
        type: Track type — midi, sampler, or audio.
        instrument: Instrument name (e.g. "Grand Piano").
        effects: Recommended effect chain as list of dicts.
    """

    name: str
    type: str = "audio"
    instrument: str = ""
    effects: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to plain dict."""
        result: dict[str, Any] = {"name": self.name, "type": self.type}
        if self.instrument:
            result["instrument"] = self.instrument
        if self.effects:
            result["effects"] = list(self.effects)
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TrackSpec:
        """Deserialize from plain dict."""
        return cls(
            name=data["name"],
            type=data.get("type", "audio"),
            instrument=data.get("instrument", ""),
            effects=data.get("effects", []),
        )


@dataclass
class Section:
    """A section within an arrangement template.

    Attributes:
        name: Section name (e.g. "intro", "verse", "chorus").
        duration_bars: Length in bars.
        tracks: Track specs active in this section.
        energy: Energy level 0-1 (0=quiet, 1=loud).
    """

    name: str
    duration_bars: int = 8
    tracks: list[TrackSpec] = field(default_factory=list)
    energy: float = 0.5

    def to_dict(self) -> dict[str, Any]:
        """Serialize to plain dict."""
        return {
            "name": self.name,
            "duration_bars": self.duration_bars,
            "tracks": [t.to_dict() for t in self.tracks],
            "energy": self.energy,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Section:
        """Deserialize from plain dict."""
        tracks = [TrackSpec.from_dict(t) for t in data.get("tracks", [])]
        return cls(
            name=data["name"],
            duration_bars=data.get("duration_bars", 8),
            tracks=tracks,
            energy=data.get("energy", 0.5),
        )


@dataclass
class ArrangementTemplate:
    """Complete arrangement structure template.

    Attributes:
        name: Display name (e.g. "Pop Standard").
        genre: Genre tag (pop/rock/edm/hiphop/rnb/ballad/progressive/lofi/orchestral).
        bpm_range: Recommended BPM range as (min, max).
        structure: Ordered list of sections.
        description: Human-readable description.
        default_key: Default musical key suggestion.
    """

    name: str
    genre: str
    bpm_range: tuple[int, int] = (120, 128)
    structure: list[Section] = field(default_factory=list)
    description: str = ""
    default_key: str = "C"

    def to_dict(self) -> dict[str, Any]:
        """Serialize to plain dict."""
        return {
            "name": self.name,
            "genre": self.genre,
            "bpm_range": list(self.bpm_range),
            "structure": [s.to_dict() for s in self.structure],
            "description": self.description,
            "default_key": self.default_key,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ArrangementTemplate:
        """Deserialize from plain dict."""
        bpm = data.get("bpm_range", [120, 128])
        sections = [Section.from_dict(s) for s in data.get("structure", [])]
        return cls(
            name=data["name"],
            genre=data.get("genre", "pop"),
            bpm_range=(int(bpm[0]), int(bpm[1])),
            structure=sections,
            description=data.get("description", ""),
            default_key=data.get("default_key", "C"),
        )

    @property
    def total_bars(self) -> int:
        """Total number of bars in the arrangement."""
        return sum(s.duration_bars for s in self.structure)

    @property
    def section_names(self) -> list[str]:
        """List of section names in order."""
        return [s.name for s in self.structure]


# ── Helper: common track specs ───────────────────────────────────────────

def _vocals(name: str = "Lead Vocal") -> TrackSpec:
    return TrackSpec(name=name, type="audio", instrument="Vocal",
                     effects=[{"name": "vc-eq", "params": {"high_shelf_db": 2}},
                              {"name": "vc-comp", "params": {"threshold": -18, "ratio": 3}},
                              {"name": "vc-reverb", "params": {"wet": 0.15, "room_size": 0.5}}])

def _drums(name: str = "Drums") -> TrackSpec:
    return TrackSpec(name=name, type="sampler", instrument="Drum Kit",
                     effects=[{"name": "vc-comp", "params": {"threshold": -12, "ratio": 4, "attack": 5}},
                              {"name": "vc-eq", "params": {"low_cut_hz": 40}}])

def _bass(name: str = "Bass") -> TrackSpec:
    return TrackSpec(name=name, type="midi", instrument="Bass",
                     effects=[{"name": "vc-comp", "params": {"threshold": -15, "ratio": 4}},
                              {"name": "vc-eq", "params": {"low_shelf_db": 2}}])

def _guitar(name: str = "Guitar") -> TrackSpec:
    return TrackSpec(name=name, type="audio", instrument="Guitar",
                     effects=[{"name": "vc-eq", "params": {}},
                              {"name": "vc-reverb", "params": {"wet": 0.2, "room_size": 0.4}}])

def _keys(name: str = "Keys") -> TrackSpec:
    return TrackSpec(name=name, type="midi", instrument="Piano",
                     effects=[{"name": "vc-eq", "params": {}},
                              {"name": "vc-reverb", "params": {"wet": 0.25, "room_size": 0.6}}])

def _synth(name: str = "Synth") -> TrackSpec:
    return TrackSpec(name=name, type="midi", instrument="Synth",
                     effects=[{"name": "vc-eq", "params": {}},
                              {"name": "vc-delay", "params": {"time_ms": 250, "feedback": 0.3}},
                              {"name": "vc-reverb", "params": {"wet": 0.2}}])

def _strings(name: str = "Strings") -> TrackSpec:
    return TrackSpec(name=name, type="midi", instrument="Strings",
                     effects=[{"name": "vc-eq", "params": {"high_shelf_db": -2}},
                              {"name": "vc-reverb", "params": {"wet": 0.35, "room_size": 0.8}}])

def _pad(name: str = "Pad") -> TrackSpec:
    return TrackSpec(name=name, type="midi", instrument="Pad",
                     effects=[{"name": "vc-reverb", "params": {"wet": 0.4, "room_size": 0.7}}])

def _bgv(name: str = "BGV") -> TrackSpec:
    return TrackSpec(name=name, type="audio", instrument="Backing Vocal",
                     effects=[{"name": "vc-comp", "params": {"threshold": -20, "ratio": 3}},
                              {"name": "vc-reverb", "params": {"wet": 0.2}}])

def _fx(name: str = "FX") -> TrackSpec:
    return TrackSpec(name=name, type="audio", instrument="FX",
                     effects=[{"name": "vc-reverb", "params": {"wet": 0.6, "room_size": 0.9}}])


# ── Pre-defined Templates ────────────────────────────────────────────────

_POP = ArrangementTemplate(
    name="Pop Standard",
    genre="pop",
    bpm_range=(118, 132),
    description="Standard pop song: Intro → Verse → Pre-Chorus → Chorus → Verse → Pre-Chorus → Chorus → Bridge → Chorus → Outro",
    default_key="C",
    structure=[
        Section("intro", 8, [_keys(), _synth("Synth Pad")], 0.3),
        Section("verse1", 16, [_vocals(), _keys(), _bass(), _drums()], 0.4),
        Section("prechorus1", 8, [_vocals(), _keys(), _bass(), _drums(), _synth()], 0.6),
        Section("chorus1", 16, [_vocals(), _bgv(), _keys(), _bass(), _drums(), _synth(), _guitar()], 0.9),
        Section("verse2", 16, [_vocals(), _keys(), _bass(), _drums()], 0.45),
        Section("prechorus2", 8, [_vocals(), _keys(), _bass(), _drums(), _synth()], 0.65),
        Section("chorus2", 16, [_vocals(), _bgv(), _keys(), _bass(), _drums(), _synth(), _guitar()], 0.95),
        Section("bridge", 8, [_vocals(), _keys(), _synth("Synth Pad"), _strings()], 0.5),
        Section("chorus3", 16, [_vocals(), _bgv(), _keys(), _bass(), _drums(), _synth(), _guitar(), _strings()], 1.0),
        Section("outro", 8, [_keys(), _synth("Synth Pad")], 0.25),
    ],
)

_EDM = ArrangementTemplate(
    name="EDM Drop",
    genre="edm",
    bpm_range=(126, 140),
    description="Electronic dance: Intro → Buildup → Drop → Break → Buildup → Drop → Outro",
    default_key="Am",
    structure=[
        Section("intro", 16, [_synth("Atmosphere"), _pad("Ambient Pad"), _drums("Kick")], 0.2),
        Section("buildup1", 16, [_synth("Riser"), _drums(), _bass("Sub Bass"), _fx("Riser FX")], 0.5),
        Section("drop1", 16, [_synth("Lead Synth"), _bass("Sub Bass"), _drums(), _synth("Chord Stab"), _fx("Impact")], 1.0),
        Section("break", 16, [_synth("Ambient Pad"), _vocals("Vocal Chop"), _keys()], 0.3),
        Section("buildup2", 16, [_synth("Riser"), _drums(), _bass("Sub Bass"), _fx("Riser FX")], 0.6),
        Section("drop2", 16, [_synth("Lead Synth"), _bass("Sub Bass"), _drums(), _synth("Chord Stab"), _fx("Impact")], 1.0),
        Section("outro", 8, [_synth("Atmosphere"), _pad("Ambient Pad")], 0.15),
    ],
)

_ROCK = ArrangementTemplate(
    name="Rock",
    genre="rock",
    bpm_range=(110, 140),
    description="Rock song: Intro → Verse → Chorus → Verse → Chorus → Solo → Chorus → Outro",
    default_key="E",
    structure=[
        Section("intro", 8, [_guitar("Rhythm Guitar"), _bass(), _drums()], 0.5),
        Section("verse1", 16, [_vocals(), _guitar("Rhythm Guitar"), _bass(), _drums()], 0.5),
        Section("chorus1", 16, [_vocals(), _bgv(), _guitar("Rhythm Guitar"), _guitar("Lead Guitar"), _bass(), _drums()], 0.85),
        Section("verse2", 16, [_vocals(), _guitar("Rhythm Guitar"), _bass(), _drums()], 0.55),
        Section("chorus2", 16, [_vocals(), _bgv(), _guitar("Rhythm Guitar"), _guitar("Lead Guitar"), _bass(), _drums()], 0.9),
        Section("solo", 16, [_guitar("Lead Guitar"), _guitar("Rhythm Guitar"), _bass(), _drums()], 0.8),
        Section("chorus3", 16, [_vocals(), _bgv(), _guitar("Rhythm Guitar"), _guitar("Lead Guitar"), _bass(), _drums()], 1.0),
        Section("outro", 8, [_guitar("Rhythm Guitar"), _bass(), _drums()], 0.4),
    ],
)

_HIPHOP = ArrangementTemplate(
    name="Hip-Hop",
    genre="hiphop",
    bpm_range=(80, 110),
    description="Hip-hop: Intro → Verse → Hook → Verse → Hook → Bridge → Hook → Outro",
    default_key="Cm",
    structure=[
        Section("intro", 8, [_drums("808 Kit"), _synth("Trap Synth"), _bass("808 Bass")], 0.3),
        Section("verse1", 16, [_vocals("Rap Vocal"), _drums("808 Kit"), _bass("808 Bass"), _synth("Trap Synth")], 0.6),
        Section("hook1", 8, [_vocals("Rap Vocal"), _bgv("Hook Vocal"), _drums("808 Kit"), _bass("808 Bass"), _synth("Trap Synth")], 0.85),
        Section("verse2", 16, [_vocals("Rap Vocal"), _drums("808 Kit"), _bass("808 Bass"), _synth("Trap Synth")], 0.65),
        Section("hook2", 8, [_vocals("Rap Vocal"), _bgv("Hook Vocal"), _drums("808 Kit"), _bass("808 Bass"), _synth("Trap Synth")], 0.9),
        Section("bridge", 8, [_vocals("Rap Vocal"), _synth("Ambient Pad"), _fx("Scratch")], 0.4),
        Section("hook3", 8, [_vocals("Rap Vocal"), _bgv("Hook Vocal"), _drums("808 Kit"), _bass("808 Bass"), _synth("Trap Synth")], 1.0),
        Section("outro", 8, [_drums("808 Kit"), _synth("Trap Synth")], 0.2),
    ],
)

_RNB = ArrangementTemplate(
    name="R&B Ballad",
    genre="rnb",
    bpm_range=(60, 85),
    description="R&B ballad: Intro → Verse → Chorus → Verse → Chorus → Bridge → Chorus → Outro",
    default_key="Db",
    structure=[
        Section("intro", 8, [_keys("Rhodes"), _strings(), _pad("Warm Pad")], 0.25),
        Section("verse1", 16, [_vocals("R&B Vocal"), _keys("Rhodes"), _bass(), _drums("Light Drums")], 0.4),
        Section("chorus1", 16, [_vocals("R&B Vocal"), _bgv("Harmonies"), _keys("Rhodes"), _bass(), _drums("Light Drums"), _strings()], 0.75),
        Section("verse2", 16, [_vocals("R&B Vocal"), _keys("Rhodes"), _bass(), _drums("Light Drums")], 0.45),
        Section("chorus2", 16, [_vocals("R&B Vocal"), _bgv("Harmonies"), _keys("Rhodes"), _bass(), _drums("Light Drums"), _strings()], 0.8),
        Section("bridge", 8, [_vocals("R&B Vocal"), _keys("Rhodes"), _strings(), _pad("Warm Pad")], 0.5),
        Section("chorus3", 16, [_vocals("R&B Vocal"), _bgv("Harmonies"), _keys("Rhodes"), _bass(), _drums("Light Drums"), _strings(), _guitar()], 0.9),
        Section("outro", 8, [_keys("Rhodes"), _strings(), _pad("Warm Pad")], 0.2),
    ],
)

_PROGRESSIVE = ArrangementTemplate(
    name="Progressive",
    genre="progressive",
    bpm_range=(120, 138),
    description="Progressive build: Intro → Rise → Peak → Fall → Rise → Peak → Outro",
    default_key="Am",
    structure=[
        Section("intro", 16, [_synth("Ambient Pad"), _keys(), _fx("Texture")], 0.15),
        Section("rise1", 16, [_synth("Arp"), _bass(), _drums(), _keys(), _fx("Riser")], 0.5),
        Section("peak1", 16, [_synth("Lead Synth"), _bass(), _drums(), _synth("Arp"), _pad("Stab")], 0.9),
        Section("fall", 16, [_synth("Ambient Pad"), _keys(), _fx("Texture")], 0.3),
        Section("rise2", 16, [_synth("Arp"), _bass(), _drums(), _keys(), _fx("Riser")], 0.65),
        Section("peak2", 16, [_synth("Lead Synth"), _bass(), _drums(), _synth("Arp"), _pad("Stab"), _fx("Impact")], 1.0),
        Section("outro", 8, [_synth("Ambient Pad"), _fx("Texture")], 0.1),
    ],
)

_LOFI = ArrangementTemplate(
    name="Lo-fi",
    genre="lofi",
    bpm_range=(70, 90),
    description="Lo-fi chill: Intro → Loop → Break → Loop → Outro",
    default_key="F",
    structure=[
        Section("intro", 8, [_keys("Lo-fi Keys"), _fx("Vinyl Noise")], 0.2),
        Section("loop1", 16, [_keys("Lo-fi Keys"), _bass("Lo-fi Bass"), _drums("Lo-fi Drums"), _fx("Vinyl Noise")], 0.5),
        Section("break", 8, [_keys("Lo-fi Keys"), _fx("Vinyl Noise"), _synth("Ambient Pad")], 0.25),
        Section("loop2", 16, [_keys("Lo-fi Keys"), _bass("Lo-fi Bass"), _drums("Lo-fi Drums"), _fx("Vinyl Noise"), _guitar("Lo-fi Guitar")], 0.55),
        Section("outro", 8, [_keys("Lo-fi Keys"), _fx("Vinyl Noise")], 0.15),
    ],
)

_ORCHESTRAL = ArrangementTemplate(
    name="Orchestral",
    genre="orchestral",
    bpm_range=(60, 100),
    description="Orchestral: Intro → Theme A → Development → Theme B → Climax → Coda",
    default_key="Dm",
    structure=[
        Section("intro", 16, [_strings("Strings Section"), _pad("Orchestral Pad")], 0.2),
        Section("theme_a", 16, [_strings("Strings Section"), _keys("Orchestral Piano"), _bass("Contrabass"), _drums("Timpani")], 0.45),
        Section("development", 16, [_strings("Strings Section"), _keys("Orchestral Piano"), _bass("Contrabass"), _drums("Timpani"), _synth("Brass")], 0.6),
        Section("theme_b", 16, [_strings("Strings Section"), _keys("Orchestral Piano"), _bass("Contrabass"), _synth("Woodwinds")], 0.5),
        Section("climax", 16, [_strings("Full Orchestra"), _keys("Orchestral Piano"), _bass("Contrabass"), _drums("Timpani"), _synth("Brass"), _synth("Woodwinds")], 1.0),
        Section("coda", 8, [_strings("Strings Section"), _pad("Orchestral Pad")], 0.15),
    ],
)


# ── Registry ─────────────────────────────────────────────────────────────

TEMPLATE_REGISTRY: dict[str, ArrangementTemplate] = {
    "pop-standard": _POP,
    "edm-drop": _EDM,
    "rock": _ROCK,
    "hiphop": _HIPHOP,
    "rnb-ballad": _RNB,
    "progressive": _PROGRESSIVE,
    "lofi": _LOFI,
    "orchestral": _ORCHESTRAL,
}


def get_template(name: str) -> ArrangementTemplate | None:
    """Get an arrangement template by registry key.

    Args:
        name: Template registry key (e.g. "pop-standard").

    Returns:
        ArrangementTemplate or None if not found.
    """
    return TEMPLATE_REGISTRY.get(name)


def list_templates() -> list[str]:
    """List all available template registry keys."""
    return sorted(TEMPLATE_REGISTRY.keys())


def list_templates_by_genre(genre: str) -> list[str]:
    """List template keys filtered by genre.

    Args:
        genre: Genre tag to filter by.

    Returns:
        List of matching template keys.
    """
    return sorted(k for k, v in TEMPLATE_REGISTRY.items() if v.genre == genre)
