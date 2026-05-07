"""
arrangement.py - Arrangement structure extraction from separated stems.

Extracts musical arrangement information:
- Section identification (intro/verse/chorus/bridge/outro)
- Instrument entry/exit timestamps
- Energy change curves
- Beat grid alignment

Part of VCMix separation module.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class Section:
    """A detected musical section (intro, verse, chorus, etc.)."""
    name: str                       # "intro" / "verse" / "chorus" / "bridge" / "outro"
    start_beat: int                 # beat index (0-based)
    end_beat: int                   # beat index (exclusive)
    start_sec: float                # start time in seconds
    end_sec: float                  # end time in seconds
    active_stems: list[str] = field(default_factory=list)
    energy_level: str = "medium"    # "low" / "medium" / "high"


@dataclass
class EnergyEnvelope:
    """Per-beat energy envelope for a single stem."""
    stem_name: str
    rms_per_beat: np.ndarray        # shape (num_beats,), RMS energy per beat


# ---------------------------------------------------------------------------
# Constants / thresholds
# ---------------------------------------------------------------------------

# Energy ratio thresholds for section classification
# (relative to the global max energy)
_ENERGY_LOW_THRESHOLD = 0.30
_ENERGY_HIGH_THRESHOLD = 0.65

# Minimum section length in beats (shorter sections are merged)
_MIN_SECTION_BEATS = 4

# Energy jump threshold for detecting section boundaries
_BOUNDARY_JUMP_RATIO = 0.25  # 25% relative change


# ---------------------------------------------------------------------------
# Core extractor
# ---------------------------------------------------------------------------

class ArrangementExtractor:
    """Extract arrangement structure from separated stems.

    Algorithm overview:
        1. Compute per-stem energy envelopes (RMS per beat).
        2. Merge envelopes into a total energy curve.
        3. Detect section boundaries from significant energy changes.
        4. Label sections based on energy level and instrument activity.
        5. Align all boundaries to the beat grid.
        6. Output a list of :class:`Section` objects.
    """

    def __init__(
        self,
        energy_low_threshold: float = _ENERGY_LOW_THRESHOLD,
        energy_high_threshold: float = _ENERGY_HIGH_THRESHOLD,
        min_section_beats: int = _MIN_SECTION_BEATS,
        boundary_jump_ratio: float = _BOUNDARY_JUMP_RATIO,
    ):
        self.energy_low_threshold = energy_low_threshold
        self.energy_high_threshold = energy_high_threshold
        self.min_section_beats = min_section_beats
        self.boundary_jump_ratio = boundary_jump_ratio

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def extract(
        self,
        stems: dict[str, np.ndarray],
        sr: int,
        bpm: float,
    ) -> list[Section]:
        """Extract arrangement sections from stems.

        Parameters
        ----------
        stems : dict mapping stem name -> 1-D float32 ndarray
            Each array is a mono audio signal at *sr* sample rate.
        sr : int
            Sample rate in Hz.
        bpm : float
            Tempo in beats per minute.

        Returns
        -------
        list[Section]
            Detected sections ordered chronologically.
        """
        if bpm <= 0:
            raise ValueError(f"bpm must be positive, got {bpm}")
        if sr <= 0:
            raise ValueError(f"sr must be positive, got {sr}")
        if not stems:
            return []

        # 1. Per-stem energy envelopes (RMS per beat)
        envelopes = self._compute_envelopes(stems, sr, bpm)
        num_beats = max(len(e.rms_per_beat) for e in envelopes.values())

        # 2. Total energy curve (normalised to [0, 1])
        total_energy = self._merge_envelopes(envelopes, num_beats)

        # 3. Detect section boundaries
        boundaries = self._detect_boundaries(total_energy)

        # 4. Label sections
        sections = self._label_sections(
            boundaries, total_energy, envelopes, sr, bpm,
        )

        # 5. Merge tiny sections
        sections = self._merge_short_sections(sections)

        return sections

    # ------------------------------------------------------------------
    # Step 1: Energy envelopes
    # ------------------------------------------------------------------

    def _compute_envelopes(
        self,
        stems: dict[str, np.ndarray],
        sr: int,
        bpm: float,
    ) -> dict[str, EnergyEnvelope]:
        """Compute per-beat RMS for each stem."""
        beat_samples = int(sr * 60.0 / bpm)  # samples per beat
        envelopes: dict[str, EnergyEnvelope] = {}

        for name, audio in stems.items():
            audio = np.asarray(audio, dtype=np.float64).ravel()
            n_beats = max(1, len(audio) // beat_samples)
            rms_values = np.zeros(n_beats, dtype=np.float64)

            for b in range(n_beats):
                start = b * beat_samples
                end = min(start + beat_samples, len(audio))
                segment = audio[start:end]
                if len(segment) > 0:
                    rms_values[b] = np.sqrt(np.mean(segment ** 2))
                else:
                    rms_values[b] = 0.0

            envelopes[name] = EnergyEnvelope(stem_name=name, rms_per_beat=rms_values)

        return envelopes

    # ------------------------------------------------------------------
    # Step 2: Merge envelopes
    # ------------------------------------------------------------------

    @staticmethod
    def _merge_envelopes(
        envelopes: dict[str, EnergyEnvelope],
        num_beats: int,
    ) -> np.ndarray:
        """Sum per-stem RMS envelopes and normalise to [0, 1]."""
        total = np.zeros(num_beats, dtype=np.float64)
        for env in envelopes.values():
            n = min(len(env.rms_per_beat), num_beats)
            total[:n] += env.rms_per_beat[:n]

        max_val = total.max()
        if max_val > 0:
            total /= max_val
        return total

    # ------------------------------------------------------------------
    # Step 3: Boundary detection
    # ------------------------------------------------------------------

    def _detect_boundaries(self, total_energy: np.ndarray) -> list[int]:
        """Detect section boundaries from energy changes.

        A boundary is placed wherever the relative energy change
        exceeds *boundary_jump_ratio*.
        """
        if len(total_energy) < 2:
            return [0]

        boundaries = [0]  # always start at beat 0

        # Smooth energy curve slightly (moving average, window=3)
        kernel = np.array([0.25, 0.5, 0.25])
        smoothed = np.convolve(total_energy, kernel, mode="same")

        for i in range(1, len(smoothed)):
            prev = smoothed[i - 1]
            curr = smoothed[i]
            # Relative change (avoid division by zero)
            ref = max(abs(prev), 1e-10)
            delta = abs(curr - prev) / ref
            if delta > self.boundary_jump_ratio:
                # Don't add a boundary too close to the previous one
                if i - boundaries[-1] >= self.min_section_beats:
                    boundaries.append(i)

        return boundaries

    # ------------------------------------------------------------------
    # Step 4: Section labelling
    # ------------------------------------------------------------------

    def _label_sections(
        self,
        boundaries: list[int],
        total_energy: np.ndarray,
        envelopes: dict[str, EnergyEnvelope],
        sr: int,
        bpm: float,
    ) -> list[Section]:
        """Label each section based on energy and instrument activity."""
        beat_sec = 60.0 / bpm  # seconds per beat
        num_beats = len(total_energy)
        sections: list[Section] = []

        for idx in range(len(boundaries)):
            start_b = boundaries[idx]
            end_b = boundaries[idx + 1] if idx + 1 < len(boundaries) else num_beats

            # Average energy in this section
            if end_b > start_b:
                avg_energy = float(np.mean(total_energy[start_b:end_b]))
            else:
                avg_energy = 0.0

            # Energy level
            energy_level = self._classify_energy(avg_energy)

            # Active stems (RMS above 10% of their own max in this section)
            active = self._find_active_stems(envelopes, start_b, end_b)

            # Section name heuristic
            name = self._name_section(
                idx, len(boundaries), energy_level, active, start_b, num_beats,
            )

            sections.append(Section(
                name=name,
                start_beat=start_b,
                end_beat=end_b,
                start_sec=start_b * beat_sec,
                end_sec=end_b * beat_sec,
                active_stems=active,
                energy_level=energy_level,
            ))

        return sections

    def _classify_energy(self, avg: float) -> str:
        """Map normalised average energy to a label."""
        if avg < self.energy_low_threshold:
            return "low"
        elif avg > self.energy_high_threshold:
            return "high"
        return "medium"

    @staticmethod
    def _find_active_stems(
        envelopes: dict[str, EnergyEnvelope],
        start_b: int,
        end_b: int,
        activity_threshold: float = 0.10,
    ) -> list[str]:
        """Return stem names that are active (above threshold) in a section."""
        active: list[str] = []
        for env in envelopes.values():
            n = min(len(env.rms_per_beat), end_b)
            if n <= start_b:
                continue
            segment = env.rms_per_beat[start_b:n]
            if len(segment) == 0:
                continue
            max_rms = env.rms_per_beat.max()
            if max_rms > 0 and np.mean(segment) / max_rms > activity_threshold:
                active.append(env.stem_name)
        return sorted(active)

    @staticmethod
    def _name_section(
        idx: int,
        total_boundaries: int,
        energy_level: str,
        active_stems: list[str],
        start_beat: int,
        total_beats: int,
    ) -> str:
        """Heuristic section naming.

        Strategy:
        - First section -> intro (if energy is low/medium)
        - Last section -> outro (if energy is low/medium)
        - High energy -> chorus
        - Medium energy -> verse
        - Low energy (not first/last) -> bridge
        """
        is_first = (idx == 0)
        is_last = (idx == total_boundaries - 1)

        # Check if section is near the end of the song
        near_end = start_beat > total_beats * 0.85

        if is_first and energy_level in ("low", "medium"):
            return "intro"
        if (is_last or near_end) and energy_level in ("low", "medium"):
            return "outro"
        if energy_level == "high":
            return "chorus"
        if energy_level == "low":
            return "bridge"
        # medium energy, not first/last
        return "verse"

    # ------------------------------------------------------------------
    # Step 5: Merge short sections
    # ------------------------------------------------------------------

    def _merge_short_sections(self, sections: list[Section]) -> list[Section]:
        """Merge consecutive sections that are shorter than *min_section_beats*."""
        if not sections:
            return sections

        merged: list[Section] = [sections[0]]

        for sec in sections[1:]:
            prev = merged[-1]
            # If the previous section is too short, merge into it
            if (prev.end_beat - prev.start_beat) < self.min_section_beats:
                prev.end_beat = sec.end_beat
                prev.end_sec = sec.end_sec
                # Keep the name of the longer / later section
                if (sec.end_beat - sec.start_beat) >= self.min_section_beats:
                    prev.name = sec.name
                    prev.energy_level = sec.energy_level
                # Merge active stems (union)
                for s in sec.active_stems:
                    if s not in prev.active_stems:
                        prev.active_stems.append(s)
                prev.active_stems.sort()
            else:
                merged.append(sec)

        # Final check: merge last section if too short
        if len(merged) >= 2:
            last = merged[-1]
            prev = merged[-2]
            if (last.end_beat - last.start_beat) < self.min_section_beats:
                prev.end_beat = last.end_beat
                prev.end_sec = last.end_sec
                for s in last.active_stems:
                    if s not in prev.active_stems:
                        prev.active_stems.append(s)
                prev.active_stems.sort()
                merged.pop()

        return merged


# ---------------------------------------------------------------------------
# Convenience function
# ---------------------------------------------------------------------------

def extract_arrangement(
    stems: dict[str, np.ndarray],
    sr: int,
    bpm: float,
    **kwargs,
) -> list[Section]:
    """Convenience wrapper around :class:`ArrangementExtractor`."""
    extractor = ArrangementExtractor(**kwargs)
    return extractor.extract(stems, sr, bpm)
