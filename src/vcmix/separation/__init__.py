"""VCMix separation module — source separation and reverse analysis."""
from vcmix.separation.arrangement import ArrangementExtractor, Section, extract_arrangement
from vcmix.separation.arrangement_analyzer import (
    ArrangementAnalyzer,
    ArrangementSection,
    ArrangementTimeline,
    analyze_arrangement,
)
from vcmix.separation.config_generator import VCMixConfigGenerator
from vcmix.separation.demucs_engine import DemucsEngine
from vcmix.separation.demucs_wrapper import separate_stems
from vcmix.separation.reverse_analyzer import (
    CompressionParams,
    DelayParams,
    EQBand,
    EQCurve,
    PanParams,
    ReverbParams,
    ReverseMixAnalyzer,
    StemMixAnalysis,
    analyze_stem_mix,
)

__all__ = [
    # Legacy
    "separate_stems",
    "ArrangementExtractor",
    "Section",
    "extract_arrangement",
    # New Demucs engine
    "DemucsEngine",
    # Reverse analyzer
    "ReverseMixAnalyzer",
    "StemMixAnalysis",
    "EQBand",
    "EQCurve",
    "CompressionParams",
    "ReverbParams",
    "DelayParams",
    "PanParams",
    "analyze_stem_mix",
    # Arrangement analyzer
    "ArrangementAnalyzer",
    "ArrangementSection",
    "ArrangementTimeline",
    "analyze_arrangement",
    # Config generator
    "VCMixConfigGenerator",
]
