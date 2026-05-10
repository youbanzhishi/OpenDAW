"""
midi — MIDI file parsing, scheduling, and routing for VCMix.

Reads .mid files, extracts note events, schedules them for rendering,
and provides hardware device management, quantization, humanization,
CC mapping, and virtual channel routing.

Modules:
    midi_parser      — MIDI file parsing and note extraction
    note_scheduler   — Note scheduling and built-in synthesizers
    device_manager   — Hardware MIDI device scanning and I/O
    quantize         — Grid quantization and swing
    humanize         — Timing and velocity humanization
    cc_mapping       — CC to plugin parameter mapping
    virtual_channel  — Multi-channel management and routing
    midi_router      — Complete MIDI routing pipeline

Usage:
    from vcmix.midi.midi_parser import MidiParser, MidiNote
    from vcmix.midi.note_scheduler import NoteScheduler
    from vcmix.midi.quantize import Quantizer
    from vcmix.midi.humanize import Humanizer
    from vcmix.midi.cc_mapping import CCMappingEngine, CCMap
    from vcmix.midi.virtual_channel import VirtualChannelManager
    from vcmix.midi.midi_router import MidiRouter
    from vcmix.midi.device_manager import MidiDeviceManager
"""

from vcmix.midi.midi_parser import MidiNote, MidiParser, MidiTrack

__all__ = [
    "MidiParser",
    "MidiNote",
    "MidiTrack",
    "NoteScheduler",
    "Quantizer",
    "Humanizer",
    "CCMappingEngine",
    "CCMap",
    "VirtualChannelManager",
    "MidiRouter",
    "MidiDeviceManager",
]
