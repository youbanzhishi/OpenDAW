"""
realtime_engine.py — Real-time audio engine for OpenDAW.

Provides low-latency audio playback, recording, and multi-track mixing
using sounddevice as the default audio backend.

Features:
- Multi-track playback with mixing
- Real-time recording to buffer
- Transport control (play/stop/pause/seek/loop)
- Tempo-synced position tracking
- Thread-safe audio callback
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Callable, Optional

import numpy as np


class EngineState(Enum):
    """Realtime engine state."""
    STOPPED = auto()
    PLAYING = auto()
    PAUSED = auto()
    RECORDING = auto()


@dataclass
class TrackClip:
    """A clip on a track with audio data and position info."""
    audio: np.ndarray          # (channels, samples) or (samples,) for mono
    sample_rate: int = 44100
    start_sample: int = 0      # position on timeline in samples
    name: str = ""
    volume: float = 1.0
    muted: bool = False
    solo: bool = False

    @property
    def num_channels(self) -> int:
        if self.audio.ndim == 1:
            return 1
        return self.audio.shape[0]

    @property
    def num_samples(self) -> int:
        if self.audio.ndim == 1:
            return len(self.audio)
        return self.audio.shape[1]

    def get_samples(self, start: int, length: int) -> np.ndarray:
        """Get a slice of audio data, zero-padded if out of range."""
        end = start + length
        clip_start = start - self.start_sample
        clip_end = end - self.start_sample

        if clip_end <= 0 or clip_start >= self.num_samples:
            if self.audio.ndim == 1:
                return np.zeros(length, dtype=np.float32)
            return np.zeros((self.audio.shape[0], length), dtype=np.float32)

        out_start = max(0, clip_start)
        out_end = min(self.num_samples, clip_end)

        if self.audio.ndim == 1:
            result = np.zeros(length, dtype=np.float32)
            dst_start = max(0, -clip_start)
            dst_end = dst_start + (out_end - out_start)
            result[dst_start:dst_end] = self.audio[out_start:out_end]
        else:
            result = np.zeros((self.audio.shape[0], length), dtype=np.float32)
            dst_start = max(0, -clip_start)
            dst_end = dst_start + (out_end - out_start)
            result[:, dst_start:dst_end] = self.audio[:, out_start:out_end]

        return result * self.volume if not self.muted else result * 0.0


@dataclass
class RealtimeTrack:
    """A track in the realtime engine."""
    name: str
    clips: list[TrackClip] = field(default_factory=list)
    volume: float = 1.0
    muted: bool = False
    solo: bool = False
    pan: float = 0.0        # -1.0 (left) to 1.0 (right)
    input_channel: int = -1  # -1 = no input, >=0 = input channel for recording

    def add_clip(self, clip: TrackClip) -> None:
        """Add a clip to this track."""
        self.clips.append(clip)

    def remove_clip(self, index: int) -> None:
        """Remove a clip by index."""
        if 0 <= index < len(self.clips):
            self.clips.pop(index)

    def get_total_duration_samples(self) -> int:
        """Get total duration in samples across all clips."""
        if not self.clips:
            return 0
        return max(c.start_sample + c.num_samples for c in self.clips)


class RealtimeEngine:
    """
    Real-time audio engine for OpenDAW.

    Supports:
    - Multi-track playback with mixing
    - Real-time recording
    - Transport control (play/stop/pause/seek/loop)
    - Low-latency audio I/O via sounddevice

    Usage:
        engine = RealtimeEngine(sample_rate=44100, buffer_size=512)
        track = engine.add_track("vocals")
        track.add_clip(TrackClip(audio=some_audio, start_sample=0))
        engine.play()
        ...
        engine.stop()
    """

    def __init__(
        self,
        sample_rate: int = 44100,
        buffer_size: int = 512,
        num_output_channels: int = 2,
        num_input_channels: int = 2,
    ) -> None:
        self.sample_rate = sample_rate
        self.buffer_size = buffer_size
        self.num_output_channels = num_output_channels
        self.num_input_channels = num_input_channels

        self._tracks: list[RealtimeTrack] = []
        self._track_map: dict[str, RealtimeTrack] = {}
        self._state = EngineState.STOPPED
        self._position_samples = 0
        self._loop_enabled = False
        self._loop_start_samples = 0
        self._loop_end_samples = 0

        # Recording buffer
        self._recording_buffer: list[np.ndarray] = []
        self._recording_channels: int = num_input_channels

        # Callback lock for thread safety
        self._lock = threading.RLock()

        # Audio stream reference
        self._stream = None

        # Callback hooks
        self._on_position_change: Optional[Callable[[float], None]] = None
        self._on_state_change: Optional[Callable[[EngineState], None]] = None

        # Tempo for time conversions
        self._tempo = 120.0
        self._time_signature_num = 4
        self._time_signature_den = 4

    @property
    def state(self) -> EngineState:
        """Current engine state."""
        return self._state

    @property
    def position_seconds(self) -> float:
        """Current playback position in seconds."""
        return self._position_samples / self.sample_rate

    @property
    def position_samples(self) -> int:
        """Current playback position in samples."""
        return self._position_samples

    @property
    def is_playing(self) -> bool:
        return self._state in (EngineState.PLAYING, EngineState.RECORDING)

    @property
    def is_recording(self) -> bool:
        return self._state == EngineState.RECORDING

    @property
    def loop_enabled(self) -> bool:
        return self._loop_enabled

    @property
    def loop_start(self) -> float:
        """Loop start in seconds."""
        return self._loop_start_samples / self.sample_rate

    @property
    def loop_end(self) -> float:
        """Loop end in seconds."""
        return self._loop_end_samples / self.sample_rate

    @property
    def tracks(self) -> list[RealtimeTrack]:
        return list(self._tracks)

    @property
    def tempo(self) -> float:
        return self._tempo

    @tempo.setter
    def tempo(self, value: float) -> None:
        self._tempo = max(20.0, min(300.0, value))

    # ── Transport Control ──────────────────────────────────────────────────

    def play(self) -> None:
        """Start or resume playback."""
        with self._lock:
            if self._state == EngineState.STOPPED or self._state == EngineState.PAUSED:
                self._set_state(EngineState.PLAYING)
                self._start_stream()

    def stop(self) -> None:
        """Stop playback and reset position."""
        with self._lock:
            self._set_state(EngineState.STOPPED)
            self._position_samples = 0
            self._stop_stream()
            self._clear_recording()

    def pause(self) -> None:
        """Pause playback (position is maintained)."""
        with self._lock:
            if self._state == EngineState.PLAYING:
                self._set_state(EngineState.PAUSED)
                self._stop_stream()

    def seek(self, position_seconds: float) -> None:
        """Seek to a position in seconds."""
        with self._lock:
            self._position_samples = max(
                0, int(position_seconds * self.sample_rate)
            )
            if self._on_position_change:
                self._on_position_change(position_seconds)

    def seek_samples(self, position_samples: int) -> None:
        """Seek to a position in samples."""
        with self._lock:
            self._position_samples = max(0, position_samples)
            if self._on_position_change:
                self._on_position_change(self.position_seconds)

    def set_loop(self, start_seconds: float, end_seconds: float) -> None:
        """Set loop region in seconds."""
        if start_seconds < 0 or end_seconds <= start_seconds:
            raise ValueError("Loop end must be greater than loop start")
        self._loop_start_samples = int(start_seconds * self.sample_rate)
        self._loop_end_samples = int(end_seconds * self.sample_rate)
        self._loop_enabled = True

    def clear_loop(self) -> None:
        """Disable looping."""
        self._loop_enabled = False
        self._loop_start_samples = 0
        self._loop_end_samples = 0

    # ── Track Management ───────────────────────────────────────────────────

    def add_track(self, name: str) -> RealtimeTrack:
        """Add a new track and return it."""
        if name in self._track_map:
            raise ValueError(f"Track '{name}' already exists")
        track = RealtimeTrack(name=name)
        self._tracks.append(track)
        self._track_map[name] = track
        return track

    def remove_track(self, name: str) -> None:
        """Remove a track by name."""
        if name in self._track_map:
            track = self._track_map.pop(name)
            self._tracks.remove(track)

    def get_track(self, name: str) -> Optional[RealtimeTrack]:
        """Get a track by name."""
        return self._track_map.get(name)

    # ── Recording ──────────────────────────────────────────────────────────

    def start_recording(self) -> None:
        """Start recording from input."""
        with self._lock:
            self._clear_recording()
            self._set_state(EngineState.RECORDING)
            self._start_stream()

    def stop_recording(self) -> np.ndarray:
        """Stop recording and return recorded audio."""
        with self._lock:
            self._stop_stream()
            self._set_state(EngineState.STOPPED)
            return self._get_recording()

    def _clear_recording(self) -> None:
        """Clear the recording buffer."""
        self._recording_buffer = []

    def _get_recording(self) -> np.ndarray:
        """Concatenate and return the recording buffer."""
        if not self._recording_buffer:
            return np.zeros((self._recording_channels, 0), dtype=np.float32)
        return np.concatenate(self._recording_buffer, axis=1)

    # ── Audio Callback ─────────────────────────────────────────────────────

    def _audio_callback(
        self,
        outdata: np.ndarray,
        indata: np.ndarray,
        frames: int,
        time_info,
        status,
    ) -> None:
        """
        PortAudio-style callback for sounddevice.

        Args:
            outdata: Output buffer to fill (channels, frames).
            indata: Input buffer from audio device (channels, frames).
            frames: Number of frames requested.
            time_info: Timing info from PortAudio.
            status: Status flags.
        """
        with self._lock:
            if not self.is_playing:
                outdata[:] = 0
                return

            # Mix all tracks
            mixed = self._mix_tracks(frames)

            # Handle output channels
            if mixed.ndim == 1:
                outdata[:] = np.broadcast_to(
                    mixed[:, np.newaxis], (frames, self.num_output_channels)
                )
            else:
                if mixed.shape[0] < self.num_output_channels:
                    padded = np.zeros(
                        (self.num_output_channels, frames), dtype=np.float32
                    )
                    padded[:mixed.shape[0], :] = mixed
                    outdata[:] = padded.T
                else:
                    outdata[:] = mixed[:self.num_output_channels, :].T

            # Record input if recording
            if self._state == EngineState.RECORDING and indata is not None:
                ch = min(indata.shape[1], self._recording_channels)
                self._recording_buffer.append(
                    indata[:, :ch].T.copy()
                )

            # Advance position
            self._position_samples += frames

            # Handle loop
            if self._loop_enabled and self._position_samples >= self._loop_end_samples:
                self._position_samples = self._loop_start_samples

            # Position change callback
            if self._on_position_change:
                self._on_position_change(self.position_seconds)

    def _mix_tracks(self, num_samples: int) -> np.ndarray:
        """Mix all tracks for the current position."""
        has_solo = any(t.solo for t in self._tracks)

        mixed = np.zeros((self.num_output_channels, num_samples), dtype=np.float32)

        for track in self._tracks:
            if has_solo and not track.solo:
                continue
            if track.muted:
                continue

            track_audio = self._render_track(track, num_samples)
            if track_audio is None:
                continue

            # Apply track volume
            track_audio = track_audio * track.volume

            # Apply panning
            if self.num_output_channels == 2:
                if track_audio.ndim == 1:
                    left = track_audio * min(1.0, 1.0 - track.pan)
                    right = track_audio * min(1.0, 1.0 + track.pan)
                    track_audio = np.stack([left, right], axis=0)

                if track_audio.ndim == 2 and track_audio.shape[0] == 2:
                    track_audio = track_audio.copy()
                    track_audio[0, :] *= min(1.0, 1.0 - track.pan)
                    track_audio[1, :] *= min(1.0, 1.0 + track.pan)

            # Add to mix
            if track_audio.ndim == 1:
                mixed[0, :] += track_audio
                if self.num_output_channels > 1:
                    mixed[1, :] += track_audio
            else:
                ch = min(track_audio.shape[0], self.num_output_channels)
                mixed[:ch, :] += track_audio[:ch, :]

        # Clip to prevent distortion
        np.clip(mixed, -1.0, 1.0, out=mixed)
        return mixed

    def _render_track(
        self, track: RealtimeTrack, num_samples: int
    ) -> Optional[np.ndarray]:
        """Render a single track for the current position."""
        result = np.zeros(num_samples, dtype=np.float32)

        for clip in track.clips:
            if clip.muted:
                continue
            clip_audio = clip.get_samples(self._position_samples, num_samples)
            if clip_audio.ndim == 1:
                result += clip_audio
            else:
                result += clip_audio.mean(axis=0)

        return result

    def get_buffer(self, num_samples: int) -> np.ndarray:
        """
        Get the next block of mixed audio without starting real playback.

        Useful for offline rendering or testing.

        Args:
            num_samples: Number of samples to render.

        Returns:
            Mixed audio buffer (channels, samples).
        """
        with self._lock:
            mixed = self._mix_tracks(num_samples)
            self._position_samples += num_samples

            if self._loop_enabled and self._position_samples >= self._loop_end_samples:
                self._position_samples = self._loop_start_samples

            return mixed

    # ── Stream Management ──────────────────────────────────────────────────

    def _start_stream(self) -> None:
        """Start the sounddevice stream."""
        try:
            import sounddevice as sd

            self._stream = sd.Stream(
                samplerate=self.sample_rate,
                blocksize=self.buffer_size,
                channels=(self.num_input_channels, self.num_output_channels),
                dtype='float32',
                callback=self._audio_callback,
            )
            self._stream.start()
        except Exception:
            pass

    def _stop_stream(self) -> None:
        """Stop the sounddevice stream."""
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
            self._stream = None

    # ── Time Conversion Utilities ──────────────────────────────────────────

    def samples_to_seconds(self, samples: int) -> float:
        """Convert sample count to seconds."""
        return samples / self.sample_rate

    def seconds_to_samples(self, seconds: float) -> int:
        """Convert seconds to sample count."""
        return int(seconds * self.sample_rate)

    def samples_to_beats(self, samples: int) -> float:
        """Convert sample count to beats."""
        seconds = samples / self.sample_rate
        return seconds * self._tempo / 60.0

    def beats_to_samples(self, beats: float) -> int:
        """Convert beats to sample count."""
        seconds = beats * 60.0 / self._tempo
        return int(seconds * self.sample_rate)

    def samples_to_mbt(self, samples: int) -> tuple[int, int, int]:
        """
        Convert samples to measures:beats:ticks.

        Returns:
            (measures, beats, ticks) tuple.
        """
        total_beats = self.samples_to_beats(samples)
        measures = int(total_beats // self._time_signature_num)
        remaining_beats = total_beats - measures * self._time_signature_num
        beats = int(remaining_beats)
        ticks = int((remaining_beats - beats) * 480)

        return (measures, beats, ticks)

    def mbt_to_samples(self, measures: int, beats: int, ticks: int) -> int:
        """Convert measures:beats:ticks to sample count."""
        total_beats = (
            measures * self._time_signature_num
            + beats
            + ticks / 480.0
        )
        return self.beats_to_samples(total_beats)

    # ── Callback Hooks ─────────────────────────────────────────────────────

    def on_position_change(
        self, callback: Callable[[float], None]
    ) -> None:
        """Register a callback for position changes."""
        self._on_position_change = callback

    def on_state_change(
        self, callback: Callable[[EngineState], None]
    ) -> None:
        """Register a callback for state changes."""
        self._on_state_change = callback

    def _set_state(self, new_state: EngineState) -> None:
        """Update state and fire callback."""
        old_state = self._state
        self._state = new_state
        if old_state != new_state and self._on_state_change:
            self._on_state_change(new_state)

    # ── Project Duration ───────────────────────────────────────────────────

    def get_project_duration_samples(self) -> int:
        """Get total project duration in samples."""
        max_end = 0
        for track in self._tracks:
            for clip in track.clips:
                end = clip.start_sample + clip.num_samples
                if end > max_end:
                    max_end = end
        return max_end

    def get_project_duration_seconds(self) -> float:
        """Get total project duration in seconds."""
        return self.samples_to_seconds(self.get_project_duration_samples())

    # ── Cleanup ────────────────────────────────────────────────────────────

    def close(self) -> None:
        """Stop playback and release resources."""
        self.stop()
        self._stop_stream()
