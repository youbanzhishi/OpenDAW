"""
vst3_track.py — VST3 track type for VCMix rendering engine.

Integrates VST3 plugins into the VCMix YAML rendering pipeline.
A VST3 track can be either:
- An **effect** track: processes existing audio through a VST3 effect
- An **instrument** track: generates audio from MIDI input via VST3 synth

YAML configuration:
    tracks:
      - name: synth
        type: vst3
        plugin_path: "/usr/lib/vst3/Serum.vst3"
        preset: "Init"
        params:
          - index: 1
            value: 0.5
        midi_file: melody.mid

      - name: vocal_fx
        type: vst3
        plugin_path: "/usr/lib/vst3/FabFilter.vst3"
        file: vocal.wav
        params:
          - index: 3
            value: 0.7
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

from vcmix.vst3.vst3_proxy import VST3Proxy
from vcmix.vst3.vst3_scanner import VST3PluginInfo, VST3Scanner


@dataclass
class VST3ParamOverride:
    """A single parameter override for a VST3 track."""
    index: int
    value: float   # normalized [0.0, 1.0]


@dataclass
class VST3TrackConfig:
    """Configuration for a VST3 track (from YAML)."""
    name: str
    plugin_path: str
    file: str = ""                          # input audio (for effects)
    preset: str = ""                        # factory preset name
    preset_file: str = ""                   # .vstpreset file path
    params: list[VST3ParamOverride] = field(default_factory=list)
    midi_file: str = ""                     # .mid or .json MIDI file
    bpm: float = 120.0
    sample_rate: int = 44100
    volume: float = 1.0
    mute: bool = False
    effects: list[Any] = field(default_factory=list)  # post-VST3 insert chain
    cli_path: str | None = None             # vst3_host binary path


class VST3Track:
    """
    A VST3 plugin track for the VCMix rendering engine.

    Supports two modes:
    1. **Effect mode**: Input audio → VST3 effect → output audio
    2. **Instrument mode**: MIDI input → VST3 synth → output audio

    Usage:
        config = VST3TrackConfig(
            name="synth",
            plugin_path="/usr/lib/vst3/Serum.vst3",
            params=[VST3ParamOverride(index=1, value=0.5)],
            midi_file="melody.mid",
        )
        track = VST3Track(config)
        output = track.render()
    """

    def __init__(self, config: VST3TrackConfig) -> None:
        self.config = config
        self._proxy = VST3Proxy(
            plugin_path=config.plugin_path,
            cli_path=config.cli_path,
            sample_rate=config.sample_rate,
        )

    @property
    def name(self) -> str:
        return self.config.name

    @property
    def is_instrument(self) -> bool:
        """True if this track has no input file (MIDI-driven synth)."""
        return not self.config.file and bool(self.config.midi_file)

    @staticmethod
    def scan_plugins(
        cli_path: str | None = None,
        extra_paths: list[str] | None = None,
    ) -> list[VST3PluginInfo]:
        """
        Scan system for installed VST3 plugins.

        Args:
            cli_path: Path to vst3_host binary (auto-detect if None).
            extra_paths: Additional VST3 search directories.

        Returns:
            List of discovered VST3PluginInfo.
        """
        scanner = VST3Scanner(cli_path=cli_path, extra_paths=extra_paths)
        return scanner.scan()

    def load_plugin(self, preset: str = "") -> None:
        """
        Load the VST3 plugin (via proxy).

        Args:
            preset: Factory preset name to load.
        """
        # Apply parameter overrides
        for param in self.config.params:
            self._proxy.set_param(param.index, param.value)

        # Load preset if specified
        actual_preset = preset or self.config.preset
        if actual_preset:
            self._proxy.load_preset(actual_preset)
        elif self.config.preset_file:
            self._proxy.load_preset(self.config.preset_file)

    def set_param(self, index: int, value: float) -> None:
        """Set a VST3 parameter (normalized [0,1])."""
        value = max(0.0, min(1.0, value))
        self._proxy.set_param(index, value)

    def get_param_info(self) -> list[dict[str, Any]]:
        """
        Get parameter information from the loaded plugin.

        Returns:
            List of param info dicts with 'index', 'name', 'current', 'default'.
        """
        params = self._proxy.get_params()
        return [
            {
                "index": p.index,
                "name": p.name,
                "current": p.current_value,
                "default": p.default_value,
            }
            for p in params
        ]

    def render(
        self,
        input_audio: np.ndarray | None = None,
        midi_events: list[dict[str, Any]] | None = None,
        duration: float = 0.0,
    ) -> np.ndarray:
        """
        Render this VST3 track.

        For effect tracks: processes input_audio through the VST3 effect.
        For instrument tracks: generates audio from MIDI events.

        Args:
            input_audio: Input audio buffer (for effect mode).
            midi_events: MIDI event list (for instrument mode).
            duration: Render duration in seconds (for instrument mode).
                If 0, calculated from MIDI events or defaults to 10s.

        Returns:
            Rendered audio buffer.
        """
        if self.config.mute:
            # Return silence
            if input_audio is not None:
                return np.zeros_like(input_audio)
            sr = self.config.sample_rate
            dur = duration or 10.0
            return np.zeros(int(sr * dur), dtype=np.float32)

        # Apply parameter overrides
        self._proxy.clear_params()
        for param in self.config.params:
            self._proxy.set_param(param.index, param.value)

        if self.is_instrument:
            # Instrument mode
            if duration <= 0:
                duration = 10.0  # default
            output = self._proxy.render_instrument(
                duration=duration,
                midi_events=midi_events,
                midi_file=self.config.midi_file or None,
                bpm=self.config.bpm,
            )
        else:
            # Effect mode
            if input_audio is None:
                raise ValueError(
                    f"VST3 effect track '{self.name}' requires input_audio"
                )
            output = self._proxy.render_effect(
                input_audio=input_audio,
                sample_rate=self.config.sample_rate,
            )

        # Apply track volume
        if self.config.volume != 1.0:
            output = output * self.config.volume

        return output

    @classmethod
    def from_yaml_track(cls, track_config: Any) -> "VST3Track":
        """
        Create a VST3Track from a parsed YAML TrackConfig.

        Args:
            track_config: TrackConfig instance with type='vst3'.

        Returns:
            VST3Track instance.
        """
        # Extract VST3-specific fields
        plugin_path = getattr(track_config, "plugin_path", "")
        if not plugin_path:
            raise ValueError(
                f"VST3 track '{track_config.name}' missing plugin_path"
            )

        # Parse param overrides
        param_overrides = []
        raw_params = getattr(track_config, "params", [])
        if isinstance(raw_params, list):
            for p in raw_params:
                if isinstance(p, dict):
                    param_overrides.append(VST3ParamOverride(
                        index=int(p.get("index", 0)),
                        value=float(p.get("value", 0.5)),
                    ))

        config = VST3TrackConfig(
            name=track_config.name,
            plugin_path=plugin_path,
            file=getattr(track_config, "file", ""),
            preset=getattr(track_config, "preset", ""),
            preset_file=getattr(track_config, "preset_file", ""),
            params=param_overrides,
            midi_file=getattr(track_config, "midi_file", "") or "",
            bpm=getattr(track_config, "bpm", 120.0),
            sample_rate=44100,
            volume=getattr(track_config, "volume", 1.0),
            mute=getattr(track_config, "mute", False),
        )

        return cls(config)
