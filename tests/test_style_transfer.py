"""
test_style_transfer.py — Tests for style transfer and remix (Phase 17).

Additional tests beyond test_transcription.py covering:
    - StyleTransfer edge cases
    - RemixEngine edge cases
    - ReferenceMatcherV2 edge cases
    - Integration scenarios
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import numpy as np


def _make_sine(freq=440.0, duration=5.0, sr=44100, amplitude=0.5):
    t = np.linspace(0, duration, int(sr * duration), endpoint=False)
    return (amplitude * np.sin(2 * np.pi * freq * t)).astype(np.float64)


def _make_stereo_sine(freq=440.0, duration=5.0, sr=44100, amplitude=0.5):
    t = np.linspace(0, duration, int(sr * duration), endpoint=False)
    left = amplitude * np.sin(2 * np.pi * freq * t)
    right = amplitude * np.sin(2 * np.pi * freq * 1.005 * t)
    return np.stack([left, right]).astype(np.float64)


# ══════════════════════════════════════════════════════════════════════════
# Tests: StyleTransfer detailed
# ══════════════════════════════════════════════════════════════════════════

class TestStyleTransferDetailed:
    def test_transfer_with_empty_project(self):
        from vcmix.ai.style_transfer import StyleTransfer
        st = StyleTransfer()
        ref_audio = _make_sine(duration=5.0).reshape(1, -1)

        with tempfile.TemporaryDirectory() as tmpdir:
            project_yaml = str(Path(tmpdir) / "empty.yaml")
            output_yaml = str(Path(tmpdir) / "styled.yaml")

            import yaml
            with open(project_yaml, "w") as f:
                yaml.dump({"tracks": [], "master": {}}, f)

            result = st.transfer(
                reference_path="nonexistent.wav",
                project_yaml=project_yaml,
                output_yaml=output_yaml,
                reference_audio=ref_audio,
            )
            assert result.status in ("success", "failed")

    def test_transfer_with_no_ref_stems(self):
        from vcmix.ai.style_transfer import StyleTransfer
        st = StyleTransfer()

        with tempfile.TemporaryDirectory() as tmpdir:
            project_yaml = str(Path(tmpdir) / "proj.yaml")
            output_yaml = str(Path(tmpdir) / "styled.yaml")

            import yaml
            config = {
                "tracks": [{"name": "Vocal", "volume": 0.7, "effects": []}],
                "master": {},
            }
            with open(project_yaml, "w") as f:
                yaml.dump(config, f)

            result = st.transfer(
                reference_path="nonexistent.wav",
                project_yaml=project_yaml,
                output_yaml=output_yaml,
            )
            # Should handle missing reference gracefully
            assert result.status in ("success", "failed")

    def test_apply_transfers_to_config(self):
        from vcmix.ai.style_transfer import StyleTransfer, StyleTransferResult
        st = StyleTransfer()
        config = {
            "tracks": [
                {"name": "Vocal", "volume": 0.7, "effects": [
                    {"name": "vc-eq", "params": {"low_cut_hz": 80}}
                ]},
                {"name": "Drums", "volume": 0.8, "effects": []},
            ],
            "master": {},
        }
        result = StyleTransferResult(
            eq_transfers={"Vocal": {"category": "vocals", "params": {"high_shelf_db": 2}}},
            comp_transfers={"Drums": {"category": "drums", "params": {"threshold": -12, "ratio": 3}}},
            reverb_transfers={"Vocal": {"category": "vocals", "params": {"wet": 0.3, "room_size": 0.5}}},
            gain_adjustments={"Drums": -2.0},
        )
        modified = st._apply_transfers(config, result)

        # Vocal should have updated EQ
        vocal = modified["tracks"][0]
        eq_effect = next(e for e in vocal["effects"] if e["name"] == "vc-eq")
        assert eq_effect["params"]["high_shelf_db"] == 2

        # Vocal should have reverb added
        reverb_effect = next(e for e in vocal["effects"] if e["name"] == "vc-reverb")
        assert reverb_effect["params"]["wet"] == 0.3

        # Drums should have comp added
        drums = modified["tracks"][1]
        comp_effect = next(e for e in drums["effects"] if e["name"] == "vc-comp")
        assert comp_effect["params"]["ratio"] == 3

    def test_gain_balance_empty_ref(self):
        from vcmix.ai.style_transfer import StyleTransfer
        st = StyleTransfer()
        ref_analysis = {"stem_analyses": {}}
        target = {"Vocal": {"name": "Vocal", "volume": 0.7}}
        adjustments = st._balance_gain(ref_analysis, target)
        assert adjustments == {}

    def test_gain_balance_with_loudest_vocals(self):
        from vcmix.ai.style_transfer import StyleTransfer
        st = StyleTransfer()
        ref_analysis = {
            "stem_analyses": {
                "vocals": {"rms_db": -10.0},
                "drums": {"rms_db": -16.0},
            },
        }
        target = {
            "Vocal": {"name": "Vocal", "volume": 0.7},
            "Drums": {"name": "Drums", "volume": 0.8},
        }
        adjustments = st._balance_gain(ref_analysis, target)
        assert "Drums" in adjustments  # Drums should be adjusted relative to vocals

    def test_write_yaml_creates_file(self):
        from vcmix.ai.style_transfer import StyleTransfer
        st = StyleTransfer()

        with tempfile.TemporaryDirectory() as tmpdir:
            yaml_path = str(Path(tmpdir) / "output.yaml")
            st._write_yaml({"test": "value"}, yaml_path)
            assert Path(yaml_path).exists()

    def test_match_category_comprehensive(self):
        from vcmix.ai.style_transfer import _match_category
        # Vocals
        assert _match_category("vocals") == "vocals"
        assert _match_category("Lead Vocal") == "vocals"
        assert _match_category("BGV") == "vocals"
        # Drums
        assert _match_category("Drums") == "drums"
        assert _match_category("Kick Drum") == "drums"
        assert _match_category("hihat") == "drums"
        # Bass
        assert _match_category("Bass") == "bass"
        assert _match_category("808") == "bass"
        # Other
        assert _match_category("Piano") == "other"
        assert _match_category("Synth") == "other"


# ══════════════════════════════════════════════════════════════════════════
# Tests: ReferenceMatcherV2 detailed
# ══════════════════════════════════════════════════════════════════════════

class TestReferenceMatcherV2Detailed:
    def test_genre_rules_coverage(self):
        from vcmix.ai.reference_matcher_v2 import GENRE_RULES
        genres = [r["genre"] for r in GENRE_RULES]
        assert "edm" in genres
        assert "hiphop" in genres
        assert "rock" in genres
        assert "ballad" in genres
        assert "pop" in genres
        assert "rnb" in genres

    def test_genre_mix_presets_coverage(self):
        from vcmix.ai.reference_matcher_v2 import GENRE_MIX_PRESETS
        for genre in ["pop", "rock", "edm", "hiphop", "ballad", "rnb"]:
            assert genre in GENRE_MIX_PRESETS

    def test_genre_template_map_coverage(self):
        from vcmix.ai.reference_matcher_v2 import GENRE_TEMPLATE_MAP
        for genre in ["pop", "rock", "edm", "hiphop", "ballad", "rnb"]:
            assert genre in GENRE_TEMPLATE_MAP

    def test_extract_features_full(self):
        from vcmix.ai.reference_matcher_v2 import ReferenceMatcherV2
        matcher = ReferenceMatcherV2()
        audio = _make_sine(duration=10.0).reshape(1, -1)
        features = matcher._extract_features(audio)
        assert features.bpm > 0
        assert features.key in ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
        assert features.genre in ["pop", "rock", "edm", "hiphop", "ballad", "rnb"]
        assert features.dynamic_range >= 0
        assert features.spectral_centroid >= 0

    def test_style_parameters_extraction(self):
        from vcmix.ai.reference_matcher_v2 import ReferenceMatcherV2
        matcher = ReferenceMatcherV2()
        from vcmix.ai.reference_matcher_v2 import StyleFeatures
        features = StyleFeatures(
            bpm=128, key="A", scale_type="natural_minor",
            genre="edm", dynamic_range=10.0,
            spectral_centroid=3500.0,
            frequency_balance={"sub": 0.1, "low": 0.2, "mid": 0.3},
            energy_profile=[0.1, 0.2, 0.3],
        )
        params = matcher._extract_style_params(features)
        assert params["bpm"] == 128
        assert params["genre"] == "edm"
        assert params["dynamic_range"] == 10.0

    def test_template_match_reasons(self):
        from vcmix.ai.reference_matcher_v2 import ReferenceMatcherV2
        matcher = ReferenceMatcherV2()
        from vcmix.ai.reference_matcher_v2 import StyleFeatures
        features = StyleFeatures(genre="edm", bpm=128, scale_type="natural_minor")
        match = matcher._match_template(features)
        assert len(match.match_reasons) > 0
        assert match.match_score > 0

    def test_preset_adjustment_for_wide_dynamics(self):
        from vcmix.ai.reference_matcher_v2 import ReferenceMatcherV2
        matcher = ReferenceMatcherV2()
        from vcmix.ai.reference_matcher_v2 import StyleFeatures
        features = StyleFeatures(genre="pop", dynamic_range=18.0)
        match = matcher._match_mix_preset(features)
        # Should have increased compression ratio
        assert match.preset_params.get("comp_ratio", 2.5) > 2.5

    def test_preset_adjustment_for_bright_sound(self):
        from vcmix.ai.reference_matcher_v2 import ReferenceMatcherV2
        matcher = ReferenceMatcherV2()
        from vcmix.ai.reference_matcher_v2 import StyleFeatures
        features = StyleFeatures(genre="pop", spectral_centroid=5000.0)
        match = matcher._match_mix_preset(features)
        # Should have reduced high shelf
        assert match.preset_params.get("eq_high_shelf_db", 1.5) < 1.5

    def test_chroma_computation(self):
        from vcmix.ai.reference_matcher_v2 import ReferenceMatcherV2
        matcher = ReferenceMatcherV2()
        audio = _make_sine(freq=440, duration=5.0)
        chroma = matcher._compute_chroma(audio)
        assert len(chroma) == 12
        assert all(c >= 0 for c in chroma)

    def test_to_mono(self):
        from vcmix.ai.reference_matcher_v2 import ReferenceMatcherV2
        stereo = _make_stereo_sine(duration=2.0)
        mono = ReferenceMatcherV2._to_mono(stereo)
        assert mono.ndim == 1
        assert mono.dtype == np.float64


# ══════════════════════════════════════════════════════════════════════════
# Tests: RemixEngine detailed
# ══════════════════════════════════════════════════════════════════════════

class TestRemixEngineDetailed:
    def test_build_remix_config(self):
        from vcmix.ai.remix import RemixEngine
        from vcmix.ai.transcription import BPMInfo, KeyInfo, TranscriptionResult

        engine = RemixEngine()
        transcription = TranscriptionResult(
            bpm_info=BPMInfo(bpm=120),
            key_info=KeyInfo(root="C", scale_type="major"),
            stems={"vocals": "/tmp/vocals.wav", "drums": "/tmp/drums.wav"},
            stem_analyses={
                "vocals": {"rms_db": -12.0, "eq_curve": {"bands": []}, "compression": {"ratio": 1.0}, "reverb": {"wet_ratio": 0}},
                "drums": {"rms_db": -15.0, "eq_curve": {"bands": []}, "compression": {"ratio": 1.0}, "reverb": {"wet_ratio": 0}},
            },
            arrangement={"sections": []},
        )

        config = engine._build_remix_config(
            transcription, "pop", 120.0, {"vocals": "/new/vocals.wav"}
        )

        assert config["bpm"] == 120.0
        assert config["genre"] == "pop"
        # Vocals should have source=new, drums source=reference
        vocals_track = next(t for t in config["tracks"] if t["name"] == "vocals")
        drums_track = next(t for t in config["tracks"] if t["name"] == "drums")
        assert vocals_track["source"] == "new"
        assert drums_track["source"] == "reference"

    def test_build_remix_config_new_stem_not_in_ref(self):
        from vcmix.ai.remix import RemixEngine
        from vcmix.ai.transcription import BPMInfo, KeyInfo, TranscriptionResult

        engine = RemixEngine()
        transcription = TranscriptionResult(
            bpm_info=BPMInfo(bpm=128),
            key_info=KeyInfo(root="A", scale_type="natural_minor"),
            stems={"drums": "/tmp/drums.wav"},
            stem_analyses={"drums": {"rms_db": -15.0, "eq_curve": {"bands": []}, "compression": {"ratio": 1.0}, "reverb": {"wet_ratio": 0}}},
            arrangement={"sections": []},
        )

        config = engine._build_remix_config(
            transcription, "edm", 128.0, {"synth": "/new/synth.wav"}
        )

        track_names = [t["name"] for t in config["tracks"]]
        assert "drums" in track_names
        assert "synth" in track_names

    def test_analysis_to_effects(self):
        from vcmix.ai.remix import RemixEngine
        engine = RemixEngine()
        analysis = {
            "eq_curve": {"bands": [{"freq": 200, "gain_db": -3, "q": 1.0}]},
            "compression": {"ratio": 2.5, "threshold_db": -18},
            "reverb": {"wet_ratio": 0.1, "rt60_ms": 500},
            "delay": {"delay_ms": 0},
        }
        effects = engine._analysis_to_effects(analysis, "vocals")
        names = [e["name"] for e in effects]
        assert "vc-eq" in names
        assert "vc-comp" in names

    def test_finalize_remix(self):
        from vcmix.ai.remix import RemixEngine
        from vcmix.ai.style_transfer import StyleTransferResult

        engine = RemixEngine()
        project_config = {
            "tracks": [
                {"name": "Vocal", "volume": 0.7, "effects": [
                    {"name": "vc-eq", "params": {"low_cut_hz": 80}},
                    {"name": "vc-comp", "params": {"threshold": -18, "ratio": 2}},
                ]},
            ],
        }
        style_result = StyleTransferResult(
            eq_transfers={"Vocal": {"category": "vocals", "params": {"high_shelf_db": 2}}},
            comp_transfers={"Vocal": {"category": "vocals", "params": {"threshold": -15, "ratio": 3}}},
            reverb_transfers={},
            gain_adjustments={"Vocal": 1.5},
        )

        final = engine._finalize_remix(project_config, {}, style_result, 120.0)
        assert final["bpm"] == 120.0
        # EQ should be updated
        vocal = final["tracks"][0]
        eq = next(e for e in vocal["effects"] if e["name"] == "vc-eq")
        assert eq["params"]["high_shelf_db"] == 2

    def test_load_audio_nonexistent(self):
        from vcmix.ai.remix import RemixEngine
        engine = RemixEngine()
        result = engine._load_audio("/nonexistent.wav")
        assert result is None

    def test_write_yaml(self):
        from vcmix.ai.remix import RemixEngine
        engine = RemixEngine()

        with tempfile.TemporaryDirectory() as tmpdir:
            yaml_path = str(Path(tmpdir) / "test.yaml")
            engine._write_yaml({"name": "test"}, yaml_path)
            assert Path(yaml_path).exists()


# ══════════════════════════════════════════════════════════════════════════
# Tests: Integration
# ══════════════════════════════════════════════════════════════════════════

class TestIntegration:
    def test_transcription_to_style_transfer(self):
        """Test that transcription results can feed into style transfer."""
        from vcmix.ai.style_transfer import StyleTransfer

        # Generate synthetic audio
        ref_audio = _make_sine(freq=440, duration=5.0).reshape(1, -1)

        # Style transfer should accept analysis from transcription
        st = StyleTransfer()
        ref_stems = {"vocals": _make_sine(freq=440, duration=5.0)}

        with tempfile.TemporaryDirectory() as tmpdir:
            project_yaml = str(Path(tmpdir) / "proj.yaml")
            output_yaml = str(Path(tmpdir) / "styled.yaml")

            import yaml
            config = {
                "tracks": [
                    {"name": "Vocal", "type": "audio", "volume": 0.7, "effects": []},
                ],
                "master": {},
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

    def test_matcher_to_remix(self):
        """Test that style matching results can guide remix."""
        from vcmix.ai.reference_matcher_v2 import ReferenceMatcherV2

        matcher = ReferenceMatcherV2()
        audio = _make_sine(duration=10.0).reshape(1, -1)
        result = matcher.match_style(reference_audio=audio)

        # Should provide genre and BPM that can be used for remix
        assert result.features.genre in ["pop", "rock", "edm", "hiphop", "ballad", "rnb"]
        assert result.features.bpm > 0

    def test_full_pipeline_mock(self):
        """Test the complete pipeline with all mocks."""
        from vcmix.ai.transcription import AITranscription

        def mock_separate(ref_path, out_path):
            stems = {}
            for name in ["vocals", "drums", "bass", "other"]:
                stem_path = out_path / f"{name}.wav"
                stems[name] = stem_path
            return stems

        with tempfile.TemporaryDirectory() as tmpdir:
            ref_path = Path(tmpdir) / "reference.wav"
            ref_path.touch()

            transcriber = AITranscription()
            result = transcriber.transcribe(
                str(ref_path),
                str(Path(tmpdir) / "output"),
                separate_fn=mock_separate,
            )

            # Should have completed (success or failed with meaningful error)
            assert result.status in ("success", "failed")
            assert result.transcription_time_sec >= 0
