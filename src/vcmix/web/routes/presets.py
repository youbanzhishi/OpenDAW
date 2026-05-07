"""
presets.py — /api/presets endpoints for VCMix Web UI.

Manages built-in and user-defined effect chain presets.
Phase 9: Extended with chain preset endpoints.

Uses the same preset manager and chain preset manager as the CLI.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from vcmix.presets.chain_presets import (
    ChainPresetManager,
)
from vcmix.presets.manager import get_preset, list_presets, save_preset

router = APIRouter()


class SavePresetRequest(BaseModel):
    """Request body for saving a custom preset."""
    name: str = Field(..., description="Preset name")
    effects: list[dict[str, Any]] = Field(
        ..., description="Effect chain configuration"
    )


class ApplyChainRequest(BaseModel):
    """Request body for applying a chain preset to a track."""
    track_name: str = Field(..., description="Target track name")
    track_config: dict[str, Any] = Field(
        ..., description="Track config dict (must have 'name' and 'file')"
    )


# ── Shared chain preset manager ─────────────────────────────────────────

_chain_manager = ChainPresetManager()


# ── Single-effect Preset Endpoints ───────────────────────────────────────

@router.get("/presets")
async def list_all_presets():
    """List all available presets."""
    names = list_presets()
    preset_list = []
    for name in names:
        chain = get_preset(name)
        preset_list.append({
            "name": name,
            "effect_count": len(chain) if chain else 0,
        })
    return {"presets": preset_list, "count": len(preset_list)}


@router.get("/presets/{name}")
async def get_preset_detail(name: str):
    """Get the full effect chain for a specific preset."""
    chain = get_preset(name)
    if chain is None:
        raise HTTPException(status_code=404, detail=f"Preset not found: {name}")

    return {"name": name, "effects": chain, "effect_count": len(chain)}


@router.post("/presets")
async def create_preset(request: SavePresetRequest):
    """Save a custom preset."""
    try:
        path = save_preset(request.name, request.effects)
        return {"name": request.name, "saved": True, "path": str(path)}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# ── Chain Preset Endpoints (Phase 9) ────────────────────────────────────

@router.get("/presets/chains")
async def list_chain_presets_endpoint():
    """
    List all available chain presets.

    Chain presets contain complete effect chains with routing,
    gain staging, and metadata.
    """
    names = _chain_manager.list_presets()
    chain_list = []
    for name in names:
        chain = _chain_manager.get(name)
        if chain:
            chain_list.append({
                "name": name,
                "description": chain.description,
                "effect_count": chain.effect_count,
                "routing": chain.routing,
                "tags": chain.tags,
                "effect_names": chain.effect_names,
            })
    return {"chains": chain_list, "count": len(chain_list)}


@router.get("/presets/chains/{name}")
async def get_chain_preset_detail(name: str):
    """
    Get detailed information about a chain preset.

    Returns the full chain configuration including all effects,
    parameters, routing, and gain staging.
    """
    chain = _chain_manager.get(name)
    if chain is None:
        raise HTTPException(status_code=404, detail=f"Chain preset not found: {name}")

    return {
        "name": chain.name,
        "description": chain.description,
        "routing": chain.routing,
        "input_gain_db": chain.input_gain_db,
        "output_gain_db": chain.output_gain_db,
        "tags": chain.tags,
        "effects": [e.to_dict() for e in chain.effects],
        "effect_count": chain.effect_count,
        "effect_names": chain.effect_names,
    }


@router.post("/presets/chains/{name}/apply")
async def apply_chain_preset(name: str, request: ApplyChainRequest):
    """
    Apply a chain preset to a track configuration.

    Replaces the track's effects with the chain preset's effects.
    Returns the updated track configuration.
    """
    chain = _chain_manager.get(name)
    if chain is None:
        raise HTTPException(status_code=404, detail=f"Chain preset not found: {name}")

    try:
        updated = _chain_manager.apply_to_track(name, request.track_config)
        return {
            "chain_name": name,
            "track_name": request.track_name,
            "updated_config": updated,
            "applied": True,
            "effect_count": len(updated.get("effects", [])),
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Apply error: {e}")
