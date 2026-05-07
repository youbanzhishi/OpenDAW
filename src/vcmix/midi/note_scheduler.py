"""
note_scheduler.py — MIDI note scheduler and synthesizer for VCMix.

Maps parsed MIDI notes to audio render events, scheduling them on a
beat-based timeline. Provides built-in synthesizers (sine, sawtooth,
square, triangle) for MIDI tracks without external instrument plugins.

Architecture:
    NoteScheduler — Takes MidiTrack data and produces audio buffers
                    by rendering each note through a synth oscillator.

    Synth types:
        - sine     — Pure sine wave (clean, fundamental only)
        - sawtooth — Sawtooth wave (bright, harmonically rich)
        - square   — Square wave (hollow, odd harmonics)
        - triangle — Triangle wave (mellow, odd harmonics, softer)

Rendering pipeline:
    1. Convert beat positions to sample positions using BPM/sample_rate
    2. For each note, generate oscillator audio at the note's frequency
    3. Apply velocity as amplitude scaling
    4. Apply ADSR envelope for natural attack/release
    5. Mix all notes into a single audio buffer

Usage:
    from vcmix.midi.note_scheduler import NoteScheduler

    scheduler = NoteScheduler(bpm=120, sample_rate=44100)
    audio = scheduler.render_track(midi_track, synth="sawtooth")

Dependencies: numpy
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from vcmix.midi.midi_parser import MidiNote, MidiTrack

# ── ADSR Envelope ────────────────────────────────────────────────────────

@dataclass
class ADSR:
    """Attack-Decay-Sustain-Release envelope.

    Attributes:
        attack: Attack time in seconds.
        decay: Decay time in seconds.
        sustain: Sustain level (0.0-1.0, relative to peak).
        release: Release time in seconds.
    """

    attack: float = 0.005
    decay: float = 0.01
    sustain: float = 0.8
    release: float = 0.02

    def generate(self, duration_samples: int, sample_rate: int) -> np.ndarray:
        """Generate ADSR envelope for a note of given sample length.

        Args:
            duration_samples: Total note duration in samples.
            sample_rate: Audio sample rate.

        Returns:
            1D float32 envelope array of length duration_samples.
        """
        if duration_samples <= 0:
            return np.array([], dtype=np.float32)

        attack_samples = min(int(self.attack * sample_rate), duration_samples)
        decay_samples = min(int(self.decay * sample_rate), duration_samples - attack_samples)
        release_samples = min(int(self.release * sample_rate), duration_samples // 4)

        envelope = np.ones(duration_samples, dtype=np.float64)

        # Attack ramp (0 -> 1)
        if attack_samples > 0:
            envelope[:attack_samples] = np.linspace(0.0, 1.0, attack_samples)

        # Decay ramp (1 -> sustain)
        decay_start = attack_samples
        decay_end = decay_start + decay_samples
        if decay_samples > 0 and decay_end <= duration_samples:
            envelope[decay_start:decay_end] = np.linspace(1.0, self.sustain, decay_samples)

        # Sustain level
        sustain_start = decay_end
        release_start = max(sustain_start, duration_samples - release_samples)
        if release_start > sustain_start:
            envelope[sustain_start:release_start] = self.sustain

        # Release ramp (sustain -> 0)
        if release_samples > 0 and release_start < duration_samples:
            remaining = duration_samples - release_start
            start_val = (
                self.sustain
                if release_start >= decay_end
                else envelope[min(release_start, duration_samples - 1)]
            )
            envelope[release_start:] = np.linspace(
                start_val,
                0.0,
                remaining,
            )

        return envelope.astype(np.float32)


# ── Oscillator Functions ─────────────────────────────────────────────────

def _osc_sine(phase: np.ndarray) -> np.ndarray:
    """Pure sine wave oscillator."""
    return np.sin(2.0 * np.pi * phase)


def _osc_sawtooth(phase: np.ndarray) -> np.ndarray:
    """Sawtooth wave oscillator (ramp up, -1 to +1)."""
    return 2.0 * (phase % 1.0) - 1.0


def _osc_square(phase: np.ndarray) -> np.ndarray:
    """Square wave oscillator."""
    return np.where((phase % 1.0) < 0.5, 1.0, -1.0)


def _osc_triangle(phase: np.ndarray) -> np.ndarray:
    """Triangle wave oscillator."""
    p = phase % 1.0
    return 4.0 * np.abs(p - 0.5) - 1.0


_OSCILLATORS: dict[str, Any] = {
    "sine": _osc_sine,
    "sawtooth": _osc_sawtooth,
    "square": _osc_square,
    "triangle": _osc_triangle,
}


# ── NoteScheduler ────────────────────────────────────────────────────────

class NoteScheduler:
    """Schedule and render MIDI notes into audio buffers.

    Converts beat-based note positions to sample positions, generates
    oscillator audio for each note, applies envelopes, and mixes into
    a single output buffer.

    Args:
        bpm: Beats per minute for timing conversion.
        sample_rate: Audio sample rate in Hz.
        synth: Default synthesizer type (sine/sawtooth/square/triangle).
        adsr: ADSR envelope settings.
    """

    def __init__(
        self,
        bpm: float = 120.0,
        sample_rate: int = 44100,
        synth: str = "sine",
        adsr: ADSR | None = None,
    ) -> None:
        """Initialize the note scheduler.

        Args:
            bpm: Beats per minute.
            sample_rate: Audio sample rate in Hz.
            synth: Synthesizer type name.
            adsr: ADSR envelope, or None for default.
        """
        if bpm <= 0:
            raise ValueError(f"BPM must be positive, got {bpm}")
        if sample_rate <= 0:
            raise ValueError(f"Sample rate must be positive, got {sample_rate}")

        self.bpm = bpm
        self.sample_rate = sample_rate
        self.synth = synth
        self.adsr = adsr or ADSR()

    @property
    def beat_duration_seconds(self) -> float:
        """Duration of one beat in seconds."""
        return 60.0 / self.bpm

    @property
    def beat_duration_samples(self) -> int:
        """Duration of one beat in samples."""
        return int(self.beat_duration_seconds * self.sample_rate)

    def beat_to_sample(self, beat: float) -> int:
        """Convert a beat position to a sample position.

        Args:
            beat: Position in beats.

        Returns:
            Sample position (integer).
        """
        return int(beat * self.beat_duration_samples)

    def render_track(
        self,
        track: MidiTrack,
        synth: str | None = None,
        total_beats: float | None = None,
    ) -> np.ndarray:
        """Render a MidiTrack into an audio buffer.

        Args:
            track: MidiTrack with note events.
            synth: Override synthesizer type (uses self.synth if None).
            total_beats: Total song length in beats. If None, computed
                from the track's notes.

        Returns:
            1D float32 audio buffer.
        """
        if not track.notes:
            return np.array([], dtype=np.float32)

        synth_name = synth or self.synth
        if synth_name not in _OSCILLATORS:
            raise ValueError(
                f"Unknown synth type: {synth_name!r}. "
                f"Available: {list(_OSCILLATORS.keys())}"
            )

        oscillator = _OSCILLATORS[synth_name]

        # Determine total length
        if total_beats is None:
            total_beats = track.total_beats
        total_samples = self.beat_to_sample(total_beats)

        if total_samples <= 0:
            return np.array([], dtype=np.float32)

        output = np.zeros(total_samples, dtype=np.float64)

        for note in track.notes:
            note_audio = self._render_note(note, oscillator, total_samples)
            start_sample = self.beat_to_sample(note.start_beat)
            end_sample = min(start_sample + len(note_audio), total_samples)
            length = end_sample - start_sample
            if length > 0:
                output[start_sample:end_sample] += note_audio[:length]

        # Normalize if clipping
        peak = np.max(np.abs(output))
        if peak > 1.0:
            output /= peak

        return output.astype(np.float32)

    def _render_note(
        self,
        note: MidiNote,
        oscillator: Any,
        max_samples: int,
    ) -> np.ndarray:
        """Render a single MIDI note as audio.

        Args:
            note: MidiNote to render.
            oscillator: Oscillator function.
            max_samples: Maximum buffer length.

        Returns:
            1D float64 audio buffer for this note.
        """
        duration_samples = self.beat_to_sample(note.duration_beats)
        if duration_samples <= 0:
            return np.array([], dtype=np.float64)

        # Generate phase array
        freq = note.frequency
        t = np.arange(duration_samples, dtype=np.float64) / self.sample_rate
        phase = freq * t

        # Generate oscillator output
        audio = oscillator(phase).astype(np.float64)

        # Apply velocity scaling (MIDI velocity 0-127 -> amplitude 0-1)
        amplitude = note.velocity / 127.0
        audio *= amplitude

        # Apply ADSR envelope
        envelope = self.adsr.generate(duration_samples, self.sample_rate)
        audio *= envelope.astype(np.float64)

        return audio

    def render_note_list(
        self,
        notes: list[MidiNote],
        synth: str | None = None,
        total_beats: float | None = None,
    ) -> np.ndarray:
        """Render a list of MidiNote events directly (without MidiTrack wrapper).

        Args:
            notes: List of MidiNote events.
            synth: Override synthesizer type.
            total_beats: Total length in beats.

        Returns:
            1D float32 audio buffer.
        """
        track = MidiTrack(name="inline", notes=sorted(notes, key=lambda n: n.start_beat))
        return self.render_track(track, synth=synth, total_beats=total_beats)

    def get_active_notes_at_beat(self, notes: list[MidiNote], beat: float) -> list[MidiNote]:
        """Get notes that are sounding at a given beat position.

        Args:
            notes: List of notes to check.
            beat: Beat position to query.

        Returns:
            List of notes active at the given beat.
        """
        active: list[MidiNote] = []
        for note in notes:
            if note.start_beat <= beat < note.start_beat + note.duration_beats:
                active.append(note)
        return active

    def schedule_events(
        self, notes: list[MidiNote]
    ) -> list[dict[str, Any]]:
        """Convert notes to a sorted event list (note_on / note_off).

        Useful for real-time playback scheduling.

        Args:
            notes: List of MidiNote events.

        Returns:
            Sorted list of event dicts with 'type', 'beat', 'note',
            'velocity', 'channel' keys.
        """
        events: list[dict[str, Any]] = []
        for note in notes:
            events.append({
                "type": "note_on",
                "beat": note.start_beat,
                "note": note.note,
                "velocity": note.velocity,
                "channel": note.channel,
            })
            events.append({
                "type": "note_off",
                "beat": note.start_beat + note.duration_beats,
                "note": note.note,
                "velocity": 0,
                "channel": note.channel,
            })
        events.sort(key=lambda e: (e["beat"], e["type"] == "note_on"))
        return events


# ── Available Synth Types ────────────────────────────────────────────────

def list_synths() -> list[str]:
    """Return list of available built-in synthesizer types.

    Returns:
        Sorted list of synth type names.
    """
    return sorted(_OSCILLATORS.keys())
