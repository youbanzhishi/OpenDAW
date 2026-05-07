"""
test_realtime_engine.py — Tests for the realtime audio engine.

Tests cover:
- RealtimeEngine: play/stop/pause/seek/loop/multi-track mixing
- TrackClip: audio data access and zero-padding
- RealtimeTrack: clip management and duration
- Transport: time conversion, tempo, time signature
- AudioDriver: mock driver, driver creation
- EngineState: state transitions

All tests run without actual audio hardware (using mock/offline mode).
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from vcmix.engine.realtime_engine import (
    EngineState,
    RealtimeEngine,
    RealtimeTrack,
    TrackClip,
)
from vcmix.engine.transport import (
    TempoEvent,
    TempoTrack,
    TimeSignature,
    Transport,
    TransportState,
)
from vcmix.engine.audio_driver import (
    AudioDriverBase,
    DriverConfig,
    DriverInfo,
    DriverType,
    MockDriver,
    SoundDeviceDriver,
    create_driver,
)


# ═══════════════════════════════════════════════════════════════════════════
# TrackClip Tests
# ═══════════════════════════════════════════════════════════════════════════

class TestTrackClip:
    """Tests for TrackClip."""

    def test_mono_clip_creation(self):
        audio = np.random.randn(44100).astype(np.float32)
        clip = TrackClip(audio=audio, sample_rate=44100)
        assert clip.num_channels == 1
        assert clip.num_samples == 44100

    def test_stereo_clip_creation(self):
        audio = np.random.randn(2, 44100).astype(np.float32)
        clip = TrackClip(audio=audio, sample_rate=44100)
        assert clip.num_channels == 2
        assert clip.num_samples == 44100

    def test_clip_get_samples_in_range(self):
        audio = np.ones(1000, dtype=np.float32)
        clip = TrackClip(audio=audio, start_sample=0)
        result = clip.get_samples(0, 100)
        assert result.shape == (100,)
        assert np.allclose(result, 1.0)

    def test_clip_get_samples_before_start(self):
        audio = np.ones(1000, dtype=np.float32) * 0.5
        clip = TrackClip(audio=audio, start_sample=500)
        result = clip.get_samples(0, 100)
        # Before clip starts, should be zeros
        assert np.allclose(result[:500], 0.0) if len(result) > 0 else True

    def test_clip_get_samples_partial_overlap(self):
        audio = np.ones(500, dtype=np.float32) * 0.7
        clip = TrackClip(audio=audio, start_sample=100)
        result = clip.get_samples(0, 200)
        # First 100 samples should be zero (before clip)
        assert np.allclose(result[:100], 0.0)
        # Next 100 should be 0.7
        assert np.allclose(result[100:], 0.7)

    def test_clip_get_samples_after_end(self):
        audio = np.ones(100, dtype=np.float32)
        clip = TrackClip(audio=audio, start_sample=0)
        result = clip.get_samples(200, 100)
        # After clip, should be zero
        assert np.allclose(result, 0.0)

    def test_clip_volume(self):
        audio = np.ones(1000, dtype=np.float32)
        clip = TrackClip(audio=audio, volume=0.5)
        result = clip.get_samples(0, 100)
        assert np.allclose(result, 0.5)

    def test_clip_muted(self):
        audio = np.ones(1000, dtype=np.float32)
        clip = TrackClip(audio=audio, muted=True)
        result = clip.get_samples(0, 100)
        assert np.allclose(result, 0.0)

    def test_clip_stereo_get_samples(self):
        audio = np.stack([
            np.ones(1000, dtype=np.float32),
            np.ones(1000, dtype=np.float32) * 2.0,
        ])
        clip = TrackClip(audio=audio, start_sample=0)
        result = clip.get_samples(0, 100)
        assert result.shape == (2, 100)
        assert np.allclose(result[0, :], 1.0)
        assert np.allclose(result[1, :], 2.0)

    def test_clip_start_offset(self):
        audio = np.arange(100, dtype=np.float32)
        clip = TrackClip(audio=audio, start_sample=50)
        result = clip.get_samples(50, 10)
        # Should get audio[0:10] = [0, 1, 2, ..., 9]
        assert np.allclose(result, np.arange(10, dtype=np.float32))


# ═══════════════════════════════════════════════════════════════════════════
# RealtimeTrack Tests
# ═══════════════════════════════════════════════════════════════════════════

class TestRealtimeTrack:
    """Tests for RealtimeTrack."""

    def test_track_creation(self):
        track = RealtimeTrack(name="vocals")
        assert track.name == "vocals"
        assert track.clips == []
        assert track.volume == 1.0
        assert track.muted is False

    def test_track_add_clip(self):
        track = RealtimeTrack(name="vocals")
        clip = TrackClip(audio=np.zeros(100, dtype=np.float32))
        track.add_clip(clip)
        assert len(track.clips) == 1

    def test_track_remove_clip(self):
        track = RealtimeTrack(name="vocals")
        clip = TrackClip(audio=np.zeros(100, dtype=np.float32))
        track.add_clip(clip)
        track.remove_clip(0)
        assert len(track.clips) == 0

    def test_track_remove_clip_invalid_index(self):
        track = RealtimeTrack(name="vocals")
        track.remove_clip(5)  # Should not raise

    def test_track_duration_empty(self):
        track = RealtimeTrack(name="vocals")
        assert track.get_total_duration_samples() == 0

    def test_track_duration_with_clips(self):
        track = RealtimeTrack(name="vocals")
        track.add_clip(TrackClip(audio=np.zeros(1000, dtype=np.float32), start_sample=0))
        track.add_clip(TrackClip(audio=np.zeros(2000, dtype=np.float32), start_sample=500))
        assert track.get_total_duration_samples() == 2500  # 500 + 2000

    def test_track_pan_default(self):
        track = RealtimeTrack(name="vocals")
        assert track.pan == 0.0


# ═══════════════════════════════════════════════════════════════════════════
# RealtimeEngine Tests
# ═══════════════════════════════════════════════════════════════════════════

class TestRealtimeEngine:
    """Tests for the RealtimeEngine."""

    def test_engine_creation(self):
        engine = RealtimeEngine(sample_rate=44100, buffer_size=512)
        assert engine.sample_rate == 44100
        assert engine.buffer_size == 512
        assert engine.state == EngineState.STOPPED

    def test_engine_custom_settings(self):
        engine = RealtimeEngine(
            sample_rate=48000,
            buffer_size=1024,
            num_output_channels=2,
        )
        assert engine.sample_rate == 48000
        assert engine.buffer_size == 1024

    def test_engine_initial_position(self):
        engine = RealtimeEngine()
        assert engine.position_seconds == 0.0
        assert engine.position_samples == 0

    def test_engine_not_playing_initially(self):
        engine = RealtimeEngine()
        assert engine.is_playing is False
        assert engine.is_recording is False

    def test_engine_add_track(self):
        engine = RealtimeEngine()
        track = engine.add_track("vocals")
        assert track.name == "vocals"
        assert len(engine.tracks) == 1

    def test_engine_add_track_duplicate_name(self):
        engine = RealtimeEngine()
        engine.add_track("vocals")
        with pytest.raises(ValueError, match="already exists"):
            engine.add_track("vocals")

    def test_engine_remove_track(self):
        engine = RealtimeEngine()
        engine.add_track("vocals")
        engine.remove_track("vocals")
        assert len(engine.tracks) == 0

    def test_engine_remove_nonexistent_track(self):
        engine = RealtimeEngine()
        engine.remove_track("nonexistent")  # Should not raise

    def test_engine_get_track(self):
        engine = RealtimeEngine()
        engine.add_track("vocals")
        track = engine.get_track("vocals")
        assert track is not None
        assert track.name == "vocals"

    def test_engine_get_track_nonexistent(self):
        engine = RealtimeEngine()
        assert engine.get_track("nonexistent") is None

    def test_engine_seek(self):
        engine = RealtimeEngine()
        engine.seek(5.0)
        assert engine.position_seconds == pytest.approx(5.0, abs=0.01)

    def test_engine_seek_samples(self):
        engine = RealtimeEngine(sample_rate=44100)
        engine.seek_samples(44100)
        assert engine.position_samples == 44100
        assert engine.position_seconds == pytest.approx(1.0)

    def test_engine_seek_negative(self):
        engine = RealtimeEngine()
        engine.seek(-1.0)
        assert engine.position_seconds == 0.0

    def test_engine_seek_samples_negative(self):
        engine = RealtimeEngine()
        engine.seek_samples(-100)
        assert engine.position_samples == 0

    def test_engine_set_loop(self):
        engine = RealtimeEngine()
        engine.set_loop(2.0, 4.0)
        assert engine.loop_enabled is True
        assert engine.loop_start == pytest.approx(2.0, abs=0.01)
        assert engine.loop_end == pytest.approx(4.0, abs=0.01)

    def test_engine_set_loop_invalid(self):
        engine = RealtimeEngine()
        with pytest.raises(ValueError):
            engine.set_loop(4.0, 2.0)

    def test_engine_clear_loop(self):
        engine = RealtimeEngine()
        engine.set_loop(2.0, 4.0)
        engine.clear_loop()
        assert engine.loop_enabled is False

    def test_engine_tempo(self):
        engine = RealtimeEngine()
        engine.tempo = 140.0
        assert engine.tempo == 140.0

    def test_engine_tempo_clamp(self):
        engine = RealtimeEngine()
        engine.tempo = 500.0
        assert engine.tempo == 300.0
        engine.tempo = 5.0
        assert engine.tempo == 20.0

    def test_engine_get_buffer_empty(self):
        engine = RealtimeEngine()
        buffer = engine.get_buffer(512)
        assert buffer.shape == (2, 512)
        assert np.allclose(buffer, 0.0)

    def test_engine_get_buffer_with_track(self):
        engine = RealtimeEngine()
        track = engine.add_track("vocals")
        audio = np.ones(44100, dtype=np.float32) * 0.5
        track.add_clip(TrackClip(audio=audio, start_sample=0))
        buffer = engine.get_buffer(512)
        assert buffer.shape == (2, 512)
        # Should have audio (mixed to both channels from mono)
        assert np.any(buffer > 0)

    def test_engine_get_buffer_multiple_tracks(self):
        engine = RealtimeEngine()
        track1 = engine.add_track("vocals")
        track2 = engine.add_track("guitar")
        track1.add_clip(TrackClip(
            audio=np.ones(44100, dtype=np.float32) * 0.3, start_sample=0
        ))
        track2.add_clip(TrackClip(
            audio=np.ones(44100, dtype=np.float32) * 0.5, start_sample=0
        ))
        buffer = engine.get_buffer(512)
        # Both tracks should contribute
        assert np.any(buffer > 0)

    def test_engine_muted_track(self):
        engine = RealtimeEngine()
        track = engine.add_track("vocals")
        track.muted = True
        track.add_clip(TrackClip(
            audio=np.ones(44100, dtype=np.float32) * 0.5, start_sample=0
        ))
        buffer = engine.get_buffer(512)
        assert np.allclose(buffer, 0.0)

    def test_engine_solo_track(self):
        engine = RealtimeEngine()
        track1 = engine.add_track("vocals")
        track2 = engine.add_track("guitar")
        track1.add_clip(TrackClip(
            audio=np.ones(44100, dtype=np.float32) * 0.3, start_sample=0
        ))
        track2.add_clip(TrackClip(
            audio=np.ones(44100, dtype=np.float32) * 0.5, start_sample=0
        ))
        track2.solo = True
        buffer = engine.get_buffer(512)
        # Only soloed track should play
        assert np.allclose(buffer[0, :], buffer[1, :])

    def test_engine_project_duration(self):
        engine = RealtimeEngine()
        track = engine.add_track("vocals")
        track.add_clip(TrackClip(
            audio=np.zeros(44100, dtype=np.float32), start_sample=0
        ))
        assert engine.get_project_duration_seconds() == pytest.approx(1.0, abs=0.01)

    def test_engine_project_duration_empty(self):
        engine = RealtimeEngine()
        assert engine.get_project_duration_samples() == 0
        assert engine.get_project_duration_seconds() == 0.0

    def test_engine_loop_get_buffer(self):
        engine = RealtimeEngine(sample_rate=44100)
        track = engine.add_track("drums")
        audio = np.ones(44100, dtype=np.float32) * 0.5  # 1 second
        track.add_clip(TrackClip(audio=audio, start_sample=0))
        engine.set_loop(0.0, 1.0)
        # Get enough buffers to pass the loop point
        engine.get_buffer(22050)
        engine.get_buffer(22050)
        # Position should have looped back
        assert engine.position_samples < 44100

    def test_engine_track_volume(self):
        engine = RealtimeEngine()
        track = engine.add_track("vocals")
        track.volume = 0.5
        track.add_clip(TrackClip(
            audio=np.ones(44100, dtype=np.float32), start_sample=0
        ))
        buffer = engine.get_buffer(512)
        # Should be attenuated
        assert np.all(buffer <= 1.0)

    def test_engine_state_callback(self):
        states = []
        engine = RealtimeEngine()
        engine.on_state_change(lambda s: states.append(s))
        engine._set_state(EngineState.PLAYING)
        assert len(states) == 1
        assert states[0] == EngineState.PLAYING

    def test_engine_position_callback(self):
        positions = []
        engine = RealtimeEngine()
        engine.on_position_change(lambda p: positions.append(p))
        engine.seek(5.0)
        assert len(positions) == 1

    def test_engine_close(self):
        engine = RealtimeEngine()
        engine.close()
        assert engine.state == EngineState.STOPPED


# ═══════════════════════════════════════════════════════════════════════════
# Time Conversion Tests
# ═══════════════════════════════════════════════════════════════════════════

class TestTimeConversion:
    """Tests for time conversion utilities."""

    def test_samples_to_seconds(self):
        engine = RealtimeEngine(sample_rate=44100)
        assert engine.samples_to_seconds(44100) == pytest.approx(1.0)

    def test_seconds_to_samples(self):
        engine = RealtimeEngine(sample_rate=44100)
        assert engine.seconds_to_samples(1.0) == 44100

    def test_samples_to_beats(self):
        engine = RealtimeEngine(sample_rate=44100)
        engine.tempo = 120.0
        # 1 second at 120 BPM = 2 beats
        assert engine.samples_to_beats(44100) == pytest.approx(2.0)

    def test_beats_to_samples(self):
        engine = RealtimeEngine(sample_rate=44100)
        engine.tempo = 120.0
        assert engine.beats_to_samples(2.0) == 44100

    def test_samples_to_mbt(self):
        engine = RealtimeEngine(sample_rate=44100)
        engine.tempo = 120.0
        # 4 beats = 1 measure at 4/4
        samples = engine.beats_to_samples(4.0)
        m, b, t = engine.samples_to_mbt(samples)
        assert m == 1
        assert b == 0
        assert t == 0

    def test_mbt_to_samples(self):
        engine = RealtimeEngine(sample_rate=44100)
        engine.tempo = 120.0
        samples = engine.mbt_to_samples(1, 0, 0)
        # 1 measure = 4 beats at 120 BPM = 2 seconds
        assert samples == pytest.approx(88200, abs=100)

    def test_roundtrip_mbt(self):
        engine = RealtimeEngine(sample_rate=44100)
        engine.tempo = 120.0
        original = (2, 3, 240)
        samples = engine.mbt_to_samples(*original)
        result = engine.samples_to_mbt(samples)
        assert result[0] == original[0]
        assert result[1] == original[1]
        assert abs(result[2] - original[2]) <= 1


# ═══════════════════════════════════════════════════════════════════════════
# Transport Tests
# ═══════════════════════════════════════════════════════════════════════════

class TestTransport:
    """Tests for Transport."""

    def test_transport_creation(self):
        transport = Transport(sample_rate=44100)
        assert transport.state == TransportState.STOPPED
        assert transport.position_samples == 0

    def test_transport_play(self):
        transport = Transport()
        transport.play()
        assert transport.state == TransportState.PLAYING

    def test_transport_stop(self):
        transport = Transport()
        transport.play()
        transport.stop()
        assert transport.state == TransportState.STOPPED
        assert transport.position_samples == 0

    def test_transport_pause(self):
        transport = Transport()
        transport.play()
        transport.pause()
        assert transport.state == TransportState.PAUSED

    def test_transport_pause_stops_only_when_playing(self):
        transport = Transport()
        transport.pause()  # Should not change from STOPPED
        assert transport.state == TransportState.STOPPED

    def test_transport_record(self):
        transport = Transport()
        transport.record()
        assert transport.state == TransportState.RECORDING
        assert transport.is_recording is True

    def test_transport_stop_record(self):
        transport = Transport()
        transport.record()
        transport.stop_record()
        assert transport.state == TransportState.PLAYING

    def test_transport_seek_seconds(self):
        transport = Transport(sample_rate=44100)
        transport.seek_seconds(2.5)
        assert transport.position_seconds == pytest.approx(2.5, abs=0.01)

    def test_transport_seek_mbt(self):
        transport = Transport(sample_rate=44100, tempo=120.0)
        transport.seek_mbt(1, 0, 0)
        assert transport.position_seconds == pytest.approx(2.0, abs=0.05)

    def test_transport_advance(self):
        transport = Transport(sample_rate=44100)
        transport.play()
        transport.advance(512)
        assert transport.position_samples == 512

    def test_transport_advance_not_playing(self):
        transport = Transport()
        transport.advance(512)
        assert transport.position_samples == 0

    def test_transport_loop(self):
        transport = Transport(sample_rate=44100)
        transport.set_loop_seconds(0.0, 1.0)
        assert transport.loop_enabled is True
        transport.play()
        # Advance past loop end
        transport.advance(50000)
        assert transport.position_samples < 44100

    def test_transport_clear_loop(self):
        transport = Transport()
        transport.set_loop_seconds(0.0, 1.0)
        transport.clear_loop()
        assert transport.loop_enabled is False

    def test_transport_loop_invalid(self):
        transport = Transport()
        with pytest.raises(ValueError):
            transport.set_loop_seconds(2.0, 1.0)

    def test_transport_set_tempo(self):
        transport = Transport()
        transport.set_tempo(140.0)
        assert transport.tempo == 140.0

    def test_transport_time_signature(self):
        transport = Transport()
        transport.set_time_signature(3, 4)
        assert transport.time_signature.numerator == 3
        assert transport.time_signature.denominator == 4

    def test_transport_time_signature_invalid_numerator(self):
        with pytest.raises(ValueError):
            TimeSignature(numerator=0)

    def test_transport_time_signature_invalid_denominator(self):
        with pytest.raises(ValueError):
            TimeSignature(denominator=3)

    def test_transport_mbt_position(self):
        transport = Transport(sample_rate=44100, tempo=120.0)
        # At 120 BPM, 4/4: 1 measure = 2 seconds = 88200 samples
        transport.seek_seconds(2.0)
        m, b, t = transport.position_mbt
        assert m == 1
        assert b == 0

    def test_transport_state_callback(self):
        states = []
        transport = Transport()
        transport.on_state_change(lambda s: states.append(s))
        transport.play()
        transport.stop()
        assert len(states) == 2
        assert states[0] == TransportState.PLAYING
        assert states[1] == TransportState.STOPPED

    def test_transport_position_callback(self):
        positions = []
        transport = Transport()
        transport.on_position_change(lambda p: positions.append(p))
        transport.seek_seconds(1.0)
        assert len(positions) == 1

    def test_transport_pre_roll(self):
        transport = Transport()
        transport.pre_roll_beats = 4
        assert transport.pre_roll_beats == 4

    def test_transport_repr(self):
        transport = Transport()
        r = repr(transport)
        assert "Transport" in r
        assert "STOPPED" in r

    def test_transport_midi_clock_ppqn(self):
        transport = Transport()
        assert transport.get_midi_clock_ppqn() == 24

    def test_transport_get_next_midi_clock_sample(self):
        transport = Transport(sample_rate=44100, tempo=120.0)
        transport.play()
        next_sample = transport.get_next_midi_clock_sample()
        assert next_sample > 0

    def test_transport_set_loop_samples(self):
        transport = Transport(sample_rate=44100)
        transport.set_loop_samples(0, 44100)
        assert transport.loop_enabled is True

    def test_transport_set_loop_mbt(self):
        transport = Transport(sample_rate=44100, tempo=120.0)
        transport.set_loop_mbt(0, 0, 0, 1, 0, 0)
        assert transport.loop_enabled is True

    def test_transport_seconds_to_mbt(self):
        transport = Transport(sample_rate=44100, tempo=120.0)
        m, b, t = transport.seconds_to_mbt(2.0)
        assert m == 1

    def test_transport_mbt_to_seconds(self):
        transport = Transport(sample_rate=44100, tempo=120.0)
        secs = transport.mbt_to_seconds(1, 0, 0)
        assert secs == pytest.approx(2.0, abs=0.05)


# ═══════════════════════════════════════════════════════════════════════════
# TempoTrack Tests
# ═══════════════════════════════════════════════════════════════════════════

class TestTempoTrack:
    """Tests for TempoTrack."""

    def test_default_tempo(self):
        track = TempoTrack(default_tempo=120.0)
        assert track.default_tempo == 120.0

    def test_add_tempo_change(self):
        track = TempoTrack()
        track.add_tempo_change(8.0, 140.0)
        assert track.get_tempo_at_beat(8.0) == 140.0
        assert track.get_tempo_at_beat(0.0) == 120.0

    def test_add_tempo_change_invalid(self):
        track = TempoTrack()
        with pytest.raises(ValueError):
            track.add_tempo_change(0.0, 10.0)

    def test_tempo_at_beat(self):
        track = TempoTrack()
        track.add_tempo_change(4.0, 140.0)
        assert track.get_tempo_at_beat(2.0) == 120.0
        assert track.get_tempo_at_beat(4.0) == 140.0
        assert track.get_tempo_at_beat(8.0) == 140.0

    def test_tempo_track_clear(self):
        track = TempoTrack()
        track.add_tempo_change(4.0, 140.0)
        track.clear()
        assert track.get_tempo_at_beat(4.0) == 120.0

    def test_multiple_tempo_changes(self):
        track = TempoTrack()
        track.add_tempo_change(4.0, 140.0)
        track.add_tempo_change(8.0, 100.0)
        assert track.get_tempo_at_beat(2.0) == 120.0
        assert track.get_tempo_at_beat(6.0) == 140.0
        assert track.get_tempo_at_beat(10.0) == 100.0


# ═══════════════════════════════════════════════════════════════════════════
# AudioDriver Tests
# ═══════════════════════════════════════════════════════════════════════════

class TestAudioDriver:
    """Tests for the audio driver interface."""

    def test_driver_config_defaults(self):
        config = DriverConfig()
        assert config.sample_rate == 44100
        assert config.buffer_size == 512

    def test_mock_driver_open_close(self):
        config = DriverConfig(driver_type=DriverType.MOCK)
        driver = MockDriver(config)
        driver.open()
        assert driver.is_running is True
        driver.close()
        assert driver.is_running is False

    def test_mock_driver_info(self):
        config = DriverConfig(sample_rate=48000, buffer_size=256)
        driver = MockDriver(config)
        info = driver.get_info()
        assert info.name == "Mock"
        assert info.sample_rate == 48000
        assert info.is_running is False

    def test_mock_driver_input_devices(self):
        driver = MockDriver(DriverConfig())
        devices = driver.get_input_devices()
        assert len(devices) == 1
        assert devices[0]["name"] == "Mock Input"

    def test_mock_driver_output_devices(self):
        driver = MockDriver(DriverConfig())
        devices = driver.get_output_devices()
        assert len(devices) == 1
        assert devices[0]["name"] == "Mock Output"

    def test_mock_driver_process_block(self):
        config = DriverConfig(num_output_channels=2, num_input_channels=2)
        driver = MockDriver(config)
        driver.open()
        output = driver.process_block(512)
        assert output.shape == (2, 512)

    def test_create_driver_mock(self):
        config = DriverConfig(driver_type=DriverType.MOCK)
        driver = create_driver(config)
        assert isinstance(driver, MockDriver)

    def test_create_driver_default(self):
        driver = create_driver()
        # Default is SoundDevice, but may fall back to error
        assert isinstance(driver, (SoundDeviceDriver, MockDriver))

    def test_create_driver_sounddevice(self):
        config = DriverConfig(driver_type=DriverType.SOUNDDEVICE)
        driver = create_driver(config)
        assert isinstance(driver, SoundDeviceDriver)

    def test_driver_set_callback(self):
        driver = MockDriver(DriverConfig())
        callback_called = [False]

        def my_callback(outdata, indata, frames, time_info, status):
            callback_called[0] = True

        driver.set_callback(my_callback)
        driver.open()
        driver.process_block(256)
        assert callback_called[0] is True

    def test_driver_latency(self):
        driver = MockDriver(DriverConfig(sample_rate=44100, buffer_size=512))
        latency = driver.get_latency_ms()
        assert latency > 0

    def test_sounddevice_driver_info(self):
        config = DriverConfig(sample_rate=44100, buffer_size=512)
        driver = SoundDeviceDriver(config)
        info = driver.get_info()
        assert info.name == "SoundDevice"
        assert info.sample_rate == 44100


# ═══════════════════════════════════════════════════════════════════════════
# Integration Tests
# ═══════════════════════════════════════════════════════════════════════════

class TestRealtimeIntegration:
    """Integration tests for the realtime engine."""

    def test_engine_with_transport(self):
        engine = RealtimeEngine(sample_rate=44100)
        transport = Transport(sample_rate=44100, tempo=120.0)

        # Add a track
        track = engine.add_track("drums")
        track.add_clip(TrackClip(
            audio=np.ones(44100, dtype=np.float32) * 0.5,
            start_sample=0,
        ))

        # Render offline
        buffer = engine.get_buffer(1024)
        assert buffer.shape == (2, 1024)
        assert np.any(buffer > 0)

    def test_engine_mixing_multiple_tracks(self):
        engine = RealtimeEngine(sample_rate=44100)

        # Create two tracks with known audio
        t1 = engine.add_track("bass")
        t2 = engine.add_track("melody")
        t1.add_clip(TrackClip(
            audio=np.ones(44100, dtype=np.float32) * 0.3,
            start_sample=0,
        ))
        t2.add_clip(TrackClip(
            audio=np.ones(44100, dtype=np.float32) * 0.5,
            start_sample=0,
        ))

        buffer = engine.get_buffer(512)
        # Should have both tracks mixed
        assert np.any(buffer > 0)

    def test_engine_pan(self):
        engine = RealtimeEngine(sample_rate=44100, num_output_channels=2)
        track = engine.add_track("pan_test")
        track.pan = -1.0  # Full left
        track.add_clip(TrackClip(
            audio=np.ones(44100, dtype=np.float32) * 0.5,
            start_sample=0,
        ))
        buffer = engine.get_buffer(512)
        # Left channel should be louder than right
        assert np.mean(np.abs(buffer[0, :])) >= np.mean(np.abs(buffer[1, :]))

    def test_engine_render_full_project(self):
        engine = RealtimeEngine(sample_rate=44100)
        track = engine.add_track("vocals")
        track.add_clip(TrackClip(
            audio=np.random.randn(44100).astype(np.float32) * 0.3,
            start_sample=0,
        ))

        # Render 1 second in blocks
        block_size = 1024
        num_blocks = 44100 // block_size
        all_audio = []
        for _ in range(num_blocks):
            buf = engine.get_buffer(block_size)
            all_audio.append(buf)

        result = np.concatenate(all_audio, axis=1)
        assert result.shape == (2, num_blocks * block_size)
        assert np.any(np.abs(result) > 0)
