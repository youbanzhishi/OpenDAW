"""
test_mix_presets.py — Tests for Phase 12 mix preset system.

Covers:
    - Mix preset data models (EffectPreset, TrackMixPreset, MasterMixPreset, MixPreset)
    - Mix preset registry (get_mix_preset, list_mix_presets, list_mix_presets_by_genre)
    - Mix preset suggestion (suggest_mix_preset)
    - Integration with arrangement templates
    - API endpoint tests
"""

from __future__ import annotations

import pytest

from vcmix.arrangement.templates import get_template
from vcmix.presets.mix_presets import (
    MIX_PRESET_REGISTRY,
    EffectPreset,
    MasterMixPreset,
    MixPreset,
    TrackMixPreset,
    get_mix_preset,
    list_mix_presets,
    list_mix_presets_by_genre,
    suggest_mix_preset,
)

# ── EffectPreset Tests ──────────────────────────────────────────────────

class TestEffectPreset:
    def test_create_basic(self):
        ep = EffectPreset(plugin="VC-EQ")
        assert ep.plugin == "VC-EQ"
        assert ep.params == {}
        assert ep.enabled is True

    def test_create_with_params(self):
        ep = EffectPreset(plugin="VC-Comp", params={"threshold": -18, "ratio": 3})
        assert ep.params["threshold"] == -18
        assert ep.params["ratio"] == 3

    def test_to_dict_converts_plugin_name(self):
        ep = EffectPreset(plugin="VC-EQ", params={"high_shelf_db": 2})
        d = ep.to_dict()
        assert d["name"] == "vc-eq"
        assert d["params"]["high_shelf_db"] == 2

    def test_to_dict_disabled(self):
        ep = EffectPreset(plugin="VC-Reverb", enabled=False)
        d = ep.to_dict()
        assert d["enabled"] is False

    def test_to_dict_no_params(self):
        ep = EffectPreset(plugin="VC-EQ")
        d = ep.to_dict()
        assert "params" not in d  # empty dict omitted

    def test_from_dict_roundtrip(self):
        ep = EffectPreset(plugin="VC-Comp", params={"threshold": -20, "ratio": 4})
        d = ep.to_dict()
        ep2 = EffectPreset.from_dict(d)
        assert ep2.plugin == "vc-comp"
        assert ep2.params["threshold"] == -20

    def test_from_dict_with_name_key(self):
        """from_dict should handle both 'name' and 'plugin' keys."""
        ep = EffectPreset.from_dict({"name": "vc-reverb", "params": {"wet": 0.3}})
        assert ep.plugin == "vc-reverb"


# ── TrackMixPreset Tests ────────────────────────────────────────────────

class TestTrackMixPreset:
    def test_create_basic(self):
        tp = TrackMixPreset(track_type="vocals")
        assert tp.track_type == "vocals"
        assert tp.effects == []
        assert tp.volume_db == 0.0
        assert tp.pan == 0.0

    def test_create_with_effects(self):
        tp = TrackMixPreset(
            track_type="drums",
            effects=[
                EffectPreset("VC-EQ", {"low_cut_hz": 40}),
                EffectPreset("VC-Comp", {"threshold": -10, "ratio": 4}),
            ],
            volume_db=-6.0,
            pan=0.0,
        )
        assert len(tp.effects) == 2
        assert tp.volume_db == -6.0

    def test_to_dict(self):
        tp = TrackMixPreset("vocals", [EffectPreset("VC-EQ", {"high_shelf_db": 3})], -3.0, 0.0)
        d = tp.to_dict()
        assert d["track_type"] == "vocals"
        assert len(d["effects"]) == 1
        assert d["volume_db"] == -3.0
        assert d["pan"] == 0.0

    def test_from_dict_roundtrip(self):
        tp = TrackMixPreset("bass", [EffectPreset("VC-Comp", {"ratio": 4})], -6.0, 0.0)
        d = tp.to_dict()
        tp2 = TrackMixPreset.from_dict(d)
        assert tp2.track_type == "bass"
        assert tp2.volume_db == -6.0
        assert len(tp2.effects) == 1


# ── MasterMixPreset Tests ───────────────────────────────────────────────

class TestMasterMixPreset:
    def test_create_default(self):
        mp = MasterMixPreset()
        assert mp.effects == []
        assert mp.volume_db == 0.0
        assert mp.target_lufs == -14.0

    def test_create_with_effects(self):
        mp = MasterMixPreset(
            effects=[EffectPreset("VC-Limiter", {"ceiling": -1})],
            volume_db=0.0,
            target_lufs=-14.0,
        )
        assert len(mp.effects) == 1
        assert mp.target_lufs == -14.0

    def test_to_dict(self):
        mp = MasterMixPreset([EffectPreset("VC-Comp", {"ratio": 2})], 0.0, -14.0)
        d = mp.to_dict()
        assert d["volume_db"] == 0.0
        assert d["target_lufs"] == -14.0
        assert len(d["effects"]) == 1

    def test_from_dict_roundtrip(self):
        mp = MasterMixPreset([EffectPreset("VC-Limiter", {"ceiling": -1})], 0.0, -14.0)
        d = mp.to_dict()
        mp2 = MasterMixPreset.from_dict(d)
        assert mp2.target_lufs == -14.0
        assert len(mp2.effects) == 1


# ── MixPreset Tests ─────────────────────────────────────────────────────

class TestMixPreset:
    def test_create_basic(self):
        mp = MixPreset(name="Test", genre="pop")
        assert mp.name == "Test"
        assert mp.genre == "pop"
        assert mp.tracks == []

    def test_track_types_property(self):
        mp = MixPreset(
            name="Test", genre="pop",
            tracks=[
                TrackMixPreset("vocals"),
                TrackMixPreset("drums"),
                TrackMixPreset("bass"),
            ],
        )
        assert mp.track_types == ["vocals", "drums", "bass"]

    def test_to_dict_roundtrip(self):
        mp = MixPreset(
            name="Test Preset",
            genre="rock",
            description="A test preset",
            tracks=[TrackMixPreset("vocals", [EffectPreset("VC-EQ", {"high_shelf_db": 2})], -3.0)],
            master=MasterMixPreset([EffectPreset("VC-Limiter", {"ceiling": -1})], 0.0, -14.0),
        )
        d = mp.to_dict()
        mp2 = MixPreset.from_dict(d)
        assert mp2.name == "Test Preset"
        assert mp2.genre == "rock"
        assert len(mp2.tracks) == 1
        assert mp2.master.target_lufs == -14.0


# ── Mix Preset Registry Tests ───────────────────────────────────────────

class TestMixPresetRegistry:
    def test_has_6_presets(self):
        assert len(MIX_PRESET_REGISTRY) >= 6

    def test_list_mix_presets_sorted(self):
        keys = list_mix_presets()
        assert keys == sorted(keys)

    def test_list_contains_clean_pop(self):
        assert "clean-pop" in list_mix_presets()

    def test_list_contains_warm_vintage(self):
        assert "warm-vintage" in list_mix_presets()

    def test_list_contains_punchy_edm(self):
        assert "punchy-edm" in list_mix_presets()

    def test_list_contains_tight_hiphop(self):
        assert "tight-hiphop" in list_mix_presets()

    def test_list_contains_airy_ballad(self):
        assert "airy-ballad" in list_mix_presets()

    def test_list_contains_lofi_chill(self):
        assert "lofi-chill" in list_mix_presets()

    def test_get_found(self):
        p = get_mix_preset("clean-pop")
        assert p is not None
        assert p.name == "Clean Pop"

    def test_get_not_found(self):
        assert get_mix_preset("nonexistent") is None

    def test_list_by_genre_pop(self):
        keys = list_mix_presets_by_genre("pop")
        assert "clean-pop" in keys

    def test_list_by_genre_edm(self):
        keys = list_mix_presets_by_genre("edm")
        assert "punchy-edm" in keys

    def test_list_by_genre_empty(self):
        keys = list_mix_presets_by_genre("nonexistent")
        assert keys == []


# ── Individual Preset Validation ─────────────────────────────────────────

class TestCleanPopPreset:
    def test_has_all_track_types(self):
        p = get_mix_preset("clean-pop")
        expected = {"vocals", "drums", "bass", "guitar", "keys", "synth", "strings"}
        assert set(p.track_types) == expected

    def test_vocals_have_effects(self):
        p = get_mix_preset("clean-pop")
        for tp in p.tracks:
            if tp.track_type == "vocals":
                assert len(tp.effects) >= 3
                return
        pytest.fail("No vocals track type found")

    def test_master_has_limiter(self):
        p = get_mix_preset("clean-pop")
        effect_names = [e.plugin for e in p.master.effects]
        assert "VC-Limiter" in effect_names

    def test_genre(self):
        assert get_mix_preset("clean-pop").genre == "pop"


class TestWarmVintagePreset:
    def test_has_track_types(self):
        p = get_mix_preset("warm-vintage")
        assert len(p.track_types) >= 5

    def test_genre(self):
        assert get_mix_preset("warm-vintage").genre == "rock"


class TestPunchyEDMPreset:
    def test_has_track_types(self):
        p = get_mix_preset("punchy-edm")
        assert len(p.track_types) >= 5

    def test_genre(self):
        assert get_mix_preset("punchy-edm").genre == "edm"


class TestTightHipHopPreset:
    def test_has_track_types(self):
        p = get_mix_preset("tight-hiphop")
        assert len(p.track_types) >= 5

    def test_genre(self):
        assert get_mix_preset("tight-hiphop").genre == "hiphop"


class TestAiryBalladPreset:
    def test_has_track_types(self):
        p = get_mix_preset("airy-ballad")
        assert len(p.track_types) >= 5

    def test_genre(self):
        assert get_mix_preset("airy-ballad").genre == "rnb"


class TestLoFiChillPreset:
    def test_has_track_types(self):
        p = get_mix_preset("lofi-chill")
        assert len(p.track_types) >= 5

    def test_genre(self):
        assert get_mix_preset("lofi-chill").genre == "lofi"

    def test_lofi_target_lufs(self):
        p = get_mix_preset("lofi-chill")
        assert p.master.target_lufs == -16.0  # Lower than standard


# ── Suggest Mix Preset Tests ────────────────────────────────────────────

class TestSuggestMixPreset:
    def test_genre_match_pop(self):
        p = suggest_mix_preset("pop")
        assert p is not None
        assert p.genre == "pop"

    def test_genre_match_edm(self):
        p = suggest_mix_preset("edm")
        assert p is not None
        assert p.genre == "edm"

    def test_genre_match_hiphop(self):
        p = suggest_mix_preset("hiphop")
        assert p is not None
        assert p.genre == "hiphop"

    def test_fallback_to_clean_pop(self):
        p = suggest_mix_preset("nonexistent-genre")
        assert p is not None
        assert p.name == "Clean Pop"

    def test_with_track_types(self):
        p = suggest_mix_preset("pop", track_types=["vocals", "drums", "bass"])
        assert p is not None
        assert "vocals" in p.track_types

    def test_track_type_overlap_scoring(self):
        """When genre doesn't match, track type overlap should guide selection."""
        p = suggest_mix_preset("unknown", track_types=["vocals", "drums"])
        assert p is not None


# ── Preset Parameter Completeness Tests ──────────────────────────────────

class TestPresetParameterCompleteness:
    def test_all_presets_have_vocals(self):
        """Every preset should have a vocals track type."""
        for key in list_mix_presets():
            p = get_mix_preset(key)
            assert "vocals" in p.track_types, f"{key} missing vocals track"

    def test_all_presets_have_drums(self):
        for key in list_mix_presets():
            p = get_mix_preset(key)
            assert "drums" in p.track_types, f"{key} missing drums track"

    def test_all_presets_have_bass(self):
        for key in list_mix_presets():
            p = get_mix_preset(key)
            assert "bass" in p.track_types, f"{key} missing bass track"

    def test_all_presets_have_master(self):
        for key in list_mix_presets():
            p = get_mix_preset(key)
            assert len(p.master.effects) > 0, f"{key} has no master effects"

    def test_all_presets_master_has_limiter(self):
        for key in list_mix_presets():
            p = get_mix_preset(key)
            effect_names = [e.plugin for e in p.master.effects]
            assert "VC-Limiter" in effect_names, f"{key} master missing limiter"

    def test_all_track_effects_have_plugin(self):
        for key in list_mix_presets():
            p = get_mix_preset(key)
            for tp in p.tracks:
                for eff in tp.effects:
                    assert eff.plugin, f"{key}/{tp.track_type} has empty plugin name"

    def test_all_track_presets_have_volume(self):
        for key in list_mix_presets():
            p = get_mix_preset(key)
            for tp in p.tracks:
                assert isinstance(tp.volume_db, (int, float)), \
                    f"{key}/{tp.track_type} volume_db not numeric"

    def test_all_track_presets_have_pan(self):
        for key in list_mix_presets():
            p = get_mix_preset(key)
            for tp in p.tracks:
                assert -1.0 <= tp.pan <= 1.0, \
                    f"{key}/{tp.track_type} pan out of range"

    def test_all_effects_params_are_dicts(self):
        for key in list_mix_presets():
            p = get_mix_preset(key)
            for tp in p.tracks:
                for eff in tp.effects:
                    assert isinstance(eff.params, dict), \
                        f"{key}/{tp.track_type}/{eff.plugin} params not dict"

    def test_serialization_roundtrip_all(self):
        """All presets should survive to_dict/from_dict roundtrip."""
        for key in list_mix_presets():
            p = get_mix_preset(key)
            d = p.to_dict()
            p2 = MixPreset.from_dict(d)
            assert p2.name == p.name
            assert len(p2.tracks) == len(p.tracks)
            assert p2.master.target_lufs == p.master.target_lufs


# ── AI Engine Integration Tests ──────────────────────────────────────────

class TestAIEngineArrangement:
    def test_suggest_arrangement_pop(self):
        from vcmix.web.ai_engine import AIEngine
        engine = AIEngine()
        result = engine.suggest_arrangement("pop")
        assert result["template_name"] == "Pop Standard"
        assert result["suggested_bpm"] > 0

    def test_suggest_arrangement_with_mood(self):
        from vcmix.web.ai_engine import AIEngine
        engine = AIEngine()
        result = engine.suggest_arrangement("edm", mood="upbeat")
        assert result["suggested_bpm"] >= 126  # EDM upbeat = high BPM

    def test_suggest_arrangement_with_duration(self):
        from vcmix.web.ai_engine import AIEngine
        engine = AIEngine()
        result = engine.suggest_arrangement("pop", duration=180)
        assert "duration_scaling" in result

    def test_suggest_arrangement_unknown_genre(self):
        from vcmix.web.ai_engine import AIEngine
        engine = AIEngine()
        result = engine.suggest_arrangement("nonexistent")
        # Should still return something
        assert "template_name" in result

    def test_suggest_mix_preset_pop(self):
        from vcmix.web.ai_engine import AIEngine
        engine = AIEngine()
        result = engine.suggest_mix_preset("pop")
        assert result["name"] == "Clean Pop"

    def test_suggest_mix_preset_with_track_types(self):
        from vcmix.web.ai_engine import AIEngine
        engine = AIEngine()
        result = engine.suggest_mix_preset("edm", track_types=["vocals", "synth", "bass"])
        assert result is not None
        assert "tracks" in result


# ── Arrangement-Mix Integration Tests ───────────────────────────────────

class TestArrangementMixIntegration:
    def test_template_recommends_matching_preset(self):
        from vcmix.arrangement.template_applier import TemplateApplier
        applier = TemplateApplier()

        # Pop template should recommend clean-pop
        tmpl = get_template("pop-standard")
        preset_name = applier._recommend_mix_preset(tmpl.genre)
        assert preset_name == "clean-pop"

    def test_edm_template_recommends_punchy(self):
        from vcmix.arrangement.template_applier import TemplateApplier
        applier = TemplateApplier()

        tmpl = get_template("edm-drop")
        preset_name = applier._recommend_mix_preset(tmpl.genre)
        assert preset_name == "punchy-edm"

    def test_lofi_template_recommends_lofi(self):
        from vcmix.arrangement.template_applier import TemplateApplier
        applier = TemplateApplier()

        tmpl = get_template("lofi")
        preset_name = applier._recommend_mix_preset(tmpl.genre)
        assert preset_name == "lofi-chill"

    def test_applied_config_has_mix_preset_reference(self):
        from vcmix.arrangement.template_applier import TemplateApplier
        tmpl = get_template("hiphop")
        applier = TemplateApplier()
        result = applier.apply_to_dict(tmpl, bpm=90, key="Cm")
        assert result["recommended_mix_preset"] == "tight-hiphop"

    def test_applied_config_tracks_have_effects(self):
        from vcmix.arrangement.template_applier import TemplateApplier
        tmpl = get_template("pop-standard")
        applier = TemplateApplier()
        result = applier.apply_to_dict(tmpl, bpm=120)
        tracks_with_effects = [t for t in result["tracks"] if t.get("effects")]
        assert len(tracks_with_effects) > 0
