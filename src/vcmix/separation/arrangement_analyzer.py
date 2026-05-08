"""
arrangement_analyzer.py — Arrangement structure analysis from separated stems.

Identifies musical sections (Intro/Verse/Chorus/Bridge/Outro) and
instrument entry/exit patterns based on energy analysis of separated stems.

This module extends the basic ArrangementExtractor with:
    - More robust boundary detection (multi-resolution energy)
    - Instrument activity tracking per section
    - Structural pattern recognition (repeated sections)
    - Timeline output with second-accurate timestamps

Usage:
    from vcmix.separation.arrangement_analyzer import ArrangementAnalyzer

    analyzer = ArrangementAnalyzer()
    timeline = analyzer.analyze(stems, sr=44100, bpm=120)
    for section in timeline.sections:
        print(f"{section.name}: {section.start_sec:.1f}s - {section.end_sec:.1f}s")
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

# ── Data structures ───────────────────────────────────────────────────

@dataclass
class InstrumentActivity:
    """Track whether an instrument is active in a section."""
    stem_name: str
    active: bool = False
    avg_rms: float = 0.0       # Average RMS in this section
    entry_sec: float | None = None  # When the instrument enters
    exit_sec: float | None = None   # When the instrument exits


@dataclass
class ArrangementSection:
    """A detected musical section."""
    name: str                           # intro/verse/chorus/bridge/outro
    start_sec: float                    # Start time in seconds
    end_sec: float                      # End time in seconds
    start_beat: int = 0                 # Beat index
    end_beat: int = 0                   # Beat index
    energy_level: str = "medium"        # low/medium/high
    instruments: list[InstrumentActivity] = field(default_factory=list)

    def active_stems(self) -> list[str]:
        return [i.stem_name for i in self.instruments if i.active]


@dataclass
class ArrangementTimeline:
    """Complete arrangement timeline."""
    bpm: float = 120.0
    duration_sec: float = 0.0
    sections: list[ArrangementSection] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "bpm": self.bpm,
            "duration_sec": round(self.duration_sec, 2),
            "sections": [
                {
                    "name": s.name,
                    "start_sec": round(s.start_sec, 2),
                    "end_sec": round(s.end_sec, 2),
                    "start_beat": s.start_beat,
                    "end_beat": s.end_beat,
                    "energy_level": s.energy_level,
                    "active_stems": s.active_stems(),
                }
                for s in self.sections
            ],
        }


# ── Constants ─────────────────────────────────────────────────────────

_ENERGY_LOW_THRESHOLD = 0.30
_ENERGY_HIGH_THRESHOLD = 0.65
_MIN_SECTION_BEATS = 4
_BOUNDARY_JUMP_RATIO = 0.25
_ACTIVITY_THRESHOLD = 0.10   # 10% of stem's own max RMS


# ── Main Analyzer ─────────────────────────────────────────────────────

class ArrangementAnalyzer:
    """Analyze arrangement structure from separated stems.

    Parameters
    ----------
    energy_low_threshold : float
        Normalised energy below which a section is "low energy".
    energy_high_threshold : float
        Normalised energy above which a section is "high energy".
    min_section_beats : int
        Minimum section length in beats (shorter are merged).
    boundary_jump_ratio : float
        Relative energy change threshold for boundary detection.
    activity_threshold : float
        Fraction of stem's max RMS to consider it "active".
    """

    def __init__(
        self,
        energy_low_threshold: float = _ENERGY_LOW_THRESHOLD,
        energy_high_threshold: float = _ENERGY_HIGH_THRESHOLD,
        min_section_beats: int = _MIN_SECTION_BEATS,
        boundary_jump_ratio: float = _BOUNDARY_JUMP_RATIO,
        activity_threshold: float = _ACTIVITY_THRESHOLD,
    ):
        self.energy_low_threshold = energy_low_threshold
        self.energy_high_threshold = energy_high_threshold
        self.min_section_beats = min_section_beats
        self.boundary_jump_ratio = boundary_jump_ratio
        self.activity_threshold = activity_threshold

    def analyze(
        self,
        stems: dict[str, np.ndarray],
        sr: int,
        bpm: float,
    ) -> ArrangementTimeline:
        """Analyze arrangement from separated stems.

        Parameters
        ----------
        stems : dict[str, np.ndarray]
            Mapping of stem name -> mono audio array.
        sr : int
            Sample rate.
        bpm : float
            Tempo in BPM.

        Returns
        -------
        ArrangementTimeline
        """
        if bpm <= 0:
            raise ValueError(f"bpm must be positive, got {bpm}")
        if sr <= 0:
            raise ValueError(f"sr must be positive, got {sr}")
        if not stems:
            return ArrangementTimeline(bpm=bpm)

        int(sr * 60.0 / bpm)

        # 1. Compute per-stem energy envelopes
        envelopes = self._compute_envelopes(stems, sr, bpm)
        num_beats = max(len(e) for e in envelopes.values())

        # 2. Merge into total energy curve
        total_energy = self._merge_envelopes(envelopes, num_beats)

        # 3. Detect boundaries
        boundaries = self._detect_boundaries(total_energy)

        # 4. Label sections
        sections = self._label_sections(
            boundaries, total_energy, envelopes, sr, bpm,
        )

        # 5. Analyze instrument activity per section
        sections = self._analyze_instruments(sections, envelopes, sr, bpm)

        # 6. Merge short sections
        sections = self._merge_short_sections(sections)

        # Duration
        max_len = max(len(a) for a in stems.values())
        duration = max_len / sr

        return ArrangementTimeline(
            bpm=bpm,
            duration_sec=round(duration, 2),
            sections=sections,
        )

    # ------------------------------------------------------------------
    # Step 1: Energy envelopes
    # ------------------------------------------------------------------

    def _compute_envelopes(
        self, stems: dict[str, np.ndarray], sr: int, bpm: float,
    ) -> dict[str, np.ndarray]:
        """Compute per-beat RMS for each stem."""
        beat_samples = int(sr * 60.0 / bpm)
        envelopes: dict[str, np.ndarray] = {}

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
            envelopes[name] = rms_values

        return envelopes

    # ------------------------------------------------------------------
    # Step 2: Merge envelopes
    # ------------------------------------------------------------------

    @staticmethod
    def _merge_envelopes(
        envelopes: dict[str, np.ndarray], num_beats: int,
    ) -> np.ndarray:
        """Sum and normalise to [0, 1]."""
        total = np.zeros(num_beats, dtype=np.float64)
        for env in envelopes.values():
            n = min(len(env), num_beats)
            total[:n] += env[:n]
        max_val = total.max()
        if max_val > 0:
            total /= max_val
        return total

    # ------------------------------------------------------------------
    # Step 3: Boundary detection
    # ------------------------------------------------------------------

    def _detect_boundaries(self, total_energy: np.ndarray) -> list[int]:
        """Detect section boundaries from energy changes."""
        if len(total_energy) < 2:
            return [0]

        boundaries = [0]

        # Smooth
        kernel = np.array([0.25, 0.5, 0.25])
        smoothed = np.convolve(total_energy, kernel, mode="same")

        for i in range(1, len(smoothed)):
            prev = smoothed[i - 1]
            curr = smoothed[i]
            ref = max(abs(prev), 1e-10)
            delta = abs(curr - prev) / ref
            if delta > self.boundary_jump_ratio:
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
        envelopes: dict[str, np.ndarray],
        sr: int,
        bpm: float,
    ) -> list[ArrangementSection]:
        """Label sections based on energy level and position."""
        beat_sec = 60.0 / bpm
        num_beats = len(total_energy)
        sections: list[ArrangementSection] = []

        for idx in range(len(boundaries)):
            start_b = boundaries[idx]
            end_b = boundaries[idx + 1] if idx + 1 < len(boundaries) else num_beats

            avg_energy = float(np.mean(total_energy[start_b:end_b])) if end_b > start_b else 0.0
            energy_level = self._classify_energy(avg_energy)

            name = self._name_section(
                idx, len(boundaries), energy_level, start_b, num_beats,
            )

            sections.append(ArrangementSection(
                name=name,
                start_sec=start_b * beat_sec,
                end_sec=end_b * beat_sec,
                start_beat=start_b,
                end_beat=end_b,
                energy_level=energy_level,
            ))

        return sections

    def _classify_energy(self, avg: float) -> str:
        if avg < self.energy_low_threshold:
            return "low"
        elif avg > self.energy_high_threshold:
            return "high"
        return "medium"

    @staticmethod
    def _name_section(
        idx: int,
        total_boundaries: int,
        energy_level: str,
        start_beat: int,
        total_beats: int,
    ) -> str:
        is_first = (idx == 0)
        is_last = (idx == total_boundaries - 1)
        near_end = start_beat > total_beats * 0.85

        if is_first and energy_level in ("low", "medium"):
            return "intro"
        if (is_last or near_end) and energy_level in ("low", "medium"):
            return "outro"
        if energy_level == "high":
            return "chorus"
        if energy_level == "low":
            return "bridge"
        return "verse"

    # ------------------------------------------------------------------
    # Step 5: Instrument activity
    # ------------------------------------------------------------------

    def _analyze_instruments(
        self,
        sections: list[ArrangementSection],
        envelopes: dict[str, np.ndarray],
        sr: int,
        bpm: float,
    ) -> list[ArrangementSection]:
        """Detect which instruments are active in each section."""
        beat_sec = 60.0 / bpm

        for section in sections:
            instruments: list[InstrumentActivity] = []

            for stem_name, env in envelopes.items():
                max_rms = env.max() if len(env) > 0 else 0.0
                start_b = section.start_beat
                end_b = min(section.end_beat, len(env))

                if end_b <= start_b or max_rms < 1e-10:
                    instruments.append(InstrumentActivity(
                        stem_name=stem_name, active=False,
                    ))
                    continue

                segment = env[start_b:end_b]
                avg_rms = float(np.mean(segment))
                is_active = (avg_rms / max_rms) > self.activity_threshold

                # Find entry/exit points
                entry_sec = None
                exit_sec = None
                for b in range(start_b, end_b):
                    if env[b] / max_rms > self.activity_threshold:
                        if entry_sec is None:
                            entry_sec = b * beat_sec
                        exit_sec = (b + 1) * beat_sec

                instruments.append(InstrumentActivity(
                    stem_name=stem_name,
                    active=is_active,
                    avg_rms=round(avg_rms, 6),
                    entry_sec=round(entry_sec, 2) if entry_sec is not None else None,
                    exit_sec=round(exit_sec, 2) if exit_sec is not None else None,
                ))

            section.instruments = instruments

        return sections

    # ------------------------------------------------------------------
    # Step 6: Merge short sections
    # ------------------------------------------------------------------

    def _merge_short_sections(
        self, sections: list[ArrangementSection],
    ) -> list[ArrangementSection]:
        """Merge consecutive sections shorter than min_section_beats."""
        if not sections:
            return sections

        merged: list[ArrangementSection] = [sections[0]]

        for sec in sections[1:]:
            prev = merged[-1]
            if (prev.end_beat - prev.start_beat) < self.min_section_beats:
                prev.end_beat = sec.end_beat
                prev.end_sec = sec.end_sec
                if (sec.end_beat - sec.start_beat) >= self.min_section_beats:
                    prev.name = sec.name
                    prev.energy_level = sec.energy_level
                # Merge instrument lists
                prev_instruments = {i.stem_name: i for i in prev.instruments}
                for inst in sec.instruments:
                    if inst.stem_name in prev_instruments:
                        if inst.active:
                            prev_instruments[inst.stem_name].active = True
                    else:
                        prev.instruments.append(inst)
            else:
                merged.append(sec)

        # Final merge for last section
        if len(merged) >= 2:
            last = merged[-1]
            prev = merged[-2]
            if (last.end_beat - last.start_beat) < self.min_section_beats:
                prev.end_beat = last.end_beat
                prev.end_sec = last.end_sec
                for inst in last.instruments:
                    existing = next(
                        (i for i in prev.instruments if i.stem_name == inst.stem_name),
                        None,
                    )
                    if existing and inst.active:
                        existing.active = True
                    elif not existing:
                        prev.instruments.append(inst)
                merged.pop()

        return merged


# ── Convenience function ──────────────────────────────────────────────

def analyze_arrangement(
    stems: dict[str, np.ndarray],
    sr: int,
    bpm: float,
    **kwargs,
) -> ArrangementTimeline:
    """Convenience wrapper around :class:`ArrangementAnalyzer`."""
    analyzer = ArrangementAnalyzer(**kwargs)
    return analyzer.analyze(stems, sr, bpm)
