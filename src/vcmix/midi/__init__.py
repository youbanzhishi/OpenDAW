"""
midi — MIDI file parsing and note scheduling for VCMix.

Reads .mid files, extracts note events, and schedules them
for rendering via built-in synthesizers.

Usage:
    from vcmix.midi.midi_parser import MidiParser, MidiNote
    from vcmix.midi.note_scheduler import NoteScheduler
"""
from vcmix.midi.midi_parser import MidiNote, MidiParser, MidiTrack

__all__ = ["MidiParser", "MidiNote", "MidiTrack"]
