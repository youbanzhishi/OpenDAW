"""
music_theory.py — Music theory primitives for AI composition (Phase 15).

Provides:
    - Scale definitions (Major, Natural Minor, Pentatonic, Blues,
      Dorian, Mixolydian, Harmonic Minor, Melodic Minor)
    - Chord construction (Triads, 7ths, 9ths, Suspended)
    - Key detection (Krumhansl-Schmuckler algorithm)
    - Chord progression library (20+ common progressions)
    - Transposition and modal interchange rules

Usage:
    from vcmix.ai.music_theory import Scale, Chord, ChordProgression, KEY_PROFILES

    scale = Scale("C", "major")
    notes = scale.notes()           # ['C', 'D', 'E', 'F', 'G', 'A', 'B']
    chords = scale.triads()         # [Chord('C'), Chord('Dm'), ...]
    prog = ChordProgression.from_name("pop_1", key="C")
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# ── Note names and MIDI helpers ──────────────────────────────────────────

NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
ENHARMONIC: dict[str, str] = {
    "Db": "C#", "Eb": "D#", "Fb": "E", "Gb": "F#",
    "Ab": "G#", "Bb": "A#", "Cb": "B",
    "E#": "F", "B#": "C",
}

# Semitone intervals from root for each scale type
SCALE_INTERVALS: dict[str, list[int]] = {
    "major":            [0, 2, 4, 5, 7, 9, 11],
    "natural_minor":    [0, 2, 3, 5, 7, 8, 10],
    "harmonic_minor":   [0, 2, 3, 5, 7, 8, 11],
    "melodic_minor":    [0, 2, 3, 5, 7, 9, 11],
    "pentatonic_major": [0, 2, 4, 7, 9],
    "pentatonic_minor": [0, 3, 5, 7, 10],
    "blues":            [0, 3, 5, 6, 7, 10],
    "dorian":           [0, 2, 3, 5, 7, 9, 10],
    "mixolydian":       [0, 2, 4, 5, 7, 9, 10],
    "phrygian":         [0, 1, 3, 5, 7, 8, 10],
    "lydian":           [0, 2, 4, 6, 7, 9, 11],
    "locrian":          [0, 1, 3, 5, 6, 8, 10],
}

# Scale quality mapping for genre defaults
GENRE_SCALE_MAP: dict[str, str] = {
    "pop": "major",
    "rock": "mixolydian",
    "edm": "natural_minor",
    "hiphop": "natural_minor",
    "rnb": "dorian",
    "ballad": "major",
    "lofi": "pentatonic_minor",
    "progressive": "natural_minor",
    "orchestral": "harmonic_minor",
}

# Mood to scale modifier
MOOD_SCALE_MAP: dict[str, str] = {
    "happy": "major",
    "sad": "natural_minor",
    "energetic": "mixolydian",
    "calm": "pentatonic_major",
    "dark": "harmonic_minor",
    "bright": "lydian",
}


def _normalize_note(note: str) -> str:
    """Normalize a note name to sharps-only representation."""
    if note in ENHARMONIC:
        return ENHARMONIC[note]
    return note


def note_to_midi(note: str, octave: int = 4) -> int:
    """Convert note name + octave to MIDI number. C4 = 60."""
    n = _normalize_note(note)
    idx = NOTE_NAMES.index(n)
    return (octave + 1) * 12 + idx


def midi_to_note(midi: int) -> str:
    """Convert MIDI number to note name (no octave)."""
    return NOTE_NAMES[midi % 12]


def midi_to_note_with_octave(midi: int) -> str:
    """Convert MIDI number to note name with octave (e.g. 'C4')."""
    return f"{NOTE_NAMES[midi % 12]}{midi // 12 - 1}"


def semitones_between(a: str, b: str) -> int:
    """Semitone distance from note a to note b (ascending, mod 12)."""
    na = _normalize_note(a)
    nb = _normalize_note(b)
    return (NOTE_NAMES.index(nb) - NOTE_NAMES.index(na)) % 12


# ── Chord quality intervals ─────────────────────────────────────────────

CHORD_QUALITY_INTERVALS: dict[str, list[int]] = {
    "":       [0, 4, 7],          # Major triad
    "m":      [0, 3, 7],          # Minor triad
    "dim":    [0, 3, 6],          # Diminished triad
    "aug":    [0, 4, 8],          # Augmented triad
    "7":      [0, 4, 7, 10],      # Dominant 7th
    "maj7":   [0, 4, 7, 11],      # Major 7th
    "m7":     [0, 3, 7, 10],      # Minor 7th
    "m7b5":   [0, 3, 6, 10],      # Half-diminished
    "dim7":   [0, 3, 6, 9],       # Diminished 7th
    "9":      [0, 4, 7, 10, 14],  # Dominant 9th
    "maj9":   [0, 4, 7, 11, 14],  # Major 9th
    "m9":     [0, 3, 7, 10, 14],  # Minor 9th
    "sus2":   [0, 2, 7],          # Sus2
    "sus4":   [0, 5, 7],          # Sus4
    "7sus4":  [0, 5, 7, 10],      # 7sus4
    "add9":   [0, 4, 7, 14],      # Add9
    "6":      [0, 4, 7, 9],       # Major 6th
    "m6":     [0, 3, 7, 9],       # Minor 6th
}


# ── Scale class ──────────────────────────────────────────────────────────

class Scale:
    """Musical scale built from a root note and scale type.

    Attributes:
        root: Root note name (e.g. 'C', 'A').
        scale_type: Scale type name (e.g. 'major', 'natural_minor').
    """

    def __init__(self, root: str, scale_type: str = "major") -> None:
        self.root = _normalize_note(root)
        self.scale_type = scale_type
        self._intervals = SCALE_INTERVALS.get(scale_type, SCALE_INTERVALS["major"])

    def notes(self) -> list[str]:
        """Return the note names in this scale."""
        root_idx = NOTE_NAMES.index(self.root)
        return [NOTE_NAMES[(root_idx + iv) % 12] for iv in self._intervals]

    def midi_notes(self, octave: int = 4) -> list[int]:
        """Return MIDI note numbers for one octave of this scale."""
        base = note_to_midi(self.root, octave)
        return [base + iv for iv in self._intervals]

    def degree_chord(self, degree: int, quality: str | None = None) -> "Chord":
        """Build a chord on the given scale degree (1-indexed).

        If quality is not specified, it is derived from the scale.
        """
        notes = self.notes()
        idx = (degree - 1) % len(notes)
        root = notes[idx]

        if quality is None:
            quality = self._diatonic_quality(degree)

        return Chord(root, quality)

    def triads(self) -> list["Chord"]:
        """Return all diatonic triads in this scale."""
        return [self.degree_chord(d) for d in range(1, len(self._intervals) + 1)]

    def seventh_chords(self) -> list["Chord"]:
        """Return all diatonic 7th chords in this scale."""
        result: list[Chord] = []
        notes = self.notes()
        for d in range(1, len(self._intervals) + 1):
            root = notes[(d - 1) % len(notes)]
            q7 = self._diatonic_7th_quality(d)
            result.append(Chord(root, q7))
        return result

    def _diatonic_quality(self, degree: int) -> str:
        """Determine diatonic triad quality for a scale degree."""
        if self.scale_type in ("major", "lydian"):
            qualities = ["", "m", "m", "", "", "m", "dim"]
        elif self.scale_type in ("natural_minor", "aeolian", "dorian", "phrygian"):
            # For minor-oriented scales
            if self.scale_type == "dorian":
                qualities = ["m", "m", "", "", "m", "dim", ""]
            elif self.scale_type == "phrygian":
                qualities = ["m", "", "", "m", "dim", "", "m"]
            else:
                qualities = ["m", "dim", "", "m", "m", "", ""]
        elif self.scale_type == "harmonic_minor":
            qualities = ["m", "dim", "aug", "m", "", "", "dim"]
        elif self.scale_type == "mixolydian":
            qualities = ["", "m", "dim", "", "m", "m", ""]
        else:
            # Default to major
            qualities = ["", "m", "m", "", "", "m", "dim"]

        idx = (degree - 1) % len(qualities)
        return qualities[idx]

    def _diatonic_7th_quality(self, degree: int) -> str:
        """Determine diatonic 7th chord quality for a scale degree."""
        if self.scale_type in ("major", "lydian"):
            qualities = ["maj7", "m7", "m7", "maj7", "7", "m7", "m7b5"]
        elif self.scale_type in ("natural_minor",):
            qualities = ["m7", "m7b5", "maj7", "m7", "m7", "maj7", "7"]
        elif self.scale_type == "dorian":
            qualities = ["m7", "m7", "maj7", "7", "m7", "m7b5", "maj7"]
        elif self.scale_type == "mixolydian":
            qualities = ["7", "m7", "m7b5", "maj7", "m7", "m7", "maj7"]
        elif self.scale_type == "harmonic_minor":
            qualities = ["m7b5", "m7b5", "aug7", "m7", "7", "maj7", "dim7"]
        else:
            qualities = ["maj7", "m7", "m7", "maj7", "7", "m7", "m7b5"]

        idx = (degree - 1) % len(qualities)
        return qualities[idx]

    def contains_note(self, note: str) -> bool:
        """Check if a note is in this scale."""
        return _normalize_note(note) in self.notes()

    def __repr__(self) -> str:
        return f"Scale('{self.root} {self.scale_type}')"


# ── Chord class ──────────────────────────────────────────────────────────

class Chord:
    """Musical chord with root note and quality.

    Attributes:
        root: Root note name (e.g. 'C').
        quality: Chord quality suffix (e.g. '', 'm', '7', 'maj7').
    """

    def __init__(self, root: str, quality: str = "") -> None:
        self.root = _normalize_note(root)
        self.quality = quality

    @property
    def name(self) -> str:
        """Full chord name (e.g. 'Cm7')."""
        return f"{self.root}{self.quality}"

    def intervals(self) -> list[int]:
        """Return semitone intervals from root for this chord quality."""
        return CHORD_QUALITY_INTERVALS.get(self.quality, [0, 4, 7])

    def notes(self) -> list[str]:
        """Return note names in this chord."""
        root_idx = NOTE_NAMES.index(self.root)
        return [NOTE_NAMES[(root_idx + iv) % 12] for iv in self.intervals()]

    def midi_notes(self, octave: int = 4) -> list[int]:
        """Return MIDI note numbers for this chord."""
        base = note_to_midi(self.root, octave)
        return [base + iv for iv in self.intervals()]

    def bass_note(self) -> str:
        """Return the root (bass) note name."""
        return self.root

    def is_major(self) -> bool:
        """Check if this is a major-type chord."""
        return self.quality in ("", "7", "maj7", "9", "maj9", "6", "add9", "sus2", "sus4", "7sus4")

    def is_minor(self) -> bool:
        """Check if this is a minor-type chord."""
        return self.quality in ("m", "m7", "m9", "m6", "m7b5")

    def is_dominant(self) -> bool:
        """Check if this is a dominant-type chord."""
        return self.quality in ("7", "9", "7sus4")

    def transpose(self, semitones: int) -> "Chord":
        """Transpose the chord by a number of semitones."""
        root_idx = NOTE_NAMES.index(self.root)
        new_root = NOTE_NAMES[(root_idx + semitones) % 12]
        return Chord(new_root, self.quality)

    def roman_numeral(self, scale: Scale) -> str:
        """Return Roman numeral representation within a scale."""
        scale_notes = scale.notes()
        if self.root not in scale_notes:
            return self.name

        degree = scale_notes.index(self.root) + 1
        roman = ["I", "II", "III", "IV", "V", "VI", "VII"][degree - 1]

        if self.is_minor() or self.quality == "dim":
            roman = roman.lower()

        suffix = self.quality
        if self.quality == "m" or self.quality == "":
            suffix = ""

        return f"{roman}{suffix}"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Chord):
            return NotImplemented
        return self.root == other.root and self.quality == other.quality

    def __hash__(self) -> int:
        return hash((self.root, self.quality))

    def __repr__(self) -> str:
        return f"Chord('{self.name}')"


# ── Chord Progression ───────────────────────────────────────────────────

@dataclass
class ChordProgression:
    """A sequence of chords with metadata.

    Attributes:
        name: Progression name (e.g. 'Pop I-V-vi-IV').
        chords: List of Chord objects.
        genre: Associated genre tag.
        mood: Associated mood tag.
        roman: Roman numeral representation (e.g. 'I-V-vi-IV').
    """

    name: str
    chords: list[Chord] = field(default_factory=list)
    genre: str = "pop"
    mood: str = "happy"
    roman: str = ""

    @classmethod
    def from_name(cls, prog_name: str, key: str = "C") -> "ChordProgression":
        """Look up a progression by name and transpose to the given key."""
        template = PROGRESSION_LIBRARY.get(prog_name)
        if template is None:
            raise ValueError(f"Unknown progression: {prog_name}")

        # Determine transposition
        source_root = template.chords[0].root if template.chords else "C"
        semitones = semitones_between(source_root, _normalize_note(key))

        transposed = [c.transpose(semitones) for c in template.chords]
        return cls(
            name=template.name,
            chords=transposed,
            genre=template.genre,
            mood=template.mood,
            roman=template.roman,
        )

    @classmethod
    def from_roman(cls, roman: str, scale: Scale, genre: str = "pop", mood: str = "happy") -> "ChordProgression":
        """Build a progression from Roman numeral string (e.g. 'I-V-vi-IV')."""
        # Ordered by length (longest first) to avoid prefix matching issues
        # e.g. 'vi' should match before 'V', 'iii' before 'I'
        roman_map_all = [
            ("VII", 7, False), ("vii", 7, True),
            ("VI", 6, False), ("vi", 6, True),
            ("IV", 4, False), ("iv", 4, True),
            ("V", 5, False), ("v", 5, True),
            ("III", 3, False), ("iii", 3, True),
            ("II", 2, False), ("ii", 2, True),
            ("I", 1, False), ("i", 1, True),
        ]

        chords: list[Chord] = []
        tokens = roman.split("-")
        for token in tokens:
            degree = 0
            is_minor = False
            quality = ""

            for prefix, deg, minor_flag in roman_map_all:
                if token.startswith(prefix):
                    degree = deg
                    is_minor = minor_flag
                    rest = token[len(prefix):]
                    if rest:
                        quality = _parse_quality_suffix(rest)
                    elif is_minor:
                        quality = "m"
                    break

            if degree > 0:
                if is_minor and quality == "":
                    quality = "m"
                elif not is_minor and quality == "":
                    quality = ""
                chords.append(scale.degree_chord(degree, quality))

        return cls(
            name=f"Custom {roman}",
            chords=chords,
            genre=genre,
            mood=mood,
            roman=roman,
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict."""
        return {
            "name": self.name,
            "chords": [c.name for c in self.chords],
            "genre": self.genre,
            "mood": self.mood,
            "roman": self.roman,
        }

    def __len__(self) -> int:
        return len(self.chords)

    def __repr__(self) -> str:
        chord_names = " - ".join(c.name for c in self.chords)
        return f"ChordProgression('{self.name}': {chord_names})"


def _parse_quality_suffix(suffix: str) -> str:
    """Parse a chord quality suffix from Roman numeral notation."""
    mapping = {
        "7": "7",
        "maj7": "maj7",
        "m7": "m7",
        "min7": "m7",
        "dim": "dim",
        "dim7": "dim7",
        "aug": "aug",
        "sus2": "sus2",
        "sus4": "sus4",
        "9": "9",
        "add9": "add9",
    }
    return mapping.get(suffix, suffix)


# ── Chord Progression Library (20+ progressions) ────────────────────────

def _make_prog(name: str, roman: str, roots_qualities: list[tuple[str, str]],
               genre: str = "pop", mood: str = "happy") -> ChordProgression:
    """Helper to create a ChordProgression from (root, quality) pairs."""
    return ChordProgression(
        name=name,
        chords=[Chord(r, q) for r, q in roots_qualities],
        genre=genre,
        mood=mood,
        roman=roman,
    )


PROGRESSION_LIBRARY: dict[str, ChordProgression] = {
    # ── Pop progressions ──
    "pop_1": _make_prog("Pop I-V-vi-IV", "I-V-vi-IV",
                        [("C", ""), ("G", ""), ("A", "m"), ("F", "")],
                        genre="pop", mood="happy"),
    "pop_2": _make_prog("Pop I-IV-V-I", "I-IV-V-I",
                        [("C", ""), ("F", ""), ("G", ""), ("C", "")],
                        genre="pop", mood="happy"),
    "pop_3": _make_prog("Pop vi-IV-I-V", "vi-IV-I-V",
                        [("A", "m"), ("F", ""), ("C", ""), ("G", "")],
                        genre="pop", mood="sad"),
    "pop_4": _make_prog("Pop I-vi-IV-V", "I-vi-IV-V",
                        [("C", ""), ("A", "m"), ("F", ""), ("G", "")],
                        genre="pop", mood="happy"),
    "pop_5": _make_prog("Pop I-IV-vi-V", "I-IV-vi-V",
                        [("C", ""), ("F", ""), ("A", "m"), ("G", "")],
                        genre="pop", mood="calm"),

    # ── Rock progressions ──
    "rock_1": _make_prog("Rock I-bVII-IV-I", "I-bVII-IV-I",
                         [("C", ""), ("Bb", ""), ("F", ""), ("C", "")],
                         genre="rock", mood="energetic"),
    "rock_2": _make_prog("Rock I-IV-I-V", "I-IV-I-V",
                         [("C", ""), ("F", ""), ("C", ""), ("G", "")],
                         genre="rock", mood="energetic"),
    "rock_3": _make_prog("Rock I-V-IV-I", "I-V-IV-I",
                         [("C", ""), ("G", ""), ("F", ""), ("C", "")],
                         genre="rock", mood="energetic"),

    # ── EDM progressions ──
    "edm_1": _make_prog("EDM i-VI-VII-i", "i-VI-VII-i",
                        [("A", "m"), ("F", ""), ("G", ""), ("A", "m")],
                        genre="edm", mood="dark"),
    "edm_2": _make_prog("EDM i-III-VII-VI", "i-III-VII-VI",
                        [("A", "m"), ("C", ""), ("G", ""), ("F", "")],
                        genre="edm", mood="energetic"),
    "edm_3": _make_prog("EDM i-iv-VII-VI", "i-iv-VII-VI",
                        [("A", "m"), ("D", "m"), ("G", ""), ("F", "")],
                        genre="edm", mood="dark"),

    # ── Hip-Hop progressions ──
    "hiphop_1": _make_prog("Hip-Hop i-iv-V-i", "i-iv-V-i",
                           [("A", "m"), ("D", "m"), ("E", ""), ("A", "m")],
                           genre="hiphop", mood="dark"),
    "hiphop_2": _make_prog("Hip-Hop i-VI-VII-i", "i-VI-VII-i",
                           [("A", "m"), ("F", ""), ("G", ""), ("A", "m")],
                           genre="hiphop", mood="calm"),
    "hiphop_3": _make_prog("Hip-Hop i-iv-i-VII", "i-iv-i-VII",
                           [("A", "m"), ("D", "m"), ("A", "m"), ("G", "")],
                           genre="hiphop", mood="dark"),

    # ── R&B progressions ──
    "rnb_1": _make_prog("R&B Imaj7-IVmaj7-vii7-iii7", "Imaj7-IVmaj7-vii7-iii7",
                        [("C", "maj7"), ("F", "maj7"), ("B", "m7b5"), ("E", "m7")],
                        genre="rnb", mood="calm"),
    "rnb_2": _make_prog("R&B i7-iv7-VII7-III7", "i7-iv7-VII7-III7",
                        [("A", "m7"), ("D", "m7"), ("G", "7"), ("C", "")],
                        genre="rnb", mood="calm"),
    "rnb_3": _make_prog("R&B vi7-II7-V7-I7", "vi7-II7-V7-I7",
                        [("A", "m7"), ("D", "7"), ("G", "7"), ("C", "maj7")],
                        genre="rnb", mood="bright"),

    # ── Ballad progressions ──
    "ballad_1": _make_prog("Ballad I-iii-IV-V", "I-iii-IV-V",
                           [("C", ""), ("E", "m"), ("F", ""), ("G", "")],
                           genre="ballad", mood="sad"),
    "ballad_2": _make_prog("Ballad I-vi-ii-V", "I-vi-ii-V",
                           [("C", ""), ("A", "m"), ("D", "m"), ("G", "")],
                           genre="ballad", mood="calm"),

    # ── Jazz-influenced ──
    "jazz_1": _make_prog("Jazz ii-V-I-vi", "ii-V-I-vi",
                         [("D", "m7"), ("G", "7"), ("C", "maj7"), ("A", "m7")],
                         genre="rnb", mood="calm"),
    "jazz_2": _make_prog("Jazz I-vi-ii-V", "I-vi-ii-V",
                         [("C", "maj7"), ("A", "m7"), ("D", "m7"), ("G", "7")],
                         genre="rnb", mood="bright"),

    # ── Blues ──
    "blues_1": _make_prog("Blues I7-IV7-I7-V7", "I7-IV7-I7-V7",
                          [("C", "7"), ("F", "7"), ("C", "7"), ("G", "7")],
                          genre="rock", mood="energetic"),
}


# ── Key Detection (Krumhansl-Schmuckler) ─────────────────────────────────

# K-S key profiles (correlation coefficients for each pitch class)
KS_MAJOR_PROFILE = [6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88]
KS_MINOR_PROFILE = [6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17]


def detect_key(chroma: list[float]) -> tuple[str, str, float]:
    """Detect musical key from a chroma histogram using K-S algorithm.

    Args:
        chroma: 12-element chroma histogram (energy per pitch class).

    Returns:
        Tuple of (root_note, scale_type, confidence).
        e.g. ('C', 'major', 0.85)
    """
    if len(chroma) != 12:
        raise ValueError("Chroma histogram must have 12 elements")

    total = sum(chroma)
    if total < 1e-10:
        return ("C", "major", 0.0)

    normalized = [c / total for c in chroma]

    best_key = "C"
    best_type = "major"
    best_corr = -2.0

    for shift in range(12):
        # Rotate chroma
        rotated = normalized[shift:] + normalized[:shift]

        # Correlate with major profile
        corr_major = _pearson_correlation(rotated, KS_MAJOR_PROFILE)
        if corr_major > best_corr:
            best_corr = corr_major
            best_key = NOTE_NAMES[shift]
            best_type = "major"

        # Correlate with minor profile
        corr_minor = _pearson_correlation(rotated, KS_MINOR_PROFILE)
        if corr_minor > best_corr:
            best_corr = corr_minor
            best_key = NOTE_NAMES[shift]
            best_type = "natural_minor"

    return (best_key, best_type, round(max(0.0, best_corr), 4))


def _pearson_correlation(x: list[float], y: list[float]) -> float:
    """Compute Pearson correlation coefficient between two lists."""
    n = len(x)
    if n == 0:
        return 0.0

    mean_x = sum(x) / n
    mean_y = sum(y) / n

    num = sum((xi - mean_x) * (yi - mean_y) for xi, yi in zip(x, y))
    den_x = sum((xi - mean_x) ** 2 for xi in x) ** 0.5
    den_y = sum((yi - mean_y) ** 2 for yi in y) ** 0.5

    if den_x < 1e-10 or den_y < 1e-10:
        return 0.0

    return num / (den_x * den_y)


# ── Transposition ───────────────────────────────────────────────────────

def transpose_progression(progression: ChordProgression, target_key: str) -> ChordProgression:
    """Transpose a chord progression to a target key.

    Args:
        progression: Source chord progression.
        target_key: Target root note.

    Returns:
        New ChordProgression transposed to the target key.
    """
    if not progression.chords:
        return progression

    source_root = progression.chords[0].root
    semitones = semitones_between(source_root, _normalize_note(target_key))

    return ChordProgression(
        name=progression.name,
        chords=[c.transpose(semitones) for c in progression.chords],
        genre=progression.genre,
        mood=progression.mood,
        roman=progression.roman,
    )


# ── Modal interchange suggestions ────────────────────────────────────────

def modal_interchange_chords(key: str, scale_type: str) -> list[Chord]:
    """Return borrowed chords available via modal interchange.

    For major keys, returns chords from the parallel minor and vice versa.
    Also includes common borrowed chords from other modes.

    Args:
        key: Root note.
        scale_type: 'major' or 'natural_minor'.

    Returns:
        List of borrowed Chord objects.
    """
    root = _normalize_note(key)
    root_idx = NOTE_NAMES.index(root)
    borrowed: list[Chord] = []

    if scale_type in ("major", "lydian", "mixolydian"):
        # From parallel minor
        minor_scale = Scale(root, "natural_minor")
        for chord in minor_scale.triads():
            if chord.root not in [c.root for c in Scale(root, "major").triads()]:
                borrowed.append(chord)
    else:
        # From parallel major
        major_scale = Scale(root, "major")
        for chord in major_scale.triads():
            if chord.root not in [c.root for c in Scale(root, "natural_minor").triads()]:
                borrowed.append(chord)

    # Common borrowed chords regardless of mode
    # bVI (from minor in major, or from major in minor context)
    bvi_root = NOTE_NAMES[(root_idx + 8) % 12]  # bVI
    borrowed.append(Chord(bvi_root, ""))

    # bVII
    bvii_root = NOTE_NAMES[(root_idx + 10) % 12]  # bVII
    borrowed.append(Chord(bvii_root, ""))

    return borrowed


# ── Convenience lookup ───────────────────────────────────────────────────

def list_progressions(genre: str | None = None, mood: str | None = None) -> list[str]:
    """List progression names, optionally filtered by genre and/or mood."""
    results: list[str] = []
    for name, prog in PROGRESSION_LIBRARY.items():
        if genre and prog.genre != genre:
            continue
        if mood and prog.mood != mood:
            continue
        results.append(name)
    return sorted(results)


def get_progression(name: str) -> ChordProgression | None:
    """Get a chord progression by name."""
    return PROGRESSION_LIBRARY.get(name)
