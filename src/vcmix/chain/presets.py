"""
presets.py — Built-in chain presets for VC-Chain.

Provides 5 production-ready chain presets with realistic parameter values
based on real-world mixing scenarios:

    1. vocal-chain: Vocal close-mic chain (DeEsser -> EQ -> Comp -> Reverb)
    2. drum-bus-chain: Drum bus chain (EQ -> Comp -> Limiter)
    3. bass-chain: Bass processing chain (EQ -> Comp -> Saturator)
    4. master-chain: Master bus chain (EQ -> Comp -> Limiter -> Reverb)
    5. parallel-comp-chain: Parallel compression chain (dry + heavy comp wet)

Each preset includes:
    - Realistic parameter values based on professional mixing practices
    - Up to 8 Macro controls for quick adjustments
    - Tags for search/filter in ChainVerse

Usage:
    from vcmix.chain.presets import list_builtin_presets, get_builtin_preset

    names = list_builtin_presets()  # ["vocal-chain", "drum-bus-chain", ...]
    chain = get_builtin_preset("vocal-chain")

Dependencies: vcmix.chain.models
"""

from __future__ import annotations

from typing import Any

from vcmix.chain.models import (
    ChainConfig,
    ChainStep,
    MacroConfig,
    MacroMapping,
    ParallelBranch,
)

# ── Built-in Presets ─────────────────────────────────────────────────────

_BUILTIN_PRESETS: dict[str, ChainConfig] = {}


def _init_presets() -> None:
    """Initialize built-in chain presets."""
    global _BUILTIN_PRESETS

    # 1. Vocal close-mic chain
    _BUILTIN_PRESETS["vocal-chain"] = ChainConfig(
        name="vocal-chain",
        author="VC-Chain",
        version="1.0",
        description="Vocal close-mic processing: DeEsser -> EQ -> Comp -> Reverb",
        tags=["vocal", "pop", "close-mic", "standard"],
        macro=[
            MacroConfig(
                name="Brightness",
                mapping=[
                    MacroMapping(plugin="vc-eq", param="high_gain", range=(0, 6)),
                    MacroMapping(plugin="vc-eq", param="high_shelf", range=(6000, 16000)),
                ],
            ),
            MacroConfig(
                name="Compression",
                mapping=[
                    MacroMapping(plugin="vc-comp", param="ratio", range=(2, 8)),
                ],
            ),
            MacroConfig(
                name="Space",
                mapping=[
                    MacroMapping(plugin="vc-reverb", param="mix", range=(5, 30)),
                ],
            ),
            MacroConfig(
                name="DeEss",
                mapping=[
                    MacroMapping(plugin="vc-deesser", param="threshold", range=(-45, -20)),
                ],
                # Inverse: more knob = higher threshold = less de-essing
            ),
            MacroConfig(
                name="Body",
                mapping=[
                    MacroMapping(plugin="vc-eq", param="peak_gain", range=(-3, 4)),
                ],
            ),
            MacroConfig(
                name="Presence",
                mapping=[
                    MacroMapping(plugin="vc-comp", param="makeup", range=(0, 6)),
                ],
            ),
        ],
        serial=[
            ChainStep(
                plugin="vc-deesser",
                params={"threshold": -35, "reduction": -6, "frequency": 6500},
            ),
            ChainStep(
                plugin="vc-eq",
                params={
                    "low_cut": 80,
                    "high_shelf": 10000,
                    "high_gain": 2.5,
                    "peak_freq": 2500,
                    "peak_gain": 1,
                    "peak_q": 1.5,
                },
            ),
            ChainStep(
                plugin="vc-comp",
                params={
                    "threshold": -22,
                    "ratio": 3.5,
                    "attack": 5,
                    "release": 50,
                    "makeup": 2,
                },
            ),
            ChainStep(
                plugin="vc-reverb",
                params={
                    "room": 25,
                    "decay": 30,
                    "damping": 55,
                    "mix": 12,
                    "predelay": 40,
                    "wetlpf": 6000,
                },
            ),
        ],
    )

    # 2. Drum bus chain
    _BUILTIN_PRESETS["drum-bus-chain"] = ChainConfig(
        name="drum-bus-chain",
        author="VC-Chain",
        version="1.0",
        description="Drum bus processing: EQ -> Comp -> Limiter",
        tags=["drums", "bus", "glue", "parallel"],
        macro=[
            MacroConfig(
                name="Punch",
                mapping=[
                    MacroMapping(plugin="vc-comp", param="attack", range=(1, 30)),
                    MacroMapping(plugin="vc-comp", param="ratio", range=(2, 6)),
                ],
            ),
            MacroConfig(
                name="Low End",
                mapping=[
                    MacroMapping(plugin="vc-eq", param="low_gain", range=(-3, 6)),
                ],
            ),
            MacroConfig(
                name="Snap",
                mapping=[
                    MacroMapping(plugin="vc-eq", param="high_gain", range=(0, 4)),
                ],
            ),
            MacroConfig(
                name="Glue",
                mapping=[
                    MacroMapping(plugin="vc-comp", param="threshold", range=(-24, -6)),
                ],
            ),
        ],
        serial=[
            ChainStep(
                plugin="vc-eq",
                params={
                    "low_shelf": 60,
                    "low_gain": 3,
                    "peak_freq": 400,
                    "peak_gain": -2,
                    "peak_q": 1.0,
                    "high_shelf": 8000,
                    "high_gain": 2,
                },
            ),
            ChainStep(
                plugin="vc-comp",
                params={
                    "threshold": -14,
                    "ratio": 3,
                    "attack": 5,
                    "release": 30,
                    "makeup": 2,
                },
            ),
            ChainStep(
                plugin="vc-limiter",
                params={"ceiling": -1, "release": 20},
            ),
        ],
    )

    # 3. Bass processing chain
    _BUILTIN_PRESETS["bass-chain"] = ChainConfig(
        name="bass-chain",
        author="VC-Chain",
        version="1.0",
        description="Bass processing: EQ -> Comp -> Saturator",
        tags=["bass", "low-end", "warmth", "consistency"],
        macro=[
            MacroConfig(
                name="Sub Level",
                mapping=[
                    MacroMapping(plugin="vc-eq", param="low_gain", range=(-6, 6)),
                ],
            ),
            MacroConfig(
                name="Tightness",
                mapping=[
                    MacroMapping(plugin="vc-comp", param="ratio", range=(2, 8)),
                    MacroMapping(plugin="vc-comp", param="attack", range=(1, 20)),
                ],
            ),
            MacroConfig(
                name="Grind",
                mapping=[
                    MacroMapping(plugin="vc-saturator", param="drive", range=(1, 8)),
                ],
            ),
            MacroConfig(
                name="Definition",
                mapping=[
                    MacroMapping(plugin="vc-eq", param="high_gain", range=(-2, 4)),
                ],
            ),
        ],
        serial=[
            ChainStep(
                plugin="vc-eq",
                params={
                    "low_cut": 30,
                    "low_shelf": 80,
                    "low_gain": 2,
                    "peak_freq": 800,
                    "peak_gain": 1.5,
                    "peak_q": 1.2,
                    "high_shelf": 3000,
                    "high_gain": 1,
                },
            ),
            ChainStep(
                plugin="vc-comp",
                params={
                    "threshold": -16,
                    "ratio": 4,
                    "attack": 8,
                    "release": 80,
                    "makeup": 1,
                },
            ),
            ChainStep(
                plugin="vc-saturator",
                params={"drive": 3, "mix": 20},
            ),
        ],
    )

    # 4. Master bus chain
    _BUILTIN_PRESETS["master-chain"] = ChainConfig(
        name="master-chain",
        author="VC-Chain",
        version="1.0",
        description="Master bus processing: EQ -> Comp -> Limiter",
        tags=["master", "bus", "final", "loudness"],
        macro=[
            MacroConfig(
                name="Tonal Balance",
                mapping=[
                    MacroMapping(plugin="vc-eq", param="high_gain", range=(-2, 3)),
                ],
            ),
            MacroConfig(
                name="Glue",
                mapping=[
                    MacroMapping(plugin="vc-comp", param="threshold", range=(-18, -4)),
                ],
            ),
            MacroConfig(
                name="Loudness",
                mapping=[
                    MacroMapping(plugin="vc-limiter", param="ceiling", range=(-3, -0.5)),
                ],
            ),
            MacroConfig(
                name="Warmth",
                mapping=[
                    MacroMapping(plugin="vc-eq", param="low_gain", range=(-2, 3)),
                ],
            ),
        ],
        serial=[
            ChainStep(
                plugin="vc-eq",
                params={
                    "low_cut": 25,
                    "low_shelf": 50,
                    "low_gain": 0.5,
                    "peak_freq": 200,
                    "peak_gain": -1,
                    "peak_q": 0.7,
                    "high_shelf": 12000,
                    "high_gain": 1,
                },
            ),
            ChainStep(
                plugin="vc-comp",
                params={
                    "threshold": -10,
                    "ratio": 2,
                    "attack": 15,
                    "release": 100,
                    "makeup": 1,
                },
            ),
            ChainStep(
                plugin="vc-limiter",
                params={"ceiling": -1, "release": 50},
            ),
        ],
    )

    # 5. Parallel compression chain
    _BUILTIN_PRESETS["parallel-comp-chain"] = ChainConfig(
        name="parallel-comp-chain",
        author="VC-Chain",
        version="1.0",
        description="Parallel compression: dry + heavy compression wet",
        tags=["parallel", "compression", "glue", "drums", "vocal"],
        macro=[
            MacroConfig(
                name="Wet Mix",
                mapping=[
                    MacroMapping(plugin="vc-comp", param="mix", range=(10, 50)),
                ],
                # This maps to the parallel branch mix instead
            ),
            MacroConfig(
                name="Squash",
                mapping=[
                    MacroMapping(plugin="vc-comp", param="ratio", range=(4, 20)),
                ],
            ),
            MacroConfig(
                name="Attack",
                mapping=[
                    MacroMapping(plugin="vc-comp", param="attack", range=(0.1, 20)),
                ],
            ),
            MacroConfig(
                name="Release",
                mapping=[
                    MacroMapping(plugin="vc-comp", param="release", range=(10, 200)),
                ],
            ),
        ],
        serial=[],  # No serial processing — all in parallel
        parallel=[
            ParallelBranch(
                mix=0.3,
                chain=[
                    ChainStep(
                        plugin="vc-comp",
                        params={
                            "threshold": -30,
                            "ratio": 10,
                            "attack": 1,
                            "release": 50,
                            "makeup": 8,
                        },
                    ),
                ],
            ),
        ],
    )


# Initialize on module load
_init_presets()


# ── Public API ───────────────────────────────────────────────────────────

def list_builtin_presets() -> list[str]:
    """List all built-in chain preset names.

    Returns:
        Sorted list of preset names.
    """
    return sorted(_BUILTIN_PRESETS.keys())


def get_builtin_preset(name: str) -> ChainConfig | None:
    """Get a built-in chain preset by name.

    Args:
        name: Preset name.

    Returns:
        ChainConfig instance, or None if not found.
    """
    return _BUILTIN_PRESETS.get(name)


def get_all_builtin_presets() -> dict[str, ChainConfig]:
    """Get all built-in chain presets.

    Returns:
        Dict of name -> ChainConfig.
    """
    return dict(_BUILTIN_PRESETS)
