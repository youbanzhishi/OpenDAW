"""
adapter.py — PluginAdapter abstract base class for VCMix.

Defines the standard interface that all plugin adapters must implement.
Every adapter takes (audio, params, sample_rate) and returns processed audio.

The adapter pattern decouples the rendering engine from the plugin
implementation, allowing:
    - VC CLI subprocess calls (VCPluginAdapter)
    - Pure Python/numpy effects (native adapters, Phase 2)
    - VST3 hosting via external bridge (Phase 5)

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
