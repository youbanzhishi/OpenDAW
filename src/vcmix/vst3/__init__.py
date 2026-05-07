"""
vcmix.vst3 — VST3 plugin hosting interface for VCMix.

Provides Python-level access to VST3 plugins through the vst3_host CLI:
- Plugin scanning (discover installed VST3 plugins)
- Plugin proxying (load, set params, render via CLI subprocess)
- VST3Track integration (YAML-driven VST3 track rendering)
- VST3HostBridge (ctypes bridge to C++ host, Phase 14)
- VST3PluginProxy (high-level Python proxy, Phase 14)
- VST3ScannerV2 (enhanced scanner with caching, Phase 14)

Phase 9 + Phase 14 of OpenDAW.
"""

from vcmix.vst3.vst3_host_bridge import VST3HostBridge, VST3HostConfig
from vcmix.vst3.vst3_plugin_proxy import (
    ParameterEnumerator,
    ParamType,
    PresetInfo,
    PresetManager,
    StateSnapshotManager,
    VST3PluginProxy,
)
from vcmix.vst3.vst3_proxy import VST3Proxy
from vcmix.vst3.vst3_scanner import VST3PluginInfo, VST3Scanner
from vcmix.vst3.vst3_scanner_v2 import PluginMetadata, VST3ScannerV2
from vcmix.vst3.vst3_track import VST3Track

__all__ = [
    "VST3Scanner",
    "VST3PluginInfo",
    "VST3Proxy",
    "VST3Track",
    # Phase 14
    "VST3HostBridge",
    "VST3HostConfig",
    "VST3PluginProxy",
    "VST3ScannerV2",
    "PluginMetadata",
    "ParameterEnumerator",
    "ParamType",
    "PresetInfo",
    "PresetManager",
    "StateSnapshotManager",
]
