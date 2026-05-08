"""
vcmix.analysis — Audio analysis module for VCMix.

Provides comprehensive audio analysis for data-driven mixing:
    - Loudness analysis (EBU R128 simplified)
    - 1/3-octave spectrum analysis
    - BPM detection
    - Key detection (Krumhansl-Schmuckler)
    - Sibilance detection
    - Dynamics analysis with compression suggestions
    - Report generation (JSON/text/markdown)

Usage:
    from vcmix.analysis import AudioAnalyzer
    analyzer = AudioAnalyzer()
    result = analyzer.analyze("vocal.wav")
    result = analyzer.analyze("vocal.wav", items=["loudness", "bpm"])

Dependencies: numpy, scipy, librosa, soundfile
"""

from __future__ import annotations

from vcmix.analysis.analyzer import AudioAnalyzer
from vcmix.analysis.bpm import BPMDetector
from vcmix.analysis.dynamics import DynamicsAnalyzer
from vcmix.analysis.key_detection import KeyDetector
from vcmix.analysis.loudness import LoudnessAnalyzer
from vcmix.analysis.report import ReportGenerator
from vcmix.analysis.sibilance import SibilanceDetector
from vcmix.analysis.spectrum import SpectrumAnalyzer

__all__ = [
    "AudioAnalyzer",
    "LoudnessAnalyzer",
    "SpectrumAnalyzer",
    "BPMDetector",
    "KeyDetector",
    "SibilanceDetector",
    "DynamicsAnalyzer",
    "ReportGenerator",
]
