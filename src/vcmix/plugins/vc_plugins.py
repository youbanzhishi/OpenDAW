"""
vc_plugins.py — VC plugin CLI subprocess adapters for VCMix.

Bridges VCMix to the existing VocalChain CLI tools by:
    1. Writing audio to a temp WAV file
    2. Calling the VC CLI via subprocess with parameters
    3. Reading the processed WAV output back into numpy

CLI Path Resolution (priority order):
    1. params["cli_path"] — per-effect override
    2. Environment variable VC_{NAME}_CLI — e.g. VC_REVERB_CLI
    3. YAML config plugin_paths section
    4. Default: /tmp/AudioFX/VC-{Name}/VC-{Name}-CLI-Standalone

Supported VC Plugins (16 total):
    VC-EQ, VC-Comp, VC-Gain, VC-DeEsser, VC-Saturator,
    VC-Limiter, VC-Delay, VC-Reverb, VC-DynamicEQ, VC-Smooth,
    VC-SurgicalDeEsser, VC-Distortion, VC-Noise, VC-Tune, VC-Gate, VC-Chorus

Usage:
    from vcmix.plugins.vc_plugins import VCPluginAdapter
    adapter = VCPluginAdapter("vc-reverb", cli_path="/usr/local/bin/VC-Reverb-CLI-Standalone")
    result = adapter.process(audio, {"room": 30, "decay": 35}, 44100)

Dependencies: numpy, soundfile, subprocess, tempfile, pathlib
"""

from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import numpy as np
import soundfile as sf

from vcmix.plugins.adapter import PluginAdapter

# ── Default CLI paths ──────────────────────────────────────────────────────

_VC_CLI_DEFAULTS: dict[str, str] = {
    "vc-eq":       "VC-EQ/VC-EQ-CLI-Standalone",
    "vc-comp":     "VC-Comp/VC-Comp-CLI-Standalone",
    "vc-gain":     "VC-Gain/VC-Gain-CLI-Standalone",
    "vc-deesser":  "VC-DeEsser/VC-DeEsser-CLI-Standalone",
    "vc-saturator":"VC-Saturator/VC-Saturator-CLI-Standalone",
    "vc-limiter":  "VC-Limiter/VC-Limiter-CLI-Standalone",
    "vc-delay":    "VC-Delay/VC-Delay-CLI-Standalone",
    "vc-reverb":   "VC-Reverb/VC-Reverb-CLI-Standalone",
    "vc-dynamiceq":"VC-DynamicEQ/VC-DynamicEQ-CLI-Standalone",
    "vc-smooth":   "VC-Smooth/VC-Smooth-CLI-Standalone",
    "vc-surgicaldeesser": "VC-SurgicalDeEsser/VC-SurgicalDeEsser-CLI-Standalone",
    "vc-distortion": "VC-Distortion/VC-Distortion-CLI-Standalone",
    "vc-noise": "VC-Noise/VC-Noise-CLI-Standalone",
    "vc-tune": "VC-Tune/VC-Tune-CLI-Standalone",
    "vc-gate": "VC-Gate/VC-Gate-CLI-Standalone",
    "vc-chorus": "VC-Chorus/VC-Chorus-CLI-Standalone",
}

# Base directory for VC CLI tools
_AUDIOFX_BASE = Path(os.environ.get("VC_AUDIOFX_DIR", "/tmp/AudioFX"))

# ── Parameter mapping: VCMix YAML param name → CLI flag ────────────────────

_PARAM_MAPS: dict[str, dict[str, str]] = {
    "vc-eq": {
        "low_cut": "--low-cut", "high_cut": "--high-cut",
        "low_shelf": "--low-shelf", "high_shelf": "--high-shelf",
        "peak_freq": "--peak-freq", "peak_gain": "--peak-gain",
        "peak_q": "--peak-q",
    },
    "vc-comp": {
        "threshold": "--threshold", "ratio": "--ratio",
        "attack": "--attack", "release": "--release",
        "makeup": "--makeup",
    },
    "vc-gain": {
        "gain": "--gain",
    },
    "vc-deesser": {
        "threshold": "--threshold", "reduction": "--reduction",
        "frequency": "--frequency",
    },
    "vc-saturator": {
        "drive": "--drive", "mix": "--mix",
    },
    "vc-limiter": {
        "ceiling": "--ceiling", "release": "--release",
    },
    "vc-delay": {
        "time": "--time", "feedback": "--feedback", "mix": "--mix",
    },
    "vc-reverb": {
        "room": "--room", "decay": "--decay", "damping": "--damping",
        "mix": "--mix", "predelay": "--predelay", "wetlpf": "--wetlpf",
    },
    "vc-dynamiceq": {
        "frequency": "--frequency", "threshold": "--threshold",
        "q": "--q", "attack": "--attack", "release": "--release",
    },
    "vc-smooth": {
        "amount": "--amount",
    },
    "vc-surgicaldeesser": {
        "threshold": "--threshold", "reduction": "--reduction",
        "frequency": "--frequency",
    },
    "vc-distortion": {
        "mode": "--mode", "drive": "--drive", "mix": "--mix",
    },
    "vc-noise": {
        "type": "--type", "level": "--level",
    },
    "vc-tune": {
        "speed": "--speed", "scale": "--scale",
        "transpose": "--transpose", "cents": "--cents",
        "formant": "--formant", "autokey": "--autokey",
    },
    "vc-gate": {
        "threshold": "--threshold", "ratio": "--ratio",
        "attack": "--attack", "hold": "--hold",
        "release": "--release", "range": "--range",
    },
    "vc-chorus": {
        "rate": "--rate", "depth": "--depth",
        "voices": "--voices", "mix": "--mix",
        "delay": "--delay", "width": "--width",
        "feedback": "--feedback",
    },
}


def resolve_cli_path(plugin_name: str, params: dict[str, Any] | None = None) -> Path | None:
    """
    Resolve the CLI executable path for a VC plugin.

    Resolution order:
        1. params["cli_path"] override
        2. Environment variable VC_{NAME}_CLI
        3. Default path under _AUDIOFX_BASE

    Args:
        plugin_name: Plugin identifier, e.g. "vc-reverb".
        params: Optional params dict (may contain cli_path override).

    Returns:
        Path to CLI executable, or None if not found.
    """
    # 1. Per-effect override
    if params and "cli_path" in params:
        p = Path(params["cli_path"])
        return p if p.exists() else None

    # 2. Environment variable
    env_key = plugin_name.upper().replace("-", "_") + "_CLI"
    env_val = os.environ.get(env_key)
    if env_val:
        p = Path(env_val)
        return p if p.exists() else None

    # 3. Default path
    default_rel = _VC_CLI_DEFAULTS.get(plugin_name)
    if default_rel:
        p = _AUDIOFX_BASE / default_rel
        return p if p.exists() else None

    return None


class VCPluginAdapter(PluginAdapter):
    """
    Plugin adapter that calls VC CLI tools via subprocess.

    Args:
        name: Plugin identifier (e.g. "vc-reverb").
        cli_path: Optional explicit path to CLI executable.
    """

    def __init__(self, name: str, cli_path: str | Path | None = None) -> None:
        self.name = name
        self._cli_path = Path(cli_path) if cli_path else None
        self._param_map = _PARAM_MAPS.get(name, {})

    def _get_cli_path(self, params: dict[str, Any]) -> Path | None:
        """Get CLI path: explicit override > env > default."""
        if self._cli_path and self._cli_path.exists():
            return self._cli_path
        return resolve_cli_path(self.name, params)

    def _build_cli_args(
        self, input_path: Path, output_path: Path, params: dict[str, Any]
    ) -> list[str]:
        """
        Build CLI argument list from params dict.

        Maps VCMix param names to CLI flags using _PARAM_MAPS.
        Unknown param names are passed as --{name} {value}.
        """
        args = [str(self._get_cli_path(params))]
        args.append(str(input_path))
        args.append(str(output_path))

        for key, value in params.items():
            if key == "cli_path":
                continue  # Skip path override param

            # Map param name to CLI flag
            flag = self._param_map.get(key, f"--{key}")
            args.extend([flag, str(value)])

        return args

    def process(
        self,
        audio: np.ndarray,
        params: dict[str, Any],
        sample_rate: int = 44100,
    ) -> np.ndarray:
        """
        Process audio through VC CLI plugin via subprocess.

        Flow:
            1. Write input audio to temp WAV
            2. Build and execute CLI command
            3. Read output WAV back to numpy
            4. Return processed audio (matching input shape)

        If CLI executable is not found, returns input audio unchanged
        with a warning.

        Args:
            audio: Input audio buffer.
            params: Plugin parameters.
            sample_rate: Audio sample rate.

        Returns:
            Processed audio buffer.

        Raises:
            RuntimeError: If CLI execution fails.
        """
        cli_path = self._get_cli_path(params)
        if cli_path is None:
            # CLI not available — passthrough with warning
            import warnings
            warnings.warn(
                f"VC CLI not found for {self.name}, passing through",
                RuntimeWarning,
                stacklevel=2,
            )
            return audio

        # Ensure 2D shape for soundfile: (channels, samples)
        if audio.ndim == 1:
            audio_2d = audio.reshape(1, -1)
        else:
            audio_2d = audio

        with tempfile.TemporaryDirectory(prefix="vcmix_") as tmpdir:
            tmpdir_path = Path(tmpdir)
            in_path = tmpdir_path / "input.wav"
            out_path = tmpdir_path / "output.wav"

            # Write input
            sf.write(str(in_path), audio_2d.T, sample_rate)

            # Build and run CLI
            args = self._build_cli_args(in_path, out_path, params)
            try:
                result = subprocess.run(
                    args,
                    capture_output=True,
                    text=True,
                    timeout=300,  # 5 minute timeout
                    encoding="utf-8",
                )
                if result.returncode != 0:
                    raise RuntimeError(
                        f"VC CLI {self.name} failed (exit {result.returncode}): "
                        f"{result.stderr[:500]}"
                    )
            except FileNotFoundError:
                raise RuntimeError(f"VC CLI executable not found: {cli_path}")
            except subprocess.TimeoutExpired:
                raise RuntimeError(f"VC CLI {self.name} timed out after 300s")

            # Read output
            if not out_path.exists():
                raise RuntimeError(f"VC CLI {self.name} produced no output file")

            output, out_sr = sf.read(str(out_path), dtype="float32")

            # Handle sample rate mismatch (shouldn't happen but be safe)
            if out_sr != sample_rate:
                import warnings
                warnings.warn(
                    f"Sample rate mismatch after {self.name}: "
                    f"{out_sr} != {sample_rate}",
                    RuntimeWarning,
                    stacklevel=2,
                )

            # Match output shape to input shape
            if audio.ndim == 1:
                if output.ndim == 2:
                    output = output[:, 0]  # Take first channel
                return output.flatten()
            else:
                return output.T if output.ndim == 2 else output.reshape(1, -1)
