"""
bus.py — Send/Return bus system for VCMix.

Implements the Send/Return routing paradigm found in professional DAWs:
    - Each send bus has its own independent effect chain
    - Tracks send audio to buses at configurable send levels
    - Bus output (return) is mixed back into the master at return_level

Signal flow:
    Track → Insert Chain → [Send to Bus A at level 0.12]
                           [Send to Bus B at level 0.05]
                           → Direct to Master Mix
    Bus A → Effect Chain → Return to Master at return_level
    Bus B → Effect Chain → Return to Master at return_level

Usage:
    from vcmix.engine.bus import SendReturnBus
    bus = SendReturnBus(name="reverb_bus", effects=[...], return_level=0.15)
    bus_audio = bus.process(send_audio, registry, sample_rate)

Dependencies: numpy, vcmix.plugins
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

from vcmix.plugins.registry import PluginRegistry


@dataclass
class SendReturnBus:
    """
    A single Send/Return bus with its own effect chain.

    Args:
        name: Bus identifier (e.g. "reverb_bus", "delay_bus").
        effects: List of EffectConfig dicts for this bus's insert chain.
        return_level: Level at which this bus returns to the master mix (0.0-1.0).
    """

    name: str
    effects: list[dict[str, Any]] = field(default_factory=list)
    return_level: float = 0.15

    def process(
        self,
        send_audio: np.ndarray,
        registry: PluginRegistry,
        sample_rate: int = 44100,
    ) -> np.ndarray:
        """
        Process audio through this bus's effect chain.

        Args:
            send_audio: Audio sent to this bus (already scaled by send level).
            registry: Plugin registry for resolving effect plugins.
            sample_rate: Audio sample rate.

        Returns:
            Processed audio ready to be returned to the master mix.
        """
        audio = send_audio.copy()

        for effect_cfg in self.effects:
            plugin = registry.get(effect_cfg.get("name", ""))
            if plugin is None:
                continue
            params = effect_cfg.get("params", {})
            audio = plugin.process(audio, params, sample_rate)

        # Apply return level
        audio = audio * self.return_level

        return audio


@dataclass
class BusManager:
    """
    Manages all Send/Return buses for a project.

    Coordinates the send/return routing:
        1. Receives rendered track audio
        2. Sends to buses according to track's sends config
        3. Processes each bus through its effect chain
        4. Returns processed bus audio for master mix inclusion

    Args:
        buses: Dict mapping bus name to SendReturnBus instance.
    """

    buses: dict[str, SendReturnBus] = field(default_factory=dict)

    def process_sends(
        self,
        track_name: str,
        track_audio: np.ndarray,
        sends: dict[str, float],
        registry: PluginRegistry,
        sample_rate: int = 44100,
    ) -> dict[str, np.ndarray]:
        """
        Process all sends from a track to their respective buses.

        Args:
            track_name: Name of the source track.
            track_audio: Rendered track audio (after insert chain).
            sends: Dict of {bus_name: send_level} from track config.
            registry: Plugin registry.
            sample_rate: Audio sample rate.

        Returns:
            Dict of {bus_name: processed_return_audio} for mixing into master.
        """
        returns: dict[str, np.ndarray] = {}

        for bus_name, send_level in sends.items():
            bus = self.buses.get(bus_name)
            if bus is None:
                continue

            # Scale track audio by send level
            send_audio = track_audio * send_level

            # Process through bus effect chain
            return_audio = bus.process(send_audio, registry, sample_rate)
            returns[bus_name] = return_audio

        return returns

    @classmethod
    def from_config(
        cls,
        sends_config: list[dict[str, Any]],
        bpm: float = 120.0,
    ) -> BusManager:
        """
        Create a BusManager from YAML sends configuration.

        Args:
            sends_config: List of send bus config dicts from YAML.
            bpm: Project BPM for note-value conversion.

        Returns:
            Configured BusManager instance.
        """
        from vcmix.config.parser import convert_note_values

        buses: dict[str, SendReturnBus] = {}
        for bus_cfg in sends_config:
            bus_name = bus_cfg.get("name", "unknown_bus")
            effects = bus_cfg.get("effects", [])
            return_level = bus_cfg.get("return_level", 0.15)

            # Convert note values in bus effect params
            for effect in effects:
                if "params" in effect and isinstance(effect["params"], dict):
                    effect["params"] = convert_note_values(effect["params"], bpm)

            buses[bus_name] = SendReturnBus(
                name=bus_name,
                effects=effects,
                return_level=return_level,
            )

        return cls(buses=buses)

    def mix_returns(
        self,
        all_returns: list[dict[str, np.ndarray]],
        max_samples: int,
    ) -> np.ndarray:
        """
        Mix all bus returns into a single return signal.

        Args:
            all_returns: List of {bus_name: audio} dicts from each track.
            max_samples: Expected output length in samples.

        Returns:
            Summed return audio array.
        """
        output = np.zeros(max_samples, dtype=np.float64)

        for track_returns in all_returns:
            for bus_name, return_audio in track_returns.items():
                # Ensure matching length
                length = min(len(return_audio.flatten()), max_samples)
                flat = return_audio.flatten()
                output[:length] += flat[:length]

        return output.astype(np.float32)
