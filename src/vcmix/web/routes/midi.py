"""
midi.py — /api/midi endpoints for VCMix Web UI (Phase 9).

Provides MIDI file scanning, parsing, and synthesizer listing.
Uses the same MidiParser and NoteScheduler as the CLI.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from vcmix.midi.midi_parser import MidiParser
from vcmix.midi.note_scheduler import list_synths

router = APIRouter()


# ── Shared parser instance ───────────────────────────────────────────────

_parser = MidiParser()


# ── Models ───────────────────────────────────────────────────────────────

class MidiParseRequest(BaseModel):
    """Request body for MIDI file parsing."""
    path: str = Field(..., description="Path to .mid file on the server")


class MidiParseResponse(BaseModel):
    """Response for MIDI file parsing."""
    bpm: float
    time_signature: str
    ticks_per_beat: int
    total_beats: float
    tracks: list[dict[str, Any]]
    track_count: int


# ── Endpoints ────────────────────────────────────────────────────────────

@router.get("/midi/scan")
async def scan_midi_files(
    directory: str = Query(default=".", description="Directory to scan for .mid files"),
):
    """
    Scan a directory for MIDI files.

    Returns a list of .mid file paths found in the specified directory.
    Recursively searches up to 3 levels deep.
    """
    scan_dir = Path(directory)
    if not scan_dir.exists():
        raise HTTPException(status_code=404, detail=f"Directory not found: {directory}")

    if not scan_dir.is_dir():
        raise HTTPException(status_code=400, detail=f"Not a directory: {directory}")

    midi_files: list[dict[str, Any]] = []
    try:
        for mid_file in scan_dir.rglob("*.mid"):
            rel = mid_file.relative_to(scan_dir)
            midi_files.append({
                "path": str(mid_file),
                "name": mid_file.name,
                "relative": str(rel),
                "size_bytes": mid_file.stat().st_size,
            })
    except PermissionError:
        raise HTTPException(status_code=403, detail=f"Permission denied: {directory}")

    return {
        "directory": str(scan_dir.resolve()),
        "files": sorted(midi_files, key=lambda f: f["name"]),
        "count": len(midi_files),
    }


@router.post("/midi/parse")
async def parse_midi_file(request: MidiParseRequest):
    """
    Parse a MIDI file and return note events with metadata.

    Extracts tracks, notes (pitch/velocity/timing), tempo, and time signature.
    """
    midi_path = Path(request.path)
    if not midi_path.exists():
        raise HTTPException(status_code=404, detail=f"MIDI file not found: {request.path}")

    if not midi_path.suffix.lower() == ".mid":
        raise HTTPException(status_code=400, detail=f"Not a MIDI file: {request.path}")

    try:
        result = _parser.parse_to_dict(midi_path)
        return MidiParseResponse(
            bpm=result["bpm"],
            time_signature=result["time_signature"],
            ticks_per_beat=result["ticks_per_beat"],
            total_beats=result["total_beats"],
            tracks=result["tracks"],
            track_count=len(result["tracks"]),
        )
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"MIDI file not found: {request.path}")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid MIDI file: {e}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Parse error: {e}")


@router.get("/midi/synths")
async def list_available_synths():
    """
    List available built-in synthesizer types.

    Returns the names of oscillator types that can be used
    to render MIDI tracks (sine, sawtooth, square, triangle).
    """
    synth_names = list_synths()
    synth_info = []
    descriptions = {
        "sine": "Pure sine wave - clean, fundamental only",
        "sawtooth": "Sawtooth wave - bright, harmonically rich",
        "square": "Square wave - hollow, odd harmonics",
        "triangle": "Triangle wave - mellow, odd harmonics, softer",
    }
    for name in synth_names:
        synth_info.append({
            "name": name,
            "description": descriptions.get(name, "Oscillator synth"),
        })
    return {"synths": synth_info, "count": len(synth_info)}
