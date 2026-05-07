"""Tests for vcmix.presets.chain_presets module — Phase 9 chain presets."""
from pathlib import Path

import pytest
import yaml

from vcmix.presets.chain_presets import (
    ChainEffect,
    ChainPreset,
    ChainPresetManager,
    get_chain_preset,
    list_chain_presets,
)

# ── ChainEffect Tests ───────────────────────────────────────────────────

class TestChainEffect:
    def test_effect_creation(self):
        effect = ChainEffect(name="vc-reverb", params={"room": 30, "mix": 10})
        assert effect.name == "vc-reverb"
        assert effect.params["room"] == 30
        assert effect.enabled is True

    def test_effect_to_dict(self):
        effect = ChainEffect(name="vc-comp", params={"threshold": -24, "ratio": 3})
        d = effect.to_dict()
        assert d["name"] == "vc-comp"
        assert d["params"]["threshold"] == -24
        assert "enabled" not in d  # True is default, not serialized

    def test_effect_to_dict_disabled(self):
        effect = ChainEffect(name="vc-gain", params={"gain": 3}, enabled=False)
        d = effect.to_dict()
        assert d["enabled"] is False

    def test_effect_to_dict_with_send(self):
        effect = ChainEffect(name="vc-reverb", params={"mix": 10}, send_level=0.5)
        d = effect.to_dict()
        assert d["send_level"] == 0.5

    def test_effect_from_dict(self):
        data = {"name": "vc-reverb", "params": {"room": 30}}
        effect = ChainEffect.from_dict(data)
        assert effect.name == "vc-reverb"
        assert effect.params["room"] == 30
        assert effect.enabled is True

    def test_effect_from_dict_string(self):
        """Effect from just a string name."""
        effect = ChainEffect.from_dict({"name": "vc-gain"})
        assert effect.name == "vc-gain"
        assert effect.params == {}


# ── ChainPreset Tests ───────────────────────────────────────────────────

class TestChainPreset:
    def test_preset_creation(self):
        effects = [
            ChainEffect(name="vc-deesser", params={"threshold": -40}),
            ChainEffect(name="vc-comp", params={"threshold": -24}),
        ]
        preset = ChainPreset(name="test-chain", effects=effects)
        assert preset.name == "test-chain"
        assert preset.effect_count == 2
        assert preset.routing == "serial"

    def test_effect_names(self):
        effects = [
            ChainEffect(name="vc-deesser"),
            ChainEffect(name="vc-comp"),
            ChainEffect(name="vc-limiter"),
        ]
        preset = ChainPreset(name="test", effects=effects)
        assert preset.effect_names == ["vc-deesser", "vc-comp", "vc-limiter"]

    def test_active_effects(self):
        effects = [
            ChainEffect(name="vc-deesser", enabled=True),
            ChainEffect(name="vc-comp", enabled=False),
            ChainEffect(name="vc-limiter", enabled=True),
        ]
        preset = ChainPreset(name="test", effects=effects)
        assert len(preset.active_effects) == 2

    def test_to_dict(self):
        effects = [ChainEffect(name="vc-reverb", params={"room": 30})]
        preset = ChainPreset(name="test", description="Test chain", effects=effects)
        d = preset.to_dict()
        assert d["name"] == "test"
        assert d["description"] == "Test chain"
        assert len(d["effects"]) == 1

    def test_from_dict(self):
        data = {
            "name": "my-chain",
            "description": "My custom chain",
            "routing": "serial",
            "effects": [
                {"name": "vc-comp", "params": {"threshold": -20}},
                {"name": "vc-limiter", "params": {"ceiling": -1}},
            ],
            "tags": ["custom"],
        }
        preset = ChainPreset.from_dict(data)
        assert preset.name == "my-chain"
        assert preset.effect_count == 2
        assert preset.tags == ["custom"]

    def test_to_yaml_and_back(self):
        effects = [
            ChainEffect(name="vc-comp", params={"threshold": -24, "ratio": 3}),
            ChainEffect(name="vc-limiter", params={"ceiling": -1}),
        ]
        preset = ChainPreset(
            name="test-yaml",
            description="YAML round-trip test",
            effects=effects,
            tags=["test"],
        )
        yaml_str = preset.to_yaml()
        restored = ChainPreset.from_yaml(yaml_str)
        assert restored.name == "test-yaml"
        assert restored.effect_count == 2
        assert restored.tags == ["test"]

    def test_input_output_gain(self):
        preset = ChainPreset(
            name="gain-test",
            effects=[ChainEffect(name="vc-gain")],
            input_gain_db=-3.0,
            output_gain_db=1.0,
        )
        d = preset.to_dict()
        assert d["input_gain_db"] == -3.0
        assert d["output_gain_db"] == 1.0


# ── ChainPresetManager Tests ────────────────────────────────────────────

class TestChainPresetManager:
    def test_list_builtin_presets(self):
        manager = ChainPresetManager()
        presets = manager.list_presets()
        assert "vocal-chain" in presets
        assert "drum-chain" in presets
        assert "master-chain" in presets
        assert "guitar-chain" in presets

    def test_get_vocal_chain(self):
        manager = ChainPresetManager()
        chain = manager.get("vocal-chain")
        assert chain is not None
        assert chain.name == "vocal-chain"
        assert chain.effect_count >= 3

    def test_get_unknown_returns_none(self):
        manager = ChainPresetManager()
        assert manager.get("nonexistent") is None

    def test_vocal_chain_has_deesser(self):
        manager = ChainPresetManager()
        chain = manager.get("vocal-chain")
        assert chain is not None
        names = chain.effect_names
        assert "vc-deesser" in names

    def test_vocal_chain_has_limiter(self):
        manager = ChainPresetManager()
        chain = manager.get("vocal-chain")
        assert chain is not None
        names = chain.effect_names
        assert "vc-limiter" in names

    def test_drum_chain(self):
        manager = ChainPresetManager()
        chain = manager.get("drum-chain")
        assert chain is not None
        assert chain.effect_count >= 2
        assert "vc-gate" in chain.effect_names

    def test_master_chain(self):
        manager = ChainPresetManager()
        chain = manager.get("master-chain")
        assert chain is not None
        assert "vc-limiter" in chain.effect_names

    def test_guitar_chain(self):
        manager = ChainPresetManager()
        chain = manager.get("guitar-chain")
        assert chain is not None
        assert "vc-reverb" in chain.effect_names

    def test_apply_to_track(self):
        manager = ChainPresetManager()
        track = {"name": "vocal", "file": "vocal.wav"}
        result = manager.apply_to_track("vocal-chain", track)
        assert "effects" in result
        assert len(result["effects"]) >= 3
        assert result["name"] == "vocal"

    def test_apply_by_preset_object(self):
        manager = ChainPresetManager()
        chain = manager.get("vocal-chain")
        assert chain is not None
        track = {"name": "vocal", "file": "vocal.wav"}
        result = manager.apply_to_track(chain, track)
        assert len(result["effects"]) >= 3

    def test_apply_unknown_raises(self):
        manager = ChainPresetManager()
        with pytest.raises(ValueError, match="not found"):
            manager.apply_to_track("nonexistent", {"name": "v"})

    def test_save_and_load(self, tmp_path):
        manager = ChainPresetManager(chains_dir=str(tmp_path))
        custom = ChainPreset(
            name="custom-chain",
            description="My custom chain",
            effects=[
                ChainEffect(name="vc-comp", params={"threshold": -18}),
            ],
            tags=["custom"],
        )
        path = manager.save(custom)
        assert path.exists()

        # Create a new manager to verify persistence
        manager2 = ChainPresetManager(chains_dir=str(tmp_path))
        loaded = manager2.get("custom-chain")
        assert loaded is not None
        assert loaded.name == "custom-chain"
        assert loaded.effect_count == 1

    def test_save_from_track(self, tmp_path):
        manager = ChainPresetManager(chains_dir=str(tmp_path))
        track_config = {
            "name": "vocal",
            "file": "vocal.wav",
            "effects": [
                {"name": "vc-comp", "params": {"threshold": -24}},
                {"name": "vc-reverb", "params": {"room": 30}},
            ],
        }
        path = manager.save_from_track("my-chain", "From vocal track", track_config)
        assert path.exists()

        loaded = manager.get("my-chain")
        assert loaded is not None
        assert loaded.effect_count == 2

    def test_delete_user_preset(self, tmp_path):
        manager = ChainPresetManager(chains_dir=str(tmp_path))
        custom = ChainPreset(name="temp-chain", effects=[ChainEffect(name="vc-gain")])
        manager.save(custom)
        assert manager.get("temp-chain") is not None

        result = manager.delete("temp-chain")
        assert result is True
        assert manager.get("temp-chain") is None

    def test_cannot_delete_builtin(self):
        manager = ChainPresetManager()
        result = manager.delete("vocal-chain")
        assert result is False  # Cannot delete built-in
        assert manager.get("vocal-chain") is not None  # Still exists

    def test_delete_nonexistent(self):
        manager = ChainPresetManager()
        result = manager.delete("nonexistent")
        assert result is False


# ── Convenience Function Tests ──────────────────────────────────────────

class TestConvenienceFunctions:
    def test_list_chain_presets(self):
        presets = list_chain_presets()
        assert isinstance(presets, list)
        assert len(presets) >= 4

    def test_get_chain_preset(self):
        chain = get_chain_preset("vocal-chain")
        assert chain is not None
        assert chain.name == "vocal-chain"

    def test_get_chain_preset_not_found(self):
        assert get_chain_preset("nonexistent") is None


# ── YAML Chain File Tests ───────────────────────────────────────────────

class TestYamlChainFiles:
    def test_vocal_chain_yaml_exists(self):
        chains_dir = Path("/tmp/OpenDAW/src/vcmix/presets/chains")
        assert (chains_dir / "vocal-chain.yaml").exists()

    def test_drum_chain_yaml_exists(self):
        chains_dir = Path("/tmp/OpenDAW/src/vcmix/presets/chains")
        assert (chains_dir / "drum-chain.yaml").exists()

    def test_master_chain_yaml_exists(self):
        chains_dir = Path("/tmp/OpenDAW/src/vcmix/presets/chains")
        assert (chains_dir / "master-chain.yaml").exists()

    def test_guitar_chain_yaml_exists(self):
        chains_dir = Path("/tmp/OpenDAW/src/vcmix/presets/chains")
        assert (chains_dir / "guitar-chain.yaml").exists()

    def test_vocal_chain_yaml_valid(self):
        chains_dir = Path("/tmp/OpenDAW/src/vcmix/presets/chains")
        with open(chains_dir / "vocal-chain.yaml") as f:
            data = yaml.safe_load(f)
        preset = ChainPreset.from_dict(data)
        assert preset.name == "vocal-chain"
        assert preset.effect_count >= 3
        assert "vc-deesser" in preset.effect_names
        assert "vc-limiter" in preset.effect_names
