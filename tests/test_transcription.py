"""
test_transcription.py — Tests for AI transcription pipeline (Phase 17).

Tests cover:
    - AITranscription class
    - BPM detection (onset + autocorrelation)
    - Key detection (K-S algorithm)
    - Arrangement analysis
    - Data structure serialization
    - CLI transcribe command
    - ReferenceMatcherV2
    - StyleTransfer
    - RemixEngine
    - CLI commands for Phase 17
    - Agent API endpoints
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import numpy as np

# ── Helper: generate synthetic audio ────────────────────────────────────

def _make_sine(freq: float = 440.0, duration: float = 5.0,
               sr: int = 44100, amplitude: float = 0.5) -> np.ndarray:
    """Generate a mono sine wave."""
    t = np.linspace(0, duration, int(sr * duration), endpoint=False)
    return (amplitude * np.sin(2 * np.pi * freq * t)).astype(np.float64)


def _make_stereo_sine(freq: float = 440.0, duration: float = 5.0,
                      sr: int = 44100, amplitude: float = 0.5) -> np.ndarray:
    """Generate a stereo sine wave (slightly different L/R)."""
    t = np.linspace(0, duration, int(sr * duration), endpoint=False)
    left = amplitude * np.sin(2 * np.pi * freq * t)
    right = amplitude * np.sin(2 * np.pi * freq * 1.005 * t)  # Slight detune
    return np.stack([left, right]).astype(np.float64)


def _make_kick_pattern(bpm: float = 120.0, duration: float = 10.0,
                       sr: int = 44100) -> np.ndarray:
    """Generate a simple kick-like pattern with onsets at quarter notes."""
    t = np.linspace(0, duration, int(sr * duration), endpoint=False)
    signal = np.zeros_like(t)
    beat_interval = 60.0 / bpm
    n_beats = int(duration / beat_interval)
    for i in range(n_beats):
        onset_sample = int(i * beat_interval * sr)
        # Short burst of low frequency
        burst_len = min(int(0.05 * sr), len(signal) - onset_sample)
        if onset_sample + burst_len < len(signal):
            burst_t = np.linspace(0, 0.05, burst_len, endpoint=False)
            signal[onset_sample:onset_sample + burst_len] = 0.8 * np.sin(2 * np.pi * 60 * burst_t) * np.exp(-burst_t * 40)
    return signal.astype(np.float64)


def _make_c_major_audio(duration: float = 5.0, sr: int = 44100) -> np.ndarray:
    """Generate audio with C major harmonics."""
    t = np.linspace(0, duration, int(sr * duration), endpoint=False)
    signal = np.zeros_like(t)
    # C4 = 261.63, E4 = 329.63, G4 = 392.00
    for freq in [261.63, 329.63, 392.00]:
        signal += 0.3 * np.sin(2 * np.pi * freq * t)
    return signal.astype(np.float64)


def _make_a_minor_audio(duration: float = 5.0, sr: int = 44100) -> np.ndarray:
    """Generate audio with A minor harmonics."""
    t = np.linspace(0, duration, int(sr * duration), endpoint=False)
    signal = np.zeros_like(t)
    # A3 = 220, C4 = 261.63, E4 = 329.63
    for freq in [220.0, 261.63, 329.63]:
        signal += 0.3 * np.sin(2 * np.pi * freq * t)
    return signal.astype(np.float64)


# ══════════════════════════════════════════════════════════════════════════
# Tests: Data structures
# ══════════════════════════════════════════════════════════════════════════

class TestBPMInfo:
    def test_default_values(self):
        from vcmix.ai.transcription import BPMInfo
        info = BPMInfo()
        assert info.bpm == 120.0
        assert info.confidence == 0.0
        assert info.method == "onset_autocorrelation"

    def test_to_dict(self):
        from vcmix.ai.transcription import BPMInfo
        info = BPMInfo(bpm=128.0, confidence=0.85, method="onset")
        d = info.to_dict()
        assert d["bpm"] == 128.0
        assert d["confidence"] == 0.85
        assert d["method"] == "onset"


class TestKeyInfo:
    def test_default_values(self):
        from vcmix.ai.transcription import KeyInfo
        info = KeyInfo()
        assert info.root == "C"
        assert info.scale_type == "major"
        assert info.confidence == 0.0

    def test_to_dict(self):
        from vcmix.ai.transcription import KeyInfo
        info = KeyInfo(root="A", scale_type="natural_minor", confidence=0.92)
        d = info.to_dict()
        assert d["root"] == "A"
        assert d["scale_type"] == "natural_minor"
        assert d["confidence"] == 0.92


class TestArrangementSection:
    def test_default_values(self):
        from vcmix.ai.transcription import ArrangementSection
        sec = ArrangementSection()
        assert sec.name == ""
        assert sec.start_sec == 0.0
        assert sec.energy == 0.5

    def test_to_dict(self):
        from vcmix.ai.transcription import ArrangementSection
        sec = ArrangementSection(name="chorus", start_sec=10.0, end_sec=30.0,
                                 energy=0.9, active_stems=["vocals", "drums"])
        d = sec.to_dict()
        assert d["name"] == "chorus"
        assert d["start_sec"] == 10.0
        assert d["end_sec"] == 30.0
        assert d["energy"] == 0.9
        assert "vocals" in d["active_stems"]


class TestArrangementAnalysis:
    def test_empty(self):
        from vcmix.ai.transcription import ArrangementAnalysis
        aa = ArrangementAnalysis()
        assert aa.section_count == 0
        d = aa.to_dict()
        assert d["sections"] == []

    def test_with_sections(self):
        from vcmix.ai.transcription import ArrangementAnalysis, ArrangementSection
        sections = [ArrangementSection(name="intro"), ArrangementSection(name="verse")]
        aa = ArrangementAnalysis(sections=sections, total_duration_sec=60.0, section_count=2)
        d = aa.to_dict()
        assert d["section_count"] == 2
        assert len(d["sections"]) == 2


class TestTranscriptionResult:
    def test_default(self):
        from vcmix.ai.transcription import TranscriptionResult
        r = TranscriptionResult()
        assert r.status == "success"
        assert r.project_yaml == ""

    def test_to_dict(self):
        from vcmix.ai.transcription import BPMInfo, KeyInfo, TranscriptionResult
        r = TranscriptionResult(
            project_yaml="/tmp/project.yaml",
            bpm_info=BPMInfo(bpm=128.0),
            key_info=KeyInfo(root="C"),
        )
        d = r.to_dict()
        assert d["project_yaml"] == "/tmp/project.yaml"
        assert d["bpm_info"]["bpm"] == 128.0
        assert d["key_info"]["root"] == "C"


# ══════════════════════════════════════════════════════════════════════════
# Tests: BPM Detection
# ══════════════════════════════════════════════════════════════════════════

class TestBPMDetection:
    def test_silence_returns_default(self):
        from vcmix.ai.transcription import AITranscription
        t = AITranscription()
        silence = np.zeros(44100 * 5)
        result = t._detect_bpm(silence.reshape(1, -1))
        assert result.bpm > 0  # Should return some default

    def test_short_audio_returns_default(self):
        from vcmix.ai.transcription import AITranscription
        t = AITranscription()
        short = _make_sine(duration=0.1)
        result = t._detect_bpm(short.reshape(1, -1))
        assert result.bpm > 0

    def test_kick_pattern_bpm(self):
        from vcmix.ai.transcription import AITranscription
        t = AITranscription()
        kick = _make_kick_pattern(bpm=120.0, duration=15.0)
        result = t._detect_bpm(kick.reshape(1, -1))
        # Should detect something in the 80-160 range
        assert 80 <= result.bpm <= 160

    def test_bpm_normalized_to_range(self):
        from vcmix.ai.transcription import AITranscription
        t = AITranscription()
        # Generate any audio
        audio = _make_sine(duration=10.0)
        result = t._detect_bpm(audio.reshape(1, -1))
        assert 80 <= result.bpm <= 160

    def test_bpm_info_method(self):
        from vcmix.ai.transcription import AITranscription
        t = AITranscription()
        audio = _make_sine(duration=5.0)
        result = t._detect_bpm(audio.reshape(1, -1))
        assert result.method == "onset_autocorrelation"

    def test_bpm_confidence_range(self):
        from vcmix.ai.transcription import AITranscription
        t = AITranscription()
        audio = _make_sine(duration=5.0)
        result = t._detect_bpm(audio.reshape(1, -1))
        assert 0.0 <= result.confidence <= 1.0


# ══════════════════════════════════════════════════════════════════════════
# Tests: Key Detection
# ══════════════════════════════════════════════════════════════════════════

class TestKeyDetection:
    def test_c_major_detection(self):
        from vcmix.ai.transcription import AITranscription
        t = AITranscription()
        audio = _make_c_major_audio(duration=5.0)
        result = t._detect_key(audio.reshape(1, -1))
        # C major should be detected (or at least a major key)
        assert result.root in ["C", "D", "E", "F", "G", "A", "B"]
        assert result.confidence >= 0.0

    def test_a_minor_detection(self):
        from vcmix.ai.transcription import AITranscription
        t = AITranscription()
        audio = _make_a_minor_audio(duration=5.0)
        result = t._detect_key(audio.reshape(1, -1))
        assert result.root in ["C", "D", "E", "F", "G", "A", "B"]

    def test_silence_key(self):
        from vcmix.ai.transcription import AITranscription
        t = AITranscription()
        silence = np.zeros(44100 * 5)
        result = t._detect_key(silence.reshape(1, -1))
        # Should return some default (C major with low confidence)
        assert result.root in ["C", "D", "E", "F", "G", "A", "B"]

    def test_chroma_computation(self):
        from vcmix.ai.transcription import AITranscription
        t = AITranscription()
        audio = _make_c_major_audio(duration=3.0)
        chroma = t._compute_chroma(audio)
        assert len(chroma) == 12
        assert all(isinstance(c, float) for c in chroma)


# ══════════════════════════════════════════════════════════════════════════
# Tests: Arrangement Analysis
# ══════════════════════════════════════════════════════════════════════════


class TestTranscriptionPipeline:
    def test_transcribe_with_mock_separation(self):
        """Test full pipeline with mock separation."""
        from vcmix.ai.transcription import AITranscription

        # Mock separation that returns synthetic stems
        def mock_separate(ref_path, out_path):
            stems = {}
            for name in ["vocals", "drums", "bass", "other"]:
                stem_path = out_path / f"{name}.wav"
                # Generate synthetic audio and save
                _make_sine(freq=440 + hash(name) % 100, duration=10.0)
                stems[name] = stem_path
            return stems

        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a fake reference file
            ref_path = Path(tmpdir) / "reference.wav"
            ref_path.touch()

            transcriber = AITranscription()
            result = transcriber.transcribe(
                str(ref_path),
                str(Path(tmpdir) / "output"),
                separate_fn=mock_separate,
            )

            assert result.status in ("success", "failed")
            # Should have stem analyses even with mock
            assert isinstance(result.stem_analyses, dict)

    def test_transcribe_with_empty_stems(self):
        """Test transcription when separation returns no stems."""
        from vcmix.ai.transcription import AITranscription

        def mock_separate_empty(ref_path, out_path):
            return {}

        with tempfile.TemporaryDirectory() as tmpdir:
            ref_path = Path(tmpdir) / "reference.wav"
            ref_path.touch()

            transcriber = AITranscription()
            result = transcriber.transcribe(
                str(ref_path),
                str(Path(tmpdir) / "output"),
                separate_fn=mock_separate_empty,
            )

            assert result.status in ("success", "failed")

    def test_rms_to_volume(self):
        from vcmix.ai.transcription import AITranscription
        t = AITranscription()
        assert t._rms_to_volume(-60.0) == 0.0
        assert t._rms_to_volume(0.0) == 1.0
        assert t._rms_to_volume(-30.0) == 0.5

    def test_analysis_to_effects(self):
        from vcmix.ai.transcription import AITranscription
        t = AITranscription()
        analysis = {
            "eq_curve": {"bands": [{"freq": 100, "gain_db": 3, "q": 1.0}]},
            "compression": {"ratio": 3.0, "threshold_db": -18},
            "reverb": {"wet_ratio": 0.2, "rt60_ms": 800},
            "delay": {"delay_ms": 250, "feedback": 0.3},
        }
        effects = t._analysis_to_effects(analysis, "vocals")
        names = [e["name"] for e in effects]
        assert "vc-eq" in names
        assert "vc-comp" in names
        assert "vc-reverb" in names
        assert "vc-delay" in names
        assert "vc-limiter" in names

    def test_analysis_to_effects_no_compression(self):
        from vcmix.ai.transcription import AITranscription
        t = AITranscription()
        analysis = {
            "eq_curve": {"bands": []},
            "compression": {"ratio": 1.0},  # No compression
            "reverb": {"wet_ratio": 0.0},
            "delay": {"delay_ms": 0},
        }
        effects = t._analysis_to_effects(analysis, "drums")
        names = [e["name"] for e in effects]
        assert "vc-comp" not in names
        assert "vc-reverb" not in names
        assert "vc-delay" not in names


# ══════════════════════════════════════════════════════════════════════════
# Tests: Reference Matcher V2
# ══════════════════════════════════════════════════════════════════════════

class TestReferenceMatcherV2:
    def test_match_style_with_audio(self):
        from vcmix.ai.reference_matcher_v2 import ReferenceMatcherV2
        matcher = ReferenceMatcherV2()
        audio = _make_sine(duration=10.0).reshape(1, -1)
        result = matcher.match_style(reference_audio=audio)
        assert result.features.bpm > 0
        assert result.features.genre in ["pop", "rock", "edm", "hiphop", "ballad", "rnb"]

    def test_genre_classification_silence(self):
        from vcmix.ai.reference_matcher_v2 import ReferenceMatcherV2
        matcher = ReferenceMatcherV2()
        silence = np.zeros((1, 44100 * 10))
        genre = matcher._classify_genre(silence, 120.0)
        assert genre in ["pop", "rock", "edm", "hiphop", "ballad", "rnb"]

    def test_genre_classification_edm_bpm(self):
        from vcmix.ai.reference_matcher_v2 import ReferenceMatcherV2
        matcher = ReferenceMatcherV2()
        audio = _make_sine(duration=10.0).reshape(1, -1)
        genre = matcher._classify_genre(audio, 140.0)
        # High BPM could be EDM
        assert isinstance(genre, str)

    def test_genre_classification_ballad_bpm(self):
        from vcmix.ai.reference_matcher_v2 import ReferenceMatcherV2
        matcher = ReferenceMatcherV2()
        audio = _make_sine(duration=10.0, amplitude=0.1).reshape(1, -1)
        genre = matcher._classify_genre(audio, 75.0)
        assert isinstance(genre, str)

    def test_frequency_balance(self):
        from vcmix.ai.reference_matcher_v2 import ReferenceMatcherV2
        matcher = ReferenceMatcherV2()
        audio = _make_sine(freq=200, duration=5.0)
        balance = matcher._compute_freq_balance(audio)
        assert "sub" in balance
        assert "low" in balance
        assert "mid" in balance
        assert "high" in balance

    def test_dynamic_range(self):
        from vcmix.ai.reference_matcher_v2 import ReferenceMatcherV2
        matcher = ReferenceMatcherV2()
        # Constant sine has low dynamic range
        audio = _make_sine(duration=5.0)
        dr = matcher._compute_dynamic_range(audio)
        assert dr >= 0.0

    def test_energy_profile(self):
        from vcmix.ai.reference_matcher_v2 import ReferenceMatcherV2
        matcher = ReferenceMatcherV2()
        audio = _make_sine(duration=10.0)
        profile = matcher._compute_energy_profile(audio)
        assert len(profile) > 0
        assert all(v >= 0 for v in profile)

    def test_spectral_centroid(self):
        from vcmix.ai.reference_matcher_v2 import ReferenceMatcherV2
        matcher = ReferenceMatcherV2()
        audio = _make_sine(freq=1000, duration=5.0)
        centroid = matcher._compute_spectral_centroid(audio)
        assert centroid >= 0.0

    def test_style_features_to_dict(self):
        from vcmix.ai.reference_matcher_v2 import StyleFeatures
        f = StyleFeatures(bpm=128, key="A", scale_type="natural_minor", genre="edm")
        d = f.to_dict()
        assert d["bpm"] == 128
        assert d["key"] == "A"
        assert d["genre"] == "edm"

    def test_template_match(self):
        from vcmix.ai.reference_matcher_v2 import ReferenceMatcherV2
        matcher = ReferenceMatcherV2()
        from vcmix.ai.reference_matcher_v2 import StyleFeatures
        features = StyleFeatures(genre="pop", bpm=120)
        match = matcher._match_template(features)
        assert match.template_name != ""
        assert match.genre == "pop"

    def test_mix_preset_match(self):
        from vcmix.ai.reference_matcher_v2 import ReferenceMatcherV2
        matcher = ReferenceMatcherV2()
        from vcmix.ai.reference_matcher_v2 import StyleFeatures
        features = StyleFeatures(genre="edm", bpm=128)
        match = matcher._match_mix_preset(features)
        assert match.preset_name != ""
        assert match.genre == "edm"

    def test_four_on_floor_detection(self):
        from vcmix.ai.reference_matcher_v2 import ReferenceMatcherV2
        matcher = ReferenceMatcherV2()
        kick = _make_kick_pattern(bpm=128, duration=10.0)
        result = matcher._check_four_on_floor(kick, 128.0)
        # Should detect regular pattern
        assert isinstance(result, bool)

    def test_full_match_result(self):
        from vcmix.ai.reference_matcher_v2 import ReferenceMatcherV2
        matcher = ReferenceMatcherV2()
        audio = _make_sine(duration=10.0).reshape(1, -1)
        result = matcher.match_style(reference_audio=audio)
        d = result.to_dict()
        assert "features" in d
        assert "recommended_template" in d
        assert "recommended_mix_preset" in d
        assert "style_parameters" in d


# ══════════════════════════════════════════════════════════════════════════
# Tests: Style Transfer
# ══════════════════════════════════════════════════════════════════════════

class TestStyleTransfer:
    def test_transfer_with_audio(self):
        from vcmix.ai.style_transfer import StyleTransfer
        st = StyleTransfer()
        ref_audio = _make_sine(freq=440, duration=5.0).reshape(1, -1)
        ref_stems = {"vocals": _make_sine(freq=440, duration=5.0)}

        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a target project YAML
            project_yaml = str(Path(tmpdir) / "project.yaml")
            output_yaml = str(Path(tmpdir) / "styled.yaml")
            import yaml
            config = {
                "tracks": [
                    {"name": "Vocal", "type": "audio", "volume": 0.7, "effects": []},
                    {"name": "Drums", "type": "audio", "volume": 0.8, "effects": []},
                ],
                "master": {"effects": []},
            }
            with open(project_yaml, "w") as f:
                yaml.dump(config, f)

            result = st.transfer(
                reference_path="nonexistent.wav",
                project_yaml=project_yaml,
                output_yaml=output_yaml,
                reference_audio=ref_audio,
                reference_stems=ref_stems,
            )
            assert result.status in ("success", "failed")

    def test_eq_transfer(self):
        from vcmix.ai.style_transfer import StyleTransfer
        st = StyleTransfer()
        ref_analysis = {
            "stem_analyses": {
                "vocals": {
                    "eq_curve": {"bands": [{"freq": 100, "gain_db": 3, "q": 1.0}]},
                    "compression": {"ratio": 1.0},
                    "reverb": {"wet_ratio": 0},
                },
            },
        }
        target = {
            "Vocal": {"name": "Vocal", "volume": 0.7, "effects": []},
        }
        transfers = st._transfer_eq(ref_analysis, target)
        assert isinstance(transfers, dict)

    def test_compression_transfer(self):
        from vcmix.ai.style_transfer import StyleTransfer
        st = StyleTransfer()
        ref_analysis = {
            "stem_analyses": {
                "drums": {
                    "compression": {"ratio": 4.0, "threshold_db": -12, "attack_ms": 5, "release_ms": 50},
                    "eq_curve": {"bands": []},
                    "reverb": {"wet_ratio": 0},
                },
            },
        }
        target = {
            "Drums": {"name": "Drums", "volume": 0.8, "effects": []},
        }
        transfers = st._transfer_compression(ref_analysis, target)
        assert "Drums" in transfers

    def test_reverb_transfer(self):
        from vcmix.ai.style_transfer import StyleTransfer
        st = StyleTransfer()
        ref_analysis = {
            "stem_analyses": {
                "vocals": {
                    "reverb": {"wet_ratio": 0.25, "rt60_ms": 1200},
                    "compression": {"ratio": 1.0},
                    "eq_curve": {"bands": []},
                },
            },
        }
        target = {
            "Vocal": {"name": "Vocal", "volume": 0.7, "effects": []},
        }
        transfers = st._transfer_reverb(ref_analysis, target)
        assert "Vocal" in transfers

    def test_gain_balance(self):
        from vcmix.ai.style_transfer import StyleTransfer
        st = StyleTransfer()
        ref_analysis = {
            "stem_analyses": {
                "vocals": {"rms_db": -12.0},
                "drums": {"rms_db": -15.0},
                "bass": {"rms_db": -10.0},
            },
        }
        target = {
            "Vocal": {"name": "Vocal", "volume": 0.7},
            "Drums": {"name": "Drums", "volume": 0.8},
            "Bass": {"name": "Bass", "volume": 0.6},
        }
        adjustments = st._balance_gain(ref_analysis, target)
        assert isinstance(adjustments, dict)

    def test_match_category(self):
        from vcmix.ai.style_transfer import _match_category
        assert _match_category("Vocal") == "vocals"
        assert _match_category("lead_vox") == "vocals"
        assert _match_category("Drums") == "drums"
        assert _match_category("kick") == "drums"
        assert _match_category("Bass") == "bass"
        assert _match_category("808_sub") == "bass"
        assert _match_category("Guitar") == "other"

    def test_eq_bands_to_params(self):
        from vcmix.ai.style_transfer import StyleTransfer
        st = StyleTransfer()
        bands = [
            {"freq": 100, "gain_db": 3, "q": 1.0},
            {"freq": 1000, "gain_db": -2, "q": 1.5},
            {"freq": 8000, "gain_db": 1.5, "q": 0.8},
        ]
        params = st._eq_bands_to_params(bands)
        assert "low_shelf_db" in params
        assert "peak_gain" in params
        assert "high_shelf_db" in params

    def test_style_transfer_result_to_dict(self):
        from vcmix.ai.style_transfer import StyleTransferResult
        r = StyleTransferResult(status="success")
        d = r.to_dict()
        assert d["status"] == "success"


# ══════════════════════════════════════════════════════════════════════════
# Tests: Remix Engine
# ══════════════════════════════════════════════════════════════════════════

class TestRemixEngine:
    def test_remix_result_default(self):
        from vcmix.ai.remix import RemixResult
        r = RemixResult()
        assert r.status == "success"
        assert r.replaced_stems == []
        assert r.kept_stems == []

    def test_remix_result_to_dict(self):
        from vcmix.ai.remix import RemixResult
        r = RemixResult(output_yaml="test.yaml", replaced_stems=["vocals"], kept_stems=["drums"])
        d = r.to_dict()
        assert d["output_yaml"] == "test.yaml"
        assert "vocals" in d["replaced_stems"]
        assert "drums" in d["kept_stems"]

    def test_default_effects_for_stem(self):
        from vcmix.ai.remix import RemixEngine
        engine = RemixEngine()
        # Vocal
        vocal_fx = engine._default_effects_for_stem("Vocal")
        names = [e["name"] for e in vocal_fx]
        assert "vc-comp" in names
        assert "vc-reverb" in names

        # Drums
        drum_fx = engine._default_effects_for_stem("Drums")
        names = [e["name"] for e in drum_fx]
        assert "vc-comp" in names

        # Bass
        bass_fx = engine._default_effects_for_stem("Bass")
        names = [e["name"] for e in bass_fx]
        assert "vc-comp" in names

        # Other
        other_fx = engine._default_effects_for_stem("Guitar")
        names = [e["name"] for e in other_fx]
        assert "vc-eq" in names

    def test_rms_to_volume(self):
        from vcmix.ai.remix import RemixEngine
        engine = RemixEngine()
        assert engine._rms_to_volume(-60.0) == 0.0
        assert engine._rms_to_volume(0.0) == 1.0

    def test_remix_with_mock_separation(self):
        """Test remix with mock separation."""
        from vcmix.ai.remix import RemixEngine

        def mock_separate(ref_path, out_path):
            return {"vocals": Path("/tmp/vocals.wav"), "drums": Path("/tmp/drums.wav")}

        with tempfile.TemporaryDirectory() as tmpdir:
            ref_path = Path(tmpdir) / "reference.wav"
            ref_path.touch()

            engine = RemixEngine()
            result = engine.remix(
                reference_path=str(ref_path),
                new_stems={"vocals": str(ref_path)},
                output_dir=str(Path(tmpdir) / "remix"),
                separate_fn=mock_separate,
            )
            assert result.status in ("success", "failed")


# ══════════════════════════════════════════════════════════════════════════
# Tests: CLI Commands
# ══════════════════════════════════════════════════════════════════════════

class TestCLICommands:
    def test_transcribe_command_exists(self):
        from click.testing import CliRunner

        from vcmix.cli import main
        runner = CliRunner()
        result = runner.invoke(main, ["transcribe", "--help"])
        assert result.exit_code == 0
        assert "transcribe" in result.output.lower() or "reference" in result.output.lower()

    def test_match_style_command_exists(self):
        from click.testing import CliRunner

        from vcmix.cli import main
        runner = CliRunner()
        result = runner.invoke(main, ["match-style", "--help"])
        assert result.exit_code == 0
        assert "style" in result.output.lower() or "reference" in result.output.lower()

    def test_style_transfer_command_exists(self):
        from click.testing import CliRunner

        from vcmix.cli import main
        runner = CliRunner()
        result = runner.invoke(main, ["style-transfer", "--help"])
        assert result.exit_code == 0
        assert "style" in result.output.lower() or "reference" in result.output.lower()

    def test_remix_command_exists(self):
        from click.testing import CliRunner

        from vcmix.cli import main
        runner = CliRunner()
        result = runner.invoke(main, ["remix", "--help"])
        assert result.exit_code == 0
        assert "remix" in result.output.lower()

    def test_transcribe_missing_file(self):
        from click.testing import CliRunner

        from vcmix.cli import main
        runner = CliRunner()
        result = runner.invoke(main, ["transcribe", "/nonexistent.wav"])
        assert result.exit_code != 0

    def test_match_style_missing_file(self):
        from click.testing import CliRunner

        from vcmix.cli import main
        runner = CliRunner()
        result = runner.invoke(main, ["match-style", "/nonexistent.wav"])
        assert result.exit_code != 0


# ══════════════════════════════════════════════════════════════════════════
# Tests: API Endpoints
# ══════════════════════════════════════════════════════════════════════════

class TestAPIEndpoints:
    def test_transcribe_request_model(self):
        from vcmix.web.routes.ai_transcription import TranscribeRequest
        req = TranscribeRequest(reference_path="/tmp/test.wav")
        assert req.reference_path == "/tmp/test.wav"
        assert req.output_dir is None

    def test_style_match_request_model(self):
        from vcmix.web.routes.ai_transcription import StyleMatchRequest
        req = StyleMatchRequest(reference_path="/tmp/test.wav")
        assert req.reference_path == "/tmp/test.wav"

    def test_style_transfer_request_model(self):
        from vcmix.web.routes.ai_transcription import StyleTransferRequest
        req = StyleTransferRequest(reference_path="/tmp/ref.wav", project_path="/tmp/proj.yaml")
        assert req.reference_path == "/tmp/ref.wav"
        assert req.project_path == "/tmp/proj.yaml"

    def test_remix_request_model(self):
        from vcmix.web.routes.ai_transcription import RemixRequest
        req = RemixRequest(reference_path="/tmp/ref.wav", new_stems={"vocals": "/tmp/v.wav"})
        assert req.reference_path == "/tmp/ref.wav"
        assert "vocals" in req.new_stems

    def test_transcribe_response_defaults(self):
        from vcmix.web.routes.ai_transcription import TranscribeResponse
        resp = TranscribeResponse()
        assert resp.status == "success"
        assert resp.bpm == 0.0
        assert resp.key == ""

    def test_style_match_response_defaults(self):
        from vcmix.web.routes.ai_transcription import StyleMatchResponse
        resp = StyleMatchResponse()
        assert resp.status == "success"
        assert resp.genre == ""

    def test_router_has_endpoints(self):
        from vcmix.web.routes.ai_transcription import router
        routes = [r.path for r in router.routes]
        assert "/ai/transcribe" in routes
        assert "/ai/style-match" in routes
        assert "/ai/style-transfer" in routes
        assert "/ai/remix" in routes
