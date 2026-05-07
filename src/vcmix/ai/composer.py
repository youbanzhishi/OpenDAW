"""
composer.py — AI composition engine for VCMix (Phase 15).

Generates complete VCMix project configurations from musical parameters:
genre, duration, BPM, key, mood, and optional reference track.

Composition pipeline:
    1. Select arrangement template based on genre/duration
    2. Generate chord progression based on key/genre/sections
    3. Generate melody based on key/scale/rhythm
    4. Generate drum pattern based on genre/BPM
    5. Generate bass line based on chord progression/genre
    6. Assign instruments based on genre/template
    7. Assemble into VCMix project configuration

Usage:
    from vcmix.ai.composer import AIComposer
    composer = AIComposer()
    project = composer.compose(
        genre="pop", duration=180, bpm=120,
        key="C", mood="happy"
    )
"""

from __future__ import annotations

import random
import time
from dataclasses import dataclass, field
from typing import Any

from vcmix.ai.music_theory import (
    GENRE_SCALE_MAP,
    MOOD_SCALE_MAP,
    NOTE_NAMES,
    Scale,
    Chord,
    ChordProgression,
    PROGRESSION_LIBRARY,
    list_progressions,
    transpose_progression,
    _normalize_note,
    note_to_midi,
)
from vcmix.arrangement.templates import (
    ArrangementTemplate,
    TEMPLATE_REGISTRY,
    get_template,
    list_templates_by_genre,
)


# ── Drum pattern definitions ────────────────────────────────────────────

# Patterns expressed as hit positions in a 16-step grid (1 bar of 4/4)
DRUM_PATTERNS: dict[str, dict[str, list[int]]] = {
    "pop": {
        "kick":  [1, 0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0],
        "snare": [0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0],
        "hihat": [1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0],
    },
    "rock": {
        "kick":  [1, 0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0],
        "snare": [0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0],
        "ride":  [1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0],
    },
    "edm": {
        "kick":  [1, 0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 0],
        "clap":  [0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0],
        "hihat": [0, 0, 1, 0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 0, 1, 0],
    },
    "hiphop": {
        "kick":  [1, 0, 0, 1, 0, 0, 1, 0, 0, 0, 1, 0, 0, 0, 0, 0],
        "snare": [0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0],
        "hihat": [1, 1, 0, 1, 1, 0, 1, 0, 1, 1, 0, 1, 1, 0, 1, 0],
    },
    "rnb": {
        "kick":  [1, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 1, 0, 0, 0],
        "snare": [0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 1],
        "hihat": [1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0],
    },
    "ballad": {
        "kick":  [1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
        "snare": [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0],
        "hihat": [1, 0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 0],
    },
    "lofi": {
        "kick":  [1, 0, 0, 0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 0, 0, 0],
        "snare": [0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0],
        "hihat": [1, 0, 1, 0, 0, 0, 1, 0, 1, 0, 0, 0, 1, 0, 1, 0],
    },
}

# Instrument assignments per genre
GENRE_INSTRUMENTS: dict[str, dict[str, dict[str, Any]]] = {
    "pop": {
        "piano":   {"type": "midi", "instrument": "Grand Piano", "volume": 0.7},
        "guitar":  {"type": "audio", "instrument": "Acoustic Guitar", "volume": 0.6},
        "bass":    {"type": "midi", "instrument": "Bass", "volume": 0.8},
        "drums":   {"type": "sampler", "instrument": "Drum Kit", "volume": 0.75},
        "strings": {"type": "midi", "instrument": "Strings", "volume": 0.5},
        "synth":   {"type": "midi", "instrument": "Synth Pad", "volume": 0.4},
    },
    "rock": {
        "guitar":  {"type": "audio", "instrument": "Electric Guitar", "volume": 0.8},
        "bass":    {"type": "midi", "instrument": "Bass", "volume": 0.75},
        "drums":   {"type": "sampler", "instrument": "Drum Kit", "volume": 0.8},
        "keys":    {"type": "midi", "instrument": "Organ", "volume": 0.5},
    },
    "edm": {
        "supersaw": {"type": "midi", "instrument": "SuperSaw Lead", "volume": 0.7},
        "plucks":   {"type": "midi", "instrument": "Pluck Synth", "volume": 0.5},
        "bass":     {"type": "midi", "instrument": "Sub Bass", "volume": 0.85},
        "drums":    {"type": "sampler", "instrument": "EDM Kit", "volume": 0.8},
        "fx":       {"type": "audio", "instrument": "FX", "volume": 0.4},
        "pad":      {"type": "midi", "instrument": "Ambient Pad", "volume": 0.45},
    },
    "hiphop": {
        "808":    {"type": "sampler", "instrument": "808 Bass", "volume": 0.85},
        "drums":  {"type": "sampler", "instrument": "Trap Kit", "volume": 0.8},
        "keys":   {"type": "midi", "instrument": "Rhodes", "volume": 0.5},
        "pluck":  {"type": "midi", "instrument": "Pluck Synth", "volume": 0.55},
        "pad":    {"type": "midi", "instrument": "Dark Pad", "volume": 0.4},
    },
    "rnb": {
        "rhodes":  {"type": "midi", "instrument": "Rhodes", "volume": 0.7},
        "bass":    {"type": "midi", "instrument": "Bass", "volume": 0.75},
        "drums":   {"type": "sampler", "instrument": "Light Kit", "volume": 0.65},
        "strings": {"type": "midi", "instrument": "Strings", "volume": 0.45},
        "guitar":  {"type": "audio", "instrument": "Clean Guitar", "volume": 0.5},
    },
    "ballad": {
        "piano":   {"type": "midi", "instrument": "Grand Piano", "volume": 0.75},
        "strings": {"type": "midi", "instrument": "Strings", "volume": 0.5},
        "bass":    {"type": "midi", "instrument": "Bass", "volume": 0.65},
        "drums":   {"type": "sampler", "instrument": "Brush Kit", "volume": 0.5},
    },
    "lofi": {
        "keys":   {"type": "midi", "instrument": "Lo-fi Keys", "volume": 0.65},
        "bass":   {"type": "midi", "instrument": "Lo-fi Bass", "volume": 0.6},
        "drums":  {"type": "sampler", "instrument": "Lo-fi Kit", "volume": 0.55},
        "guitar": {"type": "audio", "instrument": "Lo-fi Guitar", "volume": 0.5},
    },
}


@dataclass
class CompositionResult:
    """Result of AI composition.

    Attributes:
        project_config: Complete VCMix project configuration dict.
        genre: Used genre.
        key: Used musical key.
        bpm: Used BPM.
        scale: Used scale type.
        sections: Number of sections.
        total_bars: Total number of bars.
        chord_progression: Chord progression used.
        instruments: Instrument assignments.
        composition_time_sec: Time taken to compose.
    """

    project_config: dict[str, Any]
    genre: str = ""
    key: str = ""
    bpm: float = 120.0
    scale: str = ""
    sections: int = 0
    total_bars: int = 0
    chord_progression: ChordProgression | None = None
    instruments: dict[str, Any] = field(default_factory=dict)
    composition_time_sec: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict."""
        return {
            "project_config": self.project_config,
            "genre": self.genre,
            "key": self.key,
            "bpm": self.bpm,
            "scale": self.scale,
            "sections": self.sections,
            "total_bars": self.total_bars,
            "chord_progression": self.chord_progression.to_dict() if self.chord_progression else None,
            "instruments": self.instruments,
            "composition_time_sec": round(self.composition_time_sec, 3),
        }


class AIComposer:
    """AI composition engine.

    Generates complete VCMix project configurations from musical parameters.
    Supports 6 genres: pop, rock, edm, hiphop, rnb, ballad.
    Also handles: lofi, progressive, orchestral via template fallback.
    """

    SUPPORTED_GENRES = ["pop", "rock", "edm", "hiphop", "rnb", "ballad", "lofi", "progressive", "orchestral"]
    SUPPORTED_MOODS = ["happy", "sad", "energetic", "calm", "dark", "bright"]

    def compose(
        self,
        genre: str,
        duration: float,
        bpm: float,
        key: str,
        mood: str,
        reference: str | None = None,
    ) -> CompositionResult:
        """
        Generate a complete VCMix project configuration.

        Args:
            genre: Musical genre (pop/rock/edm/hiphop/rnb/ballad).
            duration: Target duration in seconds.
            bpm: Tempo in beats per minute.
            key: Musical key (e.g. 'C', 'Am', 'D Major').
            mood: Mood (happy/sad/energetic/calm/dark/bright).
            reference: Optional reference track path for analysis.

        Returns:
            CompositionResult with full project configuration.
        """
        start_time = time.time()

        # Normalize inputs
        genre = genre.lower().strip()
        mood = mood.lower().strip()
        key_root, scale_type = self._parse_key(key)

        # Determine scale from mood + genre
        effective_scale = self._determine_scale(genre, mood, scale_type)

        # 1. Select arrangement template
        template = self._select_template(genre, duration)

        # 2. Generate chord progression
        progression = self._generate_chord_progression(key_root, genre, mood, template)

        # 3. Generate melody
        scale = Scale(key_root, effective_scale)
        melody = self._generate_melody(key_root, effective_scale, bpm, template)

        # 4. Generate drum pattern
        drum_pattern = self._generate_drum_pattern(genre, bpm)

        # 5. Generate bass line
        bass_line = self._generate_bass_line(progression, genre, bpm)

        # 6. Assign instruments
        instruments = self._assign_instruments(genre, template)

        # 7. Assemble project config
        project_config = self._assemble_project(
            genre=genre,
            key=key_root,
            scale=effective_scale,
            bpm=bpm,
            duration=duration,
            template=template,
            progression=progression,
            melody=melody,
            drum_pattern=drum_pattern,
            bass_line=bass_line,
            instruments=instruments,
            mood=mood,
        )

        elapsed = time.time() - start_time

        return CompositionResult(
            project_config=project_config,
            genre=genre,
            key=key_root,
            bpm=bpm,
            scale=effective_scale,
            sections=len(template.structure),
            total_bars=template.total_bars,
            chord_progression=progression,
            instruments=instruments,
            composition_time_sec=elapsed,
        )

    def _parse_key(self, key: str) -> tuple[str, str]:
        """Parse a key string into (root_note, scale_type).

        Examples:
            'C' → ('C', 'major')
            'Am' → ('A', 'natural_minor')
            'D Major' → ('D', 'major')
            'F# Minor' → ('F#', 'natural_minor')
        """
        key = key.strip()

        # Check for explicit scale type
        parts = key.split()
        if len(parts) >= 2:
            root = _normalize_note(parts[0])
            scale_word = parts[1].lower()
            if "minor" in scale_word or scale_word == "m":
                return (root, "natural_minor")
            return (root, "major")

        # Check for 'm' suffix (e.g. 'Am')
        if key.endswith("m") and len(key) > 1:
            root = _normalize_note(key[:-1])
            return (root, "natural_minor")

        # Default to major
        root = _normalize_note(key)
        return (root, "major")

    def _determine_scale(self, genre: str, mood: str, parsed_scale: str) -> str:
        """Determine the effective scale type from genre, mood, and parsed key."""
        # Mood takes precedence
        if mood in MOOD_SCALE_MAP:
            return MOOD_SCALE_MAP[mood]

        # Then genre default
        if genre in GENRE_SCALE_MAP:
            return GENRE_SCALE_MAP[genre]

        # Then parsed key
        return parsed_scale

    def _select_template(self, genre: str, duration: float) -> ArrangementTemplate:
        """Select an arrangement template based on genre and duration."""
        # Try genre-specific templates
        genre_templates = list_templates_by_genre(genre)
        if genre_templates:
            # Pick the first (most representative)
            return TEMPLATE_REGISTRY[genre_templates[0]]

        # Fallback: try partial match
        for key, tmpl in TEMPLATE_REGISTRY.items():
            if genre in tmpl.genre or tmpl.genre in genre:
                return tmpl

        # Default to pop
        return TEMPLATE_REGISTRY["pop-standard"]

    def _generate_chord_progression(
        self, key: str, genre: str, mood: str, template: ArrangementTemplate
    ) -> ChordProgression:
        """Generate chord progression based on key, genre, and mood."""
        # Try to find matching progression
        progs = list_progressions(genre=genre, mood=mood)
        if not progs:
            progs = list_progressions(genre=genre)
        if not progs:
            progs = list_progressions(mood=mood)
        if not progs:
            progs = list_progressions()

        if progs:
            # Pick the first matching progression
            prog_name = progs[0]
            return ChordProgression.from_name(prog_name, key=key)

        # Fallback: simple I-IV-V-I
        scale = Scale(key, "major")
        return ChordProgression.from_roman("I-IV-V-I", scale, genre=genre, mood=mood)

    def _generate_melody(
        self, key: str, scale_type: str, bpm: float, template: ArrangementTemplate
    ) -> list[dict[str, Any]]:
        """Generate melody line as a list of note events.

        Each note event: {'note': str, 'midi': int, 'start_beat': float,
                          'duration_beats': float, 'velocity': int}
        """
        scale = Scale(key, scale_type)
        scale_midi = scale.midi_notes(octave=4)
        # Extend range
        scale_midi_high = scale.midi_notes(octave=5)

        all_notes = scale_midi + scale_midi_high
        rng = random.Random(hash(key) + int(bpm))

        melody: list[dict[str, Any]] = []
        beat = 0.0
        total_beats = template.total_bars * 4

        # Rhythm patterns for melody (in beat subdivisions)
        rhythm_patterns = [
            [1.0, 1.0, 1.0, 1.0],          # Quarter notes
            [0.5, 0.5, 1.0, 1.0],          # Eighth + quarter
            [1.0, 0.5, 0.5, 1.0],          # Quarter + eighth
            [2.0, 1.0, 1.0],               # Half + quarters
            [1.0, 1.0, 2.0],               # Quarters + half
            [0.5, 0.5, 0.5, 0.5, 1.0, 1.0],  # Eighth run
        ]

        current_idx = len(scale_midi) // 2  # Start in middle of first octave

        while beat < total_beats:
            pattern = rng.choice(rhythm_patterns)
            for dur in pattern:
                if beat >= total_beats:
                    break

                # Stepwise motion with occasional small leaps
                step = rng.choices([-2, -1, 0, 1, 2], weights=[1, 3, 2, 3, 1])[0]
                current_idx = max(0, min(len(all_notes) - 1, current_idx + step))

                # Avoid big jumps: clamp to within 3 steps of previous
                midi_note = all_notes[current_idx]
                note_name = NOTE_NAMES[midi_note % 12]

                melody.append({
                    "note": note_name,
                    "midi": midi_note,
                    "start_beat": round(beat, 4),
                    "duration_beats": round(dur, 4),
                    "velocity": rng.randint(70, 100),
                })
                beat += dur

        return melody

    def _generate_drum_pattern(self, genre: str, bpm: float) -> dict[str, Any]:
        """Generate drum pattern based on genre and BPM."""
        # Get base pattern for genre
        base = DRUM_PATTERNS.get(genre, DRUM_PATTERNS["pop"])

        # Create a pattern object with metadata
        pattern: dict[str, Any] = {
            "genre": genre,
            "bpm": bpm,
            "steps": 16,
            "tracks": {},
        }

        for drum_name, hits in base.items():
            pattern["tracks"][drum_name] = {
                "hits": hits,
                "velocity": 90 if drum_name in ("kick", "snare") else 70,
            }

        return pattern

    def _generate_bass_line(
        self, progression: ChordProgression, genre: str, bpm: float
    ) -> list[dict[str, Any]]:
        """Generate bass line based on chord progression and genre.

        Returns list of bass note events.
        """
        rng = random.Random(hash(genre) + int(bpm))
        bass: list[dict[str, Any]] = []

        if not progression.chords:
            return bass

        beats_per_chord = 4  # One chord per bar (4 beats)

        for i, chord in enumerate(progression.chords):
            root_midi = note_to_midi(chord.root, 3)  # Bass octave

            if genre == "pop":
                # Root note on beat 1 and 3
                for beat_offset in [0, 2]:
                    bass.append({
                        "note": chord.root,
                        "midi": root_midi,
                        "start_beat": i * beats_per_chord + beat_offset,
                        "duration_beats": 2.0,
                        "velocity": 85,
                    })

            elif genre == "rock":
                # Root + 5th pattern
                fifth_midi = root_midi + 7
                fifth_note = NOTE_NAMES[fifth_midi % 12]
                bass.append({
                    "note": chord.root,
                    "midi": root_midi,
                    "start_beat": i * beats_per_chord,
                    "duration_beats": 2.0,
                    "velocity": 90,
                })
                bass.append({
                    "note": fifth_note,
                    "midi": fifth_midi,
                    "start_beat": i * beats_per_chord + 2,
                    "duration_beats": 2.0,
                    "velocity": 80,
                })

            elif genre == "edm":
                # 16th note root pattern with octave
                for step in range(8):
                    midi = root_midi if step % 2 == 0 else root_midi + 12
                    bass.append({
                        "note": chord.root,
                        "midi": midi,
                        "start_beat": i * beats_per_chord + step * 0.5,
                        "duration_beats": 0.5,
                        "velocity": 80 + (10 if step % 2 == 0 else 0),
                    })

            elif genre == "hiphop":
                # 808 style: long sustained root with slide
                bass.append({
                    "note": chord.root,
                    "midi": root_midi - 12,  # Sub-bass
                    "start_beat": i * beats_per_chord,
                    "duration_beats": 4.0,
                    "velocity": 95,
                })

            elif genre in ("rnb", "ballad"):
                # Root on beat 1, passing tone on beat 3
                bass.append({
                    "note": chord.root,
                    "midi": root_midi,
                    "start_beat": i * beats_per_chord,
                    "duration_beats": 2.0,
                    "velocity": 80,
                })
                # 5th or 3rd on beat 3
                alt_midi = root_midi + (7 if chord.is_major() else 3)
                alt_note = NOTE_NAMES[alt_midi % 12]
                bass.append({
                    "note": alt_note,
                    "midi": alt_midi,
                    "start_beat": i * beats_per_chord + 2,
                    "duration_beats": 2.0,
                    "velocity": 75,
                })

            else:
                # Default: root on beat 1
                bass.append({
                    "note": chord.root,
                    "midi": root_midi,
                    "start_beat": i * beats_per_chord,
                    "duration_beats": 4.0,
                    "velocity": 80,
                })

        return bass

    def _assign_instruments(
        self, genre: str, template: ArrangementTemplate
    ) -> dict[str, dict[str, Any]]:
        """Assign instruments based on genre and template."""
        base_instruments = GENRE_INSTRUMENTS.get(genre, GENRE_INSTRUMENTS["pop"])

        # Enhance with template-specific tracks
        assigned = dict(base_instruments)

        # Add tracks from template that aren't in the base assignment
        for section in template.structure:
            for track_spec in section.tracks:
                if track_spec.instrument and track_spec.instrument not in assigned:
                    assigned[track_spec.instrument] = {
                        "type": track_spec.type,
                        "instrument": track_spec.instrument,
                        "volume": 0.6,
                    }

        return assigned

    def _assemble_project(
        self,
        genre: str,
        key: str,
        scale: str,
        bpm: float,
        duration: float,
        template: ArrangementTemplate,
        progression: ChordProgression,
        melody: list[dict[str, Any]],
        drum_pattern: dict[str, Any],
        bass_line: list[dict[str, Any]],
        instruments: dict[str, dict[str, Any]],
        mood: str,
    ) -> dict[str, Any]:
        """Assemble all components into a VCMix project configuration."""
        # Build track list from instruments
        tracks: list[dict[str, Any]] = []
        track_idx = 0

        for inst_name, inst_config in instruments.items():
            track: dict[str, Any] = {
                "name": inst_name,
                "type": inst_config.get("type", "audio"),
                "instrument": inst_config.get("instrument", inst_name),
                "volume": inst_config.get("volume", 0.7),
                "effects": self._default_effects_for_track(inst_name, genre),
            }

            # Add MIDI notes for melodic instruments
            if inst_name in ("piano", "keys", "rhodes", "synth", "supersaw", "plucks", "pluck", "pad"):
                track["midi_notes"] = melody
            elif inst_name == "bass" or inst_name == "808":
                track["midi_notes"] = bass_line

            # Add drum pattern for drum tracks
            if inst_name == "drums":
                track["drum_pattern"] = drum_pattern

            tracks.append(track)
            track_idx += 1

        # Build arrangement from template
        arrangement: list[dict[str, Any]] = []
        for section in template.structure:
            section_dict: dict[str, Any] = {
                "name": section.name,
                "duration_bars": section.duration_bars,
                "energy": section.energy,
                "active_tracks": [t.instrument for t in section.tracks],
            }
            arrangement.append(section_dict)

        # Build master section
        master: dict[str, Any] = {
            "target_lufs": -14.0,
            "true_peak_ceiling": -1.0,
            "effects": [
                {"name": "vc-limiter", "params": {"ceiling": -1.0}},
            ],
        }

        # Complete project config
        project: dict[str, Any] = {
            "name": f"{genre.title()} Composition in {key}",
            "bpm": bpm,
            "key": key,
            "scale": scale,
            "mood": mood,
            "genre": genre,
            "duration": duration,
            "tracks": tracks,
            "arrangement": arrangement,
            "chord_progression": [c.name for c in progression.chords],
            "master": master,
        }

        return project

    def _default_effects_for_track(self, track_name: str, genre: str) -> list[dict[str, Any]]:
        """Return default effect chain for a track type."""
        effects: list[dict[str, Any]] = []

        if track_name in ("drums",):
            effects = [
                {"name": "vc-comp", "params": {"threshold": -12, "ratio": 4, "attack": 5}},
                {"name": "vc-eq", "params": {"low_cut_hz": 40}},
            ]
        elif track_name in ("bass", "808"):
            effects = [
                {"name": "vc-comp", "params": {"threshold": -15, "ratio": 4}},
                {"name": "vc-eq", "params": {"low_shelf_db": 2}},
            ]
        elif track_name in ("piano", "keys", "rhodes"):
            effects = [
                {"name": "vc-eq", "params": {}},
                {"name": "vc-reverb", "params": {"wet": 0.25, "room_size": 0.6}},
            ]
        elif track_name in ("guitar",):
            effects = [
                {"name": "vc-eq", "params": {}},
                {"name": "vc-reverb", "params": {"wet": 0.2, "room_size": 0.4}},
            ]
        elif track_name in ("synth", "supersaw", "plucks", "pluck", "pad"):
            effects = [
                {"name": "vc-eq", "params": {}},
                {"name": "vc-delay", "params": {"time_ms": 250, "feedback": 0.3}},
                {"name": "vc-reverb", "params": {"wet": 0.2}},
            ]
        elif track_name in ("strings",):
            effects = [
                {"name": "vc-eq", "params": {"high_shelf_db": -2}},
                {"name": "vc-reverb", "params": {"wet": 0.35, "room_size": 0.8}},
            ]

        return effects
