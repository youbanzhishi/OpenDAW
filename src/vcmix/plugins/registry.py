"""
registry.py — Plugin registry for dynamic discovery and loading.

Maintains a global registry of available plugins:
    - register(): Add a plugin class to the registry
    - create(): Instantiate a plugin by name with parameters
    - list_available(): Return all registered plugin names

Usage:
    from vcmix.plugins.registry import PluginRegistry
    registry = PluginRegistry()
    registry.register("gain", GainPlugin)
    plugin = registry.create("gain", name="track_gain", gain_db=-3.0)

Dependencies: vcmix.plugins.adapter
"""

from __future__ import annotations

from typing import Any, Type

from vcmix.plugins.adapter import PluginAdapter


class PluginRegistry:
    """
    Central registry for plugin classes.

    Allows dynamic registration and instantiation of plugins
    by their type name, enabling YAML-driven plugin selection.
    """

    def __init__(self) -> None:
        self._plugins: dict[str, Type[PluginAdapter]] = {}

    def register(self, name: str, plugin_class: Type[PluginAdapter]) -> None:
        """
        Register a plugin class under a given name.

        Args:
            name: Plugin type name (used in YAML config).
            plugin_class: PluginAdapter subclass.
        """
        self._plugins[name] = plugin_class

    def create(self, name: str, **kwargs: Any) -> PluginAdapter:
        """
        Create a plugin instance by registered name.

        Args:
            name: Registered plugin type name.
            **kwargs: Arguments passed to the plugin constructor.

        Returns:
            Instantiated PluginAdapter.

        Raises:
            KeyError: If the plugin name is not registered.
        """
        if name not in self._plugins:
            raise KeyError(f"Plugin not registered: {name!r}. Available: {list(self._plugins)}")
        return self._plugins[name](**kwargs)

    def list_available(self) -> list[str]:
        """Return list of all registered plugin names."""
        return sorted(self._plugins.keys())

    def is_registered(self, name: str) -> bool:
        """Check if a plugin name is registered."""
        return name in self._plugins
