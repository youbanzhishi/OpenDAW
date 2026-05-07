"""
vcmix.engine — Core rendering, analysis, auto-fix, bus, and auto-mix engines.

This subpackage provides:
    - Renderer: 7-step audio rendering pipeline with DataStream integration
    - Analyzer: Audio data analysis (RMS, Peak, spectrum, sibilance, RT60)
    - AutoFix: Adaptive gain staging and headroom correction
    - BusManager / SendReturnBus: Send/Return bus routing (Phase 2)
    - AutoMixer: Intelligent auto-mixing from dry vocal analysis (Phase 4)

Usage:
    from vcmix.engine import Renderer, Analyzer, AutoFix, AutoMixer

Dependencies: numpy, soundfile
"""

from vcmix.engine.analyzer import Analyzer
from vcmix.engine.autofix import AutoFix
from vcmix.engine.automix import AutoMixer
from vcmix.engine.bus import BusManager, SendReturnBus
from vcmix.engine.renderer import Renderer

__all__ = ["Renderer", "Analyzer", "AutoFix", "AutoMixer", "BusManager", "SendReturnBus"]
