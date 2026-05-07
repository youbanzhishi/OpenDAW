"""
registry.py — Plugin registry for VCMix.

Central registry that maps plugin names to their adapter instances.
Supports:
    - Built-in VC plugin CLI adapters (10 plugins)
    - Native Python adapters (future)
    - Custom user-registered adapters

Usage:
    from vcmix.plugins.registry import PluginRegistry
    registry = PluginRegistry()
    plugin = registry.get("vc-reverb")
    audio = plugin.process(audio, {"room": 30, "mix": 10}, 44100)

Dependencies: vcmix.plugins.adapter, vcmix.plugins.vc_plugins
"""

from __future__ import annotations

from vcmix.plugins.adapter import PluginAdapter
from vcmix.plugins.vc_plugins import VCPluginAdapter


class PluginRegistry:
    """
    Plugin registry — maps plugin names to adapter instances.

    On construction, auto-registers all 10 VC CLI plugin adapters.
    Additional plugins can be registered manually.
    """

    # All known VC plugin names
    VC_PLUGIN_NAMES = [
        "vc-eq", "vc-comp", "vc-gain", "vc-deesser",
        "vc-saturator", "vc-surgicaldeesser",
        "vc-limiter", "vc-delay", "vc-reverb",
        "vc-dynamiceq", "vc-smooth", "vc-distortion",
        "vc-noise", "vc-tune", "vc-gate", "vc-chorus",
        "vc-stereo", "vc-pitchshift",
    ]

    def __init__(self) -> None:
        self._plugins: dict[str, PluginAdapter] = {}
        self._register_vc_plugins()

    def _register_vc_plugins(self) -> None:
        """Register all built-in VC CLI plugin adapters."""
        for name in self.VC_PLUGIN_NAMES:
            self._plugins[name] = VCPluginAdapter(name)

    def register(self, name: str, adapter: PluginAdapter) -> None:
        """
        Register a custom plugin adapter.

        Args:
            name: Plugin identifier.
            adapter: PluginAdapter instance.
        """
        self._plugins[name] = adapter

    def get(self, name: str) -> PluginAdapter | None:
        """
        Look up a plugin adapter by name.

        Args:
            name: Plugin identifier, e.g. "vc-reverb".

        Returns:
            PluginAdapter instance, or None if not found.
        """
        return self._plugins.get(name)

    def list_plugins(self) -> list[str]:
        """Return sorted list of all registered plugin names."""
        return sorted(self._plugins.keys())

    def __contains__(self, name: str) -> bool:
        return name in self._plugins

    def __repr__(self) -> str:
        return f"PluginRegistry(plugins={self.list_plugins()})"
