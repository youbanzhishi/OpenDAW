"""
cc_mapping.py — MIDI CC to plugin parameter mapping for VCMix.

Maps incoming MIDI Control Change (CC) messages to plugin parameters,
enabling real-time control of synth/effect parameters from MIDI
controllers. Supports:

    - Named parameter binding (CC number → plugin parameter name)
    - Value scaling (MIDI 0-127 → parameter range)
    - Curve types: linear, logarithmic, toggle
    - Bidirectional feedback (parameter → CC value)
    - Multi-plugin routing (one CC can control multiple parameters)

Usage:
    from vcmix.midi.cc_mapping import CCMap, CCMappingEngine

    mapping = CCMap(cc=1, param_name="filter_cutoff", min_val=20.0, max_val=20000.0, curve="log")
    engine = CCMappingEngine()
    engine.add_mapping("synth_1", mapping)

    # Process incoming CC
    param_updates = engine.process_cc(1, 64)  # CC#1, value 64
    for plugin_id, param_name, value in param_updates:
        print(f"{plugin_id}.{param_name} = {value}")
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class CCCurve(Enum):
    """Curve type for CC value mapping.

    - LINEAR: Straight line from min_val to max_val.
    - LOG: Logarithmic curve (good for frequency/gain).
    - TOGGLE: On/off switch (value >= 64 = on, < 64 = off).
    """

    LINEAR = "linear"
    LOG = "log"
    TOGGLE = "toggle"


@dataclass
class CCMap:
    """A single CC-to-parameter mapping.

    Attributes:
        cc: MIDI CC number (0-127).
        param_name: Target parameter name in the plugin.
        min_val: Minimum parameter value (when CC = 0).
        max_val: Maximum parameter value (when CC = 127).
        curve: Mapping curve type.
        channel: Optional MIDI channel filter (None = all channels).
        inverted: If True, CC 0 = max_val, CC 127 = min_val.
    """

    cc: int
    param_name: str
    min_val: float = 0.0
    max_val: float = 1.0
    curve: CCCurve = CCCurve.LINEAR
    channel: int | None = None
    inverted: bool = False

    def __post_init__(self) -> None:
        """Validate CC mapping values."""
        if not 0 <= self.cc <= 127:
            raise ValueError(f"CC number must be 0-127, got {self.cc}")
        if self.min_val >= self.max_val and self.curve != CCCurve.TOGGLE:
            raise ValueError(
                f"min_val ({self.min_val}) must be < max_val ({self.max_val})"
            )

    def map_value(self, cc_value: int) -> float | bool:
        """Convert a MIDI CC value to a parameter value.

        Args:
            cc_value: MIDI CC value (0-127).

        Returns:
            Mapped parameter value (float for linear/log, bool for toggle).
        """
        if not 0 <= cc_value <= 127:
            raise ValueError(f"CC value must be 0-127, got {cc_value}")

        if self.inverted:
            cc_value = 127 - cc_value

        if self.curve == CCCurve.TOGGLE:
            return cc_value >= 64

        # Normalized position 0.0 - 1.0
        t = cc_value / 127.0

        if self.curve == CCCurve.LINEAR:
            return self.min_val + t * (self.max_val - self.min_val)

        if self.curve == CCCurve.LOG:
            # Logarithmic interpolation
            if self.min_val <= 0:
                # Fallback to linear if min is 0 or negative
                return self.min_val + t * (self.max_val - self.min_val)
            log_min = math.log(self.min_val)
            log_max = math.log(self.max_val)
            return math.exp(log_min + t * (log_max - log_min))

        return self.min_val + t * (self.max_val - self.min_val)

    def reverse_map(self, param_value: float) -> int:
        """Convert a parameter value back to a MIDI CC value.

        Useful for feedback (sending current parameter state to controller).

        Args:
            param_value: Current parameter value.

        Returns:
            Corresponding MIDI CC value (0-127).
        """
        if self.curve == CCCurve.TOGGLE:
            cc_val = 127 if param_value else 0
        elif self.curve == CCCurve.LOG and self.min_val > 0:
            log_min = math.log(self.min_val)
            log_max = math.log(self.max_val)
            if param_value <= self.min_val:
                t = 0.0
            elif param_value >= self.max_val:
                t = 1.0
            else:
                t = (math.log(param_value) - log_min) / (log_max - log_min)
            cc_val = int(t * 127.0)
        else:
            if self.max_val == self.min_val:
                t = 0.0
            else:
                t = (param_value - self.min_val) / (self.max_val - self.min_val)
            cc_val = int(t * 127.0)

        if self.inverted:
            cc_val = 127 - cc_val

        return max(0, min(127, cc_val))


# Type alias for parameter update: (plugin_id, param_name, value)
ParamUpdate = tuple[str, str, float | bool]


class CCMappingEngine:
    """Route MIDI CC messages to plugin parameters.

    Manages a collection of CC-to-parameter mappings organized by plugin.
    When a CC message is received, the engine looks up all matching
    mappings and produces parameter update events.

    Usage:
        engine = CCMappingEngine()
        engine.add_mapping("synth_1", CCMap(cc=1, param_name="cutoff", min_val=20, max_val=20000, curve=CCCurve.LOG))
        updates = engine.process_cc(1, 100)
    """

    def __init__(self) -> None:
        """Initialize the CC mapping engine."""
        # plugin_id -> list of CCMap
        self._mappings: dict[str, list[CCMap]] = {}
        # (cc, channel) -> list of (plugin_id, CCMap) for fast lookup
        self._lookup: dict[tuple[int, int | None], list[tuple[str, CCMap]]] = {}

    def add_mapping(self, plugin_id: str, mapping: CCMap) -> None:
        """Add a CC-to-parameter mapping.

        Args:
            plugin_id: Plugin identifier.
            mapping: CCMap defining the mapping.
        """
        if plugin_id not in self._mappings:
            self._mappings[plugin_id] = []
        self._mappings[plugin_id].append(mapping)
        self._rebuild_lookup()

    def remove_mapping(self, plugin_id: str, param_name: str) -> bool:
        """Remove a mapping by plugin ID and parameter name.

        Args:
            plugin_id: Plugin identifier.
            param_name: Parameter name to remove.

        Returns:
            True if a mapping was removed, False if not found.
        """
        if plugin_id not in self._mappings:
            return False
        before = len(self._mappings[plugin_id])
        self._mappings[plugin_id] = [
            m for m in self._mappings[plugin_id] if m.param_name != param_name
        ]
        if len(self._mappings[plugin_id]) < before:
            if not self._mappings[plugin_id]:
                del self._mappings[plugin_id]
            self._rebuild_lookup()
            return True
        return False

    def get_mappings(self, plugin_id: str) -> list[CCMap]:
        """Get all mappings for a plugin.

        Args:
            plugin_id: Plugin identifier.

        Returns:
            List of CCMap objects.
        """
        return list(self._mappings.get(plugin_id, []))

    def process_cc(
        self, cc: int, value: int, channel: int | None = None
    ) -> list[ParamUpdate]:
        """Process an incoming CC message and produce parameter updates.

        Args:
            cc: MIDI CC number (0-127).
            value: MIDI CC value (0-127).
            channel: Optional MIDI channel for matching.

        Returns:
            List of (plugin_id, param_name, mapped_value) tuples.
        """
        updates: list[ParamUpdate] = []
        # Check both channel-specific and channel-agnostic mappings
        for key in [(cc, channel), (cc, None)]:
            if key in self._lookup:
                for plugin_id, mapping in self._lookup[key]:
                    if mapping.channel is not None and channel is not None and mapping.channel != channel:
                        continue
                    mapped_value = mapping.map_value(value)
                    updates.append((plugin_id, mapping.param_name, mapped_value))
        # Deduplicate (same plugin+param could appear twice)
        seen: set[tuple[str, str]] = set()
        deduped: list[ParamUpdate] = []
        for u in updates:
            key = (u[0], u[1])
            if key not in seen:
                seen.add(key)
                deduped.append(u)
        return deduped

    def get_feedback(
        self, plugin_id: str, param_name: str, param_value: float | bool
    ) -> tuple[int, int] | None:
        """Get the CC number and value for a parameter (for feedback).

        Args:
            plugin_id: Plugin identifier.
            param_name: Parameter name.
            param_value: Current parameter value.

        Returns:
            (cc_number, cc_value) tuple, or None if no mapping found.
        """
        for mapping in self._mappings.get(plugin_id, []):
            if mapping.param_name == param_name:
                cc_val = mapping.reverse_map(param_value)
                return (mapping.cc, cc_val)
        return None

    def _rebuild_lookup(self) -> None:
        """Rebuild the fast-lookup index."""
        self._lookup.clear()
        for plugin_id, mappings in self._mappings.items():
            for mapping in mappings:
                key = (mapping.cc, mapping.channel)
                if key not in self._lookup:
                    self._lookup[key] = []
                self._lookup[key].append((plugin_id, mapping))

    @property
    def plugin_count(self) -> int:
        """Number of plugins with mappings."""
        return len(self._mappings)

    @property
    def total_mappings(self) -> int:
        """Total number of CC mappings across all plugins."""
        return sum(len(m) for m in self._mappings.values())

    def clear(self) -> None:
        """Remove all mappings."""
        self._mappings.clear()
        self._lookup.clear()
