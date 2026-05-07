"""
test_arrangement_templates.py — Tests for Phase 12 arrangement template system.

Covers:
    - Template data models (TrackSpec, Section, ArrangementTemplate)
    - Template registry (get_template, list_templates, list_templates_by_genre)
    - Template applier (apply, apply_to_dict, section generation, automation)
    - CLI commands (templates, apply-template)
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from vcmix.arrangement.templates import (
    ArrangementTemplate,
    Section,
    TrackSpec,
    TEMPLATE_REGISTRY,
    get_template,
    list_templates,
    list_templates_by_genre,
)
from vcmix.arrangement.template_applier import TemplateApplier


# ── TrackSpec Tests ─────────────────────────────────────────────────────

class TestTrackSpec:
    def test_create_basic(self):
        ts = TrackSpec(name="Lead Vocal")
        assert ts.name == "Lead Vocal"
        assert ts.type == "audio"
        assert ts.instrument == ""
        assert ts.effects == []

    def test_create_full(self):
        ts = TrackSpec(
            name="Piano",
            type="midi",
            instrument="Grand Piano",
            effects=[{"name": "vc-reverb", "params": {"wet": 0.3}}],
        )
        assert ts.type == "midi"
        assert ts.instrument == "Grand Piano"
        assert len(ts.effects) == 1

    def test_to_dict_basic(self):
        ts = TrackSpec(name="Bass", type="midi")
        d = ts.to_dict()
        assert d["name"] == "Bass"
        assert d["type"] == "midi"
        assert "instrument" not in d  # empty string omitted
        assert "effects" not in d  # empty list omitted

    def test_to_dict_full(self):
        ts = TrackSpec(name="Synth", type="midi", instrument="Serum",
                       effects=[{"name": "vc-eq", "params": {}}])
        d = ts.to_dict()
        assert d["instrument"] == "Serum"
        assert len(d["effects"]) == 1

    def test_from_dict_roundtrip(self):
        ts = TrackSpec(name="Guitar", type="audio", instrument="Les Paul",
                       effects=[{"name": "vc-dist", "params": {"drive": 5}}])
        d = ts.to_dict()
        ts2 = TrackSpec.from_dict(d)
        assert ts2.name == ts.name
        assert ts2.type == ts.type
        assert ts2.instrument == ts.instrument
        assert len(ts2.effects) == 1

    def test_from_dict_minimal(self):
        ts = TrackSpec.from_dict({"name": "Drums"})
        assert ts.name == "Drums"
        assert ts.type == "audio"
        assert ts.instrument == ""


# ── Section Tests ────────────────────────────────────────────────────────

class TestSection:
    def test_create_basic(self):
        s = Section(name="intro")
        assert s.name == "intro"
        assert s.duration_bars == 8
        assert s.tracks == []
        assert s.energy == 0.5

    def test_create_full(self):
        s = Section(name="chorus", duration_bars=16,
                    tracks=[TrackSpec("Vocal")], energy=0.9)
        assert s.duration_bars == 16
        assert len(s.tracks) == 1
        assert s.energy == 0.9

    def test_to_dict(self):
        s = Section(name="verse", duration_bars=16,
                    tracks=[TrackSpec("Vocal")], energy=0.4)
        d = s.to_dict()
        assert d["name"] == "verse"
        assert d["duration_bars"] == 16
        assert len(d["tracks"]) == 1
        assert d["energy"] == 0.4

    def test_from_dict_roundtrip(self):
        s = Section(name="bridge", duration_bars=8,
                    tracks=[TrackSpec("Keys", type="midi")], energy=0.5)
        d = s.to_dict()
        s2 = Section.from_dict(d)
        assert s2.name == s.name
        assert s2.duration_bars == s.duration_bars
        assert len(s2.tracks) == 1
        assert s2.energy == s.energy

    def test_from_dict_no_tracks(self):
        s = Section.from_dict({"name": "outro", "duration_bars": 4, "energy": 0.2})
        assert s.tracks == []


# ── ArrangementTemplate Tests ────────────────────────────────────────────

class TestArrangementTemplate:
    def test_create_basic(self):
        tmpl = ArrangementTemplate(name="Test", genre="pop")
        assert tmpl.name == "Test"
        assert tmpl.genre == "pop"
        assert tmpl.bpm_range == (120, 128)
        assert tmpl.structure == []

    def test_total_bars(self):
        tmpl = ArrangementTemplate(
            name="Test", genre="pop",
            structure=[
                Section("intro", 8),
                Section("verse", 16),
                Section("chorus", 16),
            ],
        )
        assert tmpl.total_bars == 40

    def test_section_names(self):
        tmpl = ArrangementTemplate(
            name="Test", genre="pop",
            structure=[Section("intro"), Section("verse"), Section("chorus")],
        )
        assert tmpl.section_names == ["intro", "verse", "chorus"]

    def test_to_dict_roundtrip(self):
        tmpl = ArrangementTemplate(
            name="Test", genre="rock",
            bpm_range=(110, 140),
            structure=[Section("intro", 8, [TrackSpec("Guitar")], 0.5)],
            description="Test template",
            default_key="E",
        )
        d = tmpl.to_dict()
        tmpl2 = ArrangementTemplate.from_dict(d)
        assert tmpl2.name == "Test"
        assert tmpl2.genre == "rock"
        assert tmpl2.bpm_range == (110, 140)
        assert len(tmpl2.structure) == 1
        assert tmpl2.description == "Test template"
        assert tmpl2.default_key == "E"

    def test_from_dict_bpm_range_list(self):
        """Ensure bpm_range stored as list deserializes to tuple."""
        d = {"name": "X", "genre": "pop", "bpm_range": [100, 130]}
        tmpl = ArrangementTemplate.from_dict(d)
        assert tmpl.bpm_range == (100, 130)
        assert isinstance(tmpl.bpm_range, tuple)


# ── Template Registry Tests ──────────────────────────────────────────────

class TestTemplateRegistry:
    def test_has_8_templates(self):
        assert len(TEMPLATE_REGISTRY) >= 8

    def test_list_templates_returns_sorted(self):
        keys = list_templates()
        assert keys == sorted(keys)

    def test_list_templates_contains_pop(self):
        assert "pop-standard" in list_templates()

    def test_list_templates_contains_edm(self):
        assert "edm-drop" in list_templates()

    def test_list_templates_contains_rock(self):
        assert "rock" in list_templates()

    def test_list_templates_contains_hiphop(self):
        assert "hiphop" in list_templates()

    def test_list_templates_contains_rnb(self):
        assert "rnb-ballad" in list_templates()

    def test_list_templates_contains_progressive(self):
        assert "progressive" in list_templates()

    def test_list_templates_contains_lofi(self):
        assert "lofi" in list_templates()

    def test_list_templates_contains_orchestral(self):
        assert "orchestral" in list_templates()

    def test_get_template_found(self):
        tmpl = get_template("pop-standard")
        assert tmpl is not None
        assert tmpl.name == "Pop Standard"
        assert tmpl.genre == "pop"

    def test_get_template_not_found(self):
        assert get_template("nonexistent") is None

    def test_list_by_genre_pop(self):
        keys = list_templates_by_genre("pop")
        assert "pop-standard" in keys

    def test_list_by_genre_edm(self):
        keys = list_templates_by_genre("edm")
        assert "edm-drop" in keys

    def test_list_by_genre_empty(self):
        keys = list_templates_by_genre("nonexistent")
        assert keys == []


# ── Individual Template Validation ───────────────────────────────────────

class TestPopStandard:
    def test_has_sections(self):
        tmpl = get_template("pop-standard")
        assert len(tmpl.structure) >= 10

    def test_section_order(self):
        tmpl = get_template("pop-standard")
        names = tmpl.section_names
        assert names[0] == "intro"
        assert "chorus1" in names
        assert names[-1] == "outro"

    def test_has_tracks_in_sections(self):
        tmpl = get_template("pop-standard")
        for section in tmpl.structure:
            assert len(section.tracks) > 0

    def test_energy_range(self):
        tmpl = get_template("pop-standard")
        for section in tmpl.structure:
            assert 0.0 <= section.energy <= 1.0


class TestEDMDrop:
    def test_has_drops(self):
        tmpl = get_template("edm-drop")
        names = tmpl.section_names
        assert "drop1" in names
        assert "drop2" in names

    def test_genre(self):
        tmpl = get_template("edm-drop")
        assert tmpl.genre == "edm"


class TestRockTemplate:
    def test_has_solo(self):
        tmpl = get_template("rock")
        assert "solo" in tmpl.section_names

    def test_genre(self):
        assert get_template("rock").genre == "rock"


class TestHipHopTemplate:
    def test_has_hook(self):
        tmpl = get_template("hiphop")
        assert "hook1" in tmpl.section_names

    def test_genre(self):
        assert get_template("hiphop").genre == "hiphop"


class TestRnBBallad:
    def test_has_bridge(self):
        tmpl = get_template("rnb-ballad")
        assert "bridge" in tmpl.section_names

    def test_genre(self):
        assert get_template("rnb-ballad").genre == "rnb"


class TestProgressiveTemplate:
    def test_has_peak(self):
        tmpl = get_template("progressive")
        assert "peak1" in tmpl.section_names

    def test_genre(self):
        assert get_template("progressive").genre == "progressive"


class TestLoFiTemplate:
    def test_has_loop(self):
        tmpl = get_template("lofi")
        assert "loop1" in tmpl.section_names

    def test_genre(self):
        assert get_template("lofi").genre == "lofi"


class TestOrchestralTemplate:
    def test_has_climax(self):
        tmpl = get_template("orchestral")
        assert "climax" in tmpl.section_names

    def test_genre(self):
        assert get_template("orchestral").genre == "orchestral"


# ── Template Applier Tests ───────────────────────────────────────────────

class TestTemplateApplier:
    def test_apply_returns_yaml(self):
        tmpl = get_template("pop-standard")
        applier = TemplateApplier()
        result = applier.apply(tmpl, bpm=120, key="C")
        assert isinstance(result, str)
        # Should be valid YAML
        parsed = yaml.safe_load(result)
        assert isinstance(parsed, dict)

    def test_apply_to_dict(self):
        tmpl = get_template("pop-standard")
        applier = TemplateApplier()
        result = applier.apply_to_dict(tmpl, bpm=120, key="C")
        assert isinstance(result, dict)
        assert "tracks" in result
        assert "arrangement" in result
        assert "automation" in result

    def test_dict_has_correct_bpm(self):
        tmpl = get_template("pop-standard")
        applier = TemplateApplier()
        result = applier.apply_to_dict(tmpl, bpm=128, key="G")
        assert result["bpm"] == 128
        assert result["key"] == "G"

    def test_tracks_collected(self):
        tmpl = get_template("pop-standard")
        applier = TemplateApplier()
        result = applier.apply_to_dict(tmpl, bpm=120)
        assert len(result["tracks"]) > 0
        # Each track should have a name
        for track in result["tracks"]:
            assert "name" in track
            assert "type" in track

    def test_sections_have_timing(self):
        tmpl = get_template("pop-standard")
        applier = TemplateApplier()
        result = applier.apply_to_dict(tmpl, bpm=120)
        sections = result["arrangement"]["sections"]
        assert len(sections) == len(tmpl.structure)
        for sec in sections:
            assert "start_bar" in sec
            assert "end_bar" in sec
            assert "start_sec" in sec
            assert "end_sec" in sec
            assert "duration_bars" in sec
            assert "energy" in sec
            assert "active_tracks" in sec

    def test_section_timing_accurate(self):
        """Verify section timing calculations."""
        tmpl = get_template("pop-standard")
        applier = TemplateApplier()
        result = applier.apply_to_dict(tmpl, bpm=120)
        sections = result["arrangement"]["sections"]
        # First section starts at bar 0
        assert sections[0]["start_bar"] == 0
        # Sections are contiguous
        for i in range(len(sections) - 1):
            assert sections[i]["end_bar"] == sections[i + 1]["start_bar"]
        # Total bars matches
        assert sections[-1]["end_bar"] == tmpl.total_bars

    def test_automation_has_energy_curve(self):
        tmpl = get_template("pop-standard")
        applier = TemplateApplier()
        result = applier.apply_to_dict(tmpl, bpm=120)
        auto = result["automation"]
        assert "energy_curve" in auto
        assert "master_volume" in auto
        assert "track_mute" in auto

    def test_energy_curve_points(self):
        tmpl = get_template("pop-standard")
        applier = TemplateApplier()
        result = applier.apply_to_dict(tmpl, bpm=120)
        points = result["automation"]["energy_curve"]
        # Should have one point per section + end point
        assert len(points) == len(tmpl.structure) + 1
        # First point should match first section energy
        assert points[0]["value"] == tmpl.structure[0].energy
        # Last point should be end
        assert points[-1]["section"] == "end"

    def test_recommended_mix_preset(self):
        tmpl = get_template("pop-standard")
        applier = TemplateApplier()
        result = applier.apply_to_dict(tmpl, bpm=120)
        assert "recommended_mix_preset" in result
        assert result["recommended_mix_preset"] is not None

    def test_apply_to_yaml_file(self, tmp_path):
        """Write YAML output to file and verify it parses."""
        tmpl = get_template("edm-drop")
        applier = TemplateApplier()
        yaml_str = applier.apply(tmpl, bpm=130, key="Am")
        out_path = tmp_path / "test_project.yaml"
        out_path.write_text(yaml_str, encoding="utf-8")

        parsed = yaml.safe_load(out_path.read_text(encoding="utf-8"))
        assert parsed["bpm"] == 130
        assert parsed["key"] == "Am"

    def test_all_templates_apply(self):
        """Verify all 8 templates can be applied without error."""
        applier = TemplateApplier()
        for key in list_templates():
            tmpl = get_template(key)
            result = applier.apply_to_dict(tmpl, bpm=120, key="C")
            assert "tracks" in result
            assert "arrangement" in result

    def test_energy_to_db_mapping(self):
        """Verify energy-to-dB mapping."""
        assert TemplateApplier._energy_to_db(0.0) == -12.0
        assert TemplateApplier._energy_to_db(1.0) == 0.0
        db_mid = TemplateApplier._energy_to_db(0.5)
        assert -9.0 < db_mid < -5.0  # Between -12 and 0


# ── CLI Tests ────────────────────────────────────────────────────────────

class TestArrangementCLI:
    def test_templates_command(self):
        from click.testing import CliRunner
        from vcmix.cli import main

        runner = CliRunner()
        result = runner.invoke(main, ["templates"])
        assert result.exit_code == 0
        assert "pop-standard" in result.output

    def test_templates_json_output(self):
        from click.testing import CliRunner
        from vcmix.cli import main

        runner = CliRunner()
        result = runner.invoke(main, ["templates", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, list)
        assert len(data) >= 8

    def test_templates_genre_filter(self):
        from click.testing import CliRunner
        from vcmix.cli import main

        runner = CliRunner()
        result = runner.invoke(main, ["templates", "--genre", "edm"])
        assert result.exit_code == 0
        assert "edm-drop" in result.output

    def test_apply_template_command(self, tmp_path):
        from click.testing import CliRunner
        from vcmix.cli import main

        runner = CliRunner()
        out = tmp_path / "output.yaml"
        result = runner.invoke(main, [
            "apply-template", "pop-standard",
            "--bpm", "128", "--key", "G",
            "-o", str(out),
        ])
        assert result.exit_code == 0
        assert out.exists()
        parsed = yaml.safe_load(out.read_text(encoding="utf-8"))
        assert parsed["bpm"] == 128
        assert parsed["key"] == "G"

    def test_apply_template_not_found(self):
        from click.testing import CliRunner
        from vcmix.cli import main

        runner = CliRunner()
        result = runner.invoke(main, ["apply-template", "nonexistent"])
        assert result.exit_code != 0

    def test_mix_presets_command(self):
        from click.testing import CliRunner
        from vcmix.cli import main

        runner = CliRunner()
        result = runner.invoke(main, ["mix-presets"])
        assert result.exit_code == 0
        assert "clean-pop" in result.output

    def test_mix_presets_json_output(self):
        from click.testing import CliRunner
        from vcmix.cli import main

        runner = CliRunner()
        result = runner.invoke(main, ["mix-presets", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, list)
        assert len(data) >= 6
