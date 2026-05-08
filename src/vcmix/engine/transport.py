"""
transport.py — Transport control for the realtime audio engine.

Provides:
- Play/stop/pause/seek/loop control
- Time position management (samples ↔ seconds ↔ measures:beats:ticks)
- Tempo track support
- Recording state management
- MIDI Clock sync (stub)
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto
from typing import Callable, Optional


class TransportState(Enum):
    """Transport state."""
    STOPPED = auto()
    PLAYING = auto()
    PAUSED = auto()
    RECORDING = auto()


@dataclass
class TimeSignature:
    """Musical time signature."""
    numerator: int = 4
    denominator: int = 4

    def __post_init__(self) -> None:
        if self.numerator < 1:
            raise ValueError("Time signature numerator must be >= 1")
        if self.denominator not in (1, 2, 4, 8, 16):
            raise ValueError("Time signature denominator must be a power of 2")


@dataclass
class TempoEvent:
    """A tempo change event on the tempo track."""
    position_beats: float    # position in beats
    tempo_bpm: float         # tempo in BPM


class TempoTrack:
    """Tempo track supporting tempo changes over time."""

    def __init__(self, default_tempo: float = 120.0) -> None:
        self._events: list[TempoEvent] = [TempoEvent(0.0, default_tempo)]

    @property
    def default_tempo(self) -> float:
        return self._events[0].tempo_bpm

    def add_tempo_change(self, position_beats: float, tempo_bpm: float) -> None:
        """Add a tempo change event."""
        if tempo_bpm < 20.0 or tempo_bpm > 300.0:
            raise ValueError("Tempo must be between 20 and 300 BPM")
        self._events.append(TempoEvent(position_beats, tempo_bpm))
        self._events.sort(key=lambda e: e.position_beats)

    def get_tempo_at_beat(self, beat: float) -> float:
        """Get the tempo at a given beat position."""
        current = self._events[0].tempo_bpm
        for event in self._events:
            if event.position_beats <= beat:
                current = event.tempo_bpm
            else:
                break
        return current

    def get_tempo_at_sample(self, sample: int, sample_rate: int) -> float:
        """Get the tempo at a given sample position."""
        seconds = sample / sample_rate
        beats = seconds * self.default_tempo / 60.0  # approximate
        return self.get_tempo_at_beat(beats)

    def clear(self) -> None:
        """Reset to default tempo only."""
        self._events = [TempoEvent(0.0, self._events[0].tempo_bpm)]


class Transport:
    """
    Transport control for the audio engine.

    Manages playback position, tempo, time signature, and synchronization.

    Usage:
        transport = Transport(sample_rate=44100)
        transport.set_tempo(128)
        transport.play()
        ...
        transport.stop()
    """

    TICKS_PER_BEAT = 480  # Standard MIDI resolution

    def __init__(
        self,
        sample_rate: int = 44100,
        tempo: float = 120.0,
        time_signature: Optional[TimeSignature] = None,
    ) -> None:
        self.sample_rate = sample_rate
        self._state = TransportState.STOPPED
        self._position_samples = 0
        self._loop_enabled = False
        self._loop_start_samples = 0
        self._loop_end_samples = 0
        self._time_signature = time_signature or TimeSignature()
        self._tempo_track = TempoTrack(tempo)

        # Callbacks
        self._on_state_change: Optional[Callable[[TransportState], None]] = None
        self._on_position_change: Optional[Callable[[float], None]] = None

        # Pre-roll for recording (count-in measures)
        self._pre_roll_beats = 0

    @property
    def state(self) -> TransportState:
        return self._state

    @property
    def position_samples(self) -> int:
        return self._position_samples

    @property
    def position_seconds(self) -> float:
        return self._position_samples / self.sample_rate

    @property
    def position_beats(self) -> float:
        return self._samples_to_beats(self._position_samples)

    @property
    def position_mbt(self) -> tuple[int, int, int]:
        return self._samples_to_mbt(self._position_samples)

    @property
    def tempo(self) -> float:
        return self._tempo_track.get_tempo_at_beat(0.0)

    @property
    def time_signature(self) -> TimeSignature:
        return self._time_signature

    @property
    def loop_enabled(self) -> bool:
        return self._loop_enabled

    @property
    def loop_start_seconds(self) -> float:
        return self._loop_start_samples / self.sample_rate

    @property
    def loop_end_seconds(self) -> float:
        return self._loop_end_samples / self.sample_rate

    @property
    def is_playing(self) -> bool:
        return self._state in (TransportState.PLAYING, TransportState.RECORDING)

    @property
    def is_recording(self) -> bool:
        return self._state == TransportState.RECORDING

    @property
    def pre_roll_beats(self) -> int:
        return self._pre_roll_beats

    @pre_roll_beats.setter
    def pre_roll_beats(self, value: int) -> None:
        self._pre_roll_beats = max(0, value)

    # ── Transport Control ──────────────────────────────────────────────────

    def play(self) -> None:
        """Start or resume playback."""
        if self._state in (TransportState.STOPPED, TransportState.PAUSED):
            self._set_state(TransportState.PLAYING)

    def stop(self) -> None:
        """Stop playback and reset position."""
        self._set_state(TransportState.STOPPED)
        self._position_samples = 0

    def pause(self) -> None:
        """Pause playback."""
        if self._state == TransportState.PLAYING:
            self._set_state(TransportState.PAUSED)

    def record(self) -> None:
        """Start recording (with optional pre-roll)."""
        self._set_state(TransportState.RECORDING)

    def stop_record(self) -> None:
        """Stop recording and switch to playing."""
        if self._state == TransportState.RECORDING:
            self._set_state(TransportState.PLAYING)

    def seek_seconds(self, seconds: float) -> None:
        """Seek to position in seconds."""
        self._position_samples = max(0, int(seconds * self.sample_rate))
        if self._on_position_change:
            self._on_position_change(self.position_seconds)

    def seek_samples(self, samples: int) -> None:
        """Seek to position in samples."""
        self._position_samples = max(0, samples)
        if self._on_position_change:
            self._on_position_change(self.position_seconds)

    def seek_mbt(self, measures: int, beats: int, ticks: int) -> None:
        """Seek to measures:beats:ticks position."""
        self._position_samples = self._mbt_to_samples(measures, beats, ticks)
        if self._on_position_change:
            self._on_position_change(self.position_seconds)

    def advance(self, num_samples: int) -> None:
        """Advance the transport position by num_samples."""
        if not self.is_playing:
            return
        self._position_samples += num_samples

        # Handle loop
        if self._loop_enabled and self._position_samples >= self._loop_end_samples:
            self._position_samples = self._loop_start_samples

        if self._on_position_change:
            self._on_position_change(self.position_seconds)

    # ── Loop ───────────────────────────────────────────────────────────────

    def set_loop_seconds(self, start: float, end: float) -> None:
        """Set loop region in seconds."""
        if start < 0 or end <= start:
            raise ValueError("Loop end must be greater than loop start")
        self._loop_start_samples = int(start * self.sample_rate)
        self._loop_end_samples = int(end * self.sample_rate)
        self._loop_enabled = True

    def set_loop_samples(self, start: int, end: int) -> None:
        """Set loop region in samples."""
        if start < 0 or end <= start:
            raise ValueError("Loop end must be greater than loop start")
        self._loop_start_samples = start
        self._loop_end_samples = end
        self._loop_enabled = True

    def set_loop_mbt(self, start_m: int, start_b: int, start_t: int,
                     end_m: int, end_b: int, end_t: int) -> None:
        """Set loop region in MBT format."""
        start_samples = self._mbt_to_samples(start_m, start_b, start_t)
        end_samples = self._mbt_to_samples(end_m, end_b, end_t)
        self.set_loop_samples(start_samples, end_samples)

    def clear_loop(self) -> None:
        """Disable loop."""
        self._loop_enabled = False
        self._loop_start_samples = 0
        self._loop_end_samples = 0

    # ── Tempo ──────────────────────────────────────────────────────────────

    def set_tempo(self, bpm: float) -> None:
        """Set the current tempo."""
        self._tempo_track.clear()
        self._tempo_track.add_tempo_change(0.0, bpm)

    def add_tempo_change(self, position_beats: float, bpm: float) -> None:
        """Add a tempo change at a specific beat position."""
        self._tempo_track.add_tempo_change(position_beats, bpm)

    # ── Time Signature ─────────────────────────────────────────────────────

    def set_time_signature(self, numerator: int, denominator: int) -> None:
        """Set the time signature."""
        self._time_signature = TimeSignature(numerator, denominator)

    # ── Time Conversion ────────────────────────────────────────────────────

    def _samples_to_beats(self, samples: int) -> float:
        """Convert samples to beats using current tempo."""
        seconds = samples / self.sample_rate
        return seconds * self.tempo / 60.0

    def _beats_to_samples(self, beats: float) -> int:
        """Convert beats to samples using current tempo."""
        seconds = beats * 60.0 / self.tempo
        return int(seconds * self.sample_rate)

    def _samples_to_mbt(self, samples: int) -> tuple[int, int, int]:
        """Convert samples to measures:beats:ticks."""
        total_beats = self._samples_to_beats(samples)
        beats_per_measure = self._time_signature.numerator
        measures = int(total_beats // beats_per_measure)
        remaining = total_beats - measures * beats_per_measure
        beats = int(remaining)
        ticks = int((remaining - beats) * self.TICKS_PER_BEAT)
        return (measures, beats, ticks)

    def _mbt_to_samples(self, measures: int, beats: int, ticks: int) -> int:
        """Convert measures:beats:ticks to samples."""
        total_beats = (
            measures * self._time_signature.numerator
            + beats
            + ticks / self.TICKS_PER_BEAT
        )
        return self._beats_to_samples(total_beats)

    def samples_to_seconds(self, samples: int) -> float:
        """Public: convert samples to seconds."""
        return samples / self.sample_rate

    def seconds_to_samples(self, seconds: float) -> int:
        """Public: convert seconds to samples."""
        return int(seconds * self.sample_rate)

    def seconds_to_mbt(self, seconds: float) -> tuple[int, int, int]:
        """Public: convert seconds to MBT."""
        return self._samples_to_mbt(int(seconds * self.sample_rate))

    def mbt_to_seconds(self, measures: int, beats: int, ticks: int) -> float:
        """Public: convert MBT to seconds."""
        return self._mbt_to_samples(measures, beats, ticks) / self.sample_rate

    # ── Callbacks ──────────────────────────────────────────────────────────

    def on_state_change(self, callback: Callable[[TransportState], None]) -> None:
        """Register state change callback."""
        self._on_state_change = callback

    def on_position_change(self, callback: Callable[[float], None]) -> None:
        """Register position change callback."""
        self._on_position_change = callback

    def _set_state(self, new_state: TransportState) -> None:
        """Set state and fire callback."""
        old = self._state
        self._state = new_state
        if old != new_state and self._on_state_change:
            self._on_state_change(new_state)

    # ── MIDI Clock Sync (Stub) ─────────────────────────────────────────────

    def get_midi_clock_ppqn(self) -> int:
        """Get MIDI Clock pulses per quarter note."""
        return 24

    def get_next_midi_clock_sample(self) -> int:
        """Get sample position of next MIDI Clock tick."""
        ppqn = self.get_midi_clock_ppqn()
        samples_per_tick = 60.0 / (self.tempo * ppqn) * self.sample_rate
        ticks_elapsed = self._position_samples / samples_per_tick
        next_tick = int(ticks_elapsed) + 1
        return int(next_tick * samples_per_tick)

    # ── Utility ────────────────────────────────────────────────────────────

    def __repr__(self) -> str:
        mbt = self.position_mbt
        return (
            f"Transport(state={self._state.name}, "
            f"pos={mbt[0]}:{mbt[1]}:{mbt[2]}, "
            f"tempo={self.tempo:.1f})"
        )
