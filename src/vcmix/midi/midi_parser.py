"""
midi_parser.py — MIDI file parser for VCMix.

Reads Standard MIDI Files (.mid) using the mido library and extracts
note events into a simplified, beat-based representation suitable for
the VCMix rendering pipeline.

Supports:
    - Format 0 (single track) and Format 1 (multi-track) MIDI files
    - Note On/Off event extraction with velocity
    - Tempo (BPM) and time signature detection
    - Beat-based timing conversion (tick -> beat)

Data structures:
    MidiNote  — single note event (pitch, velocity, start, duration)
    MidiTrack — collection of notes from one MIDI track

Usage:
    from vcmix.midi.midi_parser import MidiParser, MidiNote

    parser = MidiParser()
    tracks = parser.parse("melody.mid")
    for track in tracks:
        for note in track.notes:
            print(f"Note {note.note} vel={note.velocity} "
                  f"beat={note.start_beat:.2f} dur={note.duration_beats:.2f}")

Dependencies: mido>=1.3.0
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import mido


@dataclass(frozen=True)
class MidiNote:
    """A single MIDI note event with beat-based timing.

    Attributes:
        note: MIDI note number (0-127, 60 = middle C).
        velocity: Note velocity (0-127).
        start_beat: Start time in beats (quarter notes).
        duration_beats: Duration in beats.
        channel: MIDI channel (0-15).
    """

    note: int
    velocity: int
    start_beat: float
    duration_beats: float
    channel: int = 0

    def __post_init__(self) -> None:
        """Validate note values."""
        if not 0 <= self.note <= 127:
            raise ValueError(f"MIDI note out of range: {self.note}")
        if not 0 <= self.velocity <= 127:
            raise ValueError(f"MIDI velocity out of range: {self.velocity}")
        if self.start_beat < 0:
            raise ValueError(f"Start beat cannot be negative: {self.start_beat}")
        if self.duration_beats <= 0:
            raise ValueError(f"Duration must be positive: {self.duration_beats}")

    @property
    def frequency(self) -> float:
        """Convert MIDI note number to frequency in Hz (A440 tuning)."""
        return 440.0 * (2.0 ** ((self.note - 69) / 12.0))

    @property
    def note_name(self) -> str:
        """Human-readable note name, e.g. 'C4', 'F#5'."""
        names = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
        octave = self.note // 12 - 1
        return f"{names[self.note % 12]}{octave}"


@dataclass
class MidiTrack:
    """A collection of MIDI notes from one track.

    Attributes:
        name: Track name from MIDI file (or auto-generated).
        notes: List of MidiNote events sorted by start_beat.
        channel: MIDI channel number.
        instrument: Instrument name from track meta events.
    """

    name: str = ""
    notes: list[MidiNote] = field(default_factory=list)
    channel: int = 0
    instrument: str = ""

    @property
    def total_beats(self) -> float:
        """Total length of the track in beats."""
        if not self.notes:
            return 0.0
        return max(n.start_beat + n.duration_beats for n in self.notes)

    @property
    def note_count(self) -> int:
        """Number of notes in this track."""
        return len(self.notes)

    def get_notes_in_range(
        self, start_beat: float, end_beat: float
    ) -> list[MidiNote]:
        """Get notes that overlap with the given beat range.

        Args:
            start_beat: Start of range in beats.
            end_beat: End of range in beats.

        Returns:
            List of MidiNote events overlapping the range.
        """
        result: list[MidiNote] = []
        for note in self.notes:
            note_end = note.start_beat + note.duration_beats
            if note.start_beat < end_beat and note_end > start_beat:
                result.append(note)
        return result


@dataclass
class MidiInfo:
    """Metadata extracted from a MIDI file.

    Attributes:
        bpm: Detected tempo in beats per minute.
        time_signature_numerator: Time signature numerator (e.g. 4 for 4/4).
        time_signature_denominator: Time signature denominator (e.g. 4 for 4/4).
        ticks_per_beat: MIDI ticks per quarter note (beat).
        total_beats: Total song length in beats.
    """

    bpm: float = 120.0
    time_signature_numerator: int = 4
    time_signature_denominator: int = 4
    ticks_per_beat: int = 480
    total_beats: float = 0.0


class MidiParser:
    """Parse Standard MIDI Files into VCMix-compatible data structures.

    Uses the mido library for low-level MIDI parsing, then converts
    tick-based timing to beat-based timing for the rendering pipeline.
    """

    def __init__(self) -> None:
        """Initialize the MIDI parser."""
        pass

    def parse(self, path: str | Path) -> tuple[list[MidiTrack], MidiInfo]:
        """Parse a MIDI file and extract note tracks with metadata.

        Args:
            path: Path to the .mid file.

        Returns:
            Tuple of (list of MidiTrack, MidiInfo metadata).

        Raises:
            FileNotFoundError: If the MIDI file doesn't exist.
            ValueError: If the file is not a valid MIDI file.
        """
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"MIDI file not found: {path}")

        try:
            mid = mido.MidiFile(str(path))
        except Exception as e:
            raise ValueError(f"Invalid MIDI file: {path}: {e}") from e

        ticks_per_beat = mid.ticks_per_beat
        bpm = 120.0  # Default BPM
        time_sig_num = 4
        time_sig_den = 4

        # First pass: extract tempo and time signature from all tracks
        for track in mid.tracks:
            for msg in track:
                if msg.type == "set_tempo":
                    bpm = mido.tempo2bpm(msg.tempo)
                elif msg.type == "time_signature":
                    time_sig_num = msg.numerator
                    time_sig_den = msg.denominator

        # Second pass: extract note events per track
        midi_tracks: list[MidiTrack] = []
        for i, track in enumerate(mid.tracks):
            midi_track = self._parse_track(track, ticks_per_beat, i)
            if midi_track.note_count > 0:
                midi_tracks.append(midi_track)

        # Compute total beats
        total_beats = 0.0
        for mt in midi_tracks:
            total_beats = max(total_beats, mt.total_beats)

        # If no tempo events found, estimate from file length
        if bpm == 120.0 and total_beats > 0:
            pass  # Keep default 120 BPM

        info = MidiInfo(
            bpm=round(bpm, 2),
            time_signature_numerator=time_sig_num,
            time_signature_denominator=time_sig_den,
            ticks_per_beat=ticks_per_beat,
            total_beats=round(total_beats, 4),
        )

        return midi_tracks, info

    def _parse_track(
        self,
        track: mido.MidiTrack,
        ticks_per_beat: int,
        track_index: int,
    ) -> MidiTrack:
        """Parse a single MIDI track into a MidiTrack.

        Handles Note On/Off pairs and converts tick positions to beats.
        Note On with velocity 0 is treated as Note Off.

        Args:
            track: mido MidiTrack object.
            ticks_per_beat: Ticks per quarter note.
            track_index: Track index for naming.

        Returns:
            MidiTrack with extracted note events.
        """
        track_name = f"Track_{track_index}"
        instrument = ""
        current_tick = 0
        # Map: (channel, note) -> (start_tick, velocity)
        active_notes: dict[tuple[int, int], tuple[int, int]] = {}
        notes: list[MidiNote] = []

        for msg in track:
            current_tick += msg.time

            if msg.type == "track_name":
                track_name = msg.name or track_name
            elif msg.type == "program_change":
                instrument = f"Program_{msg.program}"
            elif msg.type == "note_on" and msg.velocity > 0:
                key = (msg.channel, msg.note)
                active_notes[key] = (current_tick, msg.velocity)
            elif msg.type == "note_off" or (
                msg.type == "note_on" and msg.velocity == 0
            ):
                key = (msg.channel, msg.note)
                if key in active_notes:
                    start_tick, velocity = active_notes.pop(key)
                    duration_ticks = current_tick - start_tick
                    if duration_ticks > 0:
                        start_beat = start_tick / ticks_per_beat
                        duration_beats = duration_ticks / ticks_per_beat
                        notes.append(
                            MidiNote(
                                note=msg.note,
                                velocity=velocity,
                                start_beat=round(start_beat, 6),
                                duration_beats=round(duration_beats, 6),
                                channel=msg.channel,
                            )
                        )

        # Sort by start time, then by note number
        notes.sort(key=lambda n: (n.start_beat, n.note))

        # Determine the primary channel
        if notes:
            channel_counts: dict[int, int] = {}
            for n in notes:
                channel_counts[n.channel] = channel_counts.get(n.channel, 0) + 1
            primary_channel = max(channel_counts, key=channel_counts.get)
        else:
            primary_channel = 0

        return MidiTrack(
            name=track_name,
            notes=notes,
            channel=primary_channel,
            instrument=instrument,
        )

    def parse_to_dict(self, path: str | Path) -> dict[str, Any]:
        """Parse a MIDI file and return a serializable dictionary.

        Useful for YAML integration and JSON export.

        Args:
            path: Path to the .mid file.

        Returns:
            Dictionary with tracks, info, and note data.
        """
        tracks, info = self.parse(path)
        return {
            "bpm": info.bpm,
            "time_signature": f"{info.time_signature_numerator}/{info.time_signature_denominator}",
            "ticks_per_beat": info.ticks_per_beat,
            "total_beats": info.total_beats,
            "tracks": [
                {
                    "name": t.name,
                    "channel": t.channel,
                    "instrument": t.instrument,
                    "note_count": t.note_count,
                    "notes": [
                        {
                            "note": n.note,
                            "name": n.note_name,
                            "velocity": n.velocity,
                            "start_beat": n.start_beat,
                            "duration_beats": n.duration_beats,
                        }
                        for n in t.notes
                    ],
                }
                for t in tracks
            ],
        }
