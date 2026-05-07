"""
chain_presets.py — Plugin chain preset management for VCMix.

Extends the existing preset system with full chain presets that include:
    - Ordered list of effects with all parameters
    - Routing mode (serial / parallel)
    - Gain staging between effects
    - Metadata (description, tags, source track)

Chain presets differ from single-effect presets (in manager.py) in that
they represent a complete signal processing chain for a track type.

Built-in chains:
    - vocal-chain:  DeEsser → Comp → EQ → Reverb → Limiter
    - drum-chain:   Gate → Comp → EQ → Parallel Comp
    - master-chain: EQ → MultiBand Comp → Limiter
    - guitar-chain: Comp → EQ → Delay → Reverb

Storage format: YAML files in src/vcmix/presets/chains/ directory.

CLI integration:
    vcmix chain-presets list
    vcmix chain-presets apply vocal-chain --track vocal
    vcmix chain-presets save my-chain --from-track vocal

Usage (Python API):
    from vcmix.presets.chain_presets import ChainPreset, ChainPresetManager

    manager = ChainPresetManager()
    chain = manager.get("vocal-chain")
    manager.apply_to_track(chain, track_config)

Dependencies: pyyaml>=6.0
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

# ── Data Models ──────────────────────────────────────────────────────────

@dataclass
class ChainEffect:
    """A single effect in a chain preset.

    Attributes:
        name: Plugin name (e.g. "vc-reverb").
        params: Plugin parameters dict.
        send_level: Post-effect send level (0.0-1.0), if routing to a bus.
        enabled: Whether this effect is active.
    """

    name: str
    params: dict[str, Any] = field(default_factory=dict)
    send_level: float = 0.0
    enabled: bool = True

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain dict."""
        result: dict[str, Any] = {"name": self.name}
        if self.params:
            result["params"] = dict(self.params)
        if self.send_level > 0:
            result["send_level"] = self.send_level
        if not self.enabled:
            result["enabled"] = False
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ChainEffect:
        """Deserialize from a plain dict.

        Args:
            data: Dict with at least "name" key.

        Returns:
            ChainEffect instance.
        """
        return cls(
            name=data.get("name", "unknown"),
            params=data.get("params", {}),
            send_level=data.get("send_level", 0.0),
            enabled=data.get("enabled", True),
        )


@dataclass
class ChainPreset:
    """A complete plugin chain preset.

    Attributes:
        name: Preset identifier (e.g. "vocal-chain").
        description: Human-readable description.
        effects: Ordered list of effects in the chain.
        routing: Signal routing mode ("serial" or "parallel").
        input_gain_db: Input gain in dB before the chain.
        output_gain_db: Output gain in dB after the chain.
        tags: Search/filter tags.
    """

    name: str
    description: str = ""
    effects: list[ChainEffect] = field(default_factory=list)
    routing: str = "serial"
    input_gain_db: float = 0.0
    output_gain_db: float = 0.0
    tags: list[str] = field(default_factory=list)

    @property
    def effect_count(self) -> int:
        """Number of effects in the chain."""
        return len(self.effects)

    @property
    def effect_names(self) -> list[str]:
        """Names of effects in order."""
        return [e.name for e in self.effects]

    @property
    def active_effects(self) -> list[ChainEffect]:
        """List of enabled effects only."""
        return [e for e in self.effects if e.enabled]

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain dict for YAML storage."""
        result: dict[str, Any] = {
            "name": self.name,
            "description": self.description,
            "routing": self.routing,
            "effects": [e.to_dict() for e in self.effects],
        }
        if self.input_gain_db != 0.0:
            result["input_gain_db"] = self.input_gain_db
        if self.output_gain_db != 0.0:
            result["output_gain_db"] = self.output_gain_db
        if self.tags:
            result["tags"] = self.tags
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ChainPreset:
        """Deserialize from a plain dict.

        Args:
            data: Dict from YAML with chain preset data.

        Returns:
            ChainPreset instance.
        """
        effects = [
            ChainEffect.from_dict(e) if isinstance(e, dict) else ChainEffect(name=str(e))
            for e in data.get("effects", [])
        ]
        return cls(
            name=data.get("name", "unknown"),
            description=data.get("description", ""),
            effects=effects,
            routing=data.get("routing", "serial"),
            input_gain_db=data.get("input_gain_db", 0.0),
            output_gain_db=data.get("output_gain_db", 0.0),
            tags=data.get("tags", []),
        )

    def to_yaml(self) -> str:
        """Serialize to YAML string."""
        return yaml.dump(self.to_dict(), default_flow_style=False, allow_unicode=True)

    @classmethod
    def from_yaml(cls, yaml_str: str) -> ChainPreset:
        """Deserialize from YAML string.

        Args:
            yaml_str: YAML content.

        Returns:
            ChainPreset instance.
        """
        data = yaml.safe_load(yaml_str)
        if not isinstance(data, dict):
            raise ValueError("Chain preset YAML must be a mapping")
        return cls.from_dict(data)


# ── Built-in Chain Presets ───────────────────────────────────────────────

BUILTIN_CHAIN_PRESETS: dict[str, ChainPreset] = {}


def _init_builtin_chains() -> None:
    """Initialize built-in chain presets."""
    global BUILTIN_CHAIN_PRESETS

    BUILTIN_CHAIN_PRESETS = {
        "vocal-chain": ChainPreset(
            name="vocal-chain",
            description="Standard vocal processing chain: DeEsser → Comp → EQ → Reverb → Limiter",
            effects=[
                ChainEffect(name="vc-deesser", params={"threshold": -40, "reduction": -6}),
                ChainEffect(
                    name="vc-comp",
                    params={"threshold": -24, "ratio": 3, "attack": 5, "release": 50},
                ),
                ChainEffect(name="vc-eq", params={
                    "low_cut": 80, "high_shelf": 8000,
                    "peak_freq": 2500, "peak_gain": -2, "peak_q": 1.5,
                }),
                ChainEffect(name="vc-reverb", params={
                    "room": 30, "decay": 35, "damping": 50,
                    "mix": 10, "predelay": 50, "wetlpf": 5000,
                }),
                ChainEffect(name="vc-limiter", params={"ceiling": -1}),
            ],
            routing="serial",
            tags=["vocal", "pop", "standard"],
        ),
        "drum-chain": ChainPreset(
            name="drum-chain",
            description="Drum bus processing: Gate → Comp → EQ → Parallel Comp",
            effects=[
                ChainEffect(
                    name="vc-gate",
                    params={"threshold": -40, "attack": 0.1, "release": 50},
                ),
                ChainEffect(
                    name="vc-comp",
                    params={"threshold": -20, "ratio": 4, "attack": 1, "release": 20},
                ),
                ChainEffect(name="vc-eq", params={
                    "low_shelf": 60, "low_gain": 3,
                    "peak_freq": 400, "peak_gain": -2, "peak_q": 1.0,
                    "high_shelf": 8000, "high_gain": 2,
                }),
                ChainEffect(
                    name="vc-comp",
                    params={"threshold": -10, "ratio": 2, "attack": 10, "release": 100},
                ),
            ],
            routing="serial",
            tags=["drums", "bus", "parallel"],
        ),
        "master-chain": ChainPreset(
            name="master-chain",
            description="Master bus processing: EQ → MultiBand Comp → Limiter",
            effects=[
                ChainEffect(name="vc-eq", params={
                    "low_cut": 30, "high_shelf": 16000,
                    "peak_freq": 200, "peak_gain": -1, "peak_q": 0.7,
                }),
                ChainEffect(name="vc-multiband", params={
                    "low_threshold": -12, "mid_threshold": -10,
                    "high_threshold": -8, "ratio": 2.0,
                }),
                ChainEffect(name="vc-limiter", params={"ceiling": -1}),
            ],
            routing="serial",
            tags=["master", "bus", "final"],
        ),
        "guitar-chain": ChainPreset(
            name="guitar-chain",
            description="Guitar processing: Comp → EQ → Delay → Reverb",
            effects=[
                ChainEffect(
                    name="vc-comp",
                    params={"threshold": -18, "ratio": 2.5, "attack": 10, "release": 60},
                ),
                ChainEffect(name="vc-eq", params={
                    "low_cut": 80, "high_shelf": 6000,
                    "peak_freq": 800, "peak_gain": 2, "peak_q": 1.2,
                }),
                ChainEffect(name="vc-delay", params={"time": "1/4", "feedback": 15, "mix": 8}),
                ChainEffect(name="vc-reverb", params={
                    "room": 25, "decay": 20, "damping": 60,
                    "mix": 8, "predelay": 30, "wetlpf": 4000,
                }),
            ],
            routing="serial",
            tags=["guitar", "acoustic", "electric"],
        ),
    }


# Initialize on module load
_init_builtin_chains()


# ── Chain Preset Manager ─────────────────────────────────────────────────

class ChainPresetManager:
    """Manager for plugin chain presets.

    Handles built-in chains and user-defined chain preset files.
    Chain presets are stored as YAML files in the chains directory.

    Args:
        chains_dir: Directory for user-defined chain preset files.
            Defaults to src/vcmix/presets/chains/.
    """

    def __init__(self, chains_dir: str | Path | None = None) -> None:
        """Initialize the chain preset manager.

        Args:
            chains_dir: Directory path for chain preset YAML files.
        """
        if chains_dir is None:
            chains_dir = Path(__file__).parent / "chains"
        self.chains_dir = Path(chains_dir)
        self._user_presets: dict[str, ChainPreset] = {}
        self._load_user_presets()

    def _load_user_presets(self) -> None:
        """Load user-defined chain presets from the chains directory."""
        if not self.chains_dir.exists():
            return

        for yaml_file in self.chains_dir.glob("*.yaml"):
            try:
                data = yaml.safe_load(yaml_file.read_text(encoding="utf-8"))
                if isinstance(data, dict) and "name" in data:
                    preset = ChainPreset.from_dict(data)
                    self._user_presets[preset.name] = preset
            except Exception:
                pass  # Skip malformed files

    def list_presets(self) -> list[str]:
        """List all available chain preset names.

        Returns:
            Sorted list of preset names (built-in + user-defined).
        """
        all_names = set(BUILTIN_CHAIN_PRESETS.keys()) | set(self._user_presets.keys())
        return sorted(all_names)

    def get(self, name: str) -> ChainPreset | None:
        """Get a chain preset by name.

        User-defined presets take precedence over built-in presets
        with the same name.

        Args:
            name: Preset name.

        Returns:
            ChainPreset instance, or None if not found.
        """
        if name in self._user_presets:
            return self._user_presets[name]
        return BUILTIN_CHAIN_PRESETS.get(name)

    def save(
        self,
        preset: ChainPreset,
        path: str | Path | None = None,
    ) -> Path:
        """Save a chain preset as a YAML file.

        Args:
            preset: ChainPreset to save.
            path: Optional custom file path. If None, saves to chains_dir.

        Returns:
            Path to the saved file.
        """
        if path is None:
            self.chains_dir.mkdir(parents=True, exist_ok=True)
            file_path = self.chains_dir / f"{preset.name}.yaml"
        else:
            file_path = Path(path)

        file_path.parent.mkdir(parents=True, exist_ok=True)
        with open(file_path, "w", encoding="utf-8") as f:
            yaml.dump(preset.to_dict(), f, default_flow_style=False, allow_unicode=True)

        # Update in-memory cache
        self._user_presets[preset.name] = preset
        return file_path

    def apply_to_track(
        self,
        preset: ChainPreset | str,
        track_config: dict[str, Any],
    ) -> dict[str, Any]:
        """Apply a chain preset to a track configuration.

        Replaces the track's effects with the chain preset's effects.
        Preserves track name and file; adds input/output gain if non-zero.

        Args:
            preset: ChainPreset instance or preset name string.
            track_config: Track config dict.

        Returns:
            Updated track config with chain effects applied.

        Raises:
            ValueError: If preset name is not found.
        """
        if isinstance(preset, str):
            chain = self.get(preset)
            if chain is None:
                raise ValueError(f"Chain preset not found: {preset}")
        else:
            chain = preset

        result = dict(track_config)
        result["effects"] = [e.to_dict() for e in chain.effects if e.enabled]

        if chain.input_gain_db != 0.0:
            result["input_gain_db"] = chain.input_gain_db
        if chain.output_gain_db != 0.0:
            result["output_gain_db"] = chain.output_gain_db

        return result

    def save_from_track(
        self,
        name: str,
        description: str,
        track_config: dict[str, Any],
        path: str | Path | None = None,
    ) -> Path:
        """Create a chain preset from a track's effect configuration.

        Args:
            name: Preset name.
            description: Human-readable description.
            track_config: Track config with "effects" key.
            path: Optional custom save path.

        Returns:
            Path to the saved preset file.
        """
        effects_data = track_config.get("effects", [])
        effects = [
            ChainEffect.from_dict(e) if isinstance(e, dict) else ChainEffect(name=str(e))
            for e in effects_data
        ]

        preset = ChainPreset(
            name=name,
            description=description,
            effects=effects,
            routing="serial",
        )
        return self.save(preset, path=path)

    def delete(self, name: str) -> bool:
        """Delete a user-defined chain preset.

        Cannot delete built-in presets.

        Args:
            name: Preset name to delete.

        Returns:
            True if deleted, False if not found or is built-in.
        """
        if name in BUILTIN_CHAIN_PRESETS:
            return False  # Cannot delete built-in presets

        if name not in self._user_presets:
            return False

        del self._user_presets[name]

        # Also delete the file if it exists
        file_path = self.chains_dir / f"{name}.yaml"
        if file_path.exists():
            file_path.unlink()

        return True


# ── Convenience Functions ────────────────────────────────────────────────

def list_chain_presets() -> list[str]:
    """List all available chain preset names.

    Returns:
        Sorted list of chain preset names.
    """
    manager = ChainPresetManager()
    return manager.list_presets()


def get_chain_preset(name: str) -> ChainPreset | None:
    """Get a chain preset by name.

    Args:
        name: Preset name.

    Returns:
        ChainPreset instance, or None if not found.
    """
    manager = ChainPresetManager()
    return manager.get(name)
