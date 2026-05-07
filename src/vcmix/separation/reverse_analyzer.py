"""
reverse_analyzer.py - Reverse engineering mixing/arrangement from audio.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from vcmix.audio.io import read_audio
from vcmix.bpm.detector import detect_bpm
from vcmix.engine.analyzer import Analyzer


@dataclass
class StemAnalysis:
    name: str
    rms_db: float = 0.0
    peak_db: float = 0.0
    spectral_centroid: float = 0.0
    effects_chain: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class ReferenceAnalysis:
    bpm: float = 120.0
    key: str = ""
    stems: dict[str, StemAnalysis] = field(default_factory=dict)
    vcmix_config: dict[str, Any] = field(default_factory=dict)


def analyze_stem(audio: np.ndarray, sample_rate: int, stem_name: str) -> StemAnalysis:
    analyzer = Analyzer(sample_rate=sample_rate)
    result = StemAnalysis(name=stem_name)
    rms = analyzer.compute_rms(audio)
    peak = analyzer.compute_peak(audio)
    result.rms_db = 20 * np.log10(rms) if rms > 0 else -120.0
    result.peak_db = 20 * np.log10(peak) if peak > 0 else -120.0
    if stem_name == "vocals":
        result.effects_chain = _vocal_chain(audio, sample_rate, analyzer, result)
    elif stem_name == "drums":
        result.effects_chain = _drums_chain(analyzer, result)
    elif stem_name == "bass":
        result.effects_chain = _bass_chain(analyzer, result)
    else:
        result.effects_chain = _other_chain(audio, sample_rate, analyzer)
    return result


def _vocal_chain(audio, sr, analyzer, stem):
    chain = []
    sibilance = analyzer.compute_sibilance(audio)
    if sibilance > -25:
        chain.append({
            "name": "vc-deesser",
            "params": {"threshold": -40, "reduction": round(max(-3, sibilance + 20), 1)}
        })
    chain.append({"name": "vc-eq", "params": {"low_cut": 80, "high_shelf": 8000}})
    dynamic_range = stem.peak_db - stem.rms_db
    if dynamic_range > 12:
        chain.append({"name": "vc-comp", "params": {"threshold": -24,
                "ratio": min(4.0, dynamic_range / 5),
                "attack": 5, "release": 50
            }})
    chain.append({"name": "vc-limiter", "params": {"ceiling": -1}})
    return chain


def _drums_chain(analyzer, stem):
    return [
        {"name": "vc-eq", "params": {"low_cut": 30, "high_shelf": 8000}},
        {"name": "vc-comp", "params": {"threshold": -18, "ratio": 2.5, "attack": 1, "release": 20}},
        {"name": "vc-limiter", "params": {"ceiling": -1}},
    ]


def _bass_chain(analyzer, stem):
    return [
        {"name": "vc-eq", "params": {"low_cut": 30, "high_shelf": 5000}},
        {"name": "vc-comp", "params": {"threshold": -20, "ratio": 3, "attack": 10, "release": 80}},
        {"name": "vc-limiter", "params": {"ceiling": -1}},
    ]


def _other_chain(audio, sr, analyzer):
    chain = [{"name": "vc-eq", "params": {"low_cut": 60, "high_shelf": 8000}}]
    chain.append({"name": "vc-limiter", "params": {"ceiling": -1}})
    return chain


def analyze_reference(input_path, output_dir=None, separate=True):
    input_path = Path(input_path)
    if not input_path.exists():
        raise FileNotFoundError(f"Reference not found: {input_path}")
    result = ReferenceAnalysis()
    try:
        result.bpm = detect_bpm(str(input_path))
    except Exception:
        result.bpm = 120.0

    stems_paths = {}
    if separate:
        try:
            from vcmix.separation.demucs_wrapper import separate_stems
            stems_paths = separate_stems(input_path, output_dir=output_dir)
        except (ImportError, RuntimeError):
            stems_paths = {"full_mix": input_path}

    for stem_name, stem_path in stems_paths.items():
        try:
            audio, sr = read_audio(stem_path)
            result.stems[stem_name] = analyze_stem(audio, sr, stem_name)
        except Exception:
            pass

    result.vcmix_config = _generate_config(result)
    return result


def _generate_config(analysis):
    tracks = []
    levels = {}
    for stem_name, stem in analysis.stems.items():
        tracks.append({
            "name": stem_name,
            "file": f"{stem_name}.wav",
            "effects": stem.effects_chain,
        })
        level = min(1.0, max(0.1, 10 ** (stem.rms_db / 20) * 5))
        levels[stem_name] = round(level, 2)
    return {
        "name": "reference_analysis",
        "bpm": analysis.bpm,
        "sample_rate": 44100,
        "tracks": tracks,
        "master": {"levels": levels, "effects": [], "output": "reference_mix.wav"},
    }
