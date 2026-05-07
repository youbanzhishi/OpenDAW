"""
vcmix.vst3 — VST3 plugin hosting interface for VCMix.

Provides Python-level access to VST3 plugins through the vst3_host CLI:
- Plugin scanning (discover installed VST3 plugins)
- Plugin proxying (load, set params, render via CLI subprocess)
- VST3Track integration (YAML-driven VST3 track rendering)

Phase 9 of OpenDAW.
"""

from vcmix.vst3.vst3_proxy import VST3Proxy
from vcmix.vst3.vst3_scanner import VST3PluginInfo, VST3Scanner
from vcmix.vst3.vst3_track import VST3Track

__all__ = ["VST3Scanner", "VST3PluginInfo", "VST3Proxy", "VST3Track"]
