"""
plugins.py — /api/plugins endpoints for VCMix Web UI.

Lists available plugins and their parameter information.
Uses the same PluginRegistry as the CLI.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from vcmix.plugins.registry import PluginRegistry

router = APIRouter()


# ── Shared registry instance ─────────────────────────────────────────────

_registry = PluginRegistry()


@router.get("/plugins")
async def list_plugins():
    """List all registered plugins with their parameter schemas."""
    plugins = []
    for name in _registry.list_plugins():
        plugin = _registry.get(name)
        info = {
            "name": name,
            "description": getattr(plugin, "description", ""),
        }
        plugins.append(info)
    return {"plugins": plugins, "count": len(plugins)}


@router.get("/plugins/{name}")
async def get_plugin(name: str):
    """Get details for a specific plugin."""
    plugin = _registry.get(name)
    if plugin is None:
        raise HTTPException(status_code=404, detail=f"Plugin not found: {name}")

    return {
        "name": name,
        "description": getattr(plugin, "description", ""),
        "has_sidechain": hasattr(plugin, "process_with_sidechain"),
    }
