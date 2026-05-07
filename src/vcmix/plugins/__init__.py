"""
vcmix.plugins — Plugin adapter framework for VCMix.

This subpackage provides:
    - adapter: PluginAdapter base class for all plugin types
    - registry: Plugin registry for dynamic discovery and loading
    - vc_plugins: VC Plugin CLI adapters (wraps AudioFX CLI tools)

Usage:
    from vcmix.plugins import PluginAdapter, PluginRegistry

Dependencies: subprocess (for VC CLI adapters), pathlib
"""

from vcmix.plugins.adapter import PluginAdapter
from vcmix.plugins.registry import PluginRegistry

__all__ = ["PluginAdapter", "PluginRegistry"]
