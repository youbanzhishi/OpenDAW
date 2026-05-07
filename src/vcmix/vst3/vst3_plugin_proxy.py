"""
vst3_plugin_proxy.py — Python-side proxy for VST3 plugins.

Provides high-level Python interface for:
- Parameter enumeration and type inference
- Preset management (reading VST3 preset files)
- State snapshots (undo/redo)
- Parameter automation

Works on top of VST3HostBridge or VST3Proxy.
"""

from __future__ import annotations

import copy
import json
import struct
import time
from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path
from typing import Any, Optional

import numpy as np

from vcmix.vst3.vst3_host_bridge import PluginParameterInfo, VST3HostBridge


class ParamType(Enum):
    """Inferred parameter type."""
    CONTINUOUS = auto()     # Float knob [0,1]
    SWITCH = auto()         # On/off toggle
    INTEGER = auto()        # Integer steps
    ENUM = auto()           # Categorical selection


@dataclass
class ParamSnapshot:
    """Snapshot of all parameter values."""
    values: dict[int, float]  # index -> normalized value
    timestamp: float = 0.0
    label: str = ""


@dataclass
class PresetInfo:
    """Information about a VST3 preset."""
    name: str
    path: str
    category: str = ""
    vendor: str = ""
    is_factory: bool = False


class ParameterEnumerator:
    """Enumerates and infers types for plugin parameters."""

    @staticmethod
    def infer_type(
        name: str,
        default_value: float,
        num_steps: int = 0,
    ) -> ParamType:
        """
        Infer parameter type from name and default value.

        Args:
            name: Parameter name.
            default_value: Default normalized value.
            num_steps: Number of quantization steps (0 = continuous).

        Returns:
            Inferred ParamType.
        """
        name_lower = name.lower()

        # Switch detection
        if any(kw in name_lower for kw in ("on/off", "bypass", "enable", "mute",
                                            "solo", "power", "active", "toggle")):
            return ParamType.SWITCH

        # Enum detection
        if any(kw in name_lower for kw in ("mode", "type", "select", "shape",
                                            "algorithm", "routing")):
            return ParamType.ENUM

        # Integer detection
        if num_steps > 1 and num_steps <= 128:
            return ParamType.INTEGER

        # Default: continuous
        return ParamType.CONTINUOUS

    @staticmethod
    def enumerate_params(
        params: list[PluginParameterInfo],
    ) -> list[dict[str, Any]]:
        """
        Create detailed parameter enumeration with inferred types.

        Args:
            params: List of PluginParameterInfo.

        Returns:
            List of dicts with extended parameter info.
        """
        result = []
        for p in params:
            ptype = ParameterEnumerator.infer_type(p.name, p.default_value)
            result.append({
                "index": p.index,
                "name": p.name,
                "param_id": p.param_id,
                "type": ptype.name,
                "current": p.current_value,
                "default": p.default_value,
                "category": p.category,
            })
        return result


class PresetManager:
    """Manages VST3 plugin presets."""

    # VST3 preset file magic number
    VST3_PRESET_MAGIC = b'VST3'

    def __init__(self, plugin_path: str) -> None:
        self.plugin_path = plugin_path
        self._presets: list[PresetInfo] = []

    def scan_presets(self) -> list[PresetInfo]:
        """
        Scan for preset files associated with this plugin.

        Looks in:
        - Plugin bundle's Contents/Resources/Presets/
        - User preset directory

        Returns:
            List of PresetInfo for found presets.
        """
        presets: list[PresetInfo] = []
        plugin_dir = Path(self.plugin_path)

        if not plugin_dir.exists():
            return presets

        # Scan plugin bundle presets
        if plugin_dir.is_dir() and plugin_dir.suffix == ".vst3":
            preset_dir = plugin_dir / "Contents" / "Resources" / "Presets"
            if preset_dir.exists():
                for p in preset_dir.rglob("*.vstpreset"):
                    presets.append(PresetInfo(
                        name=p.stem,
                        path=str(p),
                        is_factory=True,
                        category=p.parent.stem,
                    ))

        # Scan user presets
        user_preset_dir = Path.home() / ".opendaw" / "presets"
        if user_preset_dir.exists():
            plugin_name = plugin_dir.stem
            for p in (user_preset_dir / plugin_name).rglob("*.vstpreset"):
                presets.append(PresetInfo(
                    name=p.stem,
                    path=str(p),
                    is_factory=False,
                ))

        self._presets = presets
        return presets

    def load_preset(self, preset_path: str) -> Optional[bytes]:
        """
        Load a preset file and extract the state data.

        Args:
            preset_path: Path to .vstpreset file.

        Returns:
            State data bytes, or None if loading fails.
        """
        try:
            with open(preset_path, "rb") as f:
                data = f.read()

            # Validate magic
            if data[:4] != self.VST3_PRESET_MAGIC:
                # Not a standard VST3 preset, return raw data
                return data

            # Parse VST3 preset header
            # Header: magic(4) + version(4) + class_id(32) + ...
            # For now, skip header and return the chunk data
            header_size = 64  # approximate
            if len(data) > header_size:
                return data[header_size:]
            return data

        except (IOError, OSError):
            return None

    def save_preset(
        self,
        preset_path: str,
        state_data: bytes,
        class_id: str = "",
    ) -> bool:
        """
        Save plugin state as a VST3 preset file.

        Args:
            preset_path: Output path for .vstpreset file.
            state_data: Serialized plugin state.
            class_id: Plugin class ID (optional).

        Returns:
            True if save was successful.
        """
        try:
            Path(preset_path).parent.mkdir(parents=True, exist_ok=True)

            with open(preset_path, "wb") as f:
                # Write header
                f.write(self.VST3_PRESET_MAGIC)
                f.write(struct.pack("<I", 1))  # version
                f.write(class_id.encode("utf-8").ljust(32, b'\x00')[:32])
                # Pad header
                f.write(b'\x00' * 24)
                # Write state data
                f.write(state_data)

            return True
        except (IOError, OSError):
            return False

    @property
    def presets(self) -> list[PresetInfo]:
        return self._presets


class StateSnapshotManager:
    """Manages state snapshots for undo/redo."""

    def __init__(self, max_history: int = 50) -> None:
        self._undo_stack: list[ParamSnapshot] = []
        self._redo_stack: list[ParamSnapshot] = []
        self._max_history = max_history

    def push(self, values: dict[int, float], label: str = "") -> None:
        """Push a new snapshot onto the undo stack."""
        snapshot = ParamSnapshot(
            values=copy.deepcopy(values),
            timestamp=time.time(),
            label=label,
        )
        self._undo_stack.append(snapshot)
        self._redo_stack.clear()

        # Limit history
        if len(self._undo_stack) > self._max_history:
            self._undo_stack.pop(0)

    def undo(self) -> Optional[ParamSnapshot]:
        """Pop from undo stack and push to redo stack."""
        if not self._undo_stack:
            return None
        snapshot = self._undo_stack.pop()
        self._redo_stack.append(snapshot)
        return snapshot

    def redo(self) -> Optional[ParamSnapshot]:
        """Pop from redo stack and push to undo stack."""
        if not self._redo_stack:
            return None
        snapshot = self._redo_stack.pop()
        self._undo_stack.append(snapshot)
        return snapshot

    @property
    def can_undo(self) -> bool:
        return len(self._undo_stack) > 0

    @property
    def can_redo(self) -> bool:
        return len(self._redo_stack) > 0

    @property
    def undo_count(self) -> int:
        return len(self._undo_stack)

    @property
    def redo_count(self) -> int:
        return len(self._redo_stack)

    def clear(self) -> None:
        """Clear all history."""
        self._undo_stack.clear()
        self._redo_stack.clear()


class VST3PluginProxy:
    """
    High-level Python proxy for a VST3 plugin.

    Combines VST3HostBridge, PresetManager, and StateSnapshotManager
    into a unified, Python-friendly interface.

    Usage:
        proxy = VST3PluginProxy("/usr/lib/vst3/Serum.vst3")
        proxy.setup(44100, 512)
        proxy.set_parameter(0, 0.5)
        output = proxy.process(input_audio)
        proxy.save_snapshot("init")
        proxy.set_parameter(0, 0.8)
        proxy.undo()  # back to init values
    """

    def __init__(
        self,
        plugin_path: str,
        bridge: Optional[VST3HostBridge] = None,
        sample_rate: int = 44100,
        block_size: int = 512,
    ) -> None:
        self.plugin_path = plugin_path
        self._bridge = bridge or VST3HostBridge()
        self._sample_rate = sample_rate
        self._block_size = block_size
        self._handle: Optional[int] = None

        # Sub-managers
        self._preset_mgr = PresetManager(plugin_path)
        self._snapshot_mgr = StateSnapshotManager()
        self._param_enumerator = ParameterEnumerator()

        # Current parameter values cache
        self._current_params: dict[int, float] = {}

        # Load plugin
        self._handle = self._bridge.load_plugin(plugin_path)

    @property
    def is_loaded(self) -> bool:
        return self._handle is not None

    @property
    def handle(self) -> Optional[int]:
        return self._handle

    @property
    def snapshot_manager(self) -> StateSnapshotManager:
        return self._snapshot_mgr

    @property
    def preset_manager(self) -> PresetManager:
        return self._preset_mgr

    # ── Setup ──────────────────────────────────────────────────────────────

    def setup(self, sample_rate: int = 44100, block_size: int = 512) -> None:
        """Configure the plugin for processing."""
        self._sample_rate = sample_rate
        self._block_size = block_size
        if self._handle is not None:
            self._bridge.setup_processing(self._handle, sample_rate, block_size)

    # ── Parameters ─────────────────────────────────────────────────────────

    def set_parameter(self, index: int, value: float) -> None:
        """Set a parameter value (normalized 0-1)."""
        value = max(0.0, min(1.0, value))
        self._current_params[index] = value
        if self._handle is not None:
            self._bridge.set_parameter(self._handle, index, value)

    def get_parameter(self, index: int) -> float:
        """Get a parameter value."""
        if self._handle is not None:
            return self._bridge.get_parameter(self._handle, index)
        return self._current_params.get(index, 0.0)

    def get_parameter_name(self, index: int) -> str:
        """Get a parameter name."""
        if self._handle is not None:
            return self._bridge.get_parameter_name(self._handle, index)
        return f"Param {index}"

    def enumerate_parameters(self) -> list[dict[str, Any]]:
        """Get detailed parameter enumeration with type inference."""
        params = self._bridge.get_all_parameters(self._handle or 0)
        return self._param_enumerator.enumerate_params(params)

    def get_all_parameter_values(self) -> dict[int, float]:
        """Get all current parameter values."""
        return dict(self._current_params)

    # ── Snapshots ──────────────────────────────────────────────────────────

    def save_snapshot(self, label: str = "") -> None:
        """Save current parameter state as a snapshot."""
        self._snapshot_mgr.push(self._current_params.copy(), label=label)

    def undo(self) -> bool:
        """Undo to previous snapshot.

        Pops current state from undo stack (pushes to redo),
        then restores the new top of the undo stack.
        """
        # Pop current from undo -> redo
        popped = self._snapshot_mgr.undo()
        if popped is None:
            return False
        # Now peek at the new top of undo stack by doing another undo
        # and then putting it back via redo
        prev = self._snapshot_mgr.undo()  # This pops previous and pushes to redo
        if prev is not None:
            # Restore from previous snapshot
            self._current_params = copy.deepcopy(prev.values)
            # Redo to put prev back on undo stack (it went to redo)
            self._snapshot_mgr.redo()
        else:
            # No previous state; the popped item was the only one
            # Restore empty/default
            self._current_params = copy.deepcopy(popped.values)
        self._apply_params()
        return True

    def redo(self) -> bool:
        """Redo to next snapshot."""
        snapshot = self._snapshot_mgr.redo()
        if snapshot is None:
            return False
        self._current_params = copy.deepcopy(snapshot.values)
        self._apply_params()
        return True

    def _apply_params(self) -> None:
        """Apply current params to the bridge."""
        if self._handle is not None:
            for idx, val in self._current_params.items():
                self._bridge.set_parameter(self._handle, idx, val)

    # ── Presets ────────────────────────────────────────────────────────────

    def scan_presets(self) -> list[PresetInfo]:
        """Scan for available presets."""
        return self._preset_mgr.scan_presets()

    def load_preset(self, preset_path: str) -> bool:
        """Load a preset file."""
        state_data = self._preset_mgr.load_preset(preset_path)
        if state_data is not None and self._handle is not None:
            self._bridge.set_state(self._handle, state_data)
            # Update local cache
            for idx, val in self._bridge.get_all_parameters(self._handle):
                pass  # Refresh from bridge
            return True
        return False

    def save_preset(self, preset_path: str) -> bool:
        """Save current state as a preset."""
        if self._handle is None:
            return False
        state_data = self._bridge.get_state(self._handle)
        return self._preset_mgr.save_preset(preset_path, state_data)

    # ── Processing ─────────────────────────────────────────────────────────

    def process(self, input_audio: np.ndarray) -> np.ndarray:
        """Process audio through the plugin."""
        if self._handle is None:
            return input_audio
        return self._bridge.process_audio(self._handle, input_audio)

    # ── State ──────────────────────────────────────────────────────────────

    def get_state(self) -> bytes:
        """Get serialized plugin state."""
        if self._handle is None:
            return b""
        return self._bridge.get_state(self._handle)

    def set_state(self, state: bytes) -> None:
        """Restore plugin state."""
        if self._handle is not None:
            self._bridge.set_state(self._handle, state)

    # ── Cleanup ────────────────────────────────────────────────────────────

    def close(self) -> None:
        """Unload the plugin and release resources."""
        if self._handle is not None:
            self._bridge.unload_plugin(self._handle)
            self._handle = None
