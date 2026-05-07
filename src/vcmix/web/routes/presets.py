"""
presets.py — /api/presets endpoints for VCMix Web UI.

Manages built-in and user-defined effect chain presets.
Uses the same preset manager as the CLI.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from vcmix.presets.manager import get_preset, list_presets, save_preset

router = APIRouter()


class SavePresetRequest(BaseModel):
    """Request body for saving a custom preset."""
    name: str = Field(..., description="Preset name")
    effects: list[dict[str, Any]] = Field(
        ..., description="Effect chain configuration"
    )


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
