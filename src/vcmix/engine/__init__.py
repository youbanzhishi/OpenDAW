"""
vcmix.engine — Core rendering, analysis, auto-fix, bus, and auto-mix engines.

This subpackage provides:
    - Renderer: 7-step audio rendering pipeline with DataStream integration
    - Analyzer: Audio data analysis (RMS, Peak, spectrum, sibilance, RT60)
    - AutoFix: Adaptive gain staging and headroom correction
    - BusManager / SendReturnBus: Send/Return bus routing (Phase 2)
    - AutoMixer: Intelligent auto-mixing from dry vocal analysis
    - ReferenceMatcher: Reference track spectral/dynamic matching (Phase 6)
    - ArrangementStrategy: Section-aware mixing parameters (Phase 7)

Usage:
    from vcmix.engine import Renderer, Analyzer, AutoFix, AutoMixer
    from vcmix.engine import ReferenceMatcher

Dependencies: numpy, soundfile
"""

from vcmix.engine.analyzer import Analyzer
from vcmix.engine.autofix import AutoFix
from vcmix.engine.automix import AutoMixer
from vcmix.engine.bus import BusManager, SendReturnBus
from vcmix.engine.reference_matcher import (
    ReferenceMatcher,
    SpectralFeatures,
    MatchDifference,
    AdjustmentSuggestion,
)
from vcmix.engine.renderer import Renderer

__all__ = [
    "Renderer",
    "Analyzer",
    "AutoFix",
    "AutoMixer",
    "BusManager",
    "SendReturnBus",
    "ReferenceMatcher",
    "SpectralFeatures",
    "MatchDifference",
    "AdjustmentSuggestion",
]
