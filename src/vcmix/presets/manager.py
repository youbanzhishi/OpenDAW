"""
manager.py — Preset management for VCMix.

Handles built-in presets and user-defined preset save/load.
Presets are YAML files containing effect chains with parameters.

Usage:
    from vcmix.presets.manager import list_presets, get_preset, save_preset
    presets = list_presets()         # ["pop_vocal", "rock_vocal", ...]
    chain = get_preset("pop_vocal")  # [{"name": "vc-deesser", "params": {...}}, ...]
    save_preset("my_preset", chain, path="presets/")
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

# ── Built-in Presets ──────────────────────────────────────────────────────

BUILTIN_PRESETS: dict[str, list[dict[str, Any]]] = {
    "pop_vocal": [
        {
            "name": "vc-deesser",
            "params": {"threshold": -40, "reduction": -6},
        },
        {
            "name": "vc-eq",
            "params": {
                "low_cut": 80, "high_shelf": 8000,
                "peak_freq": 2500, "peak_gain": -2, "peak_q": 1.5,
            },
        },
        {
            "name": "vc-comp",
            "params": {"threshold": -24, "ratio": 3, "attack": 5, "release": 50},
        },
        {
            "name": "vc-reverb",
            "params": {
                "room": 30, "decay": 35, "damping": 50,
                "mix": 10, "predelay": 50, "wetlpf": 5000,
            },
        },
        {
            "name": "vc-delay",
            "params": {"time": "1/8d", "feedback": 12, "mix": 5},
        },
        {
            "name": "vc-limiter",
            "params": {"ceiling": -1},
        },
    ],
    "rock_vocal": [
        {
            "name": "vc-distortion",
            "params": {"mode": 0, "drive": 15, "mix": 8},
        },
        {
            "name": "vc-eq",
            "params": {
                "low_cut": 100, "high_shelf": 6000,
                "peak_freq": 3000, "peak_gain": 3, "peak_q": 1.2,
            },
        },
        {
            "name": "vc-comp",
            "params": {"threshold": -20, "ratio": 4, "attack": 2, "release": 30},
        },
        {
            "name": "vc-reverb",
            "params": {
                "room": 40, "decay": 25, "damping": 60,
                "mix": 12, "predelay": 30, "wetlpf": 4000,
            },
        },
        {
            "name": "vc-limiter",
            "params": {"ceiling": -1},
        },
    ],
    "podcast": [
        {
            "name": "vc-deesser",
            "params": {"threshold": -35, "reduction": -8},
        },
        {
            "name": "vc-eq",
            "params": {
                "low_cut": 80, "high_shelf": 10000,
                "peak_freq": 2000, "peak_gain": 2, "peak_q": 1.0,
            },
        },
        {
            "name": "vc-comp",
            "params": {"threshold": -18, "ratio": 3, "attack": 5, "release": 80},
        },
        {
            "name": "vc-limiter",
            "params": {"ceiling": -2},
        },
    ],
    "ballad_vocal": [
        {
            "name": "vc-deesser",
            "params": {"threshold": -40, "reduction": -5},
        },
        {
            "name": "vc-eq",
            "params": {
                "low_cut": 60, "high_shelf": 12000,
                "peak_freq": 2500, "peak_gain": -1.5, "peak_q": 1.5,
            },
        },
        {
            "name": "vc-comp",
            "params": {"threshold": -24, "ratio": 2.5, "attack": 10, "release": 80},
        },
        {
            "name": "vc-reverb",
            "params": {
                "room": 50, "decay": 50, "damping": 45,
                "mix": 15, "predelay": 80, "wetlpf": 6000,
            },
        },
        {
            "name": "vc-delay",
            "params": {"time": "1/4", "feedback": 8, "mix": 3},
        },
        {
            "name": "vc-limiter",
            "params": {"ceiling": -1},
        },
    ],
    "rap_vocal": [
        {
            "name": "vc-deesser",
            "params": {"threshold": -35, "reduction": -8},
        },
        {
            "name": "vc-eq",
            "params": {
                "low_cut": 80, "high_shelf": 8000,
                "peak_freq": 3000, "peak_gain": 2, "peak_q": 1.0,
            },
        },
        {
            "name": "vc-comp",
            "params": {"threshold": -20, "ratio": 4, "attack": 1, "release": 20},
        },
        {
            "name": "vc-limiter",
            "params": {"ceiling": -1},
        },
    ],
    "choir": [
        {
            "name": "vc-chorus",
            "params": {"rate": 1.5, "depth": 30, "voices": 3, "mix": 20},
        },
        {
            "name": "vc-reverb",
            "params": {
                "room": 60, "decay": 60, "damping": 40,
                "mix": 20, "predelay": 60, "wetlpf": 5000,
            },
        },
        {
            "name": "vc-limiter",
            "params": {"ceiling": -1},
        },
    ],
    "acoustic": [
        {
            "name": "vc-eq",
            "params": {
                "low_cut": 60, "high_shelf": 10000,
                "peak_freq": 200, "peak_gain": -3, "peak_q": 1.0,
            },
        },
        {
            "name": "vc-comp",
            "params": {"threshold": -18, "ratio": 2, "attack": 10, "release": 60},
        },
        {
            "name": "vc-reverb",
            "params": {
                "room": 35, "decay": 30, "damping": 55,
                "mix": 8, "predelay": 40, "wetlpf": 5500,
            },
        },
        {
            "name": "vc-limiter",
            "params": {"ceiling": -1},
        },
    ],
}


def list_presets() -> list[str]:
    """Return sorted list of all available preset names."""
    return sorted(BUILTIN_PRESETS.keys())


def get_preset(name: str) -> list[dict[str, Any]] | None:
    """
    Get a preset's effect chain configuration.

    Args:
        name: Preset name, e.g. "pop_vocal".

    Returns:
        List of effect configs, or None if preset not found.
    """
    return BUILTIN_PRESETS.get(name)


def apply_preset(
    track_config: dict[str, Any],
    preset_name: str,
) -> dict[str, Any]:
    """
    Apply a preset to a track config, replacing its effects.

    Args:
        track_config: Track config dict with at least "name" and "file".
        preset_name: Preset to apply.

    Returns:
        Updated track config with preset effects.
    """
    chain = get_preset(preset_name)
    if chain is None:
        raise ValueError(f"Unknown preset: {preset_name}")

    result = dict(track_config)
    result["effects"] = chain
    return result


def save_preset(
    name: str,
    chain: list[dict[str, Any]],
    path: str | Path = "presets/",
) -> Path:
    """
    Save a custom preset as a YAML file.

    Args:
        name: Preset name (used as filename).
        chain: Effect chain configuration.
        path: Directory to save the preset file.

    Returns:
        Path to the saved preset file.
    """
    save_dir = Path(path)
    save_dir.mkdir(parents=True, exist_ok=True)
    file_path = save_dir / f"{name}.yaml"

    data = {
        "name": name,
        "effects": chain,
    }
    with open(file_path, "w", encoding="utf-8") as f:
        yaml.dump(data, f, default_flow_style=False, allow_unicode=True)

    return file_path
