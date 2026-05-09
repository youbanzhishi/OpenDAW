"""
engine.py — Chain execution engine for VC-Chain.

Processes audio through a chain configuration with support for:
    - Serial processing: signal passes through effects sequentially
    - Parallel processing: signal splits into wet/dry paths, mixed after
    - Multiband processing: signal splits by frequency, each band processed independently

Execution order: Serial -> Parallel -> Multiband

The engine uses VCMix's PluginRegistry to resolve plugin adapters,
falling back to passthrough if a plugin is not available.

Usage:
    from vcmix.chain import ChainConfig, ChainEngine

    chain = ChainConfig.from_yaml_file("cla-vocal.yaml")
    engine = ChainEngine(chain)
    output = engine.process(audio, sample_rate=44100)

Dependencies: numpy, vcmix.plugins.registry, vcmix.audio.mixer
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np

from vcmix.chain.models import ChainConfig, ChainStep, ParallelBranch
from vcmix.plugins.registry import PluginRegistry

logger = logging.getLogger(__name__)


class ChainEngine:
    """Chain execution engine.

    Processes audio through a ChainConfig with serial/parallel/multiband routing.

    Args:
        chain: ChainConfig instance defining the processing chain.
        registry: PluginRegistry instance for resolving plugin adapters.
            If None, creates a default registry.
    """

    def __init__(
        self,
        chain: ChainConfig,
        registry: PluginRegistry | None = None,
    ) -> None:
        self.chain = chain
        self._registry = registry or PluginRegistry()

    def process(
        self,
        audio: np.ndarray,
        sample_rate: int = 44100,
        macro_values: dict[str, float] | None = None,
    ) -> np.ndarray:
        """Process audio through the chain.

        Execution order: Serial -> Parallel -> Multiband

        Args:
            audio: Input audio buffer (1D mono or 2D multi-channel).
            sample_rate: Audio sample rate.
            macro_values: Optional dict of macro name -> value (0.0-1.0).
                Applied before processing.

        Returns:
            Processed audio buffer (same shape as input).
        """
        # Apply macro values if provided
        if macro_values:
            self._apply_macros(macro_values)

        result = audio.copy()

        # 1. Serial processing
        if self.chain.serial:
            result = self._process_serial(result, sample_rate)

        # 2. Parallel processing
        if self.chain.parallel:
            result = self._process_parallel(result, sample_rate)

        # 3. Multiband processing
        if self.chain.multiband and self.chain.multiband.bands:
            result = self._process_multiband(result, sample_rate)

        return result

    def _apply_macros(self, macro_values: dict[str, float]) -> None:
        """Apply macro values to chain step parameters.

        For each macro, maps the normalized value (0.0-1.0) to the
        target parameter's range.

        Args:
            macro_values: Dict of macro name -> normalized value (0.0-1.0).
        """
        from vcmix.chain.macro import MacroController

        controller = MacroController(self.chain.macro)

        # Get parameter updates from all macros
        updates = controller.apply_all(macro_values)

        # Apply updates to chain steps
        for step in self.chain.serial:
            if step.plugin in updates:
                for param_name, param_value in updates[step.plugin].items():
                    step.params[param_name] = param_value

        for branch in self.chain.parallel:
            for step in branch.chain:
                if step.plugin in updates:
                    for param_name, param_value in updates[step.plugin].items():
                        step.params[param_name] = param_value

    def _process_serial(
        self,
        audio: np.ndarray,
        sample_rate: int,
    ) -> np.ndarray:
        """Process audio through serial chain steps.

        Signal passes through each effect sequentially.

        Args:
            audio: Input audio buffer.
            sample_rate: Audio sample rate.

        Returns:
            Processed audio buffer.
        """
        result = audio
        for step in self.chain.serial:
            if not step.enabled:
                continue
            result = self._process_step(result, step, sample_rate)
        return result

    def _process_parallel(
        self,
        audio: np.ndarray,
        sample_rate: int,
    ) -> np.ndarray:
        """Process audio through parallel branches.

        For each branch:
            1. Copy the input signal
            2. Process through the branch's chain
            3. Mix wet signal with dry signal at branch.mix ratio

        Multiple parallel branches are summed with the dry signal.

        Args:
            audio: Input audio buffer.
            sample_rate: Audio sample rate.

        Returns:
            Processed audio buffer.
        """
        result = audio.copy()

        for branch in self.chain.parallel:
            wet = audio.copy()
            # Process wet signal through branch chain
            for step in branch.chain:
                if not step.enabled:
                    continue
                wet = self._process_step(wet, step, sample_rate)

            # Mix: result = dry * (1 - mix) + wet * mix
            mix = float(branch.mix)
            result = result * (1.0 - mix) + wet * mix

        return result

    def _process_multiband(
        self,
        audio: np.ndarray,
        sample_rate: int,
    ) -> np.ndarray:
        """Process audio through multiband configuration.

        For each band:
            1. Apply bandpass filter to extract the frequency range
            2. Process the band through its chain
            3. Sum all processed bands

        Note: This is a simplified implementation using basic FFT filters.
        A production implementation would use Linkwitz-Riley crossover filters.

        Args:
            audio: Input audio buffer.
            sample_rate: Audio sample rate.

        Returns:
            Processed audio buffer.
        """
        mb = self.chain.multiband
        if not mb or not mb.bands:
            return audio

        # Simple band-splitting using numpy FFT
        result = np.zeros_like(audio)

        for band in mb.bands:
            # Extract band
            band_audio = self._bandpass_filter(
                audio, band.range[0], band.range[1], sample_rate
            )

            # Process band through its chain
            for step in band.chain:
                if not step.enabled:
                    continue
                band_audio = self._process_step(band_audio, step, sample_rate)

            # Sum to result
            result = result + band_audio

        return result

    def _process_step(
        self,
        audio: np.ndarray,
        step: ChainStep,
        sample_rate: int,
    ) -> np.ndarray:
        """Process audio through a single chain step.

        Looks up the plugin adapter from the registry and calls process().
        If the plugin is not found, returns audio unchanged with a warning.

        Args:
            audio: Input audio buffer.
            step: ChainStep with plugin name and params.
            sample_rate: Audio sample rate.

        Returns:
            Processed audio buffer.
        """
        adapter = self._registry.get(step.plugin)
        if adapter is None:
            logger.warning(
                "Plugin '%s' not found in registry, passing through", step.plugin
            )
            return audio

        try:
            return adapter.process(audio, dict(step.params), sample_rate)
        except Exception as e:
            logger.error(
                "Plugin '%s' processing failed: %s — passing through",
                step.plugin, e,
            )
            return audio

    @staticmethod
    def _bandpass_filter(
        audio: np.ndarray,
        low_hz: float,
        high_hz: float,
        sample_rate: int,
    ) -> np.ndarray:
        """Apply a basic bandpass filter using FFT.

        Extracts the frequency range [low_hz, high_hz] from the audio.

        This is a simplified implementation. A production version would use
        Linkwitz-Riley crossover filters for phase-coherent band splitting.

        Args:
            audio: Input audio buffer.
            low_hz: Lower frequency cutoff.
            high_hz: Upper frequency cutoff.
            sample_rate: Audio sample rate.

        Returns:
            Band-limited audio buffer.
        """
        if audio.ndim == 1:
            n = len(audio)
            fft = np.fft.rfft(audio.astype(np.float64))
            freqs = np.fft.rfftfreq(n, 1.0 / sample_rate)

            # Create bandpass mask
            mask = (freqs >= low_hz) & (freqs <= high_hz)

            # Apply mask
            fft_filtered = fft.copy()
            fft_filtered[~mask] = 0

            return np.fft.irfft(fft_filtered, n).astype(np.float32)
        else:
            # Multi-channel: process each channel
            result = np.zeros_like(audio)
            for ch in range(audio.shape[0]):
                result[ch] = ChainEngine._bandpass_filter(
                    audio[ch], low_hz, high_hz, sample_rate
                )
            return result

    def get_signal_flow(self) -> dict[str, Any]:
        """Get a description of the signal flow for visualization.

        Returns:
            Dict describing the routing structure.
        """
        flow: dict[str, Any] = {
            "name": self.chain.name,
            "stages": [],
        }

        if self.chain.serial:
            flow["stages"].append({
                "type": "serial",
                "steps": [s.to_dict() for s in self.chain.serial],
            })

        if self.chain.parallel:
            flow["stages"].append({
                "type": "parallel",
                "branches": [b.to_dict() for b in self.chain.parallel],
            })

        if self.chain.multiband and self.chain.multiband.bands:
            flow["stages"].append({
                "type": "multiband",
                "crossover": self.chain.multiband.crossover,
                "bands": [b.to_dict() for b in self.chain.multiband.bands],
            })

        return flow
