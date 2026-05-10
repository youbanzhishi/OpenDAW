"""
humanize.py — MIDI humanization for VCMix.

Adds musical imperfections to MIDI notes for a more natural, human feel.
Provides random timing offsets and velocity variations.

Features:
    - Timing humanization: random offsets to note start times
    - Velocity humanization: random variations to note velocity
    - Configurable ranges for both timing and velocity
    - Reproducible results via optional seed

Usage:
    from vcmix.midi.humanize import Humanizer
    from vcmix.midi.midi_parser import MidiNote

    h = Humanizer(timing_range=0.02, velocity_range=10, seed=42)
    humanized = h.humanize_notes(notes)
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Sequence

from vcmix.midi.midi_parser import MidiNote


@dataclass
class HumanizeResult:
    """Result of a humanization operation.

    Attributes:
        notes: The humanized note list.
        timing_range: Timing offset range used (beats).
        velocity_range: Velocity variation range used.
        total_timing_offset: Sum of absolute timing offsets applied.
        total_velocity_offset: Sum of absolute velocity offsets applied.
    """

    notes: list[MidiNote]
    timing_range: float
    velocity_range: int
    total_timing_offset: float
    total_velocity_offset: int


class Humanizer:
    """Add human-like imperfections to MIDI notes.

    Args:
        timing_range: Maximum timing offset in beats (± this value).
            Typical values: 0.005 - 0.03 beats.
        velocity_range: Maximum velocity offset (± this value).
            Typical values: 5 - 20.
        seed: Random seed for reproducibility (None = random each time).
    """

    def __init__(
        self,
        timing_range: float = 0.01,
        velocity_range: int = 8,
        seed: int | None = None,
    ) -> None:
        """Initialize the humanizer.

        Args:
            timing_range: Max timing offset in beats (≥ 0).
            velocity_range: Max velocity offset (≥ 0).
            seed: Random seed for reproducibility.

        Raises:
            ValueError: If timing_range or velocity_range is negative.
        """
        if timing_range < 0:
            raise ValueError(f"timing_range must be ≥ 0, got {timing_range}")
        if velocity_range < 0:
            raise ValueError(f"velocity_range must be ≥ 0, got {velocity_range}")

        self.timing_range = timing_range
        self.velocity_range = velocity_range
        self._rng = random.Random(seed)

    def humanize_notes(self, notes: Sequence[MidiNote]) -> list[MidiNote]:
        """Apply humanization to a list of MIDI notes.

        Each note gets a random timing offset and velocity offset,
        sampled uniformly from [-range, +range].

        Args:
            notes: Sequence of MidiNote objects.

        Returns:
            New list of humanized MidiNote objects.
        """
        result: list[MidiNote] = []
        for note in notes:
            # Timing offset
            timing_offset = self._rng.uniform(-self.timing_range, self.timing_range)
            new_start = max(0.0, round(note.start_beat + timing_offset, 6))

            # Velocity offset
            vel_offset = self._rng.randint(-self.velocity_range, self.velocity_range)
            new_velocity = max(1, min(127, note.velocity + vel_offset))

            result.append(
                MidiNote(
                    note=note.note,
                    velocity=new_velocity,
                    start_beat=new_start,
                    duration_beats=note.duration_beats,
                    channel=note.channel,
                )
            )
        result.sort(key=lambda n: (n.start_beat, n.note))
        return result

    def humanize_with_result(self, notes: Sequence[MidiNote]) -> HumanizeResult:
        """Humanize notes and return detailed result information.

        Args:
            notes: Sequence of MidiNote objects.

        Returns:
            HumanizeResult with humanized notes and metadata.
        """
        humanized = self.humanize_notes(notes)
        total_timing = sum(
            abs(h.start_beat - o.start_beat)
            for o, h in zip(notes, humanized)
        )
        total_vel = sum(
            abs(h.velocity - o.velocity)
            for o, h in zip(notes, humanized)
        )
        return HumanizeResult(
            notes=humanized,
            timing_range=self.timing_range,
            velocity_range=self.velocity_range,
            total_timing_offset=round(total_timing, 6),
            total_velocity_offset=total_vel,
        )

    def humanize_timing_only(self, notes: Sequence[MidiNote]) -> list[MidiNote]:
        """Apply only timing humanization (no velocity changes).

        Args:
            notes: Sequence of MidiNote objects.

        Returns:
            New list with timing-humanized notes.
        """
        result: list[MidiNote] = []
        for note in notes:
            offset = self._rng.uniform(-self.timing_range, self.timing_range)
            new_start = max(0.0, round(note.start_beat + offset, 6))
            result.append(
                MidiNote(
                    note=note.note,
                    velocity=note.velocity,
                    start_beat=new_start,
                    duration_beats=note.duration_beats,
                    channel=note.channel,
                )
            )
        result.sort(key=lambda n: (n.start_beat, n.note))
        return result

    def humanize_velocity_only(self, notes: Sequence[MidiNote]) -> list[MidiNote]:
        """Apply only velocity humanization (no timing changes).

        Args:
            notes: Sequence of MidiNote objects.

        Returns:
            New list with velocity-humanized notes.
        """
        result: list[MidiNote] = []
        for note in notes:
            vel_offset = self._rng.randint(-self.velocity_range, self.velocity_range)
            new_velocity = max(1, min(127, note.velocity + vel_offset))
            result.append(
                MidiNote(
                    note=note.note,
                    velocity=new_velocity,
                    start_beat=note.start_beat,
                    duration_beats=note.duration_beats,
                    channel=note.channel,
                )
            )
        return result
