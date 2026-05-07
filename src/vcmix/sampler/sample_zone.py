"""
sample_zone.py — Sample zone definition for VCMix sampler.

A SampleZone maps an audio file to a range of MIDI keys and velocities,
defining how the sample is triggered, looped, and tuned.

Data structures:
    SampleZone — One sample mapped to a key/velocity range with playback options

Usage:
    from vcmix.sampler.sample_zone import SampleZone

    zone = SampleZone(
        file="piano_C4.wav",
        root_key=60,
        key_low=48,
        key_high=72,
        velocity_low=0,
        velocity_high=127,
        loop_mode="forward",
        trigger_mode="gate",
    )

    if zone.matches(note=60, velocity=100):
        print(f"Zone covers note 60 at velocity 100")
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class SampleZone:
    """A single sample mapped to a MIDI key and velocity range.

    Attributes:
        file: Path to the WAV/AIFF sample file.
        root_key: MIDI note number where the sample plays at original pitch (0-127).
        key_low: Lowest MIDI note this zone responds to (0-127).
        key_high: Highest MIDI note this zone responds to (0-127).
        velocity_low: Lowest velocity this zone responds to (0-127).
        velocity_high: Highest velocity this zone responds to (0-127).
        loop_start: Loop start point in samples (None = no loop).
        loop_end: Loop end point in samples (None = no loop).
        loop_mode: Loop mode — 'forward', 'reverse', or 'alternate'.
        trigger_mode: Trigger mode — 'gate' (stops on note_off) or 'one-shot' (plays to end).
        tune_cents: Fine tuning in cents (-100 to +100).
        gain_db: Gain adjustment in dB.
    """

    file: str
    root_key: int = 60
    key_low: int = 0
    key_high: int = 127
    velocity_low: int = 0
    velocity_high: int = 127
    loop_start: Optional[int] = None
    loop_end: Optional[int] = None
    loop_mode: str = "forward"
    trigger_mode: str = "gate"
    tune_cents: float = 0.0
    gain_db: float = 0.0

    def __post_init__(self) -> None:
        """Validate zone parameters."""
        for name, val in [("root_key", self.root_key),
                          ("key_low", self.key_low),
                          ("key_high", self.key_high)]:
            if not 0 <= val <= 127:
                raise ValueError(f"{name} must be 0-127, got {val}")

        if self.key_low > self.key_high:
            raise ValueError(
                f"key_low ({self.key_low}) must be <= key_high ({self.key_high})"
            )

        for name, val in [("velocity_low", self.velocity_low),
                          ("velocity_high", self.velocity_high)]:
            if not 0 <= val <= 127:
                raise ValueError(f"{name} must be 0-127, got {val}")

        if self.velocity_low > self.velocity_high:
            raise ValueError(
                f"velocity_low ({self.velocity_low}) must be <= "
                f"velocity_high ({self.velocity_high})"
            )

        if self.loop_mode not in ("forward", "reverse", "alternate"):
            raise ValueError(
                f"loop_mode must be 'forward', 'reverse', or 'alternate', "
                f"got {self.loop_mode!r}"
            )

        if self.trigger_mode not in ("gate", "one-shot"):
            raise ValueError(
                f"trigger_mode must be 'gate' or 'one-shot', "
                f"got {self.trigger_mode!r}"
            )

        if not -100 <= self.tune_cents <= 100:
            raise ValueError(f"tune_cents must be -100 to +100, got {self.tune_cents}")

        # Validate loop points if both are set
        if self.loop_start is not None and self.loop_end is not None:
            if self.loop_start < 0:
                raise ValueError(f"loop_start must be >= 0, got {self.loop_start}")
            if self.loop_end <= self.loop_start:
                raise ValueError(
                    f"loop_end ({self.loop_end}) must be > loop_start ({self.loop_start})"
                )

    def matches(self, note: int, velocity: int) -> bool:
        """Check if this zone responds to the given note and velocity.

        Args:
            note: MIDI note number (0-127).
            velocity: MIDI velocity (0-127).

        Returns:
            True if the note and velocity fall within this zone's range.
        """
        return (
            self.key_low <= note <= self.key_high
            and self.velocity_low <= velocity <= self.velocity_high
        )

    @property
    def has_loop(self) -> bool:
        """Whether this zone has loop points defined."""
        return self.loop_start is not None and self.loop_end is not None

    @property
    def key_range(self) -> int:
        """Number of semitones this zone covers."""
        return self.key_high - self.key_low + 1

    def pitch_ratio(self, note: int) -> float:
        """Calculate the playback speed ratio for a given MIDI note.

        Notes above root_key play faster (higher pitch),
        notes below root_key play slower (lower pitch).

        Also accounts for tune_cents fine-tuning offset.

        Args:
            note: Target MIDI note number.

        Returns:
            Playback speed ratio (1.0 = original speed).
        """
        semitones = note - self.root_key
        cents_total = semitones * 100.0 + self.tune_cents
        return 2.0 ** (cents_total / 1200.0)

    def gain_linear(self) -> float:
        """Convert gain_db to linear gain factor.

        Returns:
            Linear gain (1.0 = unity).
        """
        return 10.0 ** (self.gain_db / 20.0)

    def to_dict(self) -> dict:
        """Serialize zone to a dictionary (for YAML integration).

        Returns:
            Dict representation of the zone.
        """
        d: dict = {
            "file": self.file,
            "root_key": self.root_key,
            "key_low": self.key_low,
            "key_high": self.key_high,
            "velocity_low": self.velocity_low,
            "velocity_high": self.velocity_high,
            "loop_mode": self.loop_mode,
            "trigger_mode": self.trigger_mode,
            "tune_cents": self.tune_cents,
            "gain_db": self.gain_db,
        }
        if self.loop_start is not None:
            d["loop_start"] = self.loop_start
        if self.loop_end is not None:
            d["loop_end"] = self.loop_end
        return d

    @classmethod
    def from_dict(cls, data: dict) -> SampleZone:
        """Create a SampleZone from a dictionary (for YAML parsing).

        Args:
            data: Dict with zone parameters.

        Returns:
            SampleZone instance.
        """
        return cls(
            file=data["file"],
            root_key=data.get("root_key", 60),
            key_low=data.get("key_low", 0),
            key_high=data.get("key_high", 127),
            velocity_low=data.get("velocity_low", 0),
            velocity_high=data.get("velocity_high", 127),
            loop_start=data.get("loop_start"),
            loop_end=data.get("loop_end"),
            loop_mode=data.get("loop_mode", "forward"),
            trigger_mode=data.get("trigger_mode", "gate"),
            tune_cents=data.get("tune_cents", 0.0),
            gain_db=data.get("gain_db", 0.0),
        )
