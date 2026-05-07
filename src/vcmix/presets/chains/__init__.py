"""
chains — Built-in plugin chain presets for VCMix.

Ready-made effect chain configurations for common track types:
vocal, drums, master, guitar. Can be applied to tracks via CLI or Python API.
"""
from vcmix.presets.chain_presets import (
    ChainPreset,
    ChainPresetManager,
    get_chain_preset,
    list_chain_presets,
)

__all__ = ["ChainPreset", "ChainPresetManager", "list_chain_presets", "get_chain_preset"]
