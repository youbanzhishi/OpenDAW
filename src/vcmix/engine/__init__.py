"""
vcmix.engine — Core rendering, analysis, and auto-fix engines.

This subpackage provides:
    - Renderer: Main audio rendering pipeline (insert chain → master → output)
    - Analyzer: Audio data analysis (RMS, Peak, spectrum, LUFS)
    - AutoFix: Adaptive parameter adjustment for gain staging and headroom

Usage:
    from vcmix.engine import Renderer, Analyzer, AutoFix

Dependencies: numpy, soundfile, librosa
"""

from vcmix.engine.renderer import Renderer
from vcmix.engine.analyzer import Analyzer
from vcmix.engine.autofix import AutoFix

__all__ = ["Renderer", "Analyzer", "AutoFix"]
