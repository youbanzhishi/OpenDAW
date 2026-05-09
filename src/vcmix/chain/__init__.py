"""
vcmix.chain — VC-Chain: Waves StudioRack-compatible mixing chain system.

Provides:
    - ChainConfig: Full chain definition with serial/parallel/multiband routing
    - MacroConfig: 8-Macro control system (compatible with StudioRack)
    - ChainEngine: Chain execution engine (serial/parallel/multiband processing)
    - .xps import/export: Waves preset file compatibility
    - ChainVerse: Community sharing interface
    - Built-in presets: 5 production-ready chain presets

YAML format is the native chain definition format, compatible with VCMix
project files. Legacy ChainPreset YAML files are auto-upgraded on load.

Usage:
    from vcmix.chain import ChainConfig, ChainEngine

    chain = ChainConfig.from_yaml_file("cla-vocal.yaml")
    engine = ChainEngine(chain)
    output = engine.process(audio, sample_rate=44100)
"""

from vcmix.chain.models import (
    ChainConfig,
    ChainStep,
    MacroConfig,
    MacroMapping,
    ParallelBranch,
    MultibandConfig,
    MultibandBand,
)
from vcmix.chain.engine import ChainEngine
from vcmix.chain.macro import MacroController
from vcmix.chain.presets import list_builtin_presets, get_builtin_preset

__all__ = [
    "ChainConfig",
    "ChainStep",
    "MacroConfig",
    "MacroMapping",
    "ParallelBranch",
    "MultibandConfig",
    "MultibandBand",
    "ChainEngine",
    "MacroController",
    "list_builtin_presets",
    "get_builtin_preset",
]
