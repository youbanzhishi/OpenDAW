"""Tests for vcmix.separation module."""
import numpy as np
import pytest
import soundfile as sf
from vcmix.separation.reverse_analyzer import analyze_stem, StemAnalysis, _generate_config


class TestAnalyzeStem:
    def test_vocal_stem_analysis(self, tmp_path):
        sr = 44100
        t = np.linspace(0, 1.0, sr, endpoint=False, dtype=np.float32)
        audio = 0.5 * np.sin(2 * np.pi * 440 * t)
        result = analyze_stem(audio, sr, "vocals")
        assert isinstance(result, StemAnalysis)
        assert result.name == "vocals"
        assert len(result.effects_chain) >= 2

    def test_drums_stem_analysis(self):
        sr = 44100
        t = np.linspace(0, 1.0, sr, endpoint=False, dtype=np.float32)
        audio = 0.5 * np.sin(2 * np.pi * 100 * t)
        result = analyze_stem(audio, sr, "drums")
        assert result.name == "drums"
        assert len(result.effects_chain) >= 2

    def test_bass_stem_analysis(self):
        sr = 44100
        t = np.linspace(0, 1.0, sr, endpoint=False, dtype=np.float32)
        audio = 0.3 * np.sin(2 * np.pi * 80 * t)
        result = analyze_stem(audio, sr, "bass")
        assert result.name == "bass"
        assert len(result.effects_chain) >= 2

    def test_silence_stem(self):
        sr = 44100
        audio = np.zeros(sr, dtype=np.float32)
        result = analyze_stem(audio, sr, "vocals")
        assert result.rms_db < -100


class TestGenerateConfig:
    def test_generates_valid_config(self):
        analysis = StemAnalysis(name="vocals", rms_db=-12, peak_db=-3)
        analysis.effects_chain = [{"name": "vc-gain", "params": {"gain": 3}}]
        ref = type("R", (), {"bpm": 120, "stems": {"vocals": analysis}})()
        config = _generate_config(ref)
        assert config["bpm"] == 120
        assert len(config["tracks"]) == 1
        assert config["tracks"][0]["name"] == "vocals"
