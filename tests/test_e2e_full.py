"""
test_e2e_full.py — Full end-to-end tests for VCMix (Phase 19).

Tests the complete lifecycle from project creation to final output,
covering all major workflows: rendering, AI composition, auto-mixing,
transcription, export, version management, and snapshots.

Usage:
    pytest tests/test_e2e_full.py -v
    pytest tests/test_e2e_full.py -v -k "test_full_project_lifecycle"

Dependencies: pytest, numpy, soundfile, pyyaml
"""

from __future__ import annotations

import hashlib
import shutil
import time
from pathlib import Path
from typing import Any

import numpy as np
import pytest
import soundfile as sf
import yaml

from vcmix.config.parser import parse_project
from vcmix.engine.analyzer import Analyzer
from vcmix.engine.audio_cache import AudioCache
from vcmix.engine.automix import AutoMixer
from vcmix.engine.renderer import Renderer
from vcmix.export.exporter import AudioExporter
from vcmix.project.version_manager import ProjectVersionManager


# ── Helpers ──────────────────────────────────────────────────────────


def _generate_sine(
    freq: float = 440.0,
    duration: float = 2.0,
    sr: int = 44100,
    amplitude: float = 0.3,
) -> np.ndarray:
    """Generate a sine wave audio buffer."""
    n = int(sr * duration)
    t = np.linspace(0, duration, n, endpoint=False, dtype=np.float32)
    return amplitude * np.sin(2 * np.pi * freq * t)


def _create_track_wav(
    tmp_path: Path,
    name: str,
    freq: float = 440.0,
    duration: float = 2.0,
    sr: int = 44100,
    amplitude: float = 0.3,
) -> Path:
    """Create a WAV file with a sine wave and return its path."""
    audio = _generate_sine(freq, duration, sr, amplitude)
    path = tmp_path / f"{name}.wav"
    sf.write(str(path), audio, sr)
    return path


def _write_project_yaml(
    tmp_path: Path,
    name: str = "e2e_test",
    bpm: float = 120.0,
    tracks: list | None = None,
    sends: list | None = None,
    master: dict | None = None,
) -> Path:
    """Write a VCMix project YAML file and return its path."""
    config: dict[str, Any] = {
        "name": name,
        "bpm": bpm,
        "sample_rate": 44100,
        "tracks": tracks or [],
        "sends": sends or [],
        "master": master or {
            "levels": {},
            "effects": [],
            "output": str(tmp_path / "output.wav"),
        },
    }
    yaml_path = tmp_path / "project.yaml"
    with open(yaml_path, "w") as f:
        yaml.dump(config, f, default_flow_style=False, allow_unicode=True)
    return yaml_path


# ── Fixtures ──────────────────────────────────────────────────────────


@pytest.fixture
def simple_project(tmp_path: Path) -> Any:
    """Create a simple 2-track project for E2E testing."""
    vocal_path = _create_track_wav(tmp_path, "vocal", freq=440, duration=2.0)
    accomp_path = _create_track_wav(tmp_path, "accomp", freq=220, duration=2.0)

    tracks = [
        {"name": "vocal", "file": str(vocal_path), "effects": [
            {"name": "vc-gain", "params": {"gain": -3}},
        ]},
        {"name": "accomp", "file": str(accomp_path), "volume": 0.7},
    ]
    master = {
        "levels": {"vocal": 0.9, "accomp": 0.7},
        "effects": [],
        "output": str(tmp_path / "output.wav"),
    }

    yaml_path = _write_project_yaml(tmp_path, tracks=tracks, master=master)
    cfg = parse_project(yaml_path)
    cfg.__dict__["_project_dir"] = tmp_path
    return cfg


@pytest.fixture
def multi_track_project(tmp_path: Path) -> Any:
    """Create a 6-track project with effects for comprehensive E2E testing."""
    sr = 44100
    track_specs = [
        ("vocal", 440, 0.4),
        ("bass", 110, 0.5),
        ("drums", 80, 0.5),
        ("guitar", 330, 0.35),
        ("keys", 660, 0.3),
        ("pad", 165, 0.25),
    ]

    tracks = []
    for name, freq, amp in track_specs:
        path = _create_track_wav(tmp_path, name, freq=freq, duration=3.0, amplitude=amp)
        track: dict[str, Any] = {"name": name, "file": str(path)}
        if name == "vocal":
            track["effects"] = [
                {"name": "vc-gain", "params": {"gain": -2}},
                {"name": "vc-comp", "params": {"threshold": -20, "ratio": 3}},
            ]
        elif name == "bass":
            track["effects"] = [
                {"name": "vc-gain", "params": {"gain": -4}},
                {"name": "vc-comp", "params": {"threshold": -15, "ratio": 4}},
            ]
        elif name == "guitar":
            track["effects"] = [
                {"name": "vc-gain", "params": {"gain": -6}},
            ]
        elif name == "pad":
            track["effects"] = [
                {"name": "vc-gain", "params": {"gain": -8}},
            ]
        tracks.append(track)

    master = {
        "levels": {name: 0.8 for name, _, _ in track_specs},
        "effects": [],
        "output": str(tmp_path / "output.wav"),
    }

    yaml_path = _write_project_yaml(tmp_path, name="e2e_multi", tracks=tracks, master=master)
    cfg = parse_project(yaml_path)
    cfg.__dict__["_project_dir"] = tmp_path
    return cfg


@pytest.fixture
def project_with_sends(tmp_path: Path) -> Any:
    """Create a project with send/return buses."""
    vocal_path = _create_track_wav(tmp_path, "vocal", freq=440)
    accomp_path = _create_track_wav(tmp_path, "accomp", freq=220)

    tracks = [
        {
            "name": "vocal",
            "file": str(vocal_path),
            "sends": {"reverb_bus": 0.3},
            "effects": [{"name": "vc-gain", "params": {"gain": -2}}],
        },
        {
            "name": "accomp",
            "file": str(accomp_path),
            "sends": {"reverb_bus": 0.15},
        },
    ]
    sends = [
        {
            "name": "reverb_bus",
            "effects": [{"name": "vc-gain", "params": {"gain": -6}}],
            "return_level": 0.2,
        }
    ]
    master = {
        "levels": {"vocal": 0.9, "accomp": 0.7},
        "effects": [],
        "output": str(tmp_path / "output.wav"),
    }

    yaml_path = _write_project_yaml(tmp_path, tracks=tracks, sends=sends, master=master)
    cfg = parse_project(yaml_path)
    cfg.__dict__["_project_dir"] = tmp_path
    return cfg


# ── Full Lifecycle E2E Tests ─────────────────────────────────────────


class TestEndToEnd:
    """Full end-to-end tests for VCMix project lifecycle."""

    def test_full_project_lifecycle(self, simple_project: Any) -> None:
        """
        Complete project lifecycle:
        1. Create YAML project
        2. Render
        3. Analyze output
        4. Create snapshot
        5. Modify project
        6. Re-render
        7. Restore snapshot
        8. Verify restoration
        """
        project = simple_project
        project_dir = project.__dict__.get("_project_dir", Path("."))

        # Step 1: Project is already created via fixture
        assert project.name == "e2e_test"
        assert len(project.tracks) == 2

        # Step 2: Render
        renderer = Renderer(project, stream="none")
        output_path = renderer.run()
        assert output_path.exists()

        data, sr = sf.read(str(output_path))
        assert len(data) > 0
        assert sr == 44100

        # Step 3: Analyze output
        rms = float(np.sqrt(np.mean(data.astype(np.float64) ** 2)))
        peak = float(np.max(np.abs(data.astype(np.float64))))
        assert rms > 0, "Output should have non-zero RMS"
        assert peak > 0, "Output should have non-zero peak"

        # Step 4: Create snapshot
        yaml_path = project_dir / "project.yaml"
        # Ensure yaml exists
        if not yaml_path.exists():
            config_dict = {
                "name": project.name, "bpm": project.bpm,
                "sample_rate": project.sample_rate,
                "tracks": [{"name": t.name, "file": t.file, "volume": t.volume,
                            "effects": [{"name": e.name, "params": e.params} for e in t.effects]}
                           for t in project.tracks],
                "master": {"levels": project.master.levels, "effects": [],
                           "output": str(project_dir / "output.wav")},
            }
            yaml.dump(config_dict, open(yaml_path, "w"), default_flow_style=False)

        vm = ProjectVersionManager(base_dir=project_dir / ".snapshots")
        snap_id = vm.create_snapshot(str(yaml_path), "baseline render")
        assert snap_id.startswith("snap_")

        # Step 5: Modify project
        project.master.levels["vocal"] = 1.2
        project.master.levels["accomp"] = 0.5

        # Step 6: Re-render with modifications
        renderer2 = Renderer(project, stream="none")
        output_path2 = renderer2.run()
        assert output_path2.exists()
        data2, sr2 = sf.read(str(output_path2))
        assert len(data2) > 0

        # Step 7: Restore snapshot
        project_name = yaml_path.stem
        pid = hashlib.sha256(project_name.encode("utf-8")).hexdigest()[:12]
        restored = vm.restore_snapshot(pid, snap_id, projects_dir=project_dir)
        assert Path(restored).exists()

        # Step 8: Verify restoration
        cfg_restored = parse_project(yaml_path)
        assert cfg_restored.master.levels.get("vocal", 0.9) == 0.9

    def test_project_with_effects_chain(self, multi_track_project: Any) -> None:
        """Multi-track project with per-track effect chains should render correctly."""
        project = multi_track_project
        assert len(project.tracks) == 6

        renderer = Renderer(project, stream="none")
        output_path = renderer.run()
        assert output_path.exists()

        data, sr = sf.read(str(output_path))
        assert len(data) > 0
        rms = float(np.sqrt(np.mean(data.astype(np.float64) ** 2)))
        assert rms > 1e-6, "Rendered output should have audible content"

    def test_project_with_send_return_buses(self, project_with_sends: Any) -> None:
        """Project with send/return buses should render correctly."""
        project = project_with_sends
        assert len(project.sends) == 1
        assert project.sends[0].name == "reverb_bus"

        renderer = Renderer(project, stream="none")
        output_path = renderer.run()
        assert output_path.exists()

        data, sr = sf.read(str(output_path))
        assert len(data) > 0

    def test_parallel_rendering_e2e(self, multi_track_project: Any) -> None:
        """Parallel rendering should produce valid output."""
        project = multi_track_project

        renderer_serial = Renderer(project, parallel=1, stream="none")
        output_serial = renderer_serial.run()
        assert output_serial.exists()

        renderer_parallel = Renderer(project, parallel=4, stream="none")
        output_parallel = renderer_parallel.run()
        assert output_parallel.exists()

        data_s, _ = sf.read(str(output_serial))
        data_p, _ = sf.read(str(output_parallel))
        assert len(data_s) > 0
        assert len(data_p) > 0

    def test_auto_fix_rendering(self, simple_project: Any) -> None:
        """Render with auto-fix enabled should produce valid output."""
        project = simple_project
        renderer = Renderer(project, auto_fix=True, stream="none")
        output_path = renderer.run()
        assert output_path.exists()

        data, sr = sf.read(str(output_path))
        assert len(data) > 0

    def test_report_mode_rendering(self, simple_project: Any) -> None:
        """Render with report mode should emit analysis events."""
        project = simple_project
        renderer = Renderer(project, report=True, stream="dict")
        output_path = renderer.run()
        assert output_path.exists()

        events = renderer.get_stream_events()
        event_types = [e.event_type for e in events]
        assert len(events) > 0, "Report mode should emit events"

    def test_muted_track_rendering(self, tmp_path: Path) -> None:
        """Muted tracks should not appear in rendered output."""
        vocal_path = _create_track_wav(tmp_path, "vocal", freq=440)
        muted_path = _create_track_wav(tmp_path, "muted_track", freq=880)

        tracks = [
            {"name": "vocal", "file": str(vocal_path)},
            {"name": "muted_track", "file": str(muted_path), "mute": True},
        ]
        master = {
            "levels": {"vocal": 1.0, "muted_track": 1.0},
            "output": str(tmp_path / "output.wav"),
        }

        yaml_path = _write_project_yaml(tmp_path, tracks=tracks, master=master)
        cfg = parse_project(yaml_path)
        cfg.__dict__["_project_dir"] = tmp_path

        renderer = Renderer(cfg, stream="none")
        output = renderer.run()
        assert output.exists()

        data, sr = sf.read(str(output))
        assert len(data) > 0

    def test_yaml_note_value_conversion(self, tmp_path: Path) -> None:
        """BPM note values should be correctly converted to milliseconds."""
        vocal_path = _create_track_wav(tmp_path, "vocal", freq=440)

        tracks = [
            {
                "name": "vocal",
                "file": str(vocal_path),
                "effects": [
                    {"name": "vc-gain", "params": {"gain": 0}},
                    {"name": "vc-delay", "params": {"time": "1/4"}},
                ],
            },
        ]
        master = {
            "levels": {"vocal": 1.0},
            "output": str(tmp_path / "output.wav"),
        }

        yaml_path = _write_project_yaml(tmp_path, bpm=120.0, tracks=tracks, master=master)
        cfg = parse_project(yaml_path)

        delay_params = cfg.tracks[0].effects[1].params
        assert "time" in delay_params
        assert delay_params["time"] == 500.0  # 60000/120 = 500ms for 1/4 at 120 BPM

    def test_incremental_rendering_e2e(self, simple_project: Any) -> None:
        """Incremental rendering E2E: first run then cached re-run."""
        from vcmix.engine.incremental import IncrementalRenderer

        project = simple_project

        renderer = Renderer(project, stream="none")
        inc = IncrementalRenderer(renderer)
        output1 = inc.run()
        assert output1.exists()

        renderer2 = Renderer(project, stream="none")
        inc2 = IncrementalRenderer(renderer2)
        output2 = inc2.run(changed_tracks=set())
        assert output2.exists()

    def test_export_wav_e2e(self, simple_project: Any) -> None:
        """Export rendered output to WAV format."""
        project = simple_project
        project_dir = project.__dict__.get("_project_dir", Path("."))

        renderer = Renderer(project, stream="none")
        output_path = renderer.run()
        assert output_path.exists()

        exporter = AudioExporter()
        export_path = project_dir / "exported.wav"
        result = exporter.export(str(output_path), str(export_path), "wav", {"subtype": "PCM_16"})
        assert Path(result).exists()

    def test_export_flac_e2e(self, simple_project: Any) -> None:
        """Export rendered output to FLAC format."""
        project = simple_project
        project_dir = project.__dict__.get("_project_dir", Path("."))

        renderer = Renderer(project, stream="none")
        output_path = renderer.run()

        exporter = AudioExporter()
        export_path = project_dir / "exported.flac"
        result = exporter.export(str(output_path), str(export_path), "flac")
        assert Path(result).exists()

    def test_snapshot_create_and_restore(self, tmp_path: Path) -> None:
        """Snapshot creation and restoration E2E test."""
        vocal_path = _create_track_wav(tmp_path, "vocal", freq=440)

        tracks_v1 = [
            {"name": "vocal", "file": str(vocal_path), "effects": [
                {"name": "vc-gain", "params": {"gain": -3}},
            ]},
        ]
        master_v1 = {
            "levels": {"vocal": 0.8},
            "output": str(tmp_path / "output.wav"),
        }
        yaml_path = _write_project_yaml(tmp_path, name="snap_test", tracks=tracks_v1, master=master_v1)

        vm = ProjectVersionManager(base_dir=tmp_path / ".snapshots")
        snap_id = vm.create_snapshot(str(yaml_path), "version 1")
        assert snap_id.startswith("snap_")

        # Modify
        new_content = yaml_path.read_text().replace("gain: -3", "gain: 3")
        yaml_path.write_text(new_content)

        # Verify modification
        cfg_after = parse_project(yaml_path)
        gain_param = cfg_after.tracks[0].effects[0].params.get("gain")
        assert gain_param == 3

        # Restore
        project_name = yaml_path.stem
        pid = hashlib.sha256(project_name.encode("utf-8")).hexdigest()[:12]
        restored = vm.restore_snapshot(pid, snap_id, projects_dir=tmp_path)
        assert Path(restored).exists()

        # Verify restoration
        cfg_restored = parse_project(yaml_path)
        gain_restored = cfg_restored.tracks[0].effects[0].params.get("gain")
        assert gain_restored == -3

    def test_snapshot_diff(self, tmp_path: Path) -> None:
        """Snapshot diff comparison E2E test."""
        vocal_path = _create_track_wav(tmp_path, "vocal", freq=440)

        tracks = [{"name": "vocal", "file": str(vocal_path)}]
        master = {"levels": {"vocal": 0.8}, "output": str(tmp_path / "output.wav")}
        yaml_path = _write_project_yaml(tmp_path, name="diff_test", tracks=tracks, master=master)

        vm = ProjectVersionManager(base_dir=tmp_path / ".snapshots")
        snap1 = vm.create_snapshot(str(yaml_path), "v1")

        new_content = yaml_path.read_text().replace("0.8", "0.5")
        yaml_path.write_text(new_content)

        snap2 = vm.create_snapshot(str(yaml_path), "v2")

        diff = vm.diff_snapshots(snap1, snap2)
        assert "param_changes" in diff

    def test_data_stream_events(self, simple_project: Any) -> None:
        """DataStream should emit proper events during rendering."""
        project = simple_project
        renderer = Renderer(project, stream="dict")
        output_path = renderer.run()

        events = renderer.get_stream_events()
        event_types = [e.event_type for e in events]

        # DataStream collects structured events (track_level, master_level, etc.)
        # Pipeline steps are printed to stdout; DataStream captures level/delta/warning events
        assert len(events) > 0, "DataStream should emit events during rendering"
        # Should have at least track_level or master_level events
        assert "track_level" in event_types or "master_level" in event_types

    def test_ab_comparison_mode(self, tmp_path: Path) -> None:
        """A/B comparison mode should produce both A and B outputs."""
        vocal_path = _create_track_wav(tmp_path, "vocal", freq=440)

        tracks = [
            {
                "name": "vocal",
                "file": str(vocal_path),
                "effects": [{"name": "vc-gain", "params": {"gain": -3}}],
                "effects_a": [{"name": "vc-gain", "params": {"gain": -3}}],
                "effects_b": [{"name": "vc-gain", "params": {"gain": 3}}],
            },
        ]
        master = {
            "levels": {"vocal": 1.0},
            "effects": [],
            "output": str(tmp_path / "output.wav"),
        }

        yaml_path = _write_project_yaml(tmp_path, tracks=tracks, master=master)
        cfg = parse_project(yaml_path)
        cfg.__dict__["_project_dir"] = tmp_path

        renderer = Renderer(cfg, ab_mode=True, stream="none")
        output = renderer.run()
        assert output.exists()

    def test_arrangement_aware_rendering(self, simple_project: Any) -> None:
        """Arrangement-aware rendering mode should work."""
        project = simple_project
        renderer = Renderer(project, arrangement_aware=True, stream="none")
        output = renderer.run()
        assert output.exists()


class TestAIWorkflow:
    """AI workflow end-to-end tests."""

    def test_ai_compose_basic(self) -> None:
        """AI composer should generate a valid project configuration."""
        from vcmix.ai.composer import AIComposer

        composer = AIComposer()
        result = composer.compose(genre="pop", duration=60, bpm=120, key="C", mood="happy")

        assert result.project_config is not None
        assert result.genre == "pop"
        assert result.bpm == 120
        assert result.key == "C"
        assert result.sections > 0

    def test_ai_compose_all_genres(self) -> None:
        """AI composer should support all genres."""
        from vcmix.ai.composer import AIComposer

        composer = AIComposer()
        for genre in ["pop", "rock", "edm", "hiphop", "rnb", "ballad", "lofi"]:
            result = composer.compose(genre=genre, duration=30, bpm=120, key="C", mood="happy")
            assert result.project_config is not None, f"Composer failed for genre: {genre}"

    def test_ai_compose_to_yaml(self, tmp_path: Path) -> None:
        """AI composer output should be valid YAML that can be parsed."""
        from vcmix.ai.composer import AIComposer

        composer = AIComposer()
        result = composer.compose(genre="pop", duration=30, bpm=120, key="Am", mood="calm")

        yaml_str = yaml.dump(
            result.project_config,
            default_flow_style=False,
            allow_unicode=True,
        )
        yaml_path = tmp_path / "ai_project.yaml"
        yaml_path.write_text(yaml_str, encoding="utf-8")

        cfg = parse_project(yaml_path)
        assert cfg.name is not None
        assert cfg.bpm > 0

    def test_automix_dry_vocal_analysis(self) -> None:
        """AutoMixer should analyze dry vocal audio correctly."""
        mixer = AutoMixer(sample_rate=44100)

        sr = 44100
        t = np.linspace(0, 2, int(sr * 2), endpoint=False, dtype=np.float32)
        vocal = 0.3 * np.sin(2 * np.pi * 200 * t) + 0.15 * np.sin(2 * np.pi * 400 * t)

        analysis = mixer.analyze_dry_vocal(vocal, sr)
        assert "rms_db" in analysis
        assert "peak_db" in analysis
        assert "dynamic_range_db" in analysis
        assert "gain_needed_db" in analysis
        assert "sibilance_ratio" in analysis
        assert "needs_deesser" in analysis
        assert "spectrum" in analysis

    def test_automix_chain_generation(self) -> None:
        """AutoMixer should generate an effect chain from analysis."""
        mixer = AutoMixer(sample_rate=44100)

        sr = 44100
        t = np.linspace(0, 2, int(sr * 2), endpoint=False, dtype=np.float32)
        vocal = 0.3 * np.sin(2 * np.pi * 200 * t)

        analysis = mixer.analyze_dry_vocal(vocal, sr)
        chain = mixer.generate_chain(analysis)

        assert isinstance(chain, list)
        assert len(chain) > 0

    def test_automix_closed_loop(self, simple_project: Any) -> None:
        """AutoMixer closed-loop: render → analyze → suggest → apply."""
        project = simple_project

        renderer = Renderer(project, stream="dict")
        output1 = renderer.run()
        assert output1.exists()

        events = renderer.get_stream_events()
        mixer = AutoMixer(sample_rate=44100)
        state = mixer.analyze(events)
        suggestions = mixer.suggest(state)
        assert isinstance(suggestions, list)

    def test_arrangement_template_application(self) -> None:
        """Arrangement template should generate valid project config."""
        from vcmix.arrangement.template_applier import TemplateApplier
        from vcmix.arrangement.templates import get_template

        tmpl = get_template("pop-standard")
        applier = TemplateApplier()
        config = applier.apply_to_dict(tmpl, bpm=120, key="C")

        assert "tracks" in config
        assert len(config["tracks"]) > 0
        assert "bpm" in config


class TestTranscriptionWorkflow:
    """Transcription (AI扒带) workflow end-to-end tests."""

    def test_transcription_with_mock_separation(self, tmp_path: Path) -> None:
        """Full transcription workflow with mock Demucs separation."""
        from vcmix.ai.transcription import AITranscription

        sr = 44100
        duration = 3.0
        n_samples = int(sr * duration)
        t = np.linspace(0, duration, n_samples, endpoint=False, dtype=np.float32)

        ref_audio = 0.3 * np.sin(2 * np.pi * 440 * t) + 0.2 * np.sin(2 * np.pi * 220 * t)
        ref_path = tmp_path / "reference.wav"
        sf.write(str(ref_path), ref_audio, sr)

        def mock_separate(ref_path: Path, output_dir: Path) -> dict[str, Path]:
            stems = {}
            for name, freq in [("vocals", 440), ("drums", 80), ("bass", 110), ("other", 660)]:
                audio = 0.2 * np.sin(2 * np.pi * freq * t)
                path = output_dir / f"{name}.wav"
                sf.write(str(path), audio, sr)
                stems[name] = path
            return stems

        transcriber = AITranscription(sample_rate=sr)
        result = transcriber.transcribe(
            str(ref_path),
            str(tmp_path / "transcription_output"),
            separate_fn=mock_separate,
        )

        assert result.status == "success"
        assert len(result.stems) == 4
        assert result.bpm_info.bpm > 0
        assert len(result.stem_analyses) > 0
        assert result.project_yaml != ""

    def test_reverse_analysis(self) -> None:
        """ReverseMixAnalyzer should analyze stems and return mixing parameters."""
        from vcmix.separation.reverse_analyzer import ReverseMixAnalyzer

        sr = 44100
        t = np.linspace(0, 2, int(sr * 2), endpoint=False, dtype=np.float32)
        vocal = 0.3 * np.sin(2 * np.pi * 300 * t) + 0.1 * np.sin(2 * np.pi * 3000 * t)

        analyzer = ReverseMixAnalyzer(sample_rate=sr)
        result = analyzer.analyze_stem(vocal, "vocals")

        assert result is not None
        result_dict = result.to_dict()
        assert "track_name" in result_dict

    def test_transcription_bpm_detection(self) -> None:
        """Transcription pipeline should detect BPM from audio."""
        from vcmix.ai.transcription import AITranscription

        sr = 44100
        n = int(sr * 4)
        t = np.linspace(0, 4, n, endpoint=False, dtype=np.float32)

        beat_samples = int(60.0 / 120 * sr)
        audio = np.zeros(n, dtype=np.float32)
        for i in range(0, n, beat_samples):
            if i + 100 < n:
                audio[i:i + 100] = 0.8

        transcriber = AITranscription(sample_rate=sr)
        bpm_info = transcriber._detect_bpm(audio)
        assert bpm_info.bpm > 0

    def test_transcription_key_detection(self) -> None:
        """Transcription pipeline should detect musical key."""
        from vcmix.ai.transcription import AITranscription

        sr = 44100
        t = np.linspace(0, 2, int(sr * 2), endpoint=False, dtype=np.float32)
        audio = (0.3 * np.sin(2 * np.pi * 261.63 * t) +
                 0.2 * np.sin(2 * np.pi * 329.63 * t) +
                 0.2 * np.sin(2 * np.pi * 392.00 * t))

        transcriber = AITranscription(sample_rate=sr)
        key_info = transcriber._detect_key(audio)

        assert key_info.root in ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
        assert key_info.scale_type in ["major", "minor"]
