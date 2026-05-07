"""
automation_engine.py — Automation rendering engine for VCMix.

Reads automation definitions from YAML project config, builds
AutomationCurve instances, and provides frame-by-frame parameter
queries during the rendering loop to override static plugin parameters.

Integration with Renderer:
    The AutomationEngine is designed to be called from the main render
    loop. At each processing frame, the engine computes the current beat
    position and returns parameter overrides for each track's effects.

YAML configuration format:
    tracks:
      - name: vocal
        file: vocal.wav
        automation:
          gain:
            - [0, -6, linear]
            - [8, 0, linear]
          vc-reverb.wet:
            - [0, 0.2, linear]
            - [16, 0.5, linear]

    The automation key can be:
      - "gain" — Track-level gain automation (dB)
      - "plugin_name.param" — Plugin parameter automation

Usage:
    from vcmix.automation.automation_engine import AutomationEngine

    engine = AutomationEngine.from_config(track_configs)
    params = engine.get_params_at_beat("vocal", 4.0)
    # {"gain": -3.0, "vc-reverb": {"wet": 0.35}}
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from vcmix.automation.automation_curve import AutomationCurve


@dataclass
class TrackAutomation:
    """Automation data for a single track.

    Attributes:
        track_name: Name of the track this automation belongs to.
        gain_curve: Automation curve for track gain (in dB).
        plugin_curves: Dict mapping plugin_name -> {param_name -> AutomationCurve}.
    """

    track_name: str
    gain_curve: AutomationCurve | None = None
    plugin_curves: dict[str, dict[str, AutomationCurve]] = field(default_factory=dict)

    def get_gain_at_beat(self, beat: float) -> float | None:
        """Get the automated gain value at a given beat.

        Args:
            beat: Position in beats.

        Returns:
            Gain in dB, or None if no gain automation.
        """
        if self.gain_curve is None:
            return None
        return self.gain_curve.value_at(beat)

    def get_plugin_params_at_beat(
        self, plugin_name: str, beat: float
    ) -> dict[str, float]:
        """Get automated parameter values for a plugin at a given beat.

        Args:
            plugin_name: Plugin identifier.
            beat: Position in beats.

        Returns:
            Dict of parameter_name -> automated_value.
        """
        if plugin_name not in self.plugin_curves:
            return {}
        return {
            param_name: curve.value_at(beat)
            for param_name, curve in self.plugin_curves[plugin_name].items()
        }


class AutomationEngine:
    """Engine for querying automation values during rendering.

    Manages all track automation curves and provides a unified interface
    for the rendering loop to query parameter overrides at any beat position.

    Args:
        track_automations: Dict mapping track_name -> TrackAutomation.
        bpm: Project BPM for beat-to-time conversion.
    """

    def __init__(
        self,
        track_automations: dict[str, TrackAutomation] | None = None,
        bpm: float = 120.0,
    ) -> None:
        """Initialize the automation engine.

        Args:
            track_automations: Pre-built track automation data.
            bpm: Project BPM.
        """
        self.track_automations = track_automations or {}
        self.bpm = bpm

    @classmethod
    def from_config(
        cls,
        track_configs: list[dict[str, Any]],
        bpm: float = 120.0,
    ) -> AutomationEngine:
        """Build an AutomationEngine from YAML track config dicts.

        Each track config may have an "automation" key containing
        parameter automation definitions.

        Args:
            track_configs: List of track config dicts (from YAML).
            bpm: Project BPM.

        Returns:
            Configured AutomationEngine instance.
        """
        track_automations: dict[str, TrackAutomation] = {}

        for track_cfg in track_configs:
            if "automation" not in track_cfg:
                continue

            track_name = track_cfg.get("name", "unknown")
            automation_data = track_cfg["automation"]

            gain_curve = None
            plugin_curves: dict[str, dict[str, AutomationCurve]] = {}

            for key, point_list in automation_data.items():
                if not isinstance(point_list, list):
                    continue

                curve = AutomationCurve.from_list(point_list)

                if key == "gain":
                    gain_curve = curve
                elif "." in key:
                    # Plugin parameter: "vc-reverb.wet" -> plugin="vc-reverb", param="wet"
                    parts = key.split(".", 1)
                    plugin_name = parts[0]
                    param_name = parts[1]
                    if plugin_name not in plugin_curves:
                        plugin_curves[plugin_name] = {}
                    plugin_curves[plugin_name][param_name] = curve
                else:
                    # Treat as track-level parameter (not gain, not plugin)
                    # Store under a virtual plugin named "_track"
                    if "_track" not in plugin_curves:
                        plugin_curves["_track"] = {}
                    plugin_curves["_track"][key] = curve

            track_automations[track_name] = TrackAutomation(
                track_name=track_name,
                gain_curve=gain_curve,
                plugin_curves=plugin_curves,
            )

        return cls(track_automations=track_automations, bpm=bpm)

    def get_params_at_beat(
        self, track_name: str, beat: float
    ) -> dict[str, Any]:
        """Get all automation parameter overrides for a track at a given beat.

        Returns a dict with:
            - "gain": Automated gain in dB (if gain automation exists)
            - Plugin name -> {param -> value} for plugin automations

        Args:
            track_name: Track to query.
            beat: Position in beats.

        Returns:
            Dict of parameter overrides.
        """
        if track_name not in self.track_automations:
            return {}

        ta = self.track_automations[track_name]
        result: dict[str, Any] = {}

        # Gain automation
        gain = ta.get_gain_at_beat(beat)
        if gain is not None:
            result["gain"] = gain

        # Plugin parameter automation
        for plugin_name in ta.plugin_curves:
            if plugin_name == "_track":
                # Track-level non-gain automation
                for param_name, curve in ta.plugin_curves["_track"].items():
                    result[param_name] = curve.value_at(beat)
            else:
                plugin_params = ta.get_plugin_params_at_beat(plugin_name, beat)
                if plugin_params:
                    result[plugin_name] = plugin_params

        return result

    def get_plugin_params_at_beat(
        self, track_name: str, plugin_name: str, beat: float
    ) -> dict[str, float]:
        """Get automation overrides for a specific plugin at a given beat.

        Args:
            track_name: Track name.
            plugin_name: Plugin identifier.
            beat: Position in beats.

        Returns:
            Dict of param_name -> value for the specified plugin.
        """
        if track_name not in self.track_automations:
            return {}

        ta = self.track_automations[track_name]
        return ta.get_plugin_params_at_beat(plugin_name, beat)

    def get_gain_at_beat(self, track_name: str, beat: float) -> float | None:
        """Get the automated gain for a track at a given beat.

        Args:
            track_name: Track name.
            beat: Position in beats.

        Returns:
            Gain in dB, or None if no gain automation for this track.
        """
        if track_name not in self.track_automations:
            return None
        return self.track_automations[track_name].get_gain_at_beat(beat)

    def apply_automation_to_params(
        self,
        track_name: str,
        plugin_name: str,
        static_params: dict[str, Any],
        beat: float,
    ) -> dict[str, Any]:
        """Merge automation overrides into static plugin parameters.

        Automation values take precedence over static values.

        Args:
            track_name: Track name.
            plugin_name: Plugin identifier.
            static_params: Original (static) parameters.
            beat: Current beat position.

        Returns:
            Updated parameters dict with automation overrides applied.
        """
        overrides = self.get_plugin_params_at_beat(track_name, plugin_name, beat)
        if not overrides:
            return dict(static_params)

        result = dict(static_params)
        for param_name, value in overrides.items():
            result[param_name] = value
        return result

    @property
    def automated_track_names(self) -> list[str]:
        """List of track names that have automation."""
        return list(self.track_automations.keys())

    @property
    def has_automation(self) -> bool:
        """Whether any track has automation defined."""
        return len(self.track_automations) > 0

    def time_to_beat(self, time_seconds: float) -> float:
        """Convert time in seconds to beat position.

        Args:
            time_seconds: Time in seconds.

        Returns:
            Position in beats.
        """
        return time_seconds * self.bpm / 60.0

    def beat_to_time(self, beat: float) -> float:
        """Convert beat position to time in seconds.

        Args:
            beat: Position in beats.

        Returns:
            Time in seconds.
        """
        return beat * 60.0 / self.bpm
