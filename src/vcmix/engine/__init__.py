"""
vcmix.engine — Core rendering, analysis, and auto-fix engines.

This subpackage provides:
    - Renderer: 7-step audio rendering pipeline
    - Analyzer: Audio data analysis (RMS, Peak, spectrum, sibilance, RT60)
    - AutoFix: Adaptive gain staging and headroom correction

Usage:
    from vcmix.engine import Renderer, Analyzer, AutoFix

Dependencies: numpy, soundfile
"""

from vcmix.engine.renderer import Renderer
from vcmix.engine.analyzer import Analyzer
from vcmix.engine.autofix import AutoFix

__all__ = ["Renderer", "Analyzer", "AutoFix"]
