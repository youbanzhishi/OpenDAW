"""
vcmix.plugins — Plugin adapter layer for VC plugin CLI integration.

This subpackage provides:
    - PluginAdapter: Abstract base class for all plugin adapters
    - VCPluginAdapter: Concrete adapter for VC plugin CLI subprocess calls
    - PluginRegistry: Plugin lookup and registration by name

Usage:
    from vcmix.plugins.registry import PluginRegistry
    registry = PluginRegistry()
    plugin = registry.get("vc-reverb")

Dependencies: numpy, subprocess
"""

from vcmix.plugins.adapter import PluginAdapter
from vcmix.plugins.registry import PluginRegistry

__all__ = ["PluginAdapter", "PluginRegistry"]
