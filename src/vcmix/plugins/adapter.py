"""
adapter.py — PluginAdapter abstract base class for VCMix.

Defines the standard interface that all plugin adapters must implement.
Every adapter takes (audio, params, sample_rate) and returns processed audio.

The adapter pattern decouples the rendering engine from the plugin
implementation, allowing:
    - VC CLI subprocess calls (VCPluginAdapter)
    - Pure Python/numpy effects (native adapters, Phase 2)
    - VST3 hosting via external bridge (Phase 5)

Phase 2 additions:
    - Sidechain support: process_with_sidechain() method for effects
      that need an external key input (e.g. compression driven by kick).

Usage:
    class MyPlugin(PluginAdapter):
        def process(self, audio, params, sample_rate):
            # ... process audio ...
            return processed_audio

Dependencies: abc, numpy
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Callable

import numpy as np


class PluginAdapter(ABC):
    """
    Abstract base class for VCMix plugin adapters.

    Subclasses must implement the process() method.
    Optionally override validate_params() for parameter checking.
    """

    # Subclasses should set these
    name: str = "unknown"
    description: str = ""

    @abstractmethod
    def process(
        self,
        audio: np.ndarray,
        params: dict[str, Any],
        sample_rate: int = 44100,
    ) -> np.ndarray:
        """
        Process audio through this plugin.

        Args:
            audio: Input audio buffer (1D mono or 2D multi-channel).
            params: Plugin-specific parameters dict.
            sample_rate: Audio sample rate.

        Returns:
            Processed audio buffer (same shape as input).
        """
        ...

    def process_with_sidechain(
        self,
        audio: np.ndarray,
        params: dict[str, Any],
        sample_rate: int = 44100,
        sidechain_audio: np.ndarray | None = None,
    ) -> np.ndarray:
        """
        Process audio with an optional sidechain input.

        For plugins that support sidechain (e.g. VC-Comp), the sidechain
        audio is used as the detector/key signal instead of the main input.

        If the underlying CLI does not support sidechain directly, the
        default implementation simulates sidechain by mixing the sidechain
        audio into the main input at a detectable level, then processing
        normally. This is an approximation — proper sidechain support
        requires CLI-level --sidechain parameter support.

        Args:
            audio: Main input audio buffer.
            params: Plugin-specific parameters dict.
            sample_rate: Audio sample rate.
            sidechain_audio: Sidechain key signal (e.g. kick drum).
                If None, falls back to normal process().

        Returns:
            Processed audio buffer (same shape as main input).
        """
        if sidechain_audio is None:
            return self.process(audio, params, sample_rate)

        # Default sidechain simulation: mix sidechain into the main signal
        # at a detectable level, process, then attempt to restore.
        # This is a best-effort approximation for CLIs without --sidechain.
        #
        # Strategy: Create a composite signal that the compressor will react to,
        # then apply the same gain envelope to the original signal.
        return self._simulate_sidechain(audio, params, sample_rate, sidechain_audio)

    def _simulate_sidechain(
        self,
        audio: np.ndarray,
        params: dict[str, Any],
        sample_rate: int,
        sidechain_audio: np.ndarray,
    ) -> np.ndarray:
        """
        Simulate sidechain compression by analyzing gain reduction on
        the sidechain signal, then applying it to the main signal.

        This works by:
        1. Process sidechain alone through the compressor to get gain envelope
        2. Process main audio alone through the compressor to get gain envelope
        3. Apply the sidechain-derived gain envelope to the main audio

        This is an approximation — true sidechain requires CLI support.
        """
        # Process sidechain through the plugin to get gain-reduced output
        sc_processed = self.process(sidechain_audio, params, sample_rate)

        # Compute gain envelope from sidechain processing
        sc_flat = sidechain_audio.flatten().astype(np.float64)
        sc_out_flat = sc_processed.flatten().astype(np.float64)

        min_len = min(len(sc_flat), len(sc_out_flat))
        if min_len == 0:
            return self.process(audio, params, sample_rate)

        # Compute per-block gain reduction (50ms blocks)
        block_size = max(1, int(sample_rate * 0.05))
        n_blocks = min_len // block_size

        if n_blocks == 0:
            return self.process(audio, params, sample_rate)

        # Build gain reduction envelope
        gain_envelope = np.ones(len(audio.flatten()), dtype=np.float64)

        for i in range(n_blocks):
            start = i * block_size
            end = start + block_size

            sc_rms = np.sqrt(np.mean(sc_flat[start:end] ** 2))
            sc_out_rms = np.sqrt(np.mean(sc_out_flat[start:end] ** 2))

            if sc_rms > 1e-10:
                # Gain reduction ratio
                ratio = sc_out_rms / sc_rms
                gain_envelope[start:end] = ratio

        # Apply gain envelope to main audio
        main_flat = audio.flatten().astype(np.float64)
        min_len_main = min(len(main_flat), len(gain_envelope))
        main_flat[:min_len_main] *= gain_envelope[:min_len_main]

        # Reshape back
        if audio.ndim == 1:
            return main_flat.astype(np.float32)
        else:
            return main_flat.reshape(audio.shape).astype(np.float32)

    def validate_params(self, params: dict[str, Any]) -> list[str]:
        """
        Validate plugin parameters and return list of issues.

        Override in subclasses to add parameter validation.

        Args:
            params: Plugin parameters dict.

        Returns:
            List of validation error strings. Empty list = valid.
        """
        return []

    def get_param(self, params: dict[str, Any], key: str, default: Any = None) -> Any:
        """
        Safely get a parameter value with optional default.

        Args:
            params: Parameters dict.
            key: Parameter name.
            default: Default value if key not found.

        Returns:
            Parameter value or default.
        """
        return params.get(key, default)
