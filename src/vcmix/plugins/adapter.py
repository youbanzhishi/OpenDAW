"""
adapter.py — PluginAdapter base class for VCMix.

Defines the interface that all plugins must implement:
    - process(): Apply the plugin to an audio buffer
    - get_parameters(): Return current parameter state
    - set_parameters(): Update parameters from a dict

Two plugin backends:
    1. Native Python plugins (implement process() directly)
    2. VC CLI plugins (shell out to AudioFX CLI executables)

Usage:
    class MyPlugin(PluginAdapter):
        def process(self, audio, sample_rate):
            return audio * self.gain

    plugin = MyPlugin(name="my_gain", gain=0.8)
    result = plugin.process(audio, 44100)

Dependencies: numpy, abc
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

import numpy as np


@dataclass
class PluginAdapter(ABC):
    """
    Abstract base class for all VCMix plugins.

    Args:
        name: Unique plugin instance name.
        enabled: Whether the plugin is active.
        parameters: Dict of plugin-specific parameters.
    """

    name: str
    enabled: bool = True
    parameters: dict[str, Any] = field(default_factory=dict)

    @abstractmethod
    def process(self, audio: np.ndarray, sample_rate: int) -> np.ndarray:
        """
        Process audio buffer through this plugin.

        Args:
            audio: Input audio buffer (1D mono or 2D multi-channel).
            sample_rate: Sample rate in Hz.

        Returns:
            Processed audio buffer (same shape as input).
        """
        ...

    def get_parameters(self) -> dict[str, Any]:
        """Return current parameter state."""
        return dict(self.parameters)

    def set_parameters(self, params: dict[str, Any]) -> None:
        """Update parameters from a dict."""
        self.parameters.update(params)

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(name={self.name!r}, enabled={self.enabled})"
