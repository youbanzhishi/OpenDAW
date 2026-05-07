"""
parser.py — YAML project configuration parser for VCMix.

Parses the four-layer YAML structure:
    1. project  — metadata (name, bpm, sample_rate)
    2. track    — audio source + insert effect chain
    3. effect   — plugin name + parameters (supports BPM note values)
    4. master   — bus levels + master insert chain

BPM Note-Value Auto-Conversion:
    Any parameter value matching N/D, N/Dd, N/Dt pattern is auto-converted
    to milliseconds using the project BPM:
        "1/4"  → quarter note     = 60000 / BPM
        "1/8"  → eighth note      = 30000 / BPM
        "1/8d" → dotted eighth    = 45000 / BPM
        "1/8t" → eighth triplet   = 20000 / BPM

Pydantic models enforce type checking and provide clear validation errors.

Usage:
    from vcmix.config.parser import parse_project
    config = parse_project(Path("project.yaml"))

Dependencies: pyyaml>=6.0, pydantic>=2.0
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, field_validator

# ── BPM Note-Value Conversion ──────────────────────────────────────────────

_NOTE_RE = re.compile(r"^(\d+)/(\d+)([dt]?)\.?$")


def note_to_ms(bpm: float, note_value: str) -> float:
    """
    Convert a musical note value to milliseconds at the given BPM.

    Args:
        bpm: Beats per minute.
        note_value: Note string like "1/4", "1/8d", "1/16t".

    Returns:
        Duration in milliseconds (rounded to 1 decimal).

    Raises:
        ValueError: If note_value format is unrecognized.

    Examples:
        >>> note_to_ms(120, "1/4")
        500.0
        >>> note_to_ms(62, "1/8d")
        181.5
    """
    m = _NOTE_RE.match(note_value.strip())
    if not m:
        raise ValueError(f"Invalid note value: {note_value!r}")

    numerator = int(m.group(1))
    denominator = int(m.group(2))
    modifier = m.group(3)

    if denominator == 0:
        raise ValueError(f"Denominator cannot be zero: {note_value!r}")

    quarter_ms = 60000.0 / bpm
    base_ms = quarter_ms * (4.0 * numerator / denominator)

    if modifier == "d":
        base_ms *= 1.5
    elif modifier == "t":
        base_ms *= 2.0 / 3.0

    return round(base_ms, 1)


def is_note_value(value: Any) -> bool:
    """Check if a value looks like a BPM note value string."""
    return isinstance(value, str) and bool(_NOTE_RE.match(value.strip()))


def convert_note_values(params: dict[str, Any], bpm: float) -> dict[str, Any]:
    """
    Recursively convert note-value strings in a parameter dict to ms.

    Only converts values that match the N/D[d|t] pattern; numbers and
    other strings are left unchanged.
    """
    converted: dict[str, Any] = {}
    for key, val in params.items():
        if is_note_value(val):
            converted[key] = note_to_ms(bpm, val)
        elif isinstance(val, dict):
            converted[key] = convert_note_values(val, bpm)
        elif isinstance(val, list):
            converted[key] = [
                note_to_ms(bpm, v) if is_note_value(v)
                else convert_note_values(v, bpm) if isinstance(v, dict)
                else v
                for v in val
            ]
        else:
            converted[key] = val
    return converted


# ── Pydantic Models ────────────────────────────────────────────────────────

class EffectConfig(BaseModel):
    """A single effect/plugin in a track's insert chain."""
    name: str = Field(..., description="Plugin name, e.g. 'vc-reverb', 'vc-eq'")
    params: dict[str, Any] = Field(
        default_factory=dict,
        description="Plugin parameters (note values auto-converted to ms)"
    )


class TrackConfig(BaseModel):
    """A single audio track with its insert effect chain."""
    name: str = Field(..., description="Track name, e.g. 'vocal', 'accomp'")
    file: str = Field(..., description="Path to audio file (relative to project dir)")
    effects: list[EffectConfig] = Field(
        default_factory=list,
        description="Ordered insert effect chain"
    )
    volume: float = Field(default=1.0, ge=0.0, description="Track volume (linear, 1.0=unity)")
    mute: bool = Field(default=False, description="Mute this track")
    solo: bool = Field(default=False, description="Solo this track")


class MasterConfig(BaseModel):
    """Master bus configuration."""
    levels: dict[str, float] = Field(
        default_factory=dict,
        description="Track name -> level mapping, e.g. {'vocal': 0.8, 'accomp': 0.35}"
    )
    effects: list[EffectConfig] = Field(
        default_factory=list,
        description="Master insert effect chain"
    )
    output: str = Field(default="output.wav", description="Output file path")


class ProjectConfig(BaseModel):
    """Top-level VCMix project configuration."""
    name: str = Field(default="Untitled", description="Project name")
    bpm: float = Field(default=120.0, gt=0, description="Beats per minute")
    sample_rate: int = Field(default=44100, gt=0, description="Sample rate in Hz")
    tracks: list[TrackConfig] = Field(default_factory=list, description="Audio tracks")
    master: MasterConfig = Field(default_factory=MasterConfig, description="Master bus")

    @field_validator("bpm")
    @classmethod
    def normalize_bpm(cls, v: float) -> float:
        """Normalize BPM: if > 200, halve (librosa double-counts slow songs)."""
        if v > 200:
            v /= 2.0
        return v


# ── YAML Parse Entry Point ─────────────────────────────────────────────────

def parse_project(yaml_path: Path | str) -> ProjectConfig:
    """
    Parse a VCMix YAML project file into a validated ProjectConfig.

    Steps:
      1. Read YAML with UTF-8 encoding
      2. Validate structure via Pydantic models
      3. Auto-convert BPM note values to milliseconds

    Args:
        yaml_path: Path to the YAML project file.

    Returns:
        Validated ProjectConfig with note values converted.

    Raises:
        FileNotFoundError: If yaml_path doesn't exist.
        yaml.YAMLError: If YAML syntax is invalid.
        pydantic.ValidationError: If schema validation fails.
    """
    yaml_path = Path(yaml_path)
    if not yaml_path.exists():
        raise FileNotFoundError(f"Project file not found: {yaml_path}")

    raw = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("YAML root must be a mapping")

    bpm = float(raw.get("bpm", 120.0))

    # Convert note values in track effects
    for track in raw.get("tracks", []):
        for effect in track.get("effects", []):
            if "params" in effect and isinstance(effect["params"], dict):
                effect["params"] = convert_note_values(effect["params"], bpm)

    # Convert note values in master effects
    master = raw.get("master", {})
    for effect in master.get("effects", []):
        if "params" in effect and isinstance(effect["params"], dict):
            effect["params"] = convert_note_values(effect["params"], bpm)

    return ProjectConfig(**raw)
