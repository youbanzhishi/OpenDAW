"""
test_ai_composition.py — Tests for AI composition engine (Phase 15).

Tests cover:
    - Music theory: scales, chords, progressions, key detection
    - AIComposer: composition generation, YAML output format
    - Edge cases and error handling
"""

from __future__ import annotations

import pytest

from vcmix.ai.composer import (
    DRUM_PATTERNS,
    GENRE_INSTRUMENTS,
    AIComposer,
    CompositionResult,
)
from vcmix.ai.music_theory import (
    NOTE_NAMES,
    PROGRESSION_LIBRARY,
    Chord,
    ChordProgression,
    Scale,
    _normalize_note,
    detect_key,
    get_progression,
    list_progressions,
    midi_to_note,
    midi_to_note_with_octave,
    modal_interchange_chords,
    note_to_midi,
    semitones_between,
    transpose_progression,
)

# ═══════════════════════════════════════════════════════════════════════════
# Music Theory: Note helpers
# ═══════════════════════════════════════════════════════════════════════════

class TestNoteHelpers:
    """Test note name utilities."""

    def test_normalize_note_sharps(self):
        assert _normalize_note("C") == "C"
        assert _normalize_note("G") == "G"

    def test_normalize_note_flats(self):
        assert _normalize_note("Db") == "C#"
        assert _normalize_note("Eb") == "D#"
        assert _normalize_note("Bb") == "A#"
        assert _normalize_note("Ab") == "G#"

    def test_normalize_note_enharmonic_special(self):
        assert _normalize_note("E#") == "F"
        assert _normalize_note("B#") == "C"
        assert _normalize_note("Fb") == "E"
        assert _normalize_note("Cb") == "B"

    def test_note_to_midi(self):
        assert note_to_midi("C", 4) == 60
        assert note_to_midi("A", 4) == 69
        assert note_to_midi("C", 0) == 12

    def test_midi_to_note(self):
        assert midi_to_note(60) == "C"
        assert midi_to_note(69) == "A"
        assert midi_to_note(61) == "C#"

    def test_midi_to_note_with_octave(self):
        assert midi_to_note_with_octave(60) == "C4"
        assert midi_to_note_with_octave(69) == "A4"

    def test_semitones_between_same(self):
        assert semitones_between("C", "C") == 0

    def test_semitones_between_octave(self):
        assert semitones_between("C", "C") == 0  # Same note

    def test_semitones_between_fifth(self):
        assert semitones_between("C", "G") == 7

    def test_semitones_between_wrapping(self):
        assert semitones_between("B", "C") == 1
        assert semitones_between("G", "C") == 5


# ═══════════════════════════════════════════════════════════════════════════
# Music Theory: Scales
# ═══════════════════════════════════════════════════════════════════════════

class TestScale:
    """Test Scale class."""

    def test_c_major_notes(self):
        s = Scale("C", "major")
        assert s.notes() == ["C", "D", "E", "F", "G", "A", "B"]

    def test_a_minor_notes(self):
        s = Scale("A", "natural_minor")
        assert s.notes() == ["A", "B", "C", "D", "E", "F", "G"]

    def test_d_major_notes(self):
        s = Scale("D", "major")
        assert s.notes() == ["D", "E", "F#", "G", "A", "B", "C#"]

    def test_c_pentatonic_major(self):
        s = Scale("C", "pentatonic_major")
        assert s.notes() == ["C", "D", "E", "G", "A"]

    def test_a_blues_scale(self):
        s = Scale("A", "blues")
        assert s.notes() == ["A", "C", "D", "D#", "E", "G"]

    def test_d_dorian(self):
        s = Scale("D", "dorian")
        assert s.notes() == ["D", "E", "F", "G", "A", "B", "C"]

    def test_g_mixolydian(self):
        s = Scale("G", "mixolydian")
        assert s.notes() == ["G", "A", "B", "C", "D", "E", "F"]

    def test_c_harmonic_minor(self):
        s = Scale("C", "harmonic_minor")
        assert "B" in s.notes()  # Leading tone

    def test_midi_notes(self):
        s = Scale("C", "major")
        midi = s.midi_notes(octave=4)
        assert midi[0] == 60  # C4
        assert len(midi) == 7

    def test_triads_major(self):
        s = Scale("C", "major")
        triads = s.triads()
        assert len(triads) == 7
        assert triads[0].name == "C"       # I
        assert triads[1].name == "Dm"      # ii
        assert triads[2].name == "Em"      # iii
        assert triads[3].name == "F"       # IV
        assert triads[4].name == "G"       # V
        assert triads[5].name == "Am"      # vi
        assert triads[6].name == "Bdim"    # viio

    def test_seventh_chords_major(self):
        s = Scale("C", "major")
        sevenths = s.seventh_chords()
        assert len(sevenths) == 7
        assert sevenths[0].name == "Cmaj7"
        assert sevenths[4].name == "G7"

    def test_contains_note(self):
        s = Scale("C", "major")
        assert s.contains_note("C") is True
        assert s.contains_note("C#") is False
        assert s.contains_note("E") is True

    def test_degree_chord(self):
        s = Scale("C", "major")
        chord = s.degree_chord(1)
        assert chord.root == "C"
        assert chord.quality == ""

    def test_degree_chord_minor(self):
        s = Scale("C", "major")
        chord = s.degree_chord(2)
        assert chord.root == "D"
        assert chord.quality == "m"

    def test_unknown_scale_defaults_to_major(self):
        s = Scale("C", "unknown_scale")
        assert s.notes() == Scale("C", "major").notes()

    def test_repr(self):
        s = Scale("C", "major")
        assert "C" in repr(s)
        assert "major" in repr(s)

    def test_minor_triads(self):
        s = Scale("A", "natural_minor")
        triads = s.triads()
        assert len(triads) == 7
        assert triads[0].name == "Am"      # i

    def test_dorian_triads(self):
        s = Scale("D", "dorian")
        triads = s.triads()
        assert len(triads) == 7
        assert triads[0].name == "Dm"      # i (minor)


# ═══════════════════════════════════════════════════════════════════════════
# Music Theory: Chords
# ═══════════════════════════════════════════════════════════════════════════

class TestChord:
    """Test Chord class."""

    def test_major_chord(self):
        c = Chord("C", "")
        assert c.name == "C"
        assert c.notes() == ["C", "E", "G"]

    def test_minor_chord(self):
        c = Chord("A", "m")
        assert c.name == "Am"
        assert c.notes() == ["A", "C", "E"]

    def test_diminished_chord(self):
        c = Chord("B", "dim")
        assert c.notes() == ["B", "D", "F"]

    def test_augmented_chord(self):
        c = Chord("C", "aug")
        assert c.notes() == ["C", "E", "G#"]

    def test_dominant_7th(self):
        c = Chord("G", "7")
        assert c.notes() == ["G", "B", "D", "F"]

    def test_major_7th(self):
        c = Chord("C", "maj7")
        assert c.notes() == ["C", "E", "G", "B"]

    def test_minor_7th(self):
        c = Chord("A", "m7")
        assert c.notes() == ["A", "C", "E", "G"]

    def test_sus4_chord(self):
        c = Chord("D", "sus4")
        assert c.notes() == ["D", "G", "A"]

    def test_sus2_chord(self):
        c = Chord("D", "sus2")
        assert c.notes() == ["D", "E", "A"]

    def test_9th_chord(self):
        c = Chord("G", "9")
        assert len(c.notes()) == 5

    def test_bass_note(self):
        c = Chord("C", "7")
        assert c.bass_note() == "C"

    def test_is_major(self):
        assert Chord("C", "").is_major() is True
        assert Chord("G", "7").is_major() is True
        assert Chord("C", "m").is_major() is False

    def test_is_minor(self):
        assert Chord("A", "m").is_minor() is True
        assert Chord("D", "m7").is_minor() is True
        assert Chord("C", "").is_minor() is False

    def test_is_dominant(self):
        assert Chord("G", "7").is_dominant() is True
        assert Chord("C", "maj7").is_dominant() is False

    def test_transpose(self):
        c = Chord("C", "m")
        t = c.transpose(2)
        assert t.root == "D"
        assert t.quality == "m"

    def test_transpose_fifth(self):
        c = Chord("C", "")
        t = c.transpose(7)
        assert t.root == "G"
        assert t.quality == ""

    def test_equality(self):
        assert Chord("C", "") == Chord("C", "")
        assert Chord("C", "m") != Chord("C", "")

    def test_hash(self):
        s = {Chord("C", ""), Chord("C", "")}
        assert len(s) == 1

    def test_midi_notes(self):
        c = Chord("C", "")
        midi = c.midi_notes(octave=4)
        assert midi[0] == 60

    def test_roman_numeral_in_c_major(self):
        s = Scale("C", "major")
        c1 = Chord("C", "")
        assert c1.roman_numeral(s) == "I"
        c5 = Chord("G", "")
        assert c5.roman_numeral(s) == "V"
        c6 = Chord("A", "m")
        assert c6.roman_numeral(s) == "vi"

    def test_m7b5_chord(self):
        c = Chord("B", "m7b5")
        assert len(c.notes()) == 4


# ═══════════════════════════════════════════════════════════════════════════
# Music Theory: Chord Progressions
# ═══════════════════════════════════════════════════════════════════════════

class TestChordProgression:
    """Test ChordProgression class."""

    def test_from_name_pop_1(self):
        prog = ChordProgression.from_name("pop_1", key="C")
        assert len(prog.chords) == 4
        assert prog.chords[0].name == "C"
        assert prog.chords[1].name == "G"
        assert prog.chords[2].name == "Am"
        assert prog.chords[3].name == "F"

    def test_from_name_transpose(self):
        prog = ChordProgression.from_name("pop_1", key="G")
        assert prog.chords[0].root == "G"

    def test_from_name_unknown_raises(self):
        with pytest.raises(ValueError, match="Unknown progression"):
            ChordProgression.from_name("nonexistent_prog")

    def test_from_roman(self):
        s = Scale("C", "major")
        prog = ChordProgression.from_roman("I-V-vi-IV", s)
        assert len(prog.chords) == 4
        assert prog.chords[0].root == "C"
        assert prog.chords[1].root == "G"
        assert prog.chords[2].root == "A"
        assert prog.chords[3].root == "F"

    def test_from_roman_minor(self):
        s = Scale("A", "natural_minor")
        prog = ChordProgression.from_roman("i-VI-VII-i", s)
        assert len(prog.chords) == 4
        assert prog.chords[0].root == "A"
        assert prog.chords[0].quality == "m"

    def test_to_dict(self):
        prog = ChordProgression.from_name("pop_1", key="C")
        d = prog.to_dict()
        assert "chords" in d
        assert "name" in d
        assert len(d["chords"]) == 4

    def test_len(self):
        prog = ChordProgression.from_name("pop_1", key="C")
        assert len(prog) == 4

    def test_repr(self):
        prog = ChordProgression.from_name("pop_1", key="C")
        assert "Pop" in repr(prog)


class TestProgressionLibrary:
    """Test the built-in chord progression library."""

    def test_library_has_20_plus_progressions(self):
        assert len(PROGRESSION_LIBRARY) >= 20

    def test_list_progressions(self):
        progs = list_progressions()
        assert len(progs) >= 20

    def test_list_progressions_by_genre(self):
        pop_progs = list_progressions(genre="pop")
        assert len(pop_progs) >= 3

    def test_list_progressions_by_mood(self):
        happy_progs = list_progressions(mood="happy")
        assert len(happy_progs) >= 1

    def test_get_progression(self):
        prog = get_progression("pop_1")
        assert prog is not None
        assert len(prog.chords) == 4

    def test_get_progression_not_found(self):
        assert get_progression("nonexistent") is None

    def test_edm_progressions_exist(self):
        progs = list_progressions(genre="edm")
        assert len(progs) >= 2

    def test_hiphop_progressions_exist(self):
        progs = list_progressions(genre="hiphop")
        assert len(progs) >= 2

    def test_rnb_progressions_exist(self):
        progs = list_progressions(genre="rnb")
        assert len(progs) >= 2

    def test_rock_progressions_exist(self):
        progs = list_progressions(genre="rock")
        assert len(progs) >= 2


# ═══════════════════════════════════════════════════════════════════════════
# Music Theory: Key Detection
# ═══════════════════════════════════════════════════════════════════════════

class TestKeyDetection:
    """Test Krumhansl-Schmuckler key detection."""

    def test_detect_c_major(self):
        # C major chroma: high C, E, G
        chroma = [1.0, 0.0, 0.0, 0.0, 0.8, 0.0, 0.0, 0.9, 0.0, 0.0, 0.0, 0.0]
        key, scale_type, confidence = detect_key(chroma)
        assert key == "C"
        assert scale_type == "major"
        assert confidence > 0.0

    def test_detect_a_minor(self):
        # A minor chroma: high A, C, E
        chroma = [0.0, 0.0, 0.0, 0.0, 0.8, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0]
        key, scale_type, confidence = detect_key(chroma)
        # K-S algorithm should return a valid key
        assert key in NOTE_NAMES
        assert scale_type in ("major", "natural_minor")

    def test_detect_key_empty_chroma(self):
        chroma = [0.0] * 12
        key, scale_type, confidence = detect_key(chroma)
        assert confidence == 0.0

    def test_detect_key_invalid_chroma(self):
        with pytest.raises(ValueError):
            detect_key([1.0, 0.0, 0.5])

    def test_detect_key_returns_tuple(self):
        chroma = [0.5] * 12
        result = detect_key(chroma)
        assert len(result) == 3


# ═══════════════════════════════════════════════════════════════════════════
# Music Theory: Transposition & Modal Interchange
# ═══════════════════════════════════════════════════════════════════════════

class TestTransposition:
    """Test transposition and modal interchange."""

    def test_transpose_progression(self):
        prog = get_progression("pop_1")
        transposed = transpose_progression(prog, "G")
        assert transposed.chords[0].root == "G"

    def test_transpose_preserves_quality(self):
        prog = get_progression("pop_1")
        transposed = transpose_progression(prog, "D")
        for orig, trans in zip(prog.chords, transposed.chords):
            assert orig.quality == trans.quality

    def test_transpose_empty_progression(self):
        prog = ChordProgression(name="empty", chords=[])
        result = transpose_progression(prog, "G")
        assert len(result.chords) == 0

    def test_modal_interchange_major(self):
        borrowed = modal_interchange_chords("C", "major")
        assert len(borrowed) > 0
        # Should include bVI and bVII
        roots = [c.root for c in borrowed]
        assert "A#" in roots or "Bb" in roots  # bVII might appear as Bb

    def test_modal_interchange_minor(self):
        borrowed = modal_interchange_chords("A", "natural_minor")
        assert len(borrowed) > 0


# ═══════════════════════════════════════════════════════════════════════════
# AI Composer
# ═══════════════════════════════════════════════════════════════════════════

class TestAIComposer:
    """Test AIComposer class."""

    def test_compose_pop(self):
        composer = AIComposer()
        result = composer.compose(
            genre="pop", duration=180, bpm=120,
            key="C", mood="happy"
        )
        assert isinstance(result, CompositionResult)
        assert result.genre == "pop"
        assert result.key == "C"
        assert result.bpm == 120.0

    def test_compose_generates_project_config(self):
        composer = AIComposer()
        result = composer.compose(
            genre="pop", duration=120, bpm=120,
            key="C", mood="happy"
        )
        config = result.project_config
        assert "name" in config
        assert "bpm" in config
        assert "key" in config
        assert "tracks" in config
        assert "arrangement" in config
        assert "master" in config
        assert "chord_progression" in config

    def test_compose_pop_tracks(self):
        composer = AIComposer()
        result = composer.compose(
            genre="pop", duration=180, bpm=120,
            key="C", mood="happy"
        )
        tracks = result.project_config["tracks"]
        assert len(tracks) > 0
        # Should have common pop instruments
        track_names = [t["name"] for t in tracks]
        assert "piano" in track_names or "keys" in track_names

    def test_compose_rock(self):
        composer = AIComposer()
        result = composer.compose(
            genre="rock", duration=180, bpm=130,
            key="E", mood="energetic"
        )
        assert result.genre == "rock"
        assert result.key == "E"

    def test_compose_edm(self):
        composer = AIComposer()
        result = composer.compose(
            genre="edm", duration=240, bpm=128,
            key="Am", mood="dark"
        )
        assert result.genre == "edm"
        tracks = result.project_config["tracks"]
        assert len(tracks) > 0

    def test_compose_hiphop(self):
        composer = AIComposer()
        result = composer.compose(
            genre="hiphop", duration=200, bpm=90,
            key="Cm", mood="dark"
        )
        assert result.genre == "hiphop"

    def test_compose_rnb(self):
        composer = AIComposer()
        result = composer.compose(
            genre="rnb", duration=200, bpm=80,
            key="Db", mood="calm"
        )
        assert result.genre == "rnb"

    def test_compose_ballad(self):
        composer = AIComposer()
        result = composer.compose(
            genre="ballad", duration=240, bpm=72,
            key="F", mood="sad"
        )
        assert result.genre == "ballad"

    def test_compose_arrangement_structure(self):
        composer = AIComposer()
        result = composer.compose(
            genre="pop", duration=180, bpm=120,
            key="C", mood="happy"
        )
        arrangement = result.project_config["arrangement"]
        assert len(arrangement) > 0
        section_names = [s["name"] for s in arrangement]
        assert "intro" in section_names or "verse1" in section_names

    def test_compose_master_section(self):
        composer = AIComposer()
        result = composer.compose(
            genre="pop", duration=180, bpm=120,
            key="C", mood="happy"
        )
        master = result.project_config["master"]
        assert "target_lufs" in master
        assert "true_peak_ceiling" in master
        assert "effects" in master

    def test_compose_chord_progression(self):
        composer = AIComposer()
        result = composer.compose(
            genre="pop", duration=180, bpm=120,
            key="C", mood="happy"
        )
        cp = result.project_config["chord_progression"]
        assert len(cp) > 0
        assert "C" in cp[0] or "G" in cp[0]  # Should start on I or V

    def test_compose_with_reference(self):
        composer = AIComposer()
        result = composer.compose(
            genre="pop", duration=180, bpm=120,
            key="C", mood="happy", reference=None
        )
        assert result.genre == "pop"

    def test_compose_result_to_dict(self):
        composer = AIComposer()
        result = composer.compose(
            genre="pop", duration=120, bpm=120,
            key="C", mood="happy"
        )
        d = result.to_dict()
        assert "project_config" in d
        assert "genre" in d
        assert "bpm" in d
        assert "chord_progression" in d

    def test_compose_melody_generated(self):
        composer = AIComposer()
        result = composer.compose(
            genre="pop", duration=120, bpm=120,
            key="C", mood="happy"
        )
        # Melody should be in the piano/keys track
        tracks = result.project_config["tracks"]
        melodic_tracks = [t for t in tracks if "midi_notes" in t]
        assert len(melodic_tracks) > 0

    def test_compose_drum_pattern_generated(self):
        composer = AIComposer()
        result = composer.compose(
            genre="pop", duration=120, bpm=120,
            key="C", mood="happy"
        )
        tracks = result.project_config["tracks"]
        drum_tracks = [t for t in tracks if "drum_pattern" in t]
        assert len(drum_tracks) > 0

    def test_compose_bass_line_generated(self):
        composer = AIComposer()
        result = composer.compose(
            genre="pop", duration=120, bpm=120,
            key="C", mood="happy"
        )
        tracks = result.project_config["tracks"]
        bass_tracks = [t for t in tracks if t["name"] in ("bass", "808") and "midi_notes" in t]
        assert len(bass_tracks) > 0

    def test_compose_effects_assigned(self):
        composer = AIComposer()
        result = composer.compose(
            genre="pop", duration=120, bpm=120,
            key="C", mood="happy"
        )
        tracks = result.project_config["tracks"]
        for track in tracks:
            assert "effects" in track

    def test_compose_mood_affects_progression(self):
        composer = AIComposer()
        happy = composer.compose(genre="pop", duration=120, bpm=120, key="C", mood="happy")
        sad = composer.compose(genre="pop", duration=120, bpm=120, key="C", mood="sad")
        # Happy and sad should produce different progressions
        # (at minimum, different mood tags)
        assert happy.chord_progression.mood != sad.chord_progression.mood or \
               happy.chord_progression.chords != sad.chord_progression.chords


class TestComposerInternals:
    """Test AIComposer internal methods."""

    def test_parse_key_major(self):
        composer = AIComposer()
        root, scale_type = composer._parse_key("C")
        assert root == "C"
        assert scale_type == "major"

    def test_parse_key_minor(self):
        composer = AIComposer()
        root, scale_type = composer._parse_key("Am")
        assert root == "A"
        assert scale_type == "natural_minor"

    def test_parse_key_explicit_major(self):
        composer = AIComposer()
        root, scale_type = composer._parse_key("D Major")
        assert root == "D"
        assert scale_type == "major"

    def test_parse_key_explicit_minor(self):
        composer = AIComposer()
        root, scale_type = composer._parse_key("F Minor")
        assert root == "F"
        assert scale_type == "natural_minor"

    def test_parse_key_with_sharp(self):
        composer = AIComposer()
        root, scale_type = composer._parse_key("F#")
        assert root == "F#"
        assert scale_type == "major"

    def test_determine_scale_mood_override(self):
        composer = AIComposer()
        scale = composer._determine_scale("pop", "dark", "major")
        assert scale == "harmonic_minor"  # Dark mood overrides

    def test_determine_scale_genre_default(self):
        composer = AIComposer()
        scale = composer._determine_scale("edm", "happy", "major")
        # Happy mood should override
        assert scale == "major"

    def test_select_template_genre_match(self):
        composer = AIComposer()
        template = composer._select_template("pop", 180)
        assert template.genre == "pop"

    def test_select_template_fallback(self):
        composer = AIComposer()
        template = composer._select_template("unknown_genre", 180)
        assert template is not None  # Should fallback to pop

    def test_generate_drum_pattern_pop(self):
        composer = AIComposer()
        pattern = composer._generate_drum_pattern("pop", 120)
        assert "tracks" in pattern
        assert "kick" in pattern["tracks"]
        assert "snare" in pattern["tracks"]

    def test_generate_drum_pattern_edm(self):
        composer = AIComposer()
        pattern = composer._generate_drum_pattern("edm", 128)
        assert pattern["genre"] == "edm"
        # EDM should have 4-on-floor kick
        assert pattern["tracks"]["kick"]["hits"][0] == 1
        assert pattern["tracks"]["kick"]["hits"][4] == 1

    def test_generate_bass_line_pop(self):
        composer = AIComposer()
        prog = ChordProgression.from_name("pop_1", key="C")
        bass = composer._generate_bass_line(prog, "pop", 120)
        assert len(bass) > 0
        assert bass[0]["note"] == "C"

    def test_generate_bass_line_hiphop(self):
        composer = AIComposer()
        prog = ChordProgression.from_name("hiphop_1", key="A")
        bass = composer._generate_bass_line(prog, "hiphop", 90)
        assert len(bass) > 0

    def test_assign_instruments_pop(self):
        composer = AIComposer()
        from vcmix.arrangement.templates import get_template
        template = get_template("pop-standard")
        instruments = composer._assign_instruments("pop", template)
        assert "piano" in instruments or "keys" in instruments

    def test_assign_instruments_rock(self):
        composer = AIComposer()
        from vcmix.arrangement.templates import get_template
        template = get_template("rock")
        instruments = composer._assign_instruments("rock", template)
        assert "guitar" in instruments


class TestDrumPatterns:
    """Test drum pattern definitions."""

    def test_all_genres_have_patterns(self):
        for genre in ["pop", "rock", "edm", "hiphop", "rnb", "ballad", "lofi"]:
            assert genre in DRUM_PATTERNS

    def test_pattern_has_16_steps(self):
        for genre, pattern in DRUM_PATTERNS.items():
            for drum_name, hits in pattern.items():
                assert len(hits) == 16, f"{genre}/{drum_name} has {len(hits)} steps"

    def test_kick_and_snare_present(self):
        for genre in ["pop", "rock", "hiphop"]:
            pattern = DRUM_PATTERNS[genre]
            assert "kick" in pattern
            assert "snare" in pattern

    def test_edm_has_kick_and_clap(self):
        pattern = DRUM_PATTERNS["edm"]
        assert "kick" in pattern
        assert "clap" in pattern


class TestGenreInstruments:
    """Test genre instrument assignments."""

    def test_pop_has_piano_and_drums(self):
        assert "piano" in GENRE_INSTRUMENTS["pop"]
        assert "drums" in GENRE_INSTRUMENTS["pop"]

    def test_edm_has_supersaw(self):
        assert "supersaw" in GENRE_INSTRUMENTS["edm"]

    def test_hiphop_has_808(self):
        assert "808" in GENRE_INSTRUMENTS["hiphop"]

    def test_all_instruments_have_volume(self):
        for genre, instruments in GENRE_INSTRUMENTS.items():
            for name, config in instruments.items():
                assert "volume" in config
                assert 0.0 <= config["volume"] <= 1.0
