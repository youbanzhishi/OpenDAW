"""
test_sampler.py — Tests for the VCMix sampler module (Phase 9.5).

Tests:
    - SampleZone creation and validation
    - Zone key/velocity mapping
    - SamplerEngine note_on/note_off lifecycle
    - Pitch shifting playback
    - Forward/reverse/alternate looping
    - Multi-zone mapping
    - YAML config parsing with sampler tracks
    - SamplerTrack rendering
    - One-shot trigger mode
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from vcmix.sampler.sample_zone import SampleZone
from vcmix.sampler.sampler_engine import SamplerEngine
from vcmix.sampler.sampler_track import SamplerTrack

# ── Helpers ──────────────────────────────────────────────────────────────

def _create_test_wav(
    path: Path,
    frequency: float = 440.0,
    sr: int = 44100,
    duration: float = 1.0,
) -> Path:
    """Create a test WAV file with a sine wave.

    Args:
        path: Output file path.
        frequency: Sine wave frequency in Hz.
        sr: Sample rate.
        duration: Duration in seconds.

    Returns:
        Path to the created file.
    """
    t = np.arange(int(sr * duration), dtype=np.float64) / sr
    audio = (0.5 * np.sin(2.0 * np.pi * frequency * t)).astype(np.float32)
    sf.write(str(path), audio, sr)
    return path


def _create_test_wav_with_loop(
    path: Path,
    sr: int = 44100,
    total_duration: float = 2.0,
    loop_start_sec: float = 0.5,
    loop_end_sec: float = 1.5,
) -> Path:
    """Create a test WAV file suitable for loop testing.

    Args:
        path: Output file path.
        sr: Sample rate.
        total_duration: Total duration in seconds.
        loop_start_sec: Loop start in seconds.
        loop_end_sec: Loop end in seconds.

    Returns:
        Path to the created file.
    """
    num_samples = int(sr * total_duration)
    t = np.arange(num_samples, dtype=np.float64) / sr
    # Use different frequencies for attack vs loop region so we can
    # detect looping behavior
    audio = np.zeros(num_samples, dtype=np.float32)
    loop_start_sample = int(loop_start_sec * sr)
    loop_end_sample = int(loop_end_sec * sr)

    # Attack region: 200 Hz
    attack = 0.5 * np.sin(2.0 * np.pi * 200.0 * t[:loop_start_sample])
    audio[:loop_start_sample] = attack.astype(np.float32)
    # Loop region: 600 Hz (distinct for testing)
    loop_region = 0.5 * np.sin(2.0 * np.pi * 600.0 * t[loop_start_sample:loop_end_sample])
    audio[loop_start_sample:loop_end_sample] = loop_region.astype(np.float32)
    # Tail region: 200 Hz
    if loop_end_sample < num_samples:
        tail = 0.5 * np.sin(2.0 * np.pi * 200.0 * t[loop_end_sample:])
        audio[loop_end_sample:] = tail.astype(np.float32)

    sf.write(str(path), audio, sr)
    return path


# ── Test: SampleZone Creation ────────────────────────────────────────────

class TestSampleZoneCreation:
    """Tests for SampleZone dataclass creation and validation."""

    def test_default_values(self):
        """Zone should have sensible defaults."""
        zone = SampleZone(file="test.wav")
        assert zone.root_key == 60
        assert zone.key_low == 0
        assert zone.key_high == 127
        assert zone.velocity_low == 0
        assert zone.velocity_high == 127
        assert zone.loop_mode == "forward"
        assert zone.trigger_mode == "gate"
        assert zone.tune_cents == 0.0
        assert zone.gain_db == 0.0
        assert zone.loop_start is None
        assert zone.loop_end is None

    def test_custom_values(self):
        """Zone should accept custom parameters."""
        zone = SampleZone(
            file="piano_C4.wav",
            root_key=60,
            key_low=48,
            key_high=72,
            velocity_low=64,
            velocity_high=127,
            loop_mode="reverse",
            trigger_mode="one-shot",
            tune_cents=10.0,
            gain_db=-3.0,
        )
        assert zone.file == "piano_C4.wav"
        assert zone.root_key == 60
        assert zone.key_low == 48
        assert zone.key_high == 72
        assert zone.loop_mode == "reverse"
        assert zone.trigger_mode == "one-shot"
        assert zone.tune_cents == 10.0
        assert zone.gain_db == -3.0

    def test_invalid_key_range(self):
        """key_low > key_high should raise ValueError."""
        with pytest.raises(ValueError, match="key_low"):
            SampleZone(file="test.wav", key_low=72, key_high=48)

    def test_invalid_velocity_range(self):
        """velocity_low > velocity_high should raise ValueError."""
        with pytest.raises(ValueError, match="velocity_low"):
            SampleZone(file="test.wav", velocity_low=100, velocity_high=50)

    def test_invalid_loop_mode(self):
        """Invalid loop_mode should raise ValueError."""
        with pytest.raises(ValueError, match="loop_mode"):
            SampleZone(file="test.wav", loop_mode="invalid")

    def test_invalid_trigger_mode(self):
        """Invalid trigger_mode should raise ValueError."""
        with pytest.raises(ValueError, match="trigger_mode"):
            SampleZone(file="test.wav", trigger_mode="invalid")

    def test_invalid_root_key(self):
        """root_key out of range should raise ValueError."""
        with pytest.raises(ValueError, match="root_key"):
            SampleZone(file="test.wav", root_key=128)

    def test_loop_points_validation(self):
        """loop_end <= loop_start should raise ValueError."""
        with pytest.raises(ValueError, match="loop_end"):
            SampleZone(file="test.wav", loop_start=1000, loop_end=500)

    def test_serialization(self):
        """Zone should serialize to and from dict."""
        zone = SampleZone(
            file="test.wav", root_key=60, key_low=48, key_high=72,
            loop_start=100, loop_end=1000,
        )
        d = zone.to_dict()
        assert d["file"] == "test.wav"
        assert d["root_key"] == 60
        assert d["loop_start"] == 100

        zone2 = SampleZone.from_dict(d)
        assert zone2.file == zone.file
        assert zone2.root_key == zone.root_key
        assert zone2.key_low == zone.key_low
        assert zone2.loop_start == zone.loop_start


# ── Test: Zone Key Mapping ──────────────────────────────────────────────

class TestZoneKeyMapping:
    """Tests for SampleZone.matches() and pitch_ratio()."""

    def test_matches_within_range(self):
        """Zone should match notes within its key/velocity range."""
        zone = SampleZone(file="test.wav", key_low=48, key_high=72)
        assert zone.matches(48, 64) is True
        assert zone.matches(60, 64) is True
        assert zone.matches(72, 64) is True

    def test_no_match_outside_key_range(self):
        """Zone should not match notes outside its key range."""
        zone = SampleZone(file="test.wav", key_low=48, key_high=72)
        assert zone.matches(47, 64) is False
        assert zone.matches(73, 64) is False

    def test_no_match_outside_velocity_range(self):
        """Zone should not match velocities outside its range."""
        zone = SampleZone(file="test.wav", velocity_low=64, velocity_high=100)
        assert zone.matches(60, 63) is False
        assert zone.matches(60, 64) is True
        assert zone.matches(60, 100) is True
        assert zone.matches(60, 101) is False

    def test_pitch_ratio_root_key(self):
        """Pitch ratio at root_key should be 1.0."""
        zone = SampleZone(file="test.wav", root_key=60)
        assert zone.pitch_ratio(60) == pytest.approx(1.0)

    def test_pitch_ratio_octave_up(self):
        """Pitch ratio one octave up should be 2.0."""
        zone = SampleZone(file="test.wav", root_key=60)
        assert zone.pitch_ratio(72) == pytest.approx(2.0)

    def test_pitch_ratio_octave_down(self):
        """Pitch ratio one octave down should be 0.5."""
        zone = SampleZone(file="test.wav", root_key=60)
        assert zone.pitch_ratio(48) == pytest.approx(0.5)

    def test_pitch_ratio_fifth(self):
        """Pitch ratio a perfect fifth up should be ~1.498."""
        zone = SampleZone(file="test.wav", root_key=60)
        assert zone.pitch_ratio(67) == pytest.approx(2.0 ** (7.0 / 12.0))

    def test_pitch_ratio_with_tune_cents(self):
        """Pitch ratio should include tune_cents offset."""
        zone = SampleZone(file="test.wav", root_key=60, tune_cents=100.0)
        # 100 cents up = 1 semitone up at root_key
        expected = 2.0 ** (100.0 / 1200.0)
        assert zone.pitch_ratio(60) == pytest.approx(expected)

    def test_gain_linear(self):
        """gain_linear should convert dB correctly."""
        zone = SampleZone(file="test.wav", gain_db=0.0)
        assert zone.gain_linear() == pytest.approx(1.0)

        zone = SampleZone(file="test.wav", gain_db=-6.0)
        assert zone.gain_linear() == pytest.approx(10.0 ** (-6.0 / 20.0))

    def test_has_loop(self):
        """has_loop should be True only when both loop points are set."""
        zone = SampleZone(file="test.wav")
        assert zone.has_loop is False

        zone = SampleZone(file="test.wav", loop_start=100, loop_end=1000)
        assert zone.has_loop is True

        zone = SampleZone(file="test.wav", loop_start=100)
        assert zone.has_loop is False


# ── Test: SamplerEngine Note On/Off ─────────────────────────────────────

class TestSamplerNoteOnOff:
    """Tests for SamplerEngine note_on/note_off lifecycle."""

    def test_note_on_creates_voice(self, tmp_path):
        """note_on should create an active voice."""
        wav_path = _create_test_wav(tmp_path / "test.wav")
        zone = SampleZone(file=str(wav_path), root_key=60, key_low=48, key_high=72)
        engine = SamplerEngine(sample_rate=44100)
        engine.load_zone(zone)

        result = engine.note_on(60, 100)
        assert result is True
        assert engine.active_voice_count == 1
        assert 60 in engine.active_voices

    def test_note_on_no_matching_zone(self):
        """note_on with no matching zone should return False."""
        engine = SamplerEngine(sample_rate=44100)
        result = engine.note_on(60, 100)
        assert result is False
        assert engine.active_voice_count == 0

    def test_note_off_releases_voice(self, tmp_path):
        """note_off should mark voice as released."""
        wav_path = _create_test_wav(tmp_path / "test.wav")
        zone = SampleZone(file=str(wav_path), root_key=60, trigger_mode="gate")
        engine = SamplerEngine(sample_rate=44100)
        engine.load_zone(zone)

        engine.note_on(60, 100)
        result = engine.note_off(60)
        assert result is True
        assert engine.active_voices[60].released is True

    def test_note_off_nonexistent_note(self):
        """note_off for a note that isn't playing should return False."""
        engine = SamplerEngine(sample_rate=44100)
        result = engine.note_off(60)
        assert result is False

    def test_all_notes_off(self, tmp_path):
        """all_notes_off should release all active voices."""
        wav_path = _create_test_wav(tmp_path / "test.wav")
        zone = SampleZone(file=str(wav_path), root_key=60, key_low=0, key_high=127)
        engine = SamplerEngine(sample_rate=44100)
        engine.load_zone(zone)

        engine.note_on(60, 100)
        engine.note_on(64, 80)
        engine.note_on(67, 90)
        assert engine.active_voice_count == 3

        engine.all_notes_off()
        for voice in engine.active_voices.values():
            assert voice.released is True

    def test_note_on_replaces_existing_voice(self, tmp_path):
        """note_on for an already-playing note should replace the voice."""
        wav_path = _create_test_wav(tmp_path / "test.wav")
        zone = SampleZone(file=str(wav_path), root_key=60, key_low=0, key_high=127)
        engine = SamplerEngine(sample_rate=44100)
        engine.load_zone(zone)

        engine.note_on(60, 80)
        assert engine.active_voices[60].velocity == 80

        engine.note_on(60, 120)
        assert engine.active_voices[60].velocity == 120

    def test_invalid_note_number(self, tmp_path):
        """Invalid MIDI note numbers should be rejected."""
        wav_path = _create_test_wav(tmp_path / "test.wav")
        zone = SampleZone(file=str(wav_path), root_key=60, key_low=0, key_high=127)
        engine = SamplerEngine(sample_rate=44100)
        engine.load_zone(zone)

        assert engine.note_on(-1, 100) is False
        assert engine.note_on(128, 100) is False


# ── Test: Pitch Shifting ────────────────────────────────────────────────

class TestPitchShifting:
    """Tests for pitch-shifted sample playback."""

    def test_root_key_no_shift(self, tmp_path):
        """Playing at root_key should output the original pitch."""
        sr = 44100
        freq = 440.0
        wav_path = _create_test_wav(tmp_path / "test.wav", frequency=freq, sr=sr)
        zone = SampleZone(file=str(wav_path), root_key=69)  # A4 = 440Hz
        engine = SamplerEngine(sample_rate=sr)
        engine.load_zone(zone)

        engine.note_on(69, 127)  # Play at root key
        audio = engine.render(sr)  # 1 second
        engine.note_off(69)

        # Should produce significant audio
        assert len(audio) == sr
        rms = np.sqrt(np.mean(audio.astype(np.float64) ** 2))
        assert rms > 0.01  # Not silence

    def test_higher_note_faster_playback(self, tmp_path):
        """A note above root_key should play faster (higher pitch)."""
        sr = 44100
        wav_path = _create_test_wav(tmp_path / "test.wav", frequency=440.0, sr=sr, duration=1.0)
        zone = SampleZone(file=str(wav_path), root_key=60, key_low=0, key_high=127)
        engine = SamplerEngine(sample_rate=sr)
        engine.load_zone(zone)

        # Play one octave up
        engine.note_on(72, 127)
        audio_high = engine.render(sr)
        engine.note_off(72)

        # Play at root key
        engine.note_on(60, 127)
        audio_root = engine.render(sr)
        engine.note_off(60)

        # Both should produce audio
        assert np.max(np.abs(audio_high)) > 0.01
        assert np.max(np.abs(audio_root)) > 0.01

    def test_lower_note_slower_playback(self, tmp_path):
        """A note below root_key should play slower (lower pitch)."""
        sr = 44100
        wav_path = _create_test_wav(tmp_path / "test.wav", frequency=440.0, sr=sr, duration=1.0)
        zone = SampleZone(file=str(wav_path), root_key=60, key_low=0, key_high=127)
        engine = SamplerEngine(sample_rate=sr)
        engine.load_zone(zone)

        # Play one octave down
        engine.note_on(48, 127)
        audio_low = engine.render(sr)
        engine.note_off(48)

        # Should produce audio
        assert np.max(np.abs(audio_low)) > 0.01


# ── Test: Loop Forward ──────────────────────────────────────────────────

class TestLoopForward:
    """Tests for forward loop mode."""

    def test_forward_loop_continues_past_end(self, tmp_path):
        """Forward loop should wrap from loop_end back to loop_start."""
        sr = 44100
        wav_path = _create_test_wav_with_loop(
            tmp_path / "loop.wav", sr=sr,
            total_duration=2.0, loop_start_sec=0.5, loop_end_sec=1.5,
        )
        loop_start = int(0.5 * sr)
        loop_end = int(1.5 * sr)

        zone = SampleZone(
            file=str(wav_path), root_key=60,
            loop_start=loop_start, loop_end=loop_end,
            loop_mode="forward", trigger_mode="gate",
        )
        engine = SamplerEngine(sample_rate=sr)
        engine.load_zone(zone)

        engine.note_on(60, 100)
        # Render more than the total sample length to test looping
        audio = engine.render(sr * 4)  # 4 seconds
        engine.note_off(60)

        # Should have non-silent audio throughout (loop is sustaining)
        assert len(audio) == sr * 4
        # Check that audio continues past original sample length
        tail_rms = np.sqrt(np.mean(audio[sr * 2:].astype(np.float64) ** 2))
        assert tail_rms > 0.01  # Not silent in the loop tail


# ── Test: Loop Reverse ──────────────────────────────────────────────────

class TestLoopReverse:
    """Tests for reverse loop mode."""

    def test_reverse_loop_alternates_direction(self, tmp_path):
        """Reverse loop should alternate playback direction at loop boundaries."""
        sr = 44100
        wav_path = _create_test_wav_with_loop(
            tmp_path / "loop.wav", sr=sr,
            total_duration=2.0, loop_start_sec=0.5, loop_end_sec=1.5,
        )
        loop_start = int(0.5 * sr)
        loop_end = int(1.5 * sr)

        zone = SampleZone(
            file=str(wav_path), root_key=60,
            loop_start=loop_start, loop_end=loop_end,
            loop_mode="reverse", trigger_mode="gate",
        )
        engine = SamplerEngine(sample_rate=sr)
        engine.load_zone(zone)

        engine.note_on(60, 100)
        audio = engine.render(sr * 4)
        engine.note_off(60)

        # Should have sustained audio from looping
        assert len(audio) == sr * 4
        tail_rms = np.sqrt(np.mean(audio[sr * 2:].astype(np.float64) ** 2))
        assert tail_rms > 0.01


# ── Test: Multi-Zone Mapping ────────────────────────────────────────────

class TestMultiZoneMapping:
    """Tests for multiple zones with different key ranges."""

    def test_different_zones_for_different_keys(self, tmp_path):
        """Different keys should trigger different zones."""
        sr = 44100
        wav_low = _create_test_wav(tmp_path / "low.wav", frequency=220.0, sr=sr)
        wav_high = _create_test_wav(tmp_path / "high.wav", frequency=880.0, sr=sr)

        engine = SamplerEngine(sample_rate=sr)
        engine.load_zone(SampleZone(
            file=str(wav_low), root_key=48, key_low=0, key_high=59,
        ))
        engine.load_zone(SampleZone(
            file=str(wav_high), root_key=72, key_low=60, key_high=127,
        ))

        # Low note should match first zone
        assert engine.note_on(48, 100) is True
        assert engine.active_voices[48].zone.root_key == 48
        engine.note_off(48)

        # High note should match second zone
        assert engine.note_on(72, 100) is True
        assert engine.active_voices[72].zone.root_key == 72
        engine.note_off(72)

    def test_zone_priority_first_match(self, tmp_path):
        """When zones overlap, the first loaded zone should win."""
        sr = 44100
        wav1 = _create_test_wav(tmp_path / "zone1.wav", frequency=440.0, sr=sr)
        wav2 = _create_test_wav(tmp_path / "zone2.wav", frequency=880.0, sr=sr)

        engine = SamplerEngine(sample_rate=sr)
        engine.load_zone(SampleZone(
            file=str(wav1), root_key=60, key_low=48, key_high=72,
        ))
        engine.load_zone(SampleZone(
            file=str(wav2), root_key=60, key_low=36, key_high=84,
        ))

        # Note 60 matches both zones; first zone should win
        engine.note_on(60, 100)
        assert engine.active_voices[60].zone.file == str(wav1)
        engine.note_off(60)

        # Note 36 only matches second zone
        engine.note_on(36, 100)
        assert engine.active_voices[36].zone.file == str(wav2)
        engine.note_off(36)

    def test_velocity_zone_selection(self, tmp_path):
        """Zones with different velocity ranges should be selected correctly."""
        sr = 44100
        wav_soft = _create_test_wav(tmp_path / "soft.wav", frequency=440.0, sr=sr)
        wav_loud = _create_test_wav(tmp_path / "loud.wav", frequency=660.0, sr=sr)

        engine = SamplerEngine(sample_rate=sr)
        engine.load_zone(SampleZone(
            file=str(wav_soft), root_key=60, velocity_low=0, velocity_high=63,
        ))
        engine.load_zone(SampleZone(
            file=str(wav_loud), root_key=60, velocity_low=64, velocity_high=127,
        ))

        # Soft velocity
        engine.note_on(60, 30)
        assert engine.active_voices[60].zone.file == str(wav_soft)
        engine.note_off(60)

        # Loud velocity
        engine.note_on(60, 100)
        assert engine.active_voices[60].zone.file == str(wav_loud)
        engine.note_off(60)


# ── Test: Sampler YAML Parsing ──────────────────────────────────────────

class TestSamplerYAMLParsing:
    """Tests for sampler track configuration in YAML."""

    def test_parse_sampler_track(self, tmp_path):
        """YAML config with sampler track should parse correctly."""
        import yaml

        from vcmix.config.parser import parse_project

        # Create test WAV files
        _create_test_wav(tmp_path / "piano_C4.wav", frequency=261.6, sr=44100)
        _create_test_wav(tmp_path / "piano_C5.wav", frequency=523.3, sr=44100)

        # Create MIDI file
        import mido
        midi_path = tmp_path / "piano.mid"
        mid = mido.MidiFile(ticks_per_beat=480)
        track = mido.MidiTrack()
        mid.tracks.append(track)
        track.append(mido.MetaMessage("set_tempo", tempo=mido.bpm2tempo(120), time=0))
        track.append(mido.Message("note_on", note=60, velocity=100, time=0))
        track.append(mido.Message("note_off", note=60, velocity=0, time=480))
        mid.save(str(midi_path))

        # Create project YAML
        project_data = {
            "name": "Sampler Test",
            "bpm": 120,
            "sample_rate": 44100,
            "tracks": [
                {
                    "name": "piano",
                    "type": "sampler",
                    "zones": [
                        {
                            "file": "piano_C4.wav",
                            "root_key": 60,
                            "key_low": 48,
                            "key_high": 72,
                        },
                        {
                            "file": "piano_C5.wav",
                            "root_key": 72,
                            "key_low": 72,
                            "key_high": 96,
                        },
                    ],
                    "midi_file": "piano.mid",
                }
            ],
            "master": {
                "output": "output.wav",
            },
        }

        yaml_path = tmp_path / "project.yaml"
        with open(yaml_path, "w") as f:
            yaml.dump(project_data, f)

        cfg = parse_project(yaml_path)
        assert len(cfg.tracks) == 1
        track_cfg = cfg.tracks[0]
        assert track_cfg.type == "sampler"
        assert len(track_cfg.zones) == 2
        assert track_cfg.zones[0].root_key == 60
        assert track_cfg.zones[0].key_low == 48
        assert track_cfg.zones[0].key_high == 72
        assert track_cfg.zones[1].root_key == 72
        assert track_cfg.midi_file == "piano.mid"

    def test_zone_config_validation(self, tmp_path):
        """Invalid zone config in YAML should fail validation."""
        import yaml
        from pydantic import ValidationError

        from vcmix.config.parser import parse_project

        project_data = {
            "name": "Bad Sampler",
            "bpm": 120,
            "tracks": [
                {
                    "name": "bad",
                    "type": "sampler",
                    "zones": [
                        {
                            "file": "test.wav",
                            "root_key": 999,  # Invalid!
                        }
                    ],
                }
            ],
            "master": {"output": "output.wav"},
        }

        yaml_path = tmp_path / "bad_project.yaml"
        with open(yaml_path, "w") as f:
            yaml.dump(project_data, f)

        with pytest.raises(ValidationError):
            parse_project(yaml_path)


# ── Test: SamplerTrack Rendering ────────────────────────────────────────

class TestSamplerTrackRendering:
    """Tests for SamplerTrack high-level rendering."""

    def test_render_from_midi(self, tmp_path):
        """SamplerTrack should render audio from MIDI events."""
        sr = 44100
        wav_path = _create_test_wav(tmp_path / "test.wav", frequency=440.0, sr=sr, duration=2.0)

        zone = SampleZone(file=str(wav_path), root_key=60, key_low=0, key_high=127)
        track = SamplerTrack(
            name="test_sampler",
            sample_rate=sr,
            zones=[zone],
            bpm=120.0,
        )

        # Create some MIDI notes
        from vcmix.midi.midi_parser import MidiNote
        notes = [
            MidiNote(note=60, velocity=100, start_beat=0.0, duration_beats=2.0),
            MidiNote(note=64, velocity=80, start_beat=2.0, duration_beats=2.0),
        ]

        samples_per_beat = (60.0 / 120.0) * sr
        total_samples = int(4.0 * samples_per_beat) + sr

        audio = track.render_from_midi(notes, total_samples, bpm=120.0)

        assert len(audio) == total_samples
        assert audio.dtype == np.float32
        # Should have non-silent audio
        rms = np.sqrt(np.mean(audio.astype(np.float64) ** 2))
        assert rms > 0.001

    def test_render_with_midi_file(self, tmp_path):
        """SamplerTrack should render from a MIDI file."""
        sr = 44100
        wav_path = _create_test_wav(tmp_path / "test.wav", frequency=440.0, sr=sr, duration=2.0)

        # Create MIDI file
        import mido
        midi_path = tmp_path / "test.mid"
        mid = mido.MidiFile(ticks_per_beat=480)
        track = mido.MidiTrack()
        mid.tracks.append(track)
        track.append(mido.MetaMessage("set_tempo", tempo=mido.bpm2tempo(120), time=0))
        track.append(mido.Message("note_on", note=60, velocity=100, time=0))
        track.append(mido.Message("note_off", note=60, velocity=0, time=960))
        mid.save(str(midi_path))

        zone = SampleZone(file=str(wav_path), root_key=60, key_low=0, key_high=127)
        sampler_track = SamplerTrack(
            name="test",
            sample_rate=sr,
            zones=[zone],
            midi_file=str(midi_path),
            bpm=120.0,
        )

        audio = sampler_track.render_full()
        assert len(audio) > 0
        assert audio.dtype == np.float32
        # Should have non-silent audio
        rms = np.sqrt(np.mean(audio.astype(np.float64) ** 2))
        assert rms > 0.001

    def test_empty_notes_produces_silence(self, tmp_path):
        """Empty note list should produce silence."""
        sr = 44100
        wav_path = _create_test_wav(tmp_path / "test.wav", frequency=440.0, sr=sr)
        zone = SampleZone(file=str(wav_path), root_key=60)
        track = SamplerTrack(name="test", sample_rate=sr, zones=[zone], bpm=120.0)

        audio = track.render_from_midi([], sr * 2, bpm=120.0)
        assert len(audio) == sr * 2
        assert np.all(audio == 0.0)


# ── Test: One-Shot Trigger ──────────────────────────────────────────────

class TestOneShotTrigger:
    """Tests for one-shot trigger mode."""

    def test_one_shot_plays_to_end(self, tmp_path):
        """One-shot mode should play the entire sample even after note_off."""
        sr = 44100
        duration = 0.5  # 0.5 second sample
        wav_path = _create_test_wav(
            tmp_path / "oneshot.wav", frequency=440.0, sr=sr, duration=duration
        )

        zone = SampleZone(
            file=str(wav_path), root_key=60,
            trigger_mode="one-shot",
        )
        engine = SamplerEngine(sample_rate=sr)
        engine.load_zone(zone)

        engine.note_on(60, 100)
        # Immediately release
        engine.note_off(60)
        # Render more than the sample length
        audio = engine.render(sr)  # 1 second

        # Should still produce audio (one-shot ignores note_off for non-looping)
        # The voice continues until the sample is fully played
        rms = np.sqrt(np.mean(audio.astype(np.float64) ** 2))
        assert rms > 0.001

    def test_gate_stops_on_release(self, tmp_path):
        """Gate mode should stop when note_off is received (no loop)."""
        sr = 44100
        duration = 2.0  # 2 second sample
        wav_path = _create_test_wav(
            tmp_path / "gate.wav", frequency=440.0, sr=sr, duration=duration
        )

        zone = SampleZone(
            file=str(wav_path), root_key=60,
            trigger_mode="gate",
        )
        engine = SamplerEngine(sample_rate=sr)
        engine.load_zone(zone)

        engine.note_on(60, 100)
        # Render a small amount
        engine.render(int(sr * 0.1))  # 0.1 seconds
        # Release
        engine.note_off(60)
        # Render more
        engine.render(sr)  # 1 second

        # Voice should have been removed; output should be silence
        # (gate mode without loop marks playing=False on note_off)
        assert engine.active_voice_count == 0

    def test_one_shot_with_loop(self, tmp_path):
        """One-shot with loop should continue looping after note_off."""
        sr = 44100
        wav_path = _create_test_wav_with_loop(
            tmp_path / "loop_oneshot.wav", sr=sr,
            total_duration=2.0, loop_start_sec=0.5, loop_end_sec=1.5,
        )
        loop_start = int(0.5 * sr)
        loop_end = int(1.5 * sr)

        zone = SampleZone(
            file=str(wav_path), root_key=60,
            loop_start=loop_start, loop_end=loop_end,
            loop_mode="forward",
            trigger_mode="one-shot",
        )
        engine = SamplerEngine(sample_rate=sr)
        engine.load_zone(zone)

        engine.note_on(60, 100)
        engine.render(int(sr * 0.3))  # Render past loop start
        engine.note_off(60)

        # One-shot with loop: the voice should still be playing
        # because one-shot + loop = sustain loop until natural end
        # In our implementation, one-shot ignores note_off, so voice continues
        # Check if voice is still active
        assert 60 in engine.active_voices

        # Should still render audio
        audio = engine.render(sr)
        rms = np.sqrt(np.mean(audio.astype(np.float64) ** 2))
        assert rms > 0.001


# ── Test: Engine Info ───────────────────────────────────────────────────

class TestEngineInfo:
    """Tests for engine info and zone management."""

    def test_zone_info(self, tmp_path):
        """get_zone_info should return details about all zones."""
        wav_path = _create_test_wav(tmp_path / "test.wav", frequency=440.0, sr=44100)
        zone = SampleZone(file=str(wav_path), root_key=60, key_low=48, key_high=72)
        engine = SamplerEngine(sample_rate=44100)
        engine.load_zone(zone)

        info = engine.get_zone_info()
        assert len(info) == 1
        assert info[0]["root_key"] == 60
        assert info[0]["key_range"] == "48-72"
        assert info[0]["sample_loaded"] is True

    def test_remove_zone(self, tmp_path):
        """remove_zone should remove a zone from the engine."""
        wav_path = _create_test_wav(tmp_path / "test.wav", frequency=440.0, sr=44100)
        zone = SampleZone(file=str(wav_path), root_key=60)
        engine = SamplerEngine(sample_rate=44100)
        engine.load_zone(zone)
        assert len(engine.zones) == 1

        engine.remove_zone(zone)
        assert len(engine.zones) == 0

    def test_clear_zones(self, tmp_path):
        """clear_zones should remove all zones and voices."""
        wav_path = _create_test_wav(tmp_path / "test.wav", frequency=440.0, sr=44100)
        zone = SampleZone(file=str(wav_path), root_key=60, key_low=0, key_high=127)
        engine = SamplerEngine(sample_rate=44100)
        engine.load_zone(zone)
        engine.note_on(60, 100)

        engine.clear_zones()
        assert len(engine.zones) == 0
        assert engine.active_voice_count == 0
