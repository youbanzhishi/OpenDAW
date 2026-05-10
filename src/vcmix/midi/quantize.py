"""
quantize.py — MIDI note quantization for VCMix.

Provides grid-based quantization (snap notes to rhythmic grid) and
swing quantization (shuffle feel). Works on lists of MidiNote objects
from the midi_parser module.

Grid divisions supported:
    - 1/4  (quarter note)
    - 1/8  (eighth note)
    - 1/16 (sixteenth note)
    - 1/32 (thirty-second note)

Swing:
    Even-numbered grid positions are delayed by a percentage of the
    grid size, producing a shuffle/triplet feel.

Usage:
    from vcmix.midi.quantize import Quantizer
    from vcmix.midi.midi_parser import MidiNote

    q = Quantizer(grid="1/16", strength=0.8)
    quantized = q.quantize_notes(notes)
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Sequence

from vcmix.midi.midi_parser import MidiNote

# Grid size in beats for each division
GRID_SIZES: dict[str, float] = {
    "1/4": 1.0,       # quarter note = 1 beat
    "1/8": 0.5,       # eighth note = 0.5 beats
    "1/16": 0.25,     # sixteenth note = 0.25 beats
    "1/32": 0.125,    # thirty-second = 0.125 beats
}

VALID_GRIDS = set(GRID_SIZES.keys())


@dataclass
class QuantizeResult:
    """Result of a quantization operation.

    Attributes:
        notes: The quantized note list.
        grid: Grid division used.
        strength: Quantization strength applied (0.0-1.0).
        swing: Swing percentage applied (0.0-1.0).
        adjustments: Number of notes whose start time changed.
    """

    notes: list[MidiNote]
    grid: str
    strength: float
    swing: float
    adjustments: int


class Quantizer:
    """Quantize MIDI notes to a rhythmic grid with optional swing.

    Args:
        grid: Grid division string ('1/4', '1/8', '1/16', '1/32').
        strength: Quantization strength (0.0 = no change, 1.0 = full snap).
        swing: Swing amount (0.0 = straight, 0.67 = triplet feel).
            Only off-beat positions are delayed.
    """

    def __init__(
        self,
        grid: str = "1/16",
        strength: float = 1.0,
        swing: float = 0.0,
    ) -> None:
        """Initialize the quantizer.

        Args:
            grid: Grid division ('1/4', '1/8', '1/16', '1/32').
            strength: Quantization strength (0.0-1.0).
            swing: Swing percentage (0.0-1.0).

        Raises:
            ValueError: If grid is not a valid division.
        """
        if grid not in VALID_GRIDS:
            raise ValueError(
                f"Invalid grid {grid!r}. Must be one of {sorted(VALID_GRIDS)}"
            )
        if not 0.0 <= strength <= 1.0:
            raise ValueError(f"Strength must be 0.0-1.0, got {strength}")
        if not 0.0 <= swing <= 1.0:
            raise ValueError(f"Swing must be 0.0-1.0, got {swing}")

        self.grid = grid
        self.grid_size = GRID_SIZES[grid]
        self.strength = strength
        self.swing = swing

    def _snap_to_grid(self, beat: float) -> float:
        """Snap a beat position to the nearest grid point.

        Args:
            beat: Beat position to snap.

        Returns:
            Snapped beat position.
        """
        if self.grid_size <= 0:
            return beat
        return round(beat / self.grid_size) * self.grid_size

    def _apply_swing(self, beat: float) -> float:
        """Apply swing to an off-beat position.

        Even-numbered grid indices (downbeats) are not affected.
        Odd-numbered grid indices (upbeats) are delayed by swing%.

        Args:
            beat: Beat position (already grid-snapped).

        Returns:
            Beat position with swing applied.
        """
        if self.swing == 0.0 or self.grid_size <= 0:
            return beat

        # Determine grid index
        grid_index = round(beat / self.grid_size)
        # Only apply swing to off-beats (odd grid indices)
        if grid_index % 2 == 1:
            swing_offset = self.swing * self.grid_size * 0.5
            return beat + swing_offset
        return beat

    def quantize_notes(self, notes: Sequence[MidiNote]) -> list[MidiNote]:
        """Quantize a list of MIDI notes.

        Each note's start_beat is snapped toward the nearest grid point
        by the configured strength. Duration is preserved. Swing is then
        applied to off-beat positions.

        Args:
            notes: Sequence of MidiNote objects.

        Returns:
            New list of quantized MidiNote objects.
        """
        result: list[MidiNote] = []
        for note in notes:
            # Step 1: Snap to grid
            snapped = self._snap_to_grid(note.start_beat)
            # Step 2: Apply swing to the grid-snapped position
            target = self._apply_swing(snapped)
            # Step 3: Blend original and target based on strength
            #   strength=0 → original position (no change)
            #   strength=1 → fully snapped + swung position
            new_start = note.start_beat + (target - note.start_beat) * self.strength
            new_start = round(new_start, 6)
            # Ensure no negative start
            new_start = max(0.0, new_start)
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

    def quantize_with_result(self, notes: Sequence[MidiNote]) -> QuantizeResult:
        """Quantize notes and return detailed result information.

        Args:
            notes: Sequence of MidiNote objects.

        Returns:
            QuantizeResult with quantized notes and metadata.
        """
        quantized = self.quantize_notes(notes)
        adjustments = sum(
            1 for orig, q in zip(notes, quantized)
            if abs(orig.start_beat - q.start_beat) > 1e-9
        )
        return QuantizeResult(
            notes=quantized,
            grid=self.grid,
            strength=self.strength,
            swing=self.swing,
            adjustments=adjustments,
        )

    @staticmethod
    def available_grids() -> list[str]:
        """Return list of available grid division strings.

        Returns:
            Sorted list of grid names.
        """
        return sorted(GRID_SIZES.keys())

    @staticmethod
    def grid_to_beats(grid: str) -> float:
        """Convert a grid name to beats.

        Args:
            grid: Grid division string.

        Returns:
            Grid size in beats.

        Raises:
            ValueError: If grid name is not valid.
        """
        if grid not in GRID_SIZES:
            raise ValueError(f"Unknown grid: {grid!r}")
        return GRID_SIZES[grid]
