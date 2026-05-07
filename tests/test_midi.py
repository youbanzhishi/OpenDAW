"""Tests for vcmix.midi module — Phase 9 MIDI support."""
import tempfile
from pathlib import Path

import numpy as np
import pytest

from vcmix.midi.midi_parser import MidiInfo, MidiNote, MidiParser, MidiTrack
from vcmix.midi.note_scheduler import ADSR, NoteScheduler, list_synths

# ── Helpers ──────────────────────────────────────────────────────────────

def _create_simple_midi(
    notes: list[tuple[int, int, int, int]],
    bpm: int = 120,
    ticks_per_beat: int = 480,
) -> Path:
    """Create a simple MIDI file for testing.

    Args:
        notes: List of (note, velocity, start_tick, duration_ticks) tuples.
        bpm: Tempo in BPM.
        ticks_per_beat: Ticks per quarter note.

    Returns:
        Path to the temporary .mid file.
    """
    import mido

    mid = mido.MidiFile(ticks_per_beat=ticks_per_beat)
    track = mido.MidiTrack()
    mid.tracks.append(track)

    # Tempo meta event
    tempo = mido.bpm2tempo(bpm)
    track.append(mido.MetaMessage("set_tempo", tempo=tempo, time=0))

    # Build events list (note_on + note_off)
    events: list[tuple[int, str, int, int]] = []  # (tick, type, note, velocity)
    for note_num, velocity, start_tick, duration_ticks in notes:
        events.append((start_tick, "note_on", note_num, velocity))
        events.append((start_tick + duration_ticks, "note_off", note_num, 0))

    # Sort by tick (note_off before note_on at same tick)
    events.sort(key=lambda e: (e[0], e[1] == "note_on"))

    # Write events with delta times
    current_tick = 0
    for tick, msg_type, note_num, velocity in events:
        delta = tick - current_tick
        if msg_type == "note_on":
            track.append(mido.Message("note_on", note=note_num, velocity=velocity, time=delta))
        else:
            track.append(mido.Message("note_off", note=note_num, velocity=0, time=delta))
        current_tick = tick

    # End of track
    track.append(mido.MetaMessage("end_of_track", time=0))

    tmp = tempfile.NamedTemporaryFile(suffix=".mid", delete=False)
    tmp.close()
    mid.save(tmp.name)
    return Path(tmp.name)


# ── MidiNote Tests ───────────────────────────────────────────────────────

class TestMidiNote:
    def test_note_creation(self):
        note = MidiNote(note=60, velocity=100, start_beat=0.0, duration_beats=1.0)
        assert note.note == 60
        assert note.velocity == 100
        assert note.start_beat == 0.0
        assert note.duration_beats == 1.0

    def test_note_frequency(self):
        note = MidiNote(note=69, velocity=100, start_beat=0.0, duration_beats=1.0)
        assert abs(note.frequency - 440.0) < 0.01  # A4 = 440Hz

    def test_note_name(self):
        note = MidiNote(note=60, velocity=100, start_beat=0.0, duration_beats=1.0)
        assert note.note_name == "C4"

    def test_note_name_sharp(self):
        note = MidiNote(note=61, velocity=100, start_beat=0.0, duration_beats=1.0)
        assert note.note_name == "C#4"

    def test_note_out_of_range(self):
        with pytest.raises(ValueError):
            MidiNote(note=128, velocity=100, start_beat=0.0, duration_beats=1.0)

    def test_negative_start_beat(self):
        with pytest.raises(ValueError):
            MidiNote(note=60, velocity=100, start_beat=-1.0, duration_beats=1.0)

    def test_zero_duration(self):
        with pytest.raises(ValueError):
            MidiNote(note=60, velocity=100, start_beat=0.0, duration_beats=0.0)


# ── MidiTrack Tests ──────────────────────────────────────────────────────

class TestMidiTrack:
    def test_empty_track(self):
        track = MidiTrack(name="test")
        assert track.note_count == 0
        assert track.total_beats == 0.0

    def test_track_total_beats(self):
        notes = [
            MidiNote(note=60, velocity=100, start_beat=0.0, duration_beats=1.0),
            MidiNote(note=64, velocity=100, start_beat=2.0, duration_beats=2.0),
        ]
        track = MidiTrack(name="test", notes=notes)
        assert track.total_beats == 4.0

    def test_get_notes_in_range(self):
        notes = [
            MidiNote(note=60, velocity=100, start_beat=0.0, duration_beats=1.0),
            MidiNote(note=64, velocity=100, start_beat=2.0, duration_beats=2.0),
            MidiNote(note=67, velocity=100, start_beat=4.0, duration_beats=1.0),
        ]
        track = MidiTrack(name="test", notes=notes)
        result = track.get_notes_in_range(1.0, 3.0)
        assert len(result) == 1  # Only the note at beat 2
        assert result[0].note == 64


# ── MidiParser Tests ─────────────────────────────────────────────────────

class TestMidiParser:
    def test_parse_midi_file(self):
        """Test parsing a simple MIDI file with one note."""
        midi_path = _create_simple_midi([
            (60, 100, 0, 480),   # C4, vel 100, beat 0, 1 beat
        ])
        try:
            parser = MidiParser()
            tracks, info = parser.parse(midi_path)
            assert len(tracks) >= 1
            assert tracks[0].note_count >= 1
            assert info.bpm == 120.0
        finally:
            midi_path.unlink(missing_ok=True)

    def test_parse_multiple_notes(self):
        """Test parsing a MIDI file with multiple notes."""
        midi_path = _create_simple_midi([
            (60, 100, 0, 480),      # C4 at beat 0
            (64, 80, 480, 480),     # E4 at beat 1
            (67, 90, 960, 480),     # G4 at beat 2
        ])
        try:
            parser = MidiParser()
            tracks, info = parser.parse(midi_path)
            assert len(tracks) >= 1
            assert tracks[0].note_count == 3
            # Check first note
            first = tracks[0].notes[0]
            assert first.note == 60
            assert first.velocity == 100
            assert abs(first.start_beat) < 0.01
            assert abs(first.duration_beats - 1.0) < 0.01
        finally:
            midi_path.unlink(missing_ok=True)

    def test_parse_file_not_found(self):
        parser = MidiParser()
        with pytest.raises(FileNotFoundError):
            parser.parse("/nonexistent/file.mid")

    def test_parse_info_defaults(self):
        """Test that MidiInfo has sensible defaults."""
        info = MidiInfo()
        assert info.bpm == 120.0
        assert info.time_signature_numerator == 4
        assert info.time_signature_denominator == 4

    def test_parse_to_dict(self):
        """Test serialization to dictionary."""
        midi_path = _create_simple_midi([
            (60, 100, 0, 480),
        ])
        try:
            parser = MidiParser()
            data = parser.parse_to_dict(midi_path)
            assert "bpm" in data
            assert "tracks" in data
            assert len(data["tracks"]) >= 1
        finally:
            midi_path.unlink(missing_ok=True)

    def test_parse_different_bpm(self):
        """Test parsing with non-default BPM."""
        midi_path = _create_simple_midi([
            (60, 100, 0, 480),
        ], bpm=140)
        try:
            parser = MidiParser()
            tracks, info = parser.parse(midi_path)
            assert abs(info.bpm - 140.0) < 1.0
        finally:
            midi_path.unlink(missing_ok=True)


# ── NoteScheduler Tests ──────────────────────────────────────────────────

class TestNoteScheduler:
    def test_scheduler_basic(self):
        """Test basic note scheduling and rendering."""
        notes = [
            MidiNote(note=60, velocity=100, start_beat=0.0, duration_beats=1.0),
        ]
        track = MidiTrack(name="test", notes=notes)
        scheduler = NoteScheduler(bpm=120, sample_rate=44100, synth="sine")
        audio = scheduler.render_track(track)

        assert isinstance(audio, np.ndarray)
        assert audio.dtype == np.float32
        # At 120 BPM, 1 beat = 0.5 sec = 22050 samples
        expected_samples = int(0.5 * 44100)
        assert abs(len(audio) - expected_samples) < 100

    def test_scheduler_sawtooth(self):
        """Test sawtooth synth rendering."""
        notes = [
            MidiNote(note=69, velocity=80, start_beat=0.0, duration_beats=0.5),
        ]
        track = MidiTrack(name="test", notes=notes)
        scheduler = NoteScheduler(bpm=120, sample_rate=44100, synth="sawtooth")
        audio = scheduler.render_track(track)

        assert isinstance(audio, np.ndarray)
        assert len(audio) > 0
        # Sawtooth should have non-zero energy
        rms = float(np.sqrt(np.mean(audio.astype(np.float64) ** 2)))
        assert rms > 0.001

    def test_scheduler_square(self):
        """Test square wave rendering."""
        notes = [
            MidiNote(note=60, velocity=100, start_beat=0.0, duration_beats=1.0),
        ]
        track = MidiTrack(name="test", notes=notes)
        scheduler = NoteScheduler(bpm=120, sample_rate=44100, synth="square")
        audio = scheduler.render_track(track)
        assert len(audio) > 0

    def test_scheduler_triangle(self):
        """Test triangle wave rendering."""
        notes = [
            MidiNote(note=60, velocity=100, start_beat=0.0, duration_beats=1.0),
        ]
        track = MidiTrack(name="test", notes=notes)
        scheduler = NoteScheduler(bpm=120, sample_rate=44100, synth="triangle")
        audio = scheduler.render_track(track)
        assert len(audio) > 0

    def test_scheduler_invalid_synth(self):
        """Test that invalid synth type raises error."""
        notes = [MidiNote(note=60, velocity=100, start_beat=0.0, duration_beats=1.0)]
        track = MidiTrack(name="test", notes=notes)
        scheduler = NoteScheduler(bpm=120, sample_rate=44100, synth="sine")
        with pytest.raises(ValueError, match="Unknown synth type"):
            scheduler.render_track(track, synth="invalid_synth")

    def test_scheduler_empty_track(self):
        """Test rendering an empty track."""
        track = MidiTrack(name="empty", notes=[])
        scheduler = NoteScheduler(bpm=120, sample_rate=44100)
        audio = scheduler.render_track(track)
        assert len(audio) == 0

    def test_scheduler_multiple_notes(self):
        """Test rendering multiple overlapping notes."""
        notes = [
            MidiNote(note=60, velocity=80, start_beat=0.0, duration_beats=2.0),
            MidiNote(note=64, velocity=80, start_beat=1.0, duration_beats=2.0),
            MidiNote(note=67, velocity=80, start_beat=2.0, duration_beats=2.0),
        ]
        track = MidiTrack(name="chord", notes=notes)
        scheduler = NoteScheduler(bpm=120, sample_rate=44100, synth="sine")
        audio = scheduler.render_track(track)
        # Total beats = 4 (note at beat 2 + 2 beats duration)
        assert len(audio) > 0

    def test_scheduler_velocity_scaling(self):
        """Test that velocity affects amplitude."""
        notes_loud = [MidiNote(note=60, velocity=127, start_beat=0.0, duration_beats=1.0)]
        notes_quiet = [MidiNote(note=60, velocity=30, start_beat=0.0, duration_beats=1.0)]

        track_loud = MidiTrack(name="loud", notes=notes_loud)
        track_quiet = MidiTrack(name="quiet", notes=notes_quiet)

        scheduler = NoteScheduler(bpm=120, sample_rate=44100, synth="sine")
        audio_loud = scheduler.render_track(track_loud)
        audio_quiet = scheduler.render_track(track_quiet)

        rms_loud = float(np.sqrt(np.mean(audio_loud.astype(np.float64) ** 2)))
        rms_quiet = float(np.sqrt(np.mean(audio_quiet.astype(np.float64) ** 2)))
        assert rms_loud > rms_quiet

    def test_beat_to_sample_conversion(self):
        scheduler = NoteScheduler(bpm=120, sample_rate=44100)
        # At 120 BPM: 1 beat = 0.5 sec = 22050 samples
        assert scheduler.beat_to_sample(1.0) == 22050
        assert scheduler.beat_to_sample(0.0) == 0
        assert scheduler.beat_to_sample(2.0) == 44100

    def test_get_active_notes_at_beat(self):
        notes = [
            MidiNote(note=60, velocity=100, start_beat=0.0, duration_beats=2.0),
            MidiNote(note=64, velocity=100, start_beat=1.0, duration_beats=1.0),
        ]
        scheduler = NoteScheduler(bpm=120, sample_rate=44100)
        active = scheduler.get_active_notes_at_beat(notes, 0.5)
        assert len(active) == 1
        assert active[0].note == 60

        active = scheduler.get_active_notes_at_beat(notes, 1.5)
        assert len(active) == 2

        active = scheduler.get_active_notes_at_beat(notes, 3.0)
        assert len(active) == 0

    def test_schedule_events(self):
        notes = [
            MidiNote(note=60, velocity=100, start_beat=0.0, duration_beats=1.0),
        ]
        scheduler = NoteScheduler(bpm=120, sample_rate=44100)
        events = scheduler.schedule_events(notes)
        assert len(events) == 2  # note_on + note_off
        assert events[0]["type"] == "note_on"
        assert events[0]["beat"] == 0.0
        assert events[1]["type"] == "note_off"
        assert events[1]["beat"] == 1.0

    def test_scheduler_negative_bpm_raises(self):
        with pytest.raises(ValueError, match="BPM must be positive"):
            NoteScheduler(bpm=-1)

    def test_render_note_list(self):
        notes = [
            MidiNote(note=60, velocity=100, start_beat=0.0, duration_beats=1.0),
            MidiNote(note=64, velocity=80, start_beat=1.0, duration_beats=1.0),
        ]
        scheduler = NoteScheduler(bpm=120, sample_rate=44100, synth="sine")
        audio = scheduler.render_note_list(notes)
        assert len(audio) > 0


# ── ADSR Tests ───────────────────────────────────────────────────────────

class TestADSR:
    def test_adsr_basic(self):
        adsr = ADSR(attack=0.01, decay=0.01, sustain=0.8, release=0.01)
        envelope = adsr.generate(44100, 44100)  # 1 second
        assert len(envelope) == 44100
        assert envelope.dtype == np.float32
        # Envelope should start near 0 (attack start)
        assert envelope[0] < 0.1
        # Should have some non-zero values
        assert float(np.max(envelope)) > 0.5

    def test_adsr_zero_duration(self):
        adsr = ADSR()
        envelope = adsr.generate(0, 44100)
        assert len(envelope) == 0

    def test_adsr_default(self):
        adsr = ADSR()
        assert adsr.attack == 0.005
        assert adsr.sustain == 0.8


# ── list_synths Tests ───────────────────────────────────────────────────

class TestListSynths:
    def test_returns_synths(self):
        synths = list_synths()
        assert "sine" in synths
        assert "sawtooth" in synths
        assert "square" in synths
        assert "triangle" in synths

    def test_count(self):
        assert len(list_synths()) == 4


# ── MIDI Track in YAML integration test ──────────────────────────────────

class TestMidiTrackInYaml:
    def test_midi_track_config(self):
        """Test that parser accepts MIDI track configuration."""
        from vcmix.config.parser import TrackConfig

        track = TrackConfig(
            name="synth",
            file="",
            type="midi",
            midi_file="melody.mid",
            synth="sawtooth",
            effects=[],
        )
        assert track.type == "midi"
        assert track.midi_file == "melody.mid"
        assert track.synth == "sawtooth"

    def test_audio_track_default_type(self):
        """Test that default track type is 'audio'."""
        from vcmix.config.parser import TrackConfig

        track = TrackConfig(name="vocal", file="vocal.wav")
        assert track.type == "audio"

    def test_yaml_with_midi_track(self):
        """Test parsing a YAML with MIDI track."""
        import tempfile

        yaml_content = """
name: test_midi_project
bpm: 120
tracks:
  - name: synth
    type: midi
    midi_file: melody.mid
    synth: sawtooth
    effects:
      - name: vc-reverb
        params:
          wet: 0.3
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(yaml_content)
            f.flush()
            from vcmix.config.parser import parse_project
            config = parse_project(f.name)
            assert len(config.tracks) == 1
            assert config.tracks[0].type == "midi"
            assert config.tracks[0].midi_file == "melody.mid"
            assert config.tracks[0].synth == "sawtooth"
            Path(f.name).unlink(missing_ok=True)
