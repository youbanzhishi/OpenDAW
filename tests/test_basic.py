"""
test_basic.py — VCMix Phase 1 basic tests.

Tests core functionality without requiring VC CLI executables:
    - YAML parsing and validation
    - BPM note-value conversion
    - Audio I/O (WAV round-trip)
    - Mixer (multi-track mixing)
    - Analyzer (RMS/Peak/spectrum)
    - Plugin registry
    - CLI validate subcommand

Run: pytest tests/ -v

Dependencies: pytest, numpy, soundfile, pyyaml, pydantic
"""

import tempfile
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf


# ── Fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture
def sample_audio():
    """Generate a 1-second 440Hz sine wave at 44100Hz."""
    sr = 44100
    t = np.linspace(0, 1.0, sr, endpoint=False, dtype=np.float32)
    return (0.5 * np.sin(2 * np.pi * 440 * t), sr)


@pytest.fixture
def sample_wav(tmp_path, sample_audio):
    """Write sample audio to a temp WAV file and return path."""
    audio, sr = sample_audio
    path = tmp_path / "test_audio.wav"
    sf.write(str(path), audio, sr)
    return path


@pytest.fixture
def simple_yaml(tmp_path, sample_wav):
    """Create a simple VCMix YAML project file."""
    yaml_content = f"""
name: "Test Project"
bpm: 120
sample_rate: 44100

tracks:
  - name: vocal
    file: "{sample_wav.name}"
    volume: 0.9
    effects:
      - name: vc-gain
        params:
          gain: 3

master:
  levels:
    vocal: 1.0
  effects: []
  output: "test_output.wav"
"""
    yaml_path = tmp_path / "test_project.yaml"
    yaml_path.write_text(yaml_content, encoding="utf-8")
    return yaml_path


# ── BPM Sync Tests ──────────────────────────────────────────────────────────

class TestBPMSync:
    def test_quarter_note(self):
        from vcmix.bpm.sync import note_to_ms
        assert note_to_ms(120, "1/4") == 500.0

    def test_eighth_note(self):
        from vcmix.bpm.sync import note_to_ms
        assert note_to_ms(120, "1/8") == 250.0

    def test_dotted_eighth(self):
        from vcmix.bpm.sync import note_to_ms
        # 60000/120 * 4/8 * 1.5 = 500 * 0.5 * 1.5 = 375.0
        assert note_to_ms(120, "1/8d") == 375.0

    def test_triplet_eighth(self):
        from vcmix.bpm.sync import note_to_ms
        # 60000/120 * 4/8 * 2/3 = 166.7
        assert abs(note_to_ms(120, "1/8t") - 166.7) < 0.1

    def test_bpm62_dotted_eighth(self):
        """九万字 @BPM62: 1/8d = 181.5ms (key test case)"""
        from vcmix.bpm.sync import note_to_ms
        # 60000/62 * 4/8 * 1.5 = 967.74 * 0.5 * 1.5 = 725.8
        # Wait, let me recalculate:
        # quarter_ms = 60000/62 = 967.742
        # base = 967.742 * 4/8 * 1 = 483.871
        # dotted = 483.871 * 1.5 = 725.806
        assert abs(note_to_ms(62, "1/8d") - 725.8) < 0.2

    def test_plain_number_passthrough(self):
        from vcmix.bpm.sync import note_to_ms
        assert note_to_ms(120, 250) == 250.0

    def test_invalid_note_value(self):
        from vcmix.bpm.sync import note_to_ms
        with pytest.raises(ValueError):
            note_to_ms(120, "invalid")

    def test_resolve_bpm_times(self):
        from vcmix.bpm.sync import resolve_bpm_times
        result = resolve_bpm_times({"time": "1/8d", "feedback": 12}, bpm=120)
        assert result["time"] == 375.0
        assert result["feedback"] == 12


# ── Parser Tests ────────────────────────────────────────────────────────────

class TestParser:
    def test_parse_simple_yaml(self, simple_yaml, sample_wav):
        from vcmix.config.parser import parse_project
        # Need to adjust the file path in YAML to absolute
        content = simple_yaml.read_text()
        content = content.replace(sample_wav.name, str(sample_wav))
        simple_yaml.write_text(content, encoding="utf-8")

        cfg = parse_project(simple_yaml)
        assert cfg.name == "Test Project"
        assert cfg.bpm == 120.0
        assert len(cfg.tracks) == 1
        assert cfg.tracks[0].name == "vocal"

    def test_note_value_conversion_in_yaml(self, tmp_path, sample_wav):
        from vcmix.config.parser import parse_project
        yaml_content = f"""
name: "Note Test"
bpm: 120
sample_rate: 44100
tracks:
  - name: vocal
    file: "{sample_wav}"
    effects:
      - name: vc-delay
        params:
          time: "1/8d"
          feedback: 12
"""
        yaml_path = tmp_path / "note_test.yaml"
        yaml_path.write_text(yaml_content, encoding="utf-8")

        cfg = parse_project(yaml_path)
        # Note value should be converted to ms
        assert cfg.tracks[0].effects[0].params["time"] == 375.0
        assert cfg.tracks[0].effects[0].params["feedback"] == 12

    def test_bpm_normalization(self):
        from vcmix.config.parser import ProjectConfig
        # BPM > 200 should be halved
        cfg = ProjectConfig(name="test", bpm=240)
        assert cfg.bpm == 120.0


# ── Audio I/O Tests ─────────────────────────────────────────────────────────

class TestAudioIO:
    def test_wav_roundtrip(self, tmp_path, sample_audio):
        from vcmix.audio.io import read_audio, write_audio
        audio, sr = sample_audio
        path = tmp_path / "test.wav"
        write_audio(audio, path, sr)
        loaded, loaded_sr = read_audio(path)
        assert loaded_sr == sr
        np.testing.assert_allclose(loaded, audio, atol=1e-5)


# ── Mixer Tests ─────────────────────────────────────────────────────────────

class TestMixer:
    def test_mix_two_tracks(self):
        from vcmix.audio.mixer import Mixer
        mixer = Mixer()
        a = np.ones(1000, dtype=np.float32) * 0.5
        b = np.ones(1000, dtype=np.float32) * 0.3
        mixed = mixer.mix([a, b], levels=[1.0, 1.0])
        assert mixed.shape == (1000,)
        np.testing.assert_allclose(mixed, 0.8, atol=1e-5)

    def test_mix_with_levels(self):
        from vcmix.audio.mixer import Mixer
        mixer = Mixer()
        a = np.ones(1000, dtype=np.float32) * 0.5
        b = np.ones(1000, dtype=np.float32) * 0.3
        mixed = mixer.mix([a, b], levels=[0.8, 0.35])
        expected = 0.5 * 0.8 + 0.3 * 0.35
        np.testing.assert_allclose(mixed, expected, atol=1e-5)

    def test_mix_empty_raises(self):
        from vcmix.audio.mixer import Mixer
        mixer = Mixer()
        with pytest.raises(ValueError):
            mixer.mix([])


# ── Analyzer Tests ──────────────────────────────────────────────────────────

class TestAnalyzer:
    def test_rms_sine(self, sample_audio):
        from vcmix.engine.analyzer import Analyzer
        audio, _ = sample_audio
        analyzer = Analyzer()
        rms = analyzer.compute_rms(audio)
        # RMS of 0.5 amplitude sine = 0.5 / sqrt(2) ≈ 0.354
        assert abs(rms - 0.354) < 0.01

    def test_peak_sine(self, sample_audio):
        from vcmix.engine.analyzer import Analyzer
        audio, _ = sample_audio
        analyzer = Analyzer()
        peak = analyzer.compute_peak(audio)
        assert abs(peak - 0.5) < 0.01

    def test_spectrum_bands(self, sample_audio):
        from vcmix.engine.analyzer import Analyzer
        audio, _ = sample_audio
        analyzer = Analyzer(sample_rate=44100)
        bands = analyzer.compute_spectrum(audio)
        assert "mid" in bands
        assert "high" in bands
        # 440Hz is in mid band
        assert bands["mid"] > bands["high"]

    def test_sibilance_sine(self, sample_audio):
        from vcmix.engine.analyzer import Analyzer
        audio, _ = sample_audio
        analyzer = Analyzer()
        sib = analyzer.compute_sibilance(audio)
        # 440Hz sine has no energy in 5-9kHz sibilance band
        assert sib < 0.01


# ── Plugin Registry Tests ──────────────────────────────────────────────────

class TestRegistry:
    def test_registry_has_vc_plugins(self):
        from vcmix.plugins.registry import PluginRegistry
        reg = PluginRegistry()
        assert "vc-reverb" in reg
        assert "vc-eq" in reg
        assert len(reg.list_plugins()) == 18

    def test_registry_get_unknown(self):
        from vcmix.plugins.registry import PluginRegistry
        reg = PluginRegistry()
        assert reg.get("nonexistent") is None


# ── Meter Tests ─────────────────────────────────────────────────────────────

class TestMeter:
    def test_rms_db(self, sample_audio):
        from vcmix.audio.meter import Meter
        audio, sr = sample_audio
        meter = Meter(sample_rate=sr)
        rms_db = meter.rms_db(audio)
        # 0.5 amplitude sine ≈ -9 dBFS RMS
        assert abs(rms_db - (-9.03)) < 0.5

    def test_peak_db(self, sample_audio):
        from vcmix.audio.meter import Meter
        audio, sr = sample_audio
        meter = Meter(sample_rate=sr)
        peak_db = meter.peak_db(audio)
        # 0.5 amplitude ≈ -6 dBFS peak
        assert abs(peak_db - (-6.02)) < 0.1

    def test_full_report(self, sample_audio):
        from vcmix.audio.meter import Meter
        audio, sr = sample_audio
        meter = Meter(sample_rate=sr)
        report = meter.full_report(audio)
        assert "rms_db" in report
        assert "peak_db" in report
        assert "true_peak_db" in report
        assert "lufs" in report
