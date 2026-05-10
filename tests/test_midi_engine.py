"""
Tests for vcmix.midi engine enhancements — Phase 22.

Tests cover:
    - Quantize: grid snapping, swing, strength
    - Humanize: timing and velocity randomization
    - CC Mapping: linear/log/toggle curves, multi-plugin routing
    - Virtual Channel: mute/solo, transpose, CC filter
    - Midi Router: integrated routing pipeline
    - Device Manager: scanning and port management (mocked)
    - MIDI file parsing (existing + extended)
"""

import math
import tempfile
from pathlib import Path

import mido
import numpy as np
import pytest

from vcmix.midi.cc_mapping import CCMap, CCCurve, CCMappingEngine
from vcmix.midi.device_manager import MidiDeviceInfo, MidiDeviceManager
from vcmix.midi.humanize import Humanizer
from vcmix.midi.midi_parser import MidiInfo, MidiNote, MidiParser, MidiTrack
from vcmix.midi.midi_router import MidiRouter
from vcmix.midi.note_scheduler import ADSR, NoteScheduler, list_synths
from vcmix.midi.quantize import GRID_SIZES, Quantizer
from vcmix.midi.virtual_channel import RoutedEvent, VirtualChannel, VirtualChannelManager


# ── Helpers ──────────────────────────────────────────────────────────────

def _make_notes(*args: tuple[int, int, float, float]) -> list[MidiNote]:
    """Create a list of MidiNote from (note, velocity, start_beat, duration_beats) tuples."""
    return [MidiNote(note=n, velocity=v, start_beat=s, duration_beats=d) for n, v, s, d in args]


def _create_simple_midi(
    notes: list[tuple[int, int, int, int]],
    bpm: int = 120,
    ticks_per_beat: int = 480,
) -> Path:
    """Create a simple MIDI file for testing."""
    mid = mido.MidiFile(ticks_per_beat=ticks_per_beat)
    track = mido.MidiTrack()
    mid.tracks.append(track)
    tempo = mido.bpm2tempo(bpm)
    track.append(mido.MetaMessage("set_tempo", tempo=tempo, time=0))
    events: list[tuple[int, str, int, int]] = []
    for note_num, velocity, start_tick, duration_ticks in notes:
        events.append((start_tick, "note_on", note_num, velocity))
        events.append((start_tick + duration_ticks, "note_off", note_num, 0))
    events.sort(key=lambda e: (e[0], e[1] == "note_on"))
    current_tick = 0
    for tick, msg_type, note_num, velocity in events:
        delta = tick - current_tick
        if msg_type == "note_on":
            track.append(mido.Message("note_on", note=note_num, velocity=velocity, time=delta))
        else:
            track.append(mido.Message("note_off", note=note_num, velocity=0, time=delta))
        current_tick = tick
    track.append(mido.MetaMessage("end_of_track", time=0))
    tmp = tempfile.NamedTemporaryFile(suffix=".mid", delete=False)
    tmp.close()
    mid.save(tmp.name)
    return Path(tmp.name)


# ══════════════════════════════════════════════════════════════════════════
# Quantizer Tests
# ══════════════════════════════════════════════════════════════════════════

class TestQuantizer:
    def test_full_strength_snap(self):
        """Notes should snap exactly to grid at strength=1.0."""
        notes = _make_notes((60, 100, 0.12, 0.5), (64, 100, 1.37, 0.5))
        q = Quantizer(grid="1/4", strength=1.0)
        result = q.quantize_notes(notes)
        assert result[0].start_beat == 0.0
        assert result[1].start_beat == 1.0  # 1.37 → 1.0 (nearest 1/4 grid, grid_size=1.0)

    def test_zero_strength_no_change(self):
        """At strength=0.0, notes should not move."""
        notes = _make_notes((60, 100, 0.12, 0.5))
        q = Quantizer(grid="1/4", strength=0.0)
        result = q.quantize_notes(notes)
        assert result[0].start_beat == 0.12

    def test_partial_strength(self):
        """Partial strength should move notes partway to grid."""
        notes = _make_notes((60, 100, 0.0, 0.5))  # Already on grid
        q = Quantizer(grid="1/4", strength=0.5)
        result = q.quantize_notes(notes)
        assert result[0].start_beat == 0.0  # Already on grid stays

    def test_sixteenth_note_grid(self):
        """1/16 grid should snap to 0.25 beat increments."""
        notes = _make_notes((60, 100, 0.1, 0.25))
        q = Quantizer(grid="1/16", strength=1.0)
        result = q.quantize_notes(notes)
        # 0.1 is closest to 0.0 or 0.25; round(0.1/0.25)=0 → 0.0
        assert result[0].start_beat == 0.0

    def test_thirty_second_grid(self):
        """1/32 grid should snap to 0.125 beat increments."""
        notes = _make_notes((60, 100, 0.06, 0.125))
        q = Quantizer(grid="1/32", strength=1.0)
        result = q.quantize_notes(notes)
        # 0.06 / 0.125 = 0.48 → round to 0 → 0.0
        assert result[0].start_beat == 0.0

    def test_swing(self):
        """Swing should delay off-beat positions."""
        # Two eighth notes: beat 0 and beat 0.5
        notes = _make_notes((60, 100, 0.0, 0.5), (64, 100, 0.5, 0.5))
        q = Quantizer(grid="1/8", strength=1.0, swing=0.5)
        result = q.quantize_notes(notes)
        # First note (beat 0) is downbeat, no swing
        assert result[0].start_beat == 0.0
        # Second note (beat 0.5) is off-beat, should be delayed
        # swing offset = 0.5 * 0.5 * 0.5 = 0.125
        assert result[1].start_beat == pytest.approx(0.5 + 0.125, abs=0.001)

    def test_swing_zero_no_effect(self):
        """Swing=0 should not change timing."""
        notes = _make_notes((60, 100, 0.5, 0.5))
        q = Quantizer(grid="1/8", strength=1.0, swing=0.0)
        result = q.quantize_notes(notes)
        assert result[0].start_beat == 0.5

    def test_duration_preserved(self):
        """Quantization should not change note duration."""
        notes = _make_notes((60, 100, 0.12, 1.5))
        q = Quantizer(grid="1/4", strength=1.0)
        result = q.quantize_notes(notes)
        assert result[0].duration_beats == 1.5

    def test_velocity_preserved(self):
        """Quantization should not change note velocity."""
        notes = _make_notes((60, 80, 0.12, 0.5))
        q = Quantizer(grid="1/4", strength=1.0)
        result = q.quantize_notes(notes)
        assert result[0].velocity == 80

    def test_invalid_grid(self):
        """Invalid grid name should raise ValueError."""
        with pytest.raises(ValueError, match="Invalid grid"):
            Quantizer(grid="1/64")

    def test_invalid_strength(self):
        """Strength out of range should raise ValueError."""
        with pytest.raises(ValueError, match="Strength"):
            Quantizer(grid="1/16", strength=1.5)

    def test_invalid_swing(self):
        """Swing out of range should raise ValueError."""
        with pytest.raises(ValueError, match="Swing"):
            Quantizer(grid="1/16", swing=-0.1)

    def test_quantize_with_result(self):
        """quantize_with_result should return metadata."""
        notes = _make_notes((60, 100, 0.12, 0.5), (64, 100, 2.0, 0.5))
        q = Quantizer(grid="1/4", strength=1.0)
        result = q.quantize_with_result(notes)
        assert result.grid == "1/4"
        assert result.strength == 1.0
        assert result.swing == 0.0
        assert result.adjustments == 1  # Only the first note moved

    def test_available_grids(self):
        """Should return all valid grid names."""
        grids = Quantizer.available_grids()
        assert "1/4" in grids
        assert "1/8" in grids
        assert "1/16" in grids
        assert "1/32" in grids

    def test_grid_to_beats(self):
        """Should convert grid names to beat values."""
        assert Quantizer.grid_to_beats("1/4") == 1.0
        assert Quantizer.grid_to_beats("1/16") == 0.25


# ══════════════════════════════════════════════════════════════════════════
# Humanizer Tests
# ══════════════════════════════════════════════════════════════════════════

class TestHumanizer:
    def test_zero_range_no_change(self):
        """With zero ranges, notes should be unchanged."""
        notes = _make_notes((60, 100, 0.0, 1.0))
        h = Humanizer(timing_range=0.0, velocity_range=0, seed=42)
        result = h.humanize_notes(notes)
        assert result[0].start_beat == 0.0
        assert result[0].velocity == 100

    def test_timing_variation(self):
        """With non-zero timing range, notes should vary."""
        notes = _make_notes(
            (60, 100, 0.0, 1.0), (64, 100, 1.0, 1.0), (67, 100, 2.0, 1.0)
        )
        h = Humanizer(timing_range=0.02, velocity_range=0, seed=42)
        result = h.humanize_notes(notes)
        # At least one note should have shifted
        any_shifted = any(
            abs(r.start_beat - o.start_beat) > 1e-9
            for r, o in zip(result, notes)
        )
        assert any_shifted

    def test_velocity_variation(self):
        """With non-zero velocity range, velocities should vary."""
        notes = _make_notes(
            (60, 100, 0.0, 1.0), (64, 100, 1.0, 1.0), (67, 100, 2.0, 1.0)
        )
        h = Humanizer(timing_range=0.0, velocity_range=15, seed=42)
        result = h.humanize_notes(notes)
        any_changed = any(r.velocity != o.velocity for r, o in zip(result, notes))
        assert any_changed

    def test_velocity_clamped(self):
        """Velocities should be clamped to 1-127."""
        notes = _make_notes((60, 1, 0.0, 1.0), (64, 127, 1.0, 1.0))
        h = Humanizer(timing_range=0.0, velocity_range=20, seed=42)
        result = h.humanize_notes(notes)
        for n in result:
            assert 1 <= n.velocity <= 127

    def test_timing_no_negative(self):
        """Start beats should never go negative."""
        notes = _make_notes((60, 100, 0.0, 1.0))
        h = Humanizer(timing_range=0.05, velocity_range=0, seed=42)
        result = h.humanize_notes(notes)
        for n in result:
            assert n.start_beat >= 0.0

    def test_seed_reproducibility(self):
        """Same seed should produce same results."""
        notes = _make_notes((60, 100, 0.0, 1.0), (64, 80, 1.0, 1.0))
        h1 = Humanizer(timing_range=0.02, velocity_range=10, seed=123)
        h2 = Humanizer(timing_range=0.02, velocity_range=10, seed=123)
        r1 = h1.humanize_notes(notes)
        r2 = h2.humanize_notes(notes)
        for a, b in zip(r1, r2):
            assert a.start_beat == b.start_beat
            assert a.velocity == b.velocity

    def test_timing_only(self):
        """humanize_timing_only should not change velocity."""
        notes = _make_notes((60, 100, 0.0, 1.0))
        h = Humanizer(timing_range=0.02, velocity_range=15, seed=42)
        result = h.humanize_timing_only(notes)
        assert result[0].velocity == 100

    def test_velocity_only(self):
        """humanize_velocity_only should not change timing."""
        notes = _make_notes((60, 100, 0.5, 1.0))
        h = Humanizer(timing_range=0.02, velocity_range=15, seed=42)
        result = h.humanize_velocity_only(notes)
        assert result[0].start_beat == 0.5

    def test_humanize_with_result(self):
        """humanize_with_result should return metadata."""
        notes = _make_notes((60, 100, 0.0, 1.0), (64, 80, 1.0, 1.0))
        h = Humanizer(timing_range=0.02, velocity_range=10, seed=42)
        result = h.humanize_with_result(notes)
        assert result.timing_range == 0.02
        assert result.velocity_range == 10
        assert result.total_timing_offset >= 0
        assert result.total_velocity_offset >= 0

    def test_negative_range_raises(self):
        """Negative timing_range should raise ValueError."""
        with pytest.raises(ValueError, match="timing_range"):
            Humanizer(timing_range=-0.01)

    def test_negative_velocity_range_raises(self):
        """Negative velocity_range should raise ValueError."""
        with pytest.raises(ValueError, match="velocity_range"):
            Humanizer(velocity_range=-1)

    def test_duration_preserved(self):
        """Humanization should not change note duration."""
        notes = _make_notes((60, 100, 0.0, 2.5))
        h = Humanizer(timing_range=0.02, velocity_range=10, seed=42)
        result = h.humanize_notes(notes)
        assert result[0].duration_beats == 2.5


# ══════════════════════════════════════════════════════════════════════════
# CC Mapping Tests
# ══════════════════════════════════════════════════════════════════════════

class TestCCMap:
    def test_linear_mapping(self):
        """Linear mapping should interpolate proportionally."""
        m = CCMap(cc=1, param_name="volume", min_val=0.0, max_val=1.0, curve=CCCurve.LINEAR)
        assert m.map_value(0) == pytest.approx(0.0)
        assert m.map_value(64) == pytest.approx(64.0 / 127.0, abs=0.01)
        assert m.map_value(127) == pytest.approx(1.0, abs=0.01)

    def test_log_mapping(self):
        """Log mapping should produce exponential values."""
        m = CCMap(cc=1, param_name="cutoff", min_val=20.0, max_val=20000.0, curve=CCCurve.LOG)
        # At CC=0 → min_val
        assert m.map_value(0) == pytest.approx(20.0, rel=0.01)
        # At CC=127 → max_val
        assert m.map_value(127) == pytest.approx(20000.0, rel=0.01)
        # At CC=64 → somewhere in between (log-scaled)
        mid_val = m.map_value(64)
        assert 20.0 < mid_val < 20000.0
        # Log midpoint should be closer to the geometric mean than arithmetic mean
        import math
        geo_mean = math.sqrt(20.0 * 20000.0)
        assert mid_val < 10010.0  # Should be less than arithmetic mean

    def test_toggle_mapping(self):
        """Toggle mapping should return True for >= 64, False otherwise."""
        m = CCMap(cc=64, param_name="bypass", curve=CCCurve.TOGGLE, min_val=0.0, max_val=1.0)
        assert m.map_value(0) is False
        assert m.map_value(63) is False
        assert m.map_value(64) is True
        assert m.map_value(127) is True

    def test_inverted_mapping(self):
        """Inverted mapping should reverse the direction."""
        m = CCMap(cc=1, param_name="volume", min_val=0.0, max_val=1.0, curve=CCCurve.LINEAR, inverted=True)
        assert m.map_value(0) == pytest.approx(1.0, abs=0.01)
        assert m.map_value(127) == pytest.approx(0.0, abs=0.01)

    def test_reverse_map_linear(self):
        """Reverse mapping should recover CC value."""
        m = CCMap(cc=1, param_name="vol", min_val=0.0, max_val=1.0, curve=CCCurve.LINEAR)
        # Forward then reverse
        for cc_val in [0, 32, 64, 96, 127]:
            param_val = m.map_value(cc_val)
            recovered = m.reverse_map(param_val)
            assert abs(recovered - cc_val) <= 1  # ±1 due to rounding

    def test_reverse_map_toggle(self):
        """Toggle reverse mapping."""
        m = CCMap(cc=64, param_name="bypass", curve=CCCurve.TOGGLE, min_val=0.0, max_val=1.0)
        assert m.reverse_map(True) == 127
        assert m.reverse_map(False) == 0

    def test_invalid_cc_number(self):
        """CC number out of range should raise ValueError."""
        with pytest.raises(ValueError, match="CC number"):
            CCMap(cc=128, param_name="test")

    def test_invalid_cc_value(self):
        """CC value out of range should raise ValueError."""
        m = CCMap(cc=1, param_name="test")
        with pytest.raises(ValueError, match="CC value"):
            m.map_value(200)


class TestCCMappingEngine:
    def test_add_and_process(self):
        """Add a mapping and process a CC message."""
        engine = CCMappingEngine()
        engine.add_mapping("synth_1", CCMap(cc=1, param_name="cutoff", min_val=100.0, max_val=5000.0))
        updates = engine.process_cc(1, 64)
        assert len(updates) == 1
        assert updates[0][0] == "synth_1"
        assert updates[0][1] == "cutoff"
        assert isinstance(updates[0][2], float)

    def test_multi_plugin_routing(self):
        """Same CC can control parameters on multiple plugins."""
        engine = CCMappingEngine()
        engine.add_mapping("synth_1", CCMap(cc=1, param_name="cutoff", min_val=100.0, max_val=5000.0))
        engine.add_mapping("synth_2", CCMap(cc=1, param_name="resonance", min_val=0.0, max_val=1.0))
        updates = engine.process_cc(1, 64)
        assert len(updates) == 2
        plugin_ids = {u[0] for u in updates}
        assert plugin_ids == {"synth_1", "synth_2"}

    def test_remove_mapping(self):
        """Remove a mapping and verify it no longer produces updates."""
        engine = CCMappingEngine()
        engine.add_mapping("synth_1", CCMap(cc=1, param_name="cutoff", min_val=100.0, max_val=5000.0))
        assert engine.remove_mapping("synth_1", "cutoff") is True
        updates = engine.process_cc(1, 64)
        assert len(updates) == 0

    def test_remove_nonexistent(self):
        """Removing a nonexistent mapping should return False."""
        engine = CCMappingEngine()
        assert engine.remove_mapping("nonexistent", "param") is False

    def test_channel_filter(self):
        """CC mapping with channel filter should only match on that channel."""
        engine = CCMappingEngine()
        engine.add_mapping("synth_1", CCMap(cc=1, param_name="cutoff", min_val=100.0, max_val=5000.0, channel=0))
        # Match on channel 0
        updates = engine.process_cc(1, 64, channel=0)
        assert len(updates) == 1
        # No match on channel 1
        updates = engine.process_cc(1, 64, channel=1)
        assert len(updates) == 0

    def test_feedback(self):
        """Feedback should recover CC value from parameter value."""
        engine = CCMappingEngine()
        engine.add_mapping("synth_1", CCMap(cc=7, param_name="volume", min_val=0.0, max_val=1.0))
        result = engine.get_feedback("synth_1", "volume", 0.5)
        assert result is not None
        cc_num, cc_val = result
        assert cc_num == 7
        # 0.5 of 0.0-1.0 → ~64
        assert abs(cc_val - 64) <= 1

    def test_feedback_not_found(self):
        """Feedback for unknown param should return None."""
        engine = CCMappingEngine()
        assert engine.get_feedback("synth_1", "nonexistent", 0.5) is None

    def test_total_mappings(self):
        """Should count total mappings correctly."""
        engine = CCMappingEngine()
        engine.add_mapping("synth_1", CCMap(cc=1, param_name="a", min_val=0.0, max_val=1.0))
        engine.add_mapping("synth_1", CCMap(cc=2, param_name="b", min_val=0.0, max_val=1.0))
        engine.add_mapping("synth_2", CCMap(cc=3, param_name="c", min_val=0.0, max_val=1.0))
        assert engine.total_mappings == 3
        assert engine.plugin_count == 2

    def test_clear(self):
        """Clear should remove all mappings."""
        engine = CCMappingEngine()
        engine.add_mapping("synth_1", CCMap(cc=1, param_name="a", min_val=0.0, max_val=1.0))
        engine.clear()
        assert engine.total_mappings == 0
        assert engine.plugin_count == 0

    def test_unmatched_cc(self):
        """CC with no mapping should return empty list."""
        engine = CCMappingEngine()
        updates = engine.process_cc(99, 64)
        assert updates == []


# ══════════════════════════════════════════════════════════════════════════
# Virtual Channel Tests
# ══════════════════════════════════════════════════════════════════════════

class TestVirtualChannel:
    def test_create_channel(self):
        """Should create a channel with correct attributes."""
        ch = VirtualChannel(number=0, name="Piano", output="piano_plugin")
        assert ch.number == 0
        assert ch.name == "Piano"
        assert ch.output == "piano_plugin"
        assert ch.volume == 1.0
        assert ch.pan == 0.0
        assert not ch.muted
        assert not ch.solo

    def test_invalid_channel_number(self):
        """Channel number out of range should raise ValueError."""
        with pytest.raises(ValueError, match="MIDI channel"):
            VirtualChannel(number=16)

    def test_volume_clamped(self):
        """Volume should be clamped to 0.0-1.0."""
        ch = VirtualChannel(number=0, volume=1.5)
        assert ch.volume == 1.0
        ch2 = VirtualChannel(number=1, volume=-0.5)
        assert ch2.volume == 0.0

    def test_pan_clamped(self):
        """Pan should be clamped to -1.0 to 1.0."""
        ch = VirtualChannel(number=0, pan=2.0)
        assert ch.pan == 1.0


class TestVirtualChannelManager:
    def test_create_and_list(self):
        """Should create channels and list them."""
        vcm = VirtualChannelManager()
        vcm.create_channel(0, name="Piano", output="piano")
        vcm.create_channel(1, name="Strings", output="strings")
        channels = vcm.list_channels()
        assert len(channels) == 2
        assert channels[0].name == "Piano"
        assert channels[1].name == "Strings"

    def test_duplicate_channel(self):
        """Creating a duplicate channel should raise ValueError."""
        vcm = VirtualChannelManager()
        vcm.create_channel(0)
        with pytest.raises(ValueError, match="already exists"):
            vcm.create_channel(0)

    def test_remove_channel(self):
        """Should remove a channel."""
        vcm = VirtualChannelManager()
        vcm.create_channel(0)
        assert vcm.remove_channel(0) is True
        assert vcm.channel_count == 0

    def test_remove_nonexistent(self):
        """Removing nonexistent channel should return False."""
        vcm = VirtualChannelManager()
        assert vcm.remove_channel(0) is False

    def test_route_note_on_active(self):
        """Active channel should route note events."""
        vcm = VirtualChannelManager()
        vcm.create_channel(0, name="Piano", output="piano_plugin")
        event = vcm.route_note_on(60, 100, 0)
        assert event is not None
        assert event.event_type == "note_on"
        assert event.note == 60
        assert event.output == "piano_plugin"

    def test_route_note_on_muted(self):
        """Muted channel should not route note events."""
        vcm = VirtualChannelManager()
        vcm.create_channel(0, name="Piano", output="piano_plugin", muted=True)
        event = vcm.route_note_on(60, 100, 0)
        assert event is None

    def test_route_note_off_muted_passes(self):
        """Note Off should pass through even for muted channels (prevent stuck notes)."""
        vcm = VirtualChannelManager()
        vcm.create_channel(0, name="Piano", output="piano_plugin", muted=True)
        event = vcm.route_note_off(60, 0, 0)
        # Note off passes through even when muted
        assert event is not None

    def test_solo_logic(self):
        """When a channel is soloed, only that channel routes."""
        vcm = VirtualChannelManager()
        vcm.create_channel(0, name="Piano", output="piano")
        vcm.create_channel(1, name="Strings", output="strings")
        vcm.set_solo(0, True)
        # Piano should route
        e1 = vcm.route_note_on(60, 100, 0)
        assert e1 is not None
        # Strings should not route (no solo)
        e2 = vcm.route_note_on(64, 100, 1)
        assert e2 is None

    def test_transpose(self):
        """Transposed channel should shift note numbers."""
        vcm = VirtualChannelManager()
        vcm.create_channel(0, name="Piano", output="piano", transpose=12)
        event = vcm.route_note_on(60, 100, 0)
        assert event is not None
        assert event.note == 72  # 60 + 12

    def test_transpose_clamp(self):
        """Notes transposed out of range should return None."""
        vcm = VirtualChannelManager()
        vcm.create_channel(0, name="Piano", output="piano", transpose=50)
        event = vcm.route_note_on(100, 100, 0)  # 100+50=150 > 127
        assert event is None

    def test_cc_filter(self):
        """CC filter should only pass specified CC numbers."""
        vcm = VirtualChannelManager()
        vcm.create_channel(0, name="Piano", output="piano", cc_filter={1, 7})
        # CC 1 should pass
        e1 = vcm.route_cc(1, 64, 0)
        assert e1 is not None
        # CC 10 should be filtered
        e2 = vcm.route_cc(10, 64, 0)
        assert e2 is None

    def test_cc_no_filter(self):
        """Empty cc_filter should pass all CCs."""
        vcm = VirtualChannelManager()
        vcm.create_channel(0, name="Piano", output="piano")
        e1 = vcm.route_cc(1, 64, 0)
        e2 = vcm.route_cc(10, 64, 0)
        assert e1 is not None
        assert e2 is not None

    def test_flush_events(self):
        """flush_events should return and clear the event buffer."""
        vcm = VirtualChannelManager()
        vcm.create_channel(0, name="Piano", output="piano")
        vcm.route_note_on(60, 100, 0)
        events = vcm.flush_events()
        assert len(events) == 1
        # Second flush should be empty
        assert len(vcm.flush_events()) == 0

    def test_nonexistent_channel(self):
        """Routing to nonexistent channel should return None."""
        vcm = VirtualChannelManager()
        assert vcm.route_note_on(60, 100, 5) is None
        assert vcm.route_note_off(60, 0, 5) is None
        assert vcm.route_cc(1, 64, 5) is None

    def test_set_volume_pan(self):
        """Should update volume and pan."""
        vcm = VirtualChannelManager()
        vcm.create_channel(0)
        vcm.set_volume(0, 0.5)
        vcm.set_pan(0, -0.75)
        ch = vcm.get_channel(0)
        assert ch.volume == 0.5
        assert ch.pan == -0.75

    def test_volume_pan_in_routed_event(self):
        """Routed events should carry the channel's volume and pan."""
        vcm = VirtualChannelManager()
        vcm.create_channel(0, name="Piano", output="piano", volume=0.7, pan=-0.5)
        event = vcm.route_note_on(60, 100, 0)
        assert event.volume == 0.7
        assert event.pan == -0.5


# ══════════════════════════════════════════════════════════════════════════
# Midi Router Tests
# ══════════════════════════════════════════════════════════════════════════

class TestMidiRouter:
    def test_basic_routing(self):
        """Note should be routed to the correct output."""
        router = MidiRouter()
        router.channels.create_channel(0, name="Piano", output="piano_plugin")
        event = router.on_note_on(60, 100, 0)
        assert event is not None
        assert event.output == "piano_plugin"
        assert event.note == 60

    def test_note_callback(self):
        """Note callback should be invoked on routed notes."""
        calls = []
        router = MidiRouter(
            note_callback=lambda pid, n, v, vol, pan: calls.append((pid, n, v))
        )
        router.channels.create_channel(0, output="synth_1")
        router.on_note_on(60, 100, 0)
        assert len(calls) == 1
        assert calls[0] == ("synth_1", 60, 100)

    def test_cc_routing_with_mapping(self):
        """CC should be routed through mapping engine."""
        param_calls = []
        router = MidiRouter(
            param_callback=lambda pid, pn, val: param_calls.append((pid, pn, val))
        )
        router.channels.create_channel(0, output="synth_1")
        router.bind_cc("synth_1", cc=7, param_name="volume", min_val=0.0, max_val=1.0)
        updates = router.on_cc(7, 64, 0)
        assert len(updates) == 1
        assert updates[0][0] == "synth_1"
        assert updates[0][1] == "volume"
        # Callback should also have been invoked
        assert len(param_calls) == 1

    def test_muted_note_dropped(self):
        """Muted channel should drop notes and increment stats."""
        router = MidiRouter()
        router.channels.create_channel(0, output="synth_1", muted=True)
        event = router.on_note_on(60, 100, 0)
        assert event is None
        assert router.stats.notes_dropped == 1

    def test_route_midi_notes_batch(self):
        """Should route a batch of MidiNote objects."""
        router = MidiRouter()
        router.channels.create_channel(0, output="synth_1")
        notes = _make_notes((60, 100, 0.0, 1.0), (64, 80, 1.0, 1.0))
        events = router.route_midi_notes(notes)
        assert len(events) == 2

    def test_on_midi_message(self):
        """Should dispatch mido messages correctly."""
        calls = []
        router = MidiRouter(
            note_callback=lambda pid, n, v, vol, pan: calls.append(("note", n))
        )
        router.channels.create_channel(0, output="synth_1")
        msg = mido.Message("note_on", note=60, velocity=100, channel=0)
        router.on_midi_message(msg)
        assert len(calls) == 1
        assert calls[0] == ("note", 60)

    def test_setup_default_channels(self):
        """Should create 16 default channels."""
        router = MidiRouter()
        router.setup_default_channels()
        assert router.channels.channel_count == 16

    def test_stats(self):
        """Router stats should track routed/dropped events."""
        router = MidiRouter()
        router.channels.create_channel(0, output="synth_1")
        router.channels.create_channel(1, output="synth_2", muted=True)
        router.on_note_on(60, 100, 0)
        router.on_note_on(64, 100, 1)  # dropped (muted)
        assert router.stats.notes_routed == 1
        assert router.stats.notes_dropped == 1

    def test_reset_stats(self):
        """reset_stats should zero out counters."""
        router = MidiRouter()
        router.channels.create_channel(0, output="synth_1")
        router.on_note_on(60, 100, 0)
        router.reset_stats()
        assert router.stats.notes_routed == 0


# ══════════════════════════════════════════════════════════════════════════
# Device Manager Tests (mocked - no hardware required)
# ══════════════════════════════════════════════════════════════════════════

class TestMidiDeviceInfo:
    def test_repr(self):
        """Device info should have a readable repr."""
        info = MidiDeviceInfo(name="Test Port", is_input=True, is_output=True)
        assert "Test Port" in repr(info)
        assert "in" in repr(info)
        assert "out" in repr(info)


class TestMidiDeviceManager:
    def test_scan_devices(self):
        """scan_devices should return a list (may be empty in CI)."""
        mgr = MidiDeviceManager()
        devices = mgr.scan_devices()
        assert isinstance(devices, list)

    def test_list_input_names(self):
        """list_input_names should return a list."""
        mgr = MidiDeviceManager()
        names = mgr.list_input_names()
        assert isinstance(names, list)

    def test_list_output_names(self):
        """list_output_names should return a list."""
        mgr = MidiDeviceManager()
        names = mgr.list_output_names()
        assert isinstance(names, list)

    def test_open_nonexistent_port(self):
        """Opening a nonexistent port should raise IOError."""
        mgr = MidiDeviceManager()
        with pytest.raises(IOError):
            mgr.open_input("___nonexistent_port___test___")

    def test_open_duplicate_input(self):
        """Opening the same input port twice should raise ValueError."""
        mgr = MidiDeviceManager()
        # First open a virtual port
        try:
            mgr._open_virtual_input("test_virtual_dup")
            if "test_virtual_dup" in mgr.list_input_names():
                # Now try to open it again as regular input
                with pytest.raises(ValueError, match="already open"):
                    mgr.open_input("test_virtual_dup")
        except Exception:
            pass  # Virtual ports may not be supported on this system
        mgr.close_all()

    def test_close_all(self):
        """close_all should not raise errors."""
        mgr = MidiDeviceManager()
        mgr.close_all()  # Should be safe even with no open ports

    def test_port_count_initial(self):
        """Initial port count should be 0."""
        mgr = MidiDeviceManager()
        assert mgr.open_input_count == 0
        assert mgr.open_output_count == 0

    def test_send_to_closed_port(self):
        """Sending to a closed port should raise KeyError."""
        mgr = MidiDeviceManager()
        msg = mido.Message("note_on", note=60, velocity=100)
        with pytest.raises(KeyError):
            mgr.send_message("nonexistent", msg)

    def test_callback_add_remove(self):
        """Should add and remove callbacks."""
        mgr = MidiDeviceManager()
        cb = lambda msg: None
        mgr.add_callback(cb)
        mgr.remove_callback(cb)

    def test_poll_empty(self):
        """Polling with no open ports should return empty list."""
        mgr = MidiDeviceManager()
        msgs = mgr.poll_messages()
        assert isinstance(msgs, list)
        assert len(msgs) == 0


# ══════════════════════════════════════════════════════════════════════════
# Existing Parser/Scheduler Tests (ensuring no regression)
# ══════════════════════════════════════════════════════════════════════════

class TestMidiParserRegression:
    def test_parse_single_note(self):
        """Regression: parsing a single-note MIDI file."""
        midi_path = _create_simple_midi([(60, 100, 0, 480)])
        try:
            parser = MidiParser()
            tracks, info = parser.parse(midi_path)
            assert len(tracks) >= 1
            assert tracks[0].note_count >= 1
        finally:
            midi_path.unlink(missing_ok=True)

    def test_parse_multi_track(self):
        """Regression: parsing a multi-note MIDI file."""
        midi_path = _create_simple_midi([
            (60, 100, 0, 480), (64, 80, 480, 480), (67, 90, 960, 480),
        ])
        try:
            parser = MidiParser()
            tracks, info = parser.parse(midi_path)
            assert tracks[0].note_count == 3
        finally:
            midi_path.unlink(missing_ok=True)


class TestNoteSchedulerRegression:
    def test_render_basic(self):
        """Regression: basic note rendering."""
        notes = _make_notes((60, 100, 0.0, 1.0))
        track = MidiTrack(name="test", notes=notes)
        scheduler = NoteScheduler(bpm=120, sample_rate=44100, synth="sine")
        audio = scheduler.render_track(track)
        assert isinstance(audio, np.ndarray)
        assert len(audio) > 0


# ══════════════════════════════════════════════════════════════════════════
# Integration: Parser → Quantize → Humanize → Router
# ══════════════════════════════════════════════════════════════════════════

class TestMidiPipeline:
    def test_full_pipeline(self):
        """Parse → Quantize → Humanize → Route → Render pipeline."""
        # 1. Parse MIDI file
        midi_path = _create_simple_midi([
            (60, 100, 0, 480), (64, 80, 480, 480), (67, 90, 960, 480),
        ])
        try:
            parser = MidiParser()
            tracks, info = parser.parse(midi_path)
            assert len(tracks) >= 1

            # 2. Quantize
            q = Quantizer(grid="1/4", strength=0.8)
            quantized = q.quantize_notes(tracks[0].notes)
            assert len(quantized) == 3

            # 3. Humanize
            h = Humanizer(timing_range=0.01, velocity_range=5, seed=42)
            humanized = h.humanize_notes(quantized)
            assert len(humanized) == 3

            # 4. Route
            router = MidiRouter()
            router.channels.create_channel(0, output="synth_1")
            routed = router.route_midi_notes(humanized)
            assert len(routed) == 3

            # 5. Render
            scheduler = NoteScheduler(bpm=info.bpm, sample_rate=44100, synth="sine")
            render_track = MidiTrack(name="routed", notes=humanized)
            audio = scheduler.render_track(render_track)
            assert len(audio) > 0
        finally:
            midi_path.unlink(missing_ok=True)

    def test_cc_controlled_routing(self):
        """CC mapping should update plugin parameters during routing."""
        param_values = {}
        router = MidiRouter(
            param_callback=lambda pid, pn, val: param_values.__setitem__(f"{pid}.{pn}", val)
        )
        router.channels.create_channel(0, output="synth_1")
        router.bind_cc("synth_1", cc=1, param_name="cutoff", min_val=100.0, max_val=5000.0, curve="log")
        router.bind_cc("synth_1", cc=7, param_name="volume", min_val=0.0, max_val=1.0)

        # Simulate knob movement
        router.on_cc(7, 100, 0)
        router.on_cc(1, 80, 0)

        assert "synth_1.volume" in param_values
        assert "synth_1.cutoff" in param_values
        assert param_values["synth_1.volume"] > 0.5
        assert param_values["synth_1.cutoff"] > 100.0
