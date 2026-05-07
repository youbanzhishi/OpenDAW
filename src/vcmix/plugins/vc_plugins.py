"""
vc_plugins.py — VC Plugin CLI adapters for VCMix.

Wraps AudioFX CLI executables (VC-EQ, VC-Comp, VC-Smooth, etc.)
as PluginAdapter instances, enabling YAML-driven plugin chains
that use the existing VC plugin ecosystem.

Each adapter:
    1. Writes audio to a temp WAV file
    2. Shells out to the VC CLI executable with parameters
    3. Reads the processed WAV back into a numpy array

Usage:
    from vcmix.plugins.vc_plugins import VCEQAdapter
    eq = VCEQAdapter(name="vocal_eq", cli_path="/usr/local/bin/VC-EQ-CLI")
    result = eq.process(audio, 44100)

Dependencies: numpy, soundfile, subprocess, tempfile, pathlib
"""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path
from typing import Any

import numpy as np
import soundfile as sf

from vcmix.plugins.adapter import PluginAdapter


class VCCLIAdapter(PluginAdapter):
    """
    Base adapter for VC plugin CLI executables.

    Args:
        name: Plugin instance name.
        cli_path: Path to the VC CLI executable.
        parameters: Dict of CLI parameters.
    """

    def __init__(self, name: str, cli_path: str, parameters: dict[str, Any] | None = None) -> None:
        super().__init__(name=name, parameters=parameters or {})
        self.cli_path = Path(cli_path)

    def process(self, audio: np.ndarray, sample_rate: int) -> np.ndarray:
        """
        Process audio through the VC CLI executable.

        Args:
            audio: Input audio buffer.
            sample_rate: Sample rate in Hz.

        Returns:
            Processed audio buffer.

        Raises:
            FileNotFoundError: If the CLI executable is not found.
            RuntimeError: If the CLI returns a non-zero exit code.
        """
        if not self.cli_path.exists():
            raise FileNotFoundError(f"VC CLI not found: {self.cli_path}")

        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            input_path = tmpdir_path / "input.wav"
            output_path = tmpdir_path / "output.wav"

            # Write input
            sf.write(str(input_path), audio, sample_rate)

            # Build CLI command
            cmd = [str(self.cli_path), str(input_path), str(output_path)]
            for key, value in self.parameters.items():
                cmd.extend([f"--{key}", str(value)])

            # Execute
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            if result.returncode != 0:
                raise RuntimeError(f"VC CLI error: {result.stderr}")

            # Read output
            processed, _ = sf.read(str(output_path), dtype="float32")
            return processed


class VCEQAdapter(VCCLIAdapter):
    """Adapter for VC-EQ (parametric equalizer) CLI."""

    def __init__(self, name: str = "vc_eq", cli_path: str = "VC-EQ-CLI",
                 parameters: dict[str, Any] | None = None) -> None:
        super().__init__(name=name, cli_path=cli_path, parameters=parameters)


class VCCompAdapter(VCCLIAdapter):
    """Adapter for VC-Comp (compressor) CLI."""

    def __init__(self, name: str = "vc_comp", cli_path: str = "VC-Comp-CLI",
                 parameters: dict[str, Any] | None = None) -> None:
        super().__init__(name=name, cli_path=cli_path, parameters=parameters)


class VCSmoothAdapter(VCCLIAdapter):
    """Adapter for VC-Smooth (smoothing) CLI."""

    def __init__(self, name: str = "vc_smooth", cli_path: str = "VC-Smooth-CLI",
                 parameters: dict[str, Any] | None = None) -> None:
        super().__init__(name=name, cli_path=cli_path, parameters=parameters)
