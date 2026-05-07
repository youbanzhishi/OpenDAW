"""
presets — Built-in and user-defined mixing presets for VCMix.

Phase 9 addition: Chain presets for complete effect chain management.
Phase 12 addition: Mix presets for genre/scene-based complete mixing.
"""
from vcmix.presets.chain_presets import (
    ChainPreset,
    ChainPresetManager,
    get_chain_preset,
    list_chain_presets,
)
from vcmix.presets.manager import apply_preset, get_preset, list_presets, save_preset
from vcmix.presets.mix_presets import (
    EffectPreset,
    MasterMixPreset,
    MixPreset,
    TrackMixPreset,
    get_mix_preset,
    list_mix_presets,
    list_mix_presets_by_genre,
    suggest_mix_preset,
)

__all__ = [
    "list_presets", "get_preset", "apply_preset", "save_preset",
    "ChainPreset", "ChainPresetManager", "list_chain_presets", "get_chain_preset",
    "MixPreset", "TrackMixPreset", "EffectPreset", "MasterMixPreset",
    "get_mix_preset", "list_mix_presets", "list_mix_presets_by_genre",
    "suggest_mix_preset",
]
