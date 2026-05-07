"""
vst3_proxy.py — Python wrapper around vst3_host CLI.

Provides a high-level interface for:
- Loading VST3 plugins
- Setting parameters
- Rendering audio (effect processing or instrument rendering)
- Exporting parameter info

All operations are delegated to the vst3_host C++ subprocess.
"""

from __future__ import annotations

import json
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from vcmix.audio.io import read_audio, write_audio


@dataclass
class VST3ParamInfo:
    """Information about a single VST3 plugin parameter."""
    index: int
    name: str
    current_value: float   # normalized [0,1]
    default_value: float   # normalized [0,1]


class VST3Proxy:
    """
    Proxy to a VST3 plugin via the vst3_host CLI.

    Usage:
        proxy = VST3Proxy(plugin_path="/usr/lib/vst3/Serum.vst3")
        params = proxy.get_params()
        proxy.set_param(1, 0.5)
        output = proxy.render_effect(input_audio, sample_rate=44100)
    """

    def __init__(
        self,
        plugin_path: str,
        cli_path: str | None = None,
        sample_rate: int = 44100,
        block_size: int = 512,
        timeout: int = 300,
    ) -> None:
        """
        Args:
            plugin_path: Absolute path to VST3 plugin bundle.
            cli_path: Path to vst3_host binary. Auto-detected if None.
            sample_rate: Target sample rate for rendering.
            block_size: Processing block size.
            timeout: Subprocess timeout in seconds.
        """
        self.plugin_path = plugin_path
        self.cli_path = cli_path or self._find_cli()
        self.sample_rate = sample_rate
        self.block_size = block_size
        self.timeout = timeout

        # Cached parameter info
        self._param_cache: list[VST3ParamInfo] | None = None

    @staticmethod
    def _find_cli() -> str:
        """Find vst3_host CLI on PATH."""
        import shutil
        found = shutil.which("vst3_host")
        if found:
            return found
        # Fallback: check common locations
        for p in ["/usr/local/bin/vst3_host", "/usr/bin/vst3_host"]:
            if Path(p).exists():
                return p
        return "vst3_host"  # rely on PATH

    def _run_cli(self, args: list[str]) -> subprocess.CompletedProcess:
        """Run vst3_host CLI with given arguments."""
        cmd = [self.cli_path] + args
        return subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=self.timeout,
        )

    def is_available(self) -> bool:
        """Check if the vst3_host CLI is available and functional."""
        try:
            result = self._run_cli(["list"])
            return result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
            return False

    def get_params(self, use_cache: bool = True) -> list[VST3ParamInfo]:
        """
        Get parameter list from the plugin.

        Args:
            use_cache: Return cached param info if available.

        Returns:
            List of VST3ParamInfo for each parameter.
        """
        if use_cache and self._param_cache is not None:
            return self._param_cache

        result = self._run_cli([
            "params",
            "--plugin", self.plugin_path,
            "--sample-rate", str(self.sample_rate),
        ])

        if result.returncode != 0:
            raise RuntimeError(
                f"vst3_host params failed: {result.stderr}"
            )

        try:
            info = json.loads(result.stdout)
        except json.JSONDecodeError as e:
            raise RuntimeError(f"Failed to parse params output: {e}")

        params = []
        for p in info.get("params", []):
            params.append(VST3ParamInfo(
                index=p["index"],
                name=p["name"],
                current_value=p["current"],
                default_value=p["default"],
            ))

        self._param_cache = params
        return params

    def set_param(self, index: int, value: float) -> None:
        """
        Set a parameter value.

        Note: This stores the param override for the next render call.
        The actual VST3 parameter is set during subprocess invocation.

        Args:
            index: Parameter index (0-based).
            value: Normalized value [0.0, 1.0].
        """
        value = max(0.0, min(1.0, value))
        self._param_overrides[index] = value

    def render_effect(
        self,
        input_audio: np.ndarray,
        sample_rate: int = 44100,
    ) -> np.ndarray:
        """
        Render audio through a VST3 effect plugin.

        Args:
            input_audio: Input audio buffer (1D mono or 2D multi-channel).
            sample_rate: Audio sample rate.

        Returns:
            Processed audio buffer.
        """
        with tempfile.TemporaryDirectory(prefix="vcmix_vst3_") as tmpdir:
            input_path = Path(tmpdir) / "input.wav"
            output_path = Path(tmpdir) / "output.wav"

            # Write input audio
            write_audio(input_audio, input_path, sample_rate)

            # Build CLI args
            args = [
                "process",
                "--plugin", self.plugin_path,
                "--input", str(input_path),
                "--output", str(output_path),
                "--sample-rate", str(sample_rate),
                "--block-size", str(self.block_size),
            ]

            # Add parameter overrides
            for idx, val in self._param_overrides.items():
                args.extend(["--param", f"{idx}={val}"])

            # Add preset if set
            if self._preset_file:
                args.extend(["--preset-file", self._preset_file])

            # Run
            result = self._run_cli(args)

            if result.returncode != 0:
                raise RuntimeError(
                    f"vst3_host process failed (exit {result.returncode}): "
                    f"{result.stderr}"
                )

            # Read output
            output_audio, _ = read_audio(output_path)
            return output_audio

    def render_instrument(
        self,
        duration: float,
        midi_events: list[dict[str, Any]] | None = None,
        midi_file: str | None = None,
        bpm: float = 120.0,
    ) -> np.ndarray:
        """
        Render audio from a VST3 instrument plugin.

        Args:
            duration: Render duration in seconds.
            midi_events: List of MIDI event dicts (for JSON MIDI file).
            midi_file: Path to .mid or .json MIDI file.
            bpm: Tempo for MIDI timing.

        Returns:
            Rendered audio buffer.
        """
        with tempfile.TemporaryDirectory(prefix="vcmix_vst3_") as tmpdir:
            output_path = Path(tmpdir) / "output.wav"

            args = [
                "process",
                "--plugin", self.plugin_path,
                "--output", str(output_path),
                "--duration", str(duration),
                "--bpm", str(bpm),
                "--sample-rate", str(self.sample_rate),
                "--block-size", str(self.block_size),
            ]

            # Handle MIDI
            if midi_file:
                args.extend(["--midi-file", midi_file])
            elif midi_events:
                # Write MIDI events to JSON file
                midi_json_path = Path(tmpdir) / "midi.json"
                midi_json_path.write_text(json.dumps({
                    "ppq": 480,
                    "bpm": bpm,
                    "events": midi_events,
                }))
                args.extend(["--midi-file", str(midi_json_path)])

            # Add parameter overrides
            for idx, val in self._param_overrides.items():
                args.extend(["--param", f"{idx}={val}"])

            # Add preset if set
            if self._preset_file:
                args.extend(["--preset-file", self._preset_file])

            # Run
            result = self._run_cli(args)

            if result.returncode != 0:
                raise RuntimeError(
                    f"vst3_host process failed (exit {result.returncode}): "
                    f"{result.stderr}"
                )

            # Read output
            output_audio, _ = read_audio(output_path)
            return output_audio

    def load_preset(self, preset_file: str) -> None:
        """
        Set a .vstpreset file to load on next render.

        Args:
            preset_file: Path to .vstpreset file.
        """
        self._preset_file = preset_file

    def clear_params(self) -> None:
        """Clear all parameter overrides."""
        self._param_overrides.clear()

    # ── Private ────────────────────────────────────────────────────────

    _param_overrides: dict[int, float] = {}
    _preset_file: str = ""

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)

    def __post_init__(self) -> None:
        """Initialize mutable defaults."""
        if not hasattr(self, '_param_overrides') or self._param_overrides is None:
            self._param_overrides = {}
        if not hasattr(self, '_preset_file'):
            self._preset_file = ""


# Fix: dataclass-like init for mutable defaults
# Since this isn't a dataclass, handle in __init__
_original_init = VST3Proxy.__init__

def _patched_init(self, *args: Any, **kwargs: Any) -> None:
    _original_init(self, *args, **kwargs)
    self._param_overrides: dict[int, float] = {}
    self._preset_file: str = ""

VST3Proxy.__init__ = _patched_init  # type: ignore[assignment]
