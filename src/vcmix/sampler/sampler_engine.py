"""
sampler_engine.py — Core sampler engine for VCMix.

Manages sample zones, maps MIDI note events to zones, and renders
audio with pitch shifting, looping, and trigger mode support.

Architecture:
    SamplerEngine — Holds zones, manages active voices, renders audio
    ActiveVoice   — Represents a currently-sounding note with playback state

Rendering pipeline:
    1. note_on()  → find matching zone → create ActiveVoice
    2. render()   → for each voice: read samples at playback position,
                    apply pitch shifting via resampling ratio,
                    handle loop points, mix into output buffer
    3. note_off() → mark voice as released (gate mode stops, one-shot continues)

Pitch shifting:
    Uses variable-rate sample playback. The playback speed ratio is
    2^((note - root_key) / 12), which naturally pitch-shifts the sample.
    Linear interpolation is used for sub-sample positioning.

Loop modes:
    forward   — Loop from loop_end back to loop_start, always forward
    reverse   — Play forward to loop_end, then backward to loop_start, repeat
    alternate — Toggle direction each time a loop boundary is reached

Usage:
    from vcmix.sampler.sampler_engine import SamplerEngine, ActiveVoice
    from vcmix.sampler.sample_zone import SampleZone

    engine = SamplerEngine(sample_rate=44100)
    engine.load_zone(SampleZone(file="piano.wav", root_key=60, key_low=48, key_high=72))
    engine.note_on(60, 100)
    audio = engine.render(44100)
    engine.note_off(60)

Dependencies: numpy, soundfile
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np

from vcmix.sampler.sample_zone import SampleZone


@dataclass
class ActiveVoice:
    """Represents a currently-sounding sampler voice.

    Tracks playback position, direction (for reverse/alternate loops),
    and whether the note has been released.

    Attributes:
        zone: The SampleZone this voice is playing from.
        note: The MIDI note number that triggered this voice.
        velocity: The MIDI velocity of the triggering note.
        position: Current playback position in the sample (float for interpolation).
        playing: Whether this voice is still active.
        released: Whether note_off has been received (gate mode).
        direction: Playback direction: 1 = forward, -1 = reverse.
        loop_count: Number of times the loop has been traversed (for alternate mode).
    """

    zone: SampleZone
    note: int
    velocity: int
    position: float = 0.0
    playing: bool = True
    released: bool = False
    direction: int = 1  # 1=forward, -1=reverse
    loop_count: int = 0


class SamplerEngine:
    """Core sampler engine with zone mapping, voice management, and rendering.

    Supports:
        - Multi-zone key/velocity mapping (first matching zone wins)
        - Pitch shifting via variable playback rate
        - Three loop modes: forward, reverse, alternate
        - Gate and one-shot trigger modes
        - Linear interpolation for sub-sample positioning

    Args:
        sample_rate: Output sample rate in Hz.
    """

    def __init__(self, sample_rate: int = 44100) -> None:
        """Initialize the sampler engine.

        Args:
            sample_rate: Output sample rate in Hz.
        """
        if sample_rate <= 0:
            raise ValueError(f"Sample rate must be positive, got {sample_rate}")

        self.sample_rate = sample_rate
        self.zones: list[SampleZone] = []
        self.active_voices: dict[int, ActiveVoice] = {}
        # Cache loaded sample data: {file_path: numpy_array}
        self._sample_cache: dict[str, np.ndarray] = {}

    def load_zone(self, zone: SampleZone) -> None:
        """Add a sample zone to the engine.

        The zone's sample file will be loaded lazily on first use,
        or eagerly if the file is accessible.

        Args:
            zone: SampleZone to add.
        """
        self.zones.append(zone)
        # Try to preload the sample
        self._load_sample(zone.file)

    def remove_zone(self, zone: SampleZone) -> None:
        """Remove a sample zone from the engine.

        Args:
            zone: SampleZone to remove.
        """
        if zone in self.zones:
            self.zones.remove(zone)

    def clear_zones(self) -> None:
        """Remove all zones and stop all voices."""
        self.zones.clear()
        self.active_voices.clear()
        self._sample_cache.clear()

    def _load_sample(self, file_path: str) -> np.ndarray | None:
        """Load a sample file into the cache.

        Supports WAV and AIFF via soundfile. Mono samples are converted
        to 1D arrays; stereo samples are mixed down to mono.

        Args:
            file_path: Path to the audio file.

        Returns:
            1D float32 numpy array, or None if loading fails.
        """
        if file_path in self._sample_cache:
            return self._sample_cache[file_path]

        path = Path(file_path)
        if not path.exists():
            # Don't raise — allow lazy loading later
            return None

        try:
            import soundfile as sf
            audio, sr = sf.read(str(path), dtype="float32")
        except Exception:
            return None

        # Convert to mono if needed
        if audio.ndim > 1:
            audio = np.mean(audio, axis=1).astype(np.float32)

        # Resample if needed
        if sr != self.sample_rate:
            try:
                from scipy.signal import resample
                num_samples = int(len(audio) * self.sample_rate / sr)
                audio = resample(audio, num_samples).astype(np.float32)
            except ImportError:
                # Fallback: simple linear interpolation resampling
                ratio = self.sample_rate / sr
                old_len = len(audio)
                new_len = int(old_len * ratio)
                old_indices = np.linspace(0, old_len - 1, new_len)
                audio = np.interp(old_indices, np.arange(old_len), audio).astype(np.float32)

        self._sample_cache[file_path] = audio
        return audio

    def _get_sample(self, file_path: str) -> np.ndarray | None:
        """Get cached sample data, loading if necessary.

        Args:
            file_path: Path to the audio file.

        Returns:
            1D float32 numpy array, or None if unavailable.
        """
        if file_path in self._sample_cache:
            return self._sample_cache[file_path]
        return self._load_sample(file_path)

    def _find_zone(self, note: int, velocity: int) -> SampleZone | None:
        """Find the first zone matching the given note and velocity.

        Zones are searched in insertion order; the first match wins.

        Args:
            note: MIDI note number (0-127).
            velocity: MIDI velocity (0-127).

        Returns:
            Matching SampleZone, or None if no zone matches.
        """
        for zone in self.zones:
            if zone.matches(note, velocity):
                return zone
        return None

    def note_on(self, note: int, velocity: int) -> bool:
        """Trigger a note on the sampler.

        Finds a matching zone and creates an ActiveVoice. If a voice
        is already active for this note, it is replaced.

        Args:
            note: MIDI note number (0-127).
            velocity: MIDI velocity (0-127).

        Returns:
            True if a zone was found and voice created, False otherwise.
        """
        if not 0 <= note <= 127:
            return False
        if not 0 <= velocity <= 127:
            return False

        zone = self._find_zone(note, velocity)
        if zone is None:
            return False

        # Ensure sample is loaded
        sample = self._get_sample(zone.file)
        if sample is None:
            return False

        # Create voice (replaces any existing voice for this note)
        voice = ActiveVoice(
            zone=zone,
            note=note,
            velocity=velocity,
            position=0.0,
            playing=True,
            released=False,
            direction=1,
            loop_count=0,
        )
        self.active_voices[note] = voice
        return True

    def note_off(self, note: int) -> bool:
        """Release a note.

        For gate-mode zones, the voice will stop rendering.
        For one-shot zones, the voice continues playing to the end.

        Args:
            note: MIDI note number (0-127).

        Returns:
            True if an active voice was found and released, False otherwise.
        """
        if note in self.active_voices:
            voice = self.active_voices[note]
            voice.released = True
            # For gate mode without looping, mark as not playing
            if voice.zone.trigger_mode == "gate" and not voice.zone.has_loop:
                voice.playing = False
            return True
        return False

    def all_notes_off(self) -> None:
        """Release all active voices."""
        for note in list(self.active_voices.keys()):
            self.note_off(note)

    def render(self, num_samples: int) -> np.ndarray:
        """Render audio from all active voices.

        For each active voice, reads samples from the zone's audio data
        at the current position with pitch-shifted playback rate. Handles
        loop points and removes voices that have finished playing.

        Args:
            num_samples: Number of samples to render.

        Returns:
            1D float32 audio array of length num_samples.
        """
        output = np.zeros(num_samples, dtype=np.float64)
        finished_notes: list[int] = []

        for note, voice in self.active_voices.items():
            if not voice.playing:
                finished_notes.append(note)
                continue

            sample_data = self._get_sample(voice.zone.file)
            if sample_data is None:
                finished_notes.append(note)
                continue

            voice_output = self._render_voice(voice, sample_data, num_samples)
            output += voice_output

            if not voice.playing:
                finished_notes.append(note)

        for note in finished_notes:
            del self.active_voices[note]

        return output.astype(np.float32)

    def _render_voice(
        self,
        voice: ActiveVoice,
        sample_data: np.ndarray,
        num_samples: int,
    ) -> np.ndarray:
        """Render a single voice into an audio buffer.

        Handles pitch shifting, looping, and trigger modes.

        Args:
            voice: ActiveVoice to render.
            sample_data: The sample's audio data (1D float32).
            num_samples: Number of output samples to produce.

        Returns:
            1D float64 audio buffer of length num_samples.
        """
        output = np.zeros(num_samples, dtype=np.float64)
        zone = voice.zone
        total_samples = len(sample_data)

        if total_samples == 0:
            voice.playing = False
            return output

        # Playback rate: pitch shift ratio
        pitch_ratio = zone.pitch_ratio(voice.note)

        # Velocity scaling (0-127 -> 0.0-1.0)
        velocity_scale = voice.velocity / 127.0

        # Zone gain (linear)
        zone_gain = zone.gain_linear()

        # Loop parameters
        has_loop = zone.has_loop and total_samples > 0
        loop_start = zone.loop_start if has_loop else None
        loop_end = zone.loop_end if has_loop else None

        # Validate loop points against sample length
        if has_loop:
            if loop_start is not None and loop_start >= total_samples:
                has_loop = False
            if loop_end is not None and loop_end > total_samples:
                loop_end = total_samples
            if has_loop and loop_start is not None and loop_end is not None:
                if loop_end <= loop_start:
                    has_loop = False

        for i in range(num_samples):
            if not voice.playing:
                break

            pos = voice.position

            # Gate mode: if released and no loop, play until end of sample
            # One-shot mode: always play until end regardless of release
            if voice.released and zone.trigger_mode == "gate" and not has_loop:
                if pos >= total_samples:
                    voice.playing = False
                    break

            # Check if we've gone past the end of the sample (no loop)
            if pos >= total_samples:
                if has_loop and loop_start is not None:
                    # Wrap to loop start
                    voice.position = float(loop_start)
                    pos = voice.position
                    voice.loop_count += 1
                else:
                    voice.playing = False
                    break

            # Check if position went below 0 (reverse playback)
            if pos < 0:
                if has_loop and loop_end is not None:
                    voice.position = float(loop_end - 1)
                    pos = voice.position
                    voice.loop_count += 1
                else:
                    voice.playing = False
                    break

            # Linear interpolation
            sample_val = self._interpolate_sample(sample_data, pos)
            output[i] = sample_val * velocity_scale * zone_gain

            # Advance position
            new_pos = pos + pitch_ratio * voice.direction

            # Handle loop boundaries
            if has_loop and loop_start is not None and loop_end is not None:
                if voice.direction == 1:
                    # Forward: check if we hit loop_end
                    if new_pos >= loop_end:
                        if zone.loop_mode == "forward":
                            # Wrap back to loop_start
                            new_pos = float(loop_start)
                        elif zone.loop_mode == "reverse":
                            # Reverse direction
                            voice.direction = -1
                            new_pos = float(loop_end - 1) - (new_pos - loop_end)
                        elif zone.loop_mode == "alternate":
                            voice.direction = -1
                            new_pos = float(loop_end - 1) - (new_pos - loop_end)
                        voice.loop_count += 1
                else:
                    # Reverse: check if we hit loop_start
                    if new_pos <= loop_start:
                        if zone.loop_mode == "forward":
                            # Shouldn't happen in forward mode, but safety
                            new_pos = float(loop_start)
                        elif zone.loop_mode == "reverse":
                            # Reverse back to loop_end
                            new_pos = float(loop_end - 1)
                        elif zone.loop_mode == "alternate":
                            voice.direction = 1
                            new_pos = float(loop_start) + (loop_start - new_pos)
                        voice.loop_count += 1
            else:
                # No loop: for one-shot, if released and past end, stop
                if voice.released and zone.trigger_mode == "one-shot" and new_pos >= total_samples:
                    voice.playing = False

            voice.position = new_pos

        return output

    @staticmethod
    def _interpolate_sample(sample_data: np.ndarray, position: float) -> float:
        """Linear interpolation of sample data at a fractional position.

        Args:
            sample_data: 1D sample array.
            position: Fractional sample position.

        Returns:
            Interpolated sample value.
        """
        total = len(sample_data)
        if total == 0:
            return 0.0

        if position < 0:
            return 0.0
        if position >= total - 1:
            return float(sample_data[total - 1])

        idx = int(position)
        frac = position - idx

        if idx + 1 < total:
            return float(sample_data[idx] * (1.0 - frac) + sample_data[idx + 1] * frac)
        else:
            return float(sample_data[idx])

    @property
    def active_voice_count(self) -> int:
        """Number of currently active voices."""
        return len(self.active_voices)

    def get_zone_info(self) -> list[dict]:
        """Get information about all loaded zones.

        Returns:
            List of dicts with zone details.
        """
        info = []
        for i, zone in enumerate(self.zones):
            sample = self._get_sample(zone.file)
            info.append({
                "index": i,
                "file": zone.file,
                "root_key": zone.root_key,
                "key_range": f"{zone.key_low}-{zone.key_high}",
                "velocity_range": f"{zone.velocity_low}-{zone.velocity_high}",
                "loop_mode": zone.loop_mode,
                "trigger_mode": zone.trigger_mode,
                "has_loop": zone.has_loop,
                "sample_loaded": sample is not None,
                "sample_length": len(sample) if sample is not None else 0,
                "tune_cents": zone.tune_cents,
                "gain_db": zone.gain_db,
            })
        return info
