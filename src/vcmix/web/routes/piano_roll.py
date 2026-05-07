"""
piano_roll.py — MIDI Piano Roll API endpoint for VCMix (Phase 13).

Provides:
    GET /api/v1/midi/{project_id}/{track} — Get MIDI note data for a track
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from vcmix.web.project_manager import ProjectManager

router = APIRouter()

# ── Shared project manager ───────────────────────────────────────────────

_pm = ProjectManager()


# ── Models ───────────────────────────────────────────────────────────────

class MidiNoteItem(BaseModel):
    """A single MIDI note event."""
    note: int = Field(description="MIDI note number (0-127)")
    name: str = Field(default="", description="Note name, e.g. C4")
    velocity: int = Field(description="Velocity (0-127)")
    start_beat: float = Field(description="Start time in beats")
    duration_beats: float = Field(description="Duration in beats")
    channel: int = Field(default=0, description="MIDI channel")


class MidiTrackResponse(BaseModel):
    """Response for MIDI note data."""
    notes: list[MidiNoteItem] = Field(default_factory=list, description="MIDI note events")
    note_count: int = Field(default=0, description="Total number of notes")
    bpm: float = Field(default=120.0, description="Beats per minute")
    total_beats: float = Field(default=0.0, description="Total track length in beats")
    time_signature: str = Field(default="4/4", description="Time signature")
    track_name: str = Field(default="", description="Track name")


# ── Helpers ──────────────────────────────────────────────────────────────

_NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]


def _note_to_name(note_num: int) -> str:
    """Convert MIDI note number to name (e.g. 60 → 'C4')."""
    octave = note_num // 12 - 1
    return f"{_NOTE_NAMES[note_num % 12]}{octave}"


def _generate_demo_midi(bpm: float = 120.0) -> dict[str, Any]:
    """Generate demo MIDI note data for testing/visualization."""
    notes = []

    # C major scale
    scale = [60, 62, 64, 65, 67, 69, 71, 72]
    for i, note in enumerate(scale):
        notes.append({
            "note": note,
            "name": _note_to_name(note),
            "velocity": 80 + (i * 5),
            "start_beat": i * 2.0,
            "duration_beats": 1.5,
            "channel": 0,
        })

    # Chord
    for note in [60, 64, 67]:
        notes.append({
            "note": note,
            "name": _note_to_name(note),
            "velocity": 100,
            "start_beat": 16.0,
            "duration_beats": 4.0,
            "channel": 0,
        })

    # Bass line
    for start, note in [(0, 48), (8, 48), (16, 43), (24, 45)]:
        notes.append({
            "note": note,
            "name": _note_to_name(note),
            "velocity": 110,
            "start_beat": float(start),
            "duration_beats": 4.0,
            "channel": 1,
        })

    total_beats = max(n["start_beat"] + n["duration_beats"] for n in notes) if notes else 0.0

    return {
        "notes": notes,
        "note_count": len(notes),
        "bpm": bpm,
        "total_beats": total_beats,
        "time_signature": "4/4",
        "track_name": "demo",
    }


# ── Endpoint ─────────────────────────────────────────────────────────────

@router.get("/midi/{project_id}/{track}", response_model=MidiTrackResponse)
async def get_midi_track(
    project_id: str,
    track: str,
):
    """
    Get MIDI note data for a track.

    If the track has a midi_file configured, parse it.
    Otherwise, return demo/placeholder note data for visualization.
    """
    filepath = _pm.get_filepath(project_id)
    if filepath is None:
        raise HTTPException(status_code=404, detail=f"Project not found: {project_id}")

    import yaml
    try:
        content = filepath.read_text(encoding="utf-8")
        config = yaml.safe_load(content)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read project: {e}")

    tracks = config.get("tracks", [])
    track_config = None
    for t in tracks:
        if t.get("name") == track:
            track_config = t
            break

    if track_config is None:
        raise HTTPException(status_code=404, detail=f"Track '{track}' not found in project")

    bpm = config.get("bpm", 120.0)
    track_type = track_config.get("type", "audio")
    midi_file = track_config.get("midi_file", "")

    # If track has a MIDI file, parse it
    if midi_file and track_type in ("midi", "sampler"):
        midi_path = filepath.parent / midi_file
        if midi_path.exists():
            try:
                from vcmix.midi.midi_parser import MidiParser
                parser = MidiParser()
                midi_tracks, info = parser.parse(midi_path)

                all_notes = []
                for mt in midi_tracks:
                    for n in mt.notes:
                        all_notes.append({
                            "note": n.note,
                            "name": n.note_name,
                            "velocity": n.velocity,
                            "start_beat": n.start_beat,
                            "duration_beats": n.duration_beats,
                            "channel": n.channel,
                        })

                total_beats = info.total_beats if all_notes else 0.0
                return MidiTrackResponse(
                    notes=all_notes,
                    note_count=len(all_notes),
                    bpm=bpm,
                    total_beats=total_beats,
                    time_signature=f"{info.time_signature_numerator}/{info.time_signature_denominator}",
                    track_name=track,
                )
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"Failed to parse MIDI: {e}")

    # No MIDI file — return demo data for visualization
    demo = _generate_demo_midi(bpm)
    return MidiTrackResponse(
        notes=[MidiNoteItem(**n) for n in demo["notes"]],
        note_count=demo["note_count"],
        bpm=demo["bpm"],
        total_beats=demo["total_beats"],
        time_signature=demo["time_signature"],
        track_name=track,
    )
