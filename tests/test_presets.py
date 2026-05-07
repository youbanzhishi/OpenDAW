"""Tests for vcmix.presets module."""
import pytest
from vcmix.presets.manager import list_presets, get_preset, apply_preset, save_preset


class TestListPresets:
    def test_returns_nonempty(self):
        presets = list_presets()
        assert len(presets) >= 5

    def test_contains_pop_vocal(self):
        assert "pop_vocal" in list_presets()

    def test_contains_podcast(self):
        assert "podcast" in list_presets()


class TestGetPreset:
    def test_pop_vocal_has_effects(self):
        chain = get_preset("pop_vocal")
        assert chain is not None
        assert len(chain) >= 3

    def test_pop_vocal_has_deesser(self):
        chain = get_preset("pop_vocal")
        names = [e["name"] for e in chain]
        assert "vc-deesser" in names

    def test_pop_vocal_has_limiter(self):
        chain = get_preset("pop_vocal")
        names = [e["name"] for e in chain]
        assert "vc-limiter" in names

    def test_unknown_returns_none(self):
        assert get_preset("nonexistent") is None

    def test_each_effect_has_name_and_params(self):
        for preset_name in list_presets():
            chain = get_preset(preset_name)
            for effect in chain:
                assert "name" in effect
                assert "params" in effect


class TestApplyPreset:
    def test_apply_replaces_effects(self):
        track = {"name": "vocal", "file": "vocal.wav", "effects": []}
        result = apply_preset(track, "pop_vocal")
        assert len(result["effects"]) >= 3

    def test_apply_preserves_name(self):
        track = {"name": "vocal", "file": "vocal.wav", "effects": []}
        result = apply_preset(track, "pop_vocal")
        assert result["name"] == "vocal"

    def test_apply_unknown_raises(self):
        with pytest.raises(ValueError):
            apply_preset({"name": "v", "file": "v.wav"}, "nonexistent")


class TestSavePreset:
    def test_save_creates_file(self, tmp_path):
        chain = [{"name": "vc-gain", "params": {"gain": 3}}]
        path = save_preset("test_preset", chain, path=str(tmp_path))
        assert path.exists()

    def test_save_loadable(self, tmp_path):
        import yaml
        chain = [{"name": "vc-gain", "params": {"gain": 3}}]
        path = save_preset("test_preset", chain, path=str(tmp_path))
        with open(path) as f:
            data = yaml.safe_load(f)
        assert data["name"] == "test_preset"
        assert len(data["effects"]) == 1
