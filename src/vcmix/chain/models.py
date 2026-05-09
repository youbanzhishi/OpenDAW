"""
models.py — Data models for VC-Chain.

Defines the core data structures for chain configurations:
    - ChainStep: A single plugin step in a chain (plugin name + params)
    - MacroMapping: A single parameter mapping within a Macro
    - MacroConfig: A Macro controller definition (name + mappings)
    - ParallelBranch: A parallel processing branch (mix + chain)
    - MultibandBand: A multiband processing band (range + chain)
    - MultibandConfig: Multiband configuration (crossover + bands)
    - ChainConfig: Top-level chain configuration

Supports:
    - Serialization to/from dict and YAML
    - Legacy ChainPreset auto-upgrade
    - Validation (max 8 macros, max 5 multiband bands)

Dependencies: pyyaml>=6.0
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

# ── Constants ────────────────────────────────────────────────────────────

MAX_MACROS = 8
MAX_MULTIBAND_BANDS = 5
MAX_CHAIN_STEPS = 8  # Compatible with StudioRack


# ── ChainStep ────────────────────────────────────────────────────────────

@dataclass
class ChainStep:
    """A single plugin step in a chain.

    Attributes:
        plugin: Plugin name (e.g. "vc-comp", "vc-reverb").
        params: Plugin parameters dict.
        enabled: Whether this step is active.
    """

    plugin: str
    params: dict[str, Any] = field(default_factory=dict)
    enabled: bool = True

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain dict."""
        result: dict[str, Any] = {"plugin": self.plugin}
        if self.params:
            result["params"] = dict(self.params)
        if not self.enabled:
            result["enabled"] = False
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ChainStep:
        """Deserialize from a plain dict.

        Supports both new format (plugin:) and legacy format (name:).
        """
        plugin = data.get("plugin", data.get("name", "unknown"))
        return cls(
            plugin=plugin,
            params=data.get("params", {}),
            enabled=data.get("enabled", True),
        )


# ── MacroMapping ─────────────────────────────────────────────────────────

@dataclass
class MacroMapping:
    """A single parameter mapping within a Macro.

    Attributes:
        plugin: Target plugin name.
        param: Target parameter name.
        range: (min, max) mapping range.
        inverse: If True, mapping is reversed (knob right = param decreases).
    """

    plugin: str
    param: str
    range: tuple[float, float] = (0.0, 1.0)
    inverse: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain dict."""
        result: dict[str, Any] = {
            "plugin": self.plugin,
            "param": self.param,
            "range": list(self.range),
        }
        if self.inverse:
            result["inverse"] = True
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MacroMapping:
        """Deserialize from a plain dict."""
        range_val = data.get("range", [0.0, 1.0])
        if isinstance(range_val, (list, tuple)) and len(range_val) == 2:
            range_tuple = (float(range_val[0]), float(range_val[1]))
        else:
            range_tuple = (0.0, 1.0)
        return cls(
            plugin=data.get("plugin", ""),
            param=data.get("param", ""),
            range=range_tuple,
            inverse=data.get("inverse", False),
        )


# ── MacroConfig ──────────────────────────────────────────────────────────

@dataclass
class MacroConfig:
    """A Macro controller definition.

    A Macro maps a single knob (0.0-1.0) to one or more plugin parameters.
    Compatible with Waves StudioRack's 8-Macro system.

    Attributes:
        name: Display name for the Macro knob.
        mapping: List of parameter mappings.
    """

    name: str
    mapping: list[MacroMapping] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain dict."""
        result: dict[str, Any] = {"name": self.name}
        if self.mapping:
            result["mapping"] = [m.to_dict() for m in self.mapping]
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MacroConfig:
        """Deserialize from a plain dict."""
        mappings = [
            MacroMapping.from_dict(m) if isinstance(m, dict) else MacroMapping(plugin=str(m))
            for m in data.get("mapping", [])
        ]
        return cls(
            name=data.get("name", ""),
            mapping=mappings,
        )


# ── ParallelBranch ───────────────────────────────────────────────────────

@dataclass
class ParallelBranch:
    """A parallel processing branch.

    Attributes:
        mix: Wet signal mix level (0.0-1.0).
        chain: List of ChainStep in this parallel branch.
    """

    mix: float = 0.5
    chain: list[ChainStep] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain dict."""
        result: dict[str, Any] = {"mix": self.mix}
        if self.chain:
            result["chain"] = [s.to_dict() for s in self.chain]
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ParallelBranch:
        """Deserialize from a plain dict."""
        chain_steps = [
            ChainStep.from_dict(s) if isinstance(s, dict) else ChainStep(plugin=str(s))
            for s in data.get("chain", [])
        ]
        return cls(
            mix=float(data.get("mix", 0.5)),
            chain=chain_steps,
        )


# ── MultibandBand ────────────────────────────────────────────────────────

@dataclass
class MultibandBand:
    """A multiband processing band.

    Attributes:
        range: Frequency range (low_hz, high_hz).
        chain: List of ChainStep for this band.
    """

    range: tuple[float, float] = (0.0, 22050.0)
    chain: list[ChainStep] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain dict."""
        result: dict[str, Any] = {"range": list(self.range)}
        if self.chain:
            result["chain"] = [s.to_dict() for s in self.chain]
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MultibandBand:
        """Deserialize from a plain dict."""
        range_val = data.get("range", [0.0, 22050.0])
        if isinstance(range_val, (list, tuple)) and len(range_val) == 2:
            range_tuple = (float(range_val[0]), float(range_val[1]))
        else:
            range_tuple = (0.0, 22050.0)
        chain_steps = [
            ChainStep.from_dict(s) if isinstance(s, dict) else ChainStep(plugin=str(s))
            for s in data.get("chain", [])
        ]
        return cls(range=range_tuple, chain=chain_steps)


# ── MultibandConfig ──────────────────────────────────────────────────────

@dataclass
class MultibandConfig:
    """Multiband processing configuration.

    Attributes:
        crossover: Crossover frequency points (N bands = N-1 crossover points).
        bands: List of processing bands (max 5, compatible with StudioRack).
    """

    crossover: list[float] = field(default_factory=list)
    bands: list[MultibandBand] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain dict."""
        result: dict[str, Any] = {}
        if self.crossover:
            result["crossover"] = self.crossover
        if self.bands:
            result["bands"] = [b.to_dict() for b in self.bands]
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MultibandConfig:
        """Deserialize from a plain dict."""
        crossover = [float(f) for f in data.get("crossover", [])]
        bands = [
            MultibandBand.from_dict(b) if isinstance(b, dict) else MultibandBand()
            for b in data.get("bands", [])
        ]
        return cls(crossover=crossover, bands=bands)


# ── ChainConfig ──────────────────────────────────────────────────────────

@dataclass
class ChainConfig:
    """Top-level chain configuration.

    Compatible with Waves StudioRack and VCMix project YAML format.
    Supports legacy ChainPreset auto-upgrade.

    Attributes:
        name: Chain name.
        author: Chain author.
        version: Format version.
        description: Human-readable description.
        tags: Search/filter tags.
        macro: List of Macro controllers (max 8).
        serial: Serial processing chain.
        parallel: Parallel processing branches.
        multiband: Multiband processing configuration.
    """

    name: str
    author: str = ""
    version: str = "1.0"
    description: str = ""
    tags: list[str] = field(default_factory=list)
    macro: list[MacroConfig] = field(default_factory=list)
    serial: list[ChainStep] = field(default_factory=list)
    parallel: list[ParallelBranch] = field(default_factory=list)
    multiband: MultibandConfig | None = None

    @property
    def step_count(self) -> int:
        """Total number of processing steps across all routing modes."""
        count = len(self.serial)
        for branch in self.parallel:
            count += len(branch.chain)
        if self.multiband:
            for band in self.multiband.bands:
                count += len(band.chain)
        return count

    @property
    def macro_count(self) -> int:
        """Number of defined Macros."""
        return len(self.macro)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain dict for YAML storage."""
        result: dict[str, Any] = {
            "name": self.name,
            "version": self.version,
        }
        if self.author:
            result["author"] = self.author
        if self.description:
            result["description"] = self.description
        if self.tags:
            result["tags"] = self.tags

        # Macro
        if self.macro:
            result["macro"] = [m.to_dict() for m in self.macro]

        # Chain
        chain_dict: dict[str, Any] = {}
        if self.serial:
            chain_dict["serial"] = [s.to_dict() for s in self.serial]
        if self.parallel:
            chain_dict["parallel"] = [p.to_dict() for p in self.parallel]
        if self.multiband:
            mb = self.multiband.to_dict()
            if mb:
                chain_dict["multiband"] = mb
        if chain_dict:
            result["chain"] = chain_dict

        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ChainConfig:
        """Deserialize from a plain dict.

        Supports both new VC-Chain format and legacy ChainPreset format.

        Legacy format:
            name, description, routing, effects, tags, input_gain_db, output_gain_db

        New format:
            name, author, version, description, tags, macro, chain.serial,
            chain.parallel, chain.multiband
        """
        # Parse macros
        macros = [
            MacroConfig.from_dict(m) if isinstance(m, dict) else MacroConfig(name=str(m))
            for m in data.get("macro", [])
        ]

        # Parse chain — new format
        chain_data = data.get("chain", {})
        if isinstance(chain_data, dict):
            serial_steps = [
                ChainStep.from_dict(s) if isinstance(s, dict) else ChainStep(plugin=str(s))
                for s in chain_data.get("serial", [])
            ]
            parallel_branches = [
                ParallelBranch.from_dict(p) if isinstance(p, dict) else ParallelBranch()
                for p in chain_data.get("parallel", [])
            ]
            multiband_data = chain_data.get("multiband")
            multiband = MultibandConfig.from_dict(multiband_data) if multiband_data else None
        else:
            serial_steps = []
            parallel_branches = []
            multiband = None

        # Legacy format upgrade: effects → serial
        if not serial_steps and "effects" in data:
            serial_steps = [
                ChainStep.from_dict(e) if isinstance(e, dict) else ChainStep(plugin=str(e))
                for e in data.get("effects", [])
            ]

        # Enforce max macros
        if len(macros) > MAX_MACROS:
            macros = macros[:MAX_MACROS]

        # Enforce max multiband bands
        if multiband and len(multiband.bands) > MAX_MULTIBAND_BANDS:
            multiband.bands = multiband.bands[:MAX_MULTIBAND_BANDS]

        return cls(
            name=data.get("name", "unnamed"),
            author=data.get("author", ""),
            version=data.get("version", "1.0"),
            description=data.get("description", ""),
            tags=data.get("tags", []),
            macro=macros,
            serial=serial_steps,
            parallel=parallel_branches,
            multiband=multiband,
        )

    def to_yaml(self) -> str:
        """Serialize to YAML string."""
        return yaml.dump(self.to_dict(), default_flow_style=False, allow_unicode=True)

    @classmethod
    def from_yaml(cls, yaml_str: str) -> ChainConfig:
        """Deserialize from YAML string."""
        data = yaml.safe_load(yaml_str)
        if not isinstance(data, dict):
            raise ValueError("Chain config YAML must be a mapping")
        return cls.from_dict(data)

    @classmethod
    def from_yaml_file(cls, path: str | Path) -> ChainConfig:
        """Load chain config from a YAML file."""
        path = Path(path)
        return cls.from_yaml(path.read_text(encoding="utf-8"))

    def save_yaml(self, path: str | Path) -> Path:
        """Save chain config to a YAML file."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.to_yaml(), encoding="utf-8")
        return path

    def validate(self) -> list[str]:
        """Validate chain configuration and return list of issues."""
        issues: list[str] = []

        if not self.name:
            issues.append("Chain name is required")

        if len(self.macro) > MAX_MACROS:
            issues.append(f"Too many macros: {len(self.macro)} (max {MAX_MACROS})")

        if self.multiband and len(self.multiband.bands) > MAX_MULTIBAND_BANDS:
            issues.append(
                f"Too many multiband bands: {len(self.multiband.bands)} "
                f"(max {MAX_MULTIBAND_BANDS})"
            )

        # Validate macro mappings reference existing plugins
        serial_plugins = {s.plugin for s in self.serial}
        parallel_plugins = set()
        for branch in self.parallel:
            for step in branch.chain:
                parallel_plugins.add(step.plugin)
        all_plugins = serial_plugins | parallel_plugins

        for i, macro in enumerate(self.macro):
            for j, mapping in enumerate(macro.mapping):
                if mapping.plugin not in all_plugins:
                    issues.append(
                        f"Macro[{i}] '{macro.name}' mapping[{j}] references "
                        f"unknown plugin '{mapping.plugin}'"
                    )

        # Validate chain step count
        if self.step_count > MAX_CHAIN_STEPS * 2:
            issues.append(
                f"Total step count ({self.step_count}) exceeds recommended max "
                f"({MAX_CHAIN_STEPS * 2})"
            )

        return issues


def pascal_to_snake(name: str) -> str:
    """Convert PascalCase to snake_case.

    Examples:
        Threshold -> threshold
        HighGain -> high_gain
        AttackTime -> attack_time
    """
    # Insert underscore before uppercase letters that follow lowercase
    s1 = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", name)
    # Insert underscore between consecutive uppercase letters followed by lowercase
    s2 = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", s1)
    return s2.lower()
