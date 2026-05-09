"""
macro.py — Macro controller for VC-Chain.

Implements the 8-Macro control system compatible with Waves StudioRack:
    - Each Macro maps a normalized knob (0.0-1.0) to one or more plugin parameters
    - Supports range mapping (min/max) and inverse mapping
    - One Macro can control multiple parameters across multiple plugins

Mapping formula:
    Normal:  param_value = min + macro_value * (max - min)
    Inverse: param_value = max - macro_value * (max - min)

Usage:
    from vcmix.chain.macro import MacroController
    from vcmix.chain.models import MacroConfig, MacroMapping

    macros = [
        MacroConfig(
            name="Brightness",
            mapping=[
                MacroMapping(plugin="vc-eq", param="high_gain", range=(0, 6)),
            ],
        ),
    ]
    controller = MacroController(macros)
    updates = controller.apply_all({"Brightness": 0.7})
    # updates == {"vc-eq": {"high_gain": 4.2}}

Dependencies: vcmix.chain.models
"""

from __future__ import annotations

import logging
from typing import Any

from vcmix.chain.models import MAX_MACROS, MacroConfig, MacroMapping

logger = logging.getLogger(__name__)


class MacroController:
    """Macro controller for VC-Chain.

    Manages up to 8 Macro controllers, each mapping a normalized knob
    value to one or more plugin parameters.

    Args:
        macros: List of MacroConfig instances (max 8).
    """

    def __init__(self, macros: list[MacroConfig] | None = None) -> None:
        self._macros: list[MacroConfig] = (macros or [])[:MAX_MACROS]
        self._macro_index: dict[str, MacroConfig] = {
            m.name: m for m in self._macros
        }

    @property
    def macros(self) -> list[MacroConfig]:
        """List of Macro configurations."""
        return list(self._macros)

    @property
    def count(self) -> int:
        """Number of defined Macros."""
        return len(self._macros)

    def get_macro(self, name: str) -> MacroConfig | None:
        """Get a Macro by name.

        Args:
            name: Macro name.

        Returns:
            MacroConfig or None if not found.
        """
        return self._macro_index.get(name)

    def get_macro_by_index(self, index: int) -> MacroConfig | None:
        """Get a Macro by index (0-7).

        Args:
            index: Macro index (0-based).

        Returns:
            MacroConfig or None if out of range.
        """
        if 0 <= index < len(self._macros):
            return self._macros[index]
        return None

    def apply(self, macro_name: str, value: float) -> dict[str, dict[str, float]]:
        """Apply a single Macro value.

        Maps the normalized value (0.0-1.0) to all mapped parameters.

        Args:
            macro_name: Macro name.
            value: Normalized knob value (0.0-1.0).

        Returns:
            Dict of {plugin_name: {param_name: param_value}}.
        """
        macro = self._macro_index.get(macro_name)
        if macro is None:
            logger.warning("Macro '%s' not found", macro_name)
            return {}

        return self._compute_mapping(macro, value)

    def apply_all(
        self, macro_values: dict[str, float]
    ) -> dict[str, dict[str, float]]:
        """Apply all Macro values.

        Args:
            macro_values: Dict of macro_name -> normalized value (0.0-1.0).

        Returns:
            Merged dict of {plugin_name: {param_name: param_value}}.
            If multiple macros map to the same parameter, the last one wins.
        """
        result: dict[str, dict[str, float]] = {}

        for macro_name, value in macro_values.items():
            updates = self.apply(macro_name, value)
            for plugin_name, params in updates.items():
                if plugin_name not in result:
                    result[plugin_name] = {}
                result[plugin_name].update(params)

        return result

    def get_current_values(
        self,
        chain_params: dict[str, dict[str, float]],
    ) -> dict[str, float]:
        """Reverse-compute Macro knob values from current parameter values.

        Given current plugin parameter values, compute what Macro knob
        positions would produce those values.

        Args:
            chain_params: Dict of {plugin_name: {param_name: value}}.

        Returns:
            Dict of macro_name -> normalized value (0.0-1.0).
        """
        result: dict[str, float] = {}

        for macro in self._macros:
            # Use the first mapping to reverse-compute the knob position
            if not macro.mapping:
                continue

            # Try to find a mapping where we have the current param value
            knob_value = 0.5  # Default to center

            for mapping in macro.mapping:
                plugin_params = chain_params.get(mapping.plugin, {})
                current_val = plugin_params.get(mapping.param)
                if current_val is not None:
                    min_val, max_val = mapping.range
                    if max_val == min_val:
                        knob_value = 0.5
                    elif mapping.inverse:
                        knob_value = (max_val - current_val) / (max_val - min_val)
                    else:
                        knob_value = (current_val - min_val) / (max_val - min_val)
                    # Clamp to 0-1
                    knob_value = max(0.0, min(1.0, knob_value))
                    break

            result[macro.name] = knob_value

        return result

    @staticmethod
    def _compute_mapping(
        macro: MacroConfig, value: float
    ) -> dict[str, dict[str, float]]:
        """Compute parameter values from a Macro config and normalized value.

        Args:
            macro: MacroConfig with mappings.
            value: Normalized knob value (0.0-1.0).

        Returns:
            Dict of {plugin_name: {param_name: param_value}}.
        """
        # Clamp value to 0-1
        value = max(0.0, min(1.0, value))

        result: dict[str, dict[str, float]] = {}

        for mapping in macro.mapping:
            min_val, max_val = mapping.range

            if mapping.inverse:
                param_value = max_val - value * (max_val - min_val)
            else:
                param_value = min_val + value * (max_val - min_val)

            if mapping.plugin not in result:
                result[mapping.plugin] = {}
            result[mapping.plugin][mapping.param] = param_value

        return result

    def describe(self) -> list[dict[str, Any]]:
        """Get a human-readable description of all Macros.

        Returns:
            List of Macro description dicts.
        """
        descriptions = []
        for i, macro in enumerate(self._macros):
            desc: dict[str, Any] = {
                "index": i,
                "name": macro.name,
                "mapping_count": len(macro.mapping),
                "mappings": [],
            }
            for mapping in macro.mapping:
                desc["mappings"].append({
                    "plugin": mapping.plugin,
                    "param": mapping.param,
                    "range": list(mapping.range),
                    "inverse": mapping.inverse,
                })
            descriptions.append(desc)
        return descriptions
