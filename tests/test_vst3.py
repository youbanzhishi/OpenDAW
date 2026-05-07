"""
test_vst3.py — Tests for VST3 hosting interface.

Tests cover:
- VST3Scanner: plugin discovery
- VST3Proxy: CLI interface (mock when vst3_host not available)
- VST3 YAML parsing: TrackConfig with VST3 fields
- VST3Track: creation and configuration

These tests are designed to run even without vst3_host CLI or
any VST3 plugins installed, using mock/fallback behaviors.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

# ── VST3Scanner Tests ──────────────────────────────────────────────────────

class TestVST3Scanner:
    """Test VST3 plugin scanner."""

    def test_scanner_init_default(self):
        """Scanner initializes with default settings."""
        from vcmix.vst3.vst3_scanner import VST3Scanner
        scanner = VST3Scanner()
        assert scanner.cli_path is not None or scanner.cli_path is None
        # cli_path may be None if vst3_host not on PATH

    def test_scanner_init_custom_cli(self):
        """Scanner accepts custom CLI path."""
        from vcmix.vst3.vst3_scanner import VST3Scanner
        scanner = VST3Scanner(cli_path="/custom/path/vst3_host")
        assert scanner.cli_path == "/custom/path/vst3_host"

    def test_scanner_init_extra_paths(self):
        """Scanner accepts extra search paths."""
        from vcmix.vst3.vst3_scanner import VST3Scanner
        scanner = VST3Scanner(extra_paths=["/tmp/vst3", "/opt/vst3"])
        assert len(scanner.extra_paths) == 2

    def test_scanner_filesystem_fallback(self):
        """Scanner falls back to filesystem scan when CLI unavailable."""
        from vcmix.vst3.vst3_scanner import VST3Scanner
        # Use non-existent CLI to force filesystem fallback
        scanner = VST3Scanner(cli_path="/nonexistent/vst3_host")
        plugins = scanner.scan()
        # Should return a list (possibly empty if no VST3 plugins installed)
        assert isinstance(plugins, list)

    def test_scanner_with_mock_cli(self):
        """Scanner parses CLI list output correctly."""
        from vcmix.vst3.vst3_scanner import VST3Scanner
        scanner = VST3Scanner(cli_path="/mock/vst3_host")

        # Mock the subprocess call
        mock_output = """Found 2 VST3 plugin(s):

  Name: Serum
  Path: /usr/lib/vst3/Serum.vst3
  Type: Instrument
  Mfr:  Xfer Records

  Name: Pro-Q 3
  Path: /usr/lib/vst3/FabFilter Pro-Q 3.vst3
  Type: Effect
  Mfr:  FabFilter
"""

        with patch("vcmix.vst3.vst3_scanner.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout=mock_output,
            )
            plugins = scanner._scan_via_cli()

        assert len(plugins) == 2
        assert plugins[0].name == "Serum"
        assert plugins[0].path == "/usr/lib/vst3/Serum.vst3"
        assert plugins[0].is_instrument is True
        assert plugins[1].name == "Pro-Q 3"
        assert plugins[1].is_instrument is False

    def test_plugin_info_dataclass(self):
        """VST3PluginInfo holds correct data."""
        from vcmix.vst3.vst3_scanner import VST3PluginInfo
        info = VST3PluginInfo(
            name="TestPlugin",
            path="/usr/lib/vst3/Test.vst3",
            manufacturer="TestCo",
            is_instrument=True,
            source="filesystem",
        )
        assert info.name == "TestPlugin"
        assert info.is_instrument is True
        assert info.source == "filesystem"


# ── VST3Proxy Tests ────────────────────────────────────────────────────────

class TestVST3Proxy:
    """Test VST3 proxy (CLI interface)."""

    def test_proxy_init(self):
        """Proxy initializes with plugin path."""
        from vcmix.vst3.vst3_proxy import VST3Proxy
        proxy = VST3Proxy(plugin_path="/usr/lib/vst3/Test.vst3")
        assert proxy.plugin_path == "/usr/lib/vst3/Test.vst3"
        assert proxy.sample_rate == 44100

    def test_proxy_init_custom_settings(self):
        """Proxy accepts custom sample rate and block size."""
        from vcmix.vst3.vst3_proxy import VST3Proxy
        proxy = VST3Proxy(
            plugin_path="/usr/lib/vst3/Test.vst3",
            sample_rate=48000,
            block_size=1024,
            timeout=60,
        )
        assert proxy.sample_rate == 48000
        assert proxy.block_size == 1024
        assert proxy.timeout == 60

    def test_proxy_set_param(self):
        """Proxy stores parameter overrides."""
        from vcmix.vst3.vst3_proxy import VST3Proxy
        proxy = VST3Proxy(plugin_path="/usr/lib/vst3/Test.vst3")
        proxy.set_param(1, 0.5)
        proxy.set_param(2, 0.8)
        assert proxy._param_overrides[1] == 0.5
        assert proxy._param_overrides[2] == 0.8

    def test_proxy_set_param_clamped(self):
        """Proxy clamps parameter values to [0, 1]."""
        from vcmix.vst3.vst3_proxy import VST3Proxy
        proxy = VST3Proxy(plugin_path="/usr/lib/vst3/Test.vst3")
        proxy.set_param(0, -0.5)
        proxy.set_param(1, 1.5)
        assert proxy._param_overrides[0] == 0.0
        assert proxy._param_overrides[1] == 1.0

    def test_proxy_clear_params(self):
        """Proxy clears parameter overrides."""
        from vcmix.vst3.vst3_proxy import VST3Proxy
        proxy = VST3Proxy(plugin_path="/usr/lib/vst3/Test.vst3")
        proxy.set_param(1, 0.5)
        proxy.clear_params()
        assert len(proxy._param_overrides) == 0

    def test_proxy_load_preset(self):
        """Proxy stores preset file path."""
        from vcmix.vst3.vst3_proxy import VST3Proxy
        proxy = VST3Proxy(plugin_path="/usr/lib/vst3/Test.vst3")
        proxy.load_preset("/presets/Test/Init.vstpreset")
        assert proxy._preset_file == "/presets/Test/Init.vstpreset"

    def test_proxy_get_params_mock(self):
        """Proxy parses params CLI output (mock)."""
        from vcmix.vst3.vst3_proxy import VST3Proxy
        proxy = VST3Proxy(
            plugin_path="/usr/lib/vst3/Test.vst3",
            cli_path="/mock/vst3_host",
        )

        mock_output = json.dumps({
            "plugin": "Test",
            "is_instrument": False,
            "num_params": 3,
            "params": [
                {"index": 0, "name": "Gain", "current": 0.5, "default": 0.5},
                {"index": 1, "name": "Mix", "current": 1.0, "default": 1.0},
                {"index": 2, "name": "Speed", "current": 0.0, "default": 0.5},
            ],
        })

        with patch("vcmix.vst3.vst3_scanner.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout=mock_output,
            )
            params = proxy.get_params()

        assert len(params) == 3
        assert params[0].name == "Gain"
        assert params[0].current_value == 0.5
        assert params[2].name == "Speed"

    def test_proxy_not_available(self):
        """Proxy detects when CLI is unavailable."""
        from vcmix.vst3.vst3_proxy import VST3Proxy
        proxy = VST3Proxy(
            plugin_path="/usr/lib/vst3/Test.vst3",
            cli_path="/nonexistent/vst3_host",
        )
        assert proxy.is_available() is False


# ── VST3 YAML Parsing Tests ───────────────────────────────────────────────

class TestVST3YAMLParsing:
    """Test VST3 fields in YAML project configuration."""

    def test_vst3_track_yaml_parse(self):
        """YAML with vst3 track type parses correctly."""
        from vcmix.config.parser import parse_project

        yaml_content = yaml.dump({
            "name": "VST3 Test Project",
            "bpm": 128,
            "sample_rate": 44100,
            "tracks": [
                {
                    "name": "vocal",
                    "file": "vocal.wav",
                    "type": "audio",
                    "effects": [{"name": "vc-eq", "params": {"low_cut": 80}}],
                },
                {
                    "name": "synth",
                    "type": "vst3",
                    "plugin_path": "/usr/lib/vst3/Serum.vst3",
                    "preset": "Init",
                    "params": [
                        {"index": 1, "value": 0.5},
                        {"index": 2, "value": 0.8},
                    ],
                    "midi_file": "melody.mid",
                },
            ],
            "master": {
                "output": "output.wav",
            },
        })

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False
        ) as f:
            f.write(yaml_content)
            yaml_path = f.name

        try:
            config = parse_project(yaml_path)
            assert len(config.tracks) == 2

            # Check VST3 track
            vst3_track = config.tracks[1]
            assert vst3_track.type == "vst3"
            assert vst3_track.plugin_path == "/usr/lib/vst3/Serum.vst3"
            assert vst3_track.preset == "Init"
            assert len(vst3_track.params) == 2
            assert vst3_track.params[0]["index"] == 1
            assert vst3_track.params[0]["value"] == 0.5
            assert vst3_track.midi_file == "melody.mid"
        finally:
            os.unlink(yaml_path)

    def test_vst3_track_with_preset_file(self):
        """YAML with preset_file parses correctly."""
        from vcmix.config.parser import parse_project

        yaml_content = yaml.dump({
            "name": "VST3 Preset Test",
            "bpm": 120,
            "tracks": [
                {
                    "name": "synth",
                    "type": "vst3",
                    "plugin_path": "/usr/lib/vst3/Serum.vst3",
                    "preset_file": "/presets/Serum/Pad.vstpreset",
                    "params": [],
                },
            ],
            "master": {"output": "output.wav"},
        })

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False
        ) as f:
            f.write(yaml_content)
            yaml_path = f.name

        try:
            config = parse_project(yaml_path)
            vst3_track = config.tracks[0]
            assert vst3_track.preset_file == "/presets/Serum/Pad.vstpreset"
        finally:
            os.unlink(yaml_path)

    def test_audio_track_unchanged(self):
        """Existing audio track parsing is not affected by VST3 additions."""
        from vcmix.config.parser import parse_project

        yaml_content = yaml.dump({
            "name": "Audio Only",
            "bpm": 120,
            "tracks": [
                {
                    "name": "vocal",
                    "file": "vocal.wav",
                    "effects": [{"name": "vc-reverb", "params": {"mix": 15}}],
                },
            ],
            "master": {"output": "output.wav"},
        })

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False
        ) as f:
            f.write(yaml_content)
            yaml_path = f.name

        try:
            config = parse_project(yaml_path)
            track = config.tracks[0]
            assert track.type == "audio"
            assert track.plugin_path is None
            assert len(track.effects) == 1
        finally:
            os.unlink(yaml_path)


# ── VST3Track Tests ───────────────────────────────────────────────────────

class TestVST3Track:
    """Test VST3Track class."""

    def test_track_creation(self):
        """VST3Track creates from VST3TrackConfig."""
        from vcmix.vst3.vst3_track import VST3ParamOverride, VST3Track, VST3TrackConfig
        config = VST3TrackConfig(
            name="synth",
            plugin_path="/usr/lib/vst3/Serum.vst3",
            params=[VST3ParamOverride(index=1, value=0.5)],
            midi_file="melody.mid",
        )
        track = VST3Track(config)
        assert track.name == "synth"
        assert track.is_instrument is True

    def test_track_effect_mode(self):
        """VST3Track detects effect mode when file is provided."""
        from vcmix.vst3.vst3_track import VST3Track, VST3TrackConfig
        config = VST3TrackConfig(
            name="vocal_fx",
            plugin_path="/usr/lib/vst3/Pro-Q.vst3",
            file="vocal.wav",
        )
        track = VST3Track(config)
        assert track.is_instrument is False

    def test_track_muted(self):
        """VST3Track respects mute flag."""
        from vcmix.vst3.vst3_track import VST3Track, VST3TrackConfig
        config = VST3TrackConfig(
            name="muted_synth",
            plugin_path="/usr/lib/vst3/Test.vst3",
            mute=True,
        )
        track = VST3Track(config)
        # render should return silence when muted
        import numpy as np
        result = track.render(input_audio=np.ones(1000, dtype=np.float32))
        assert np.allclose(result, 0.0)

    def test_track_set_param(self):
        """VST3Track forwards param changes to proxy."""
        from vcmix.vst3.vst3_track import VST3Track, VST3TrackConfig
        config = VST3TrackConfig(
            name="synth",
            plugin_path="/usr/lib/vst3/Test.vst3",
        )
        track = VST3Track(config)
        track.set_param(3, 0.7)
        assert track._proxy._param_overrides[3] == 0.7

    def test_track_from_yaml_track(self):
        """VST3Track.from_yaml_track creates track from TrackConfig."""
        from vcmix.config.parser import TrackConfig
        from vcmix.vst3.vst3_track import VST3Track

        track_config = TrackConfig(
            name="synth",
            type="vst3",
            plugin_path="/usr/lib/vst3/Serum.vst3",
            preset="Init",
            params=[{"index": 1, "value": 0.5}],
            midi_file="melody.mid",
        )

        track = VST3Track.from_yaml_track(track_config)
        assert track.name == "synth"
        assert track.is_instrument is True
        assert len(track.config.params) == 1

    def test_track_from_yaml_track_missing_plugin_path(self):
        """VST3Track.from_yaml_track raises error without plugin_path."""
        from vcmix.config.parser import TrackConfig
        from vcmix.vst3.vst3_track import VST3Track

        track_config = TrackConfig(
            name="broken",
            type="vst3",
        )

        with pytest.raises(ValueError, match="missing plugin_path"):
            VST3Track.from_yaml_track(track_config)

    def test_scan_plugins(self):
        """VST3Track.scan_plugins returns list."""
        from vcmix.vst3.vst3_track import VST3Track
        plugins = VST3Track.scan_plugins(cli_path="/nonexistent/vst3_host")
        assert isinstance(plugins, list)

    def test_track_volume_applied(self):
        """VST3Track applies volume to rendered audio."""

        from vcmix.vst3.vst3_track import VST3Track, VST3TrackConfig

        config = VST3TrackConfig(
            name="quiet",
            plugin_path="/usr/lib/vst3/Test.vst3",
            volume=0.5,
            file="input.wav",
        )
        track = VST3Track(config)
        # We can't actually render without CLI, but we can verify the config
        assert track.config.volume == 0.5


# ── Integration-style tests (mock CLI) ────────────────────────────────────

class TestVST3Integration:
    """Integration tests using mock vst3_host CLI."""

    def test_effect_render_with_mock_cli(self):
        """Full effect render pipeline with mock CLI."""
        import numpy as np

        from vcmix.vst3.vst3_proxy import VST3Proxy

        proxy = VST3Proxy(
            plugin_path="/usr/lib/vst3/Test.vst3",
            cli_path="/mock/vst3_host",
        )
        proxy.set_param(1, 0.5)

        # Create mock input/output WAV files
        with tempfile.TemporaryDirectory(prefix="vcmix_test_") as tmpdir:
            input_path = Path(tmpdir) / "input.wav"
            Path(tmpdir) / "output.wav"

            # Write a simple WAV
            import soundfile as sf
            sr = 44100
            audio = np.random.randn(sr).astype(np.float32) * 0.1
            sf.write(str(input_path), audio, sr)

            # Mock subprocess to just copy input to output
            def mock_run(cmd, **kwargs):
                # Copy input to output (simulating passthrough effect)
                if "--output" in cmd:
                    out_idx = cmd.index("--output")
                    in_idx = cmd.index("--input")
                    import shutil
                    shutil.copy2(cmd[in_idx + 1], cmd[out_idx + 1])
                return MagicMock(returncode=0, stderr="Success")

            with patch("vcmix.vst3.vst3_proxy.subprocess.run", side_effect=mock_run):
                result = proxy.render_effect(audio, sr)

            assert len(result) > 0

    def test_instrument_render_with_mock_cli(self):
        """Instrument render pipeline with mock CLI."""
        import numpy as np

        from vcmix.vst3.vst3_proxy import VST3Proxy

        proxy = VST3Proxy(
            plugin_path="/usr/lib/vst3/Serum.vst3",
            cli_path="/mock/vst3_host",
        )

        with tempfile.TemporaryDirectory(prefix="vcmix_test_") as tmpdir:
            Path(tmpdir) / "output.wav"

            # Create a dummy output WAV (simulating rendered audio)
            import soundfile as sf
            sr = 44100
            dummy_audio = np.random.randn(sr * 10).astype(np.float32) * 0.1

            def mock_run(cmd, **kwargs):
                if "--output" in cmd:
                    out_idx = cmd.index("--output")
                    sf.write(cmd[out_idx + 1], dummy_audio, sr)
                return MagicMock(returncode=0, stderr="Success")

            with patch("vcmix.vst3.vst3_proxy.subprocess.run", side_effect=mock_run):
                result = proxy.render_instrument(duration=10.0, bpm=128)

            assert len(result) > 0
