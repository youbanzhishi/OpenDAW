"""
vst3_host_bridge.py — Python-to-C++ VST3 Host bridge.

Bridges Python code to the C++ VST3 Host library using ctypes.
Provides a Python-friendly interface for:
- Loading/unloading VST3 plugins
- Creating audio processor instances
- Setting/getting parameters
- Processing audio buffers
- Saving/restoring plugin state

If the C++ library is not available, falls back to a mock implementation
for testing and development.
"""

from __future__ import annotations

import ctypes
import platform
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np


@dataclass
class VST3HostConfig:
    """Configuration for the VST3 Host bridge."""
    library_path: Optional[str] = None
    sample_rate: int = 44100
    block_size: int = 512
    max_channels: int = 8


@dataclass
class PluginParameterInfo:
    """Information about a plugin parameter."""
    index: int
    name: str
    current_value: float     # normalized [0,1]
    default_value: float     # normalized [0,1]
    param_id: str = ""       # VST3 param ID string
    category: str = ""


class VST3HostBridge:
    """
    Bridge to the C++ VST3 Host library.

    Uses ctypes to call the native library, with automatic fallback
    to a mock implementation if the library is not found.

    Usage:
        bridge = VST3HostBridge()
        handle = bridge.load_plugin("/usr/lib/vst3/Serum.vst3")
        bridge.setup_processing(handle, 44100, 512)
        bridge.set_parameter(handle, 0, 0.5)
        output = bridge.process_audio(handle, input_audio)
        bridge.unload_plugin(handle)
    """

    def __init__(self, config: Optional[VST3HostConfig] = None) -> None:
        self.config = config or VST3HostConfig()
        self._lib = None
        self._handles: dict[int, dict] = {}
        self._next_handle = 1
        self._is_mock = True

        self._load_library()

    @property
    def is_native(self) -> bool:
        """True if using the native C++ library."""
        return not self._is_mock

    @property
    def is_mock(self) -> bool:
        """True if using mock implementation."""
        return self._is_mock

    def _load_library(self) -> None:
        """Try to load the native C++ library."""
        lib_path = self.config.library_path
        if lib_path is None:
            lib_path = self._find_library()

        if lib_path and Path(lib_path).exists():
            try:
                self._lib = ctypes.CDLL(lib_path)
                self._is_mock = False
                self._setup_c_functions()
            except OSError:
                self._lib = None
                self._is_mock = True

    def _find_library(self) -> Optional[str]:
        """Find the VST3 Host library on the system."""
        system = platform.system()

        # Check relative paths first
        candidates = []
        if system == "Darwin":
            candidates = [
                "vst3_host/libvst3host.dylib",
                "/usr/local/lib/libvst3host.dylib",
            ]
        elif system == "Linux":
            candidates = [
                "vst3_host/libvst3host.so",
                "/usr/local/lib/libvst3host.so",
                "/usr/lib/libvst3host.so",
            ]
        elif system == "Windows":
            candidates = [
                "vst3_host\\vst3host.dll",
                "C:\\Program Files\\OpenDAW\\vst3host.dll",
            ]

        for path in candidates:
            if Path(path).exists():
                return path

        return None

    def _setup_c_functions(self) -> None:
        """Setup ctypes function signatures for the C++ library."""
        if self._lib is None:
            return

        # vst3_host_create()
        self._lib.vst3_host_create.restype = ctypes.c_void_p
        self._lib.vst3_host_create.argtypes = []

        # vst3_host_destroy(host)
        self._lib.vst3_host_destroy.restype = None
        self._lib.vst3_host_destroy.argtypes = [ctypes.c_void_p]

        # vst3_load_plugin(host, path) -> handle
        self._lib.vst3_load_plugin.restype = ctypes.c_int
        self._lib.vst3_load_plugin.argtypes = [ctypes.c_void_p, ctypes.c_char_p]

        # vst3_setup_processing(host, handle, sample_rate, block_size)
        self._lib.vst3_setup_processing.restype = ctypes.c_int
        self._lib.vst3_setup_processing.argtypes = [
            ctypes.c_void_p, ctypes.c_int, ctypes.c_double, ctypes.c_int
        ]

        # vst3_set_parameter(host, handle, index, value)
        self._lib.vst3_set_parameter.restype = None
        self._lib.vst3_set_parameter.argtypes = [
            ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_float
        ]

        # vst3_get_parameter(host, handle, index) -> float
        self._lib.vst3_get_parameter.restype = ctypes.c_float
        self._lib.vst3_get_parameter.argtypes = [
            ctypes.c_void_p, ctypes.c_int, ctypes.c_int
        ]

    # ── Plugin Management ──────────────────────────────────────────────────

    def load_plugin(self, path: str) -> int:
        """
        Load a VST3 plugin.

        Args:
            path: Path to the VST3 plugin bundle.

        Returns:
            Handle (integer ID) for the loaded plugin.
        """
        handle = self._next_handle
        self._next_handle += 1

        if self._is_mock:
            self._handles[handle] = {
                "path": path,
                "sample_rate": self.config.sample_rate,
                "block_size": self.config.block_size,
                "parameters": {},  # index -> value
                "param_info": [],  # list of PluginParameterInfo
                "state": None,
                "prepared": False,
            }
        else:
            # Native: call C++ function
            result = self._lib.vst3_load_plugin(
                self._host_ptr, path.encode("utf-8")
            )
            if result < 0:
                raise RuntimeError(f"Failed to load plugin: {path}")
            self._handles[handle] = {
                "native_handle": result,
                "path": path,
            }

        return handle

    def unload_plugin(self, handle: int) -> None:
        """Unload a previously loaded plugin."""
        if handle in self._handles:
            del self._handles[handle]

    def setup_processing(
        self, handle: int, sample_rate: int, block_size: int
    ) -> None:
        """Configure processing parameters for a plugin."""
        if handle not in self._handles:
            raise ValueError(f"Invalid plugin handle: {handle}")

        info = self._handles[handle]
        info["sample_rate"] = sample_rate
        info["block_size"] = block_size
        info["prepared"] = True

    def create_processor(self, handle: int) -> None:
        """Create an AudioProcessor instance for the plugin."""
        if handle not in self._handles:
            raise ValueError(f"Invalid plugin handle: {handle}")
        # In mock mode, processor creation is implicit
        self._handles[handle]["processor_created"] = True

    # ── Parameters ─────────────────────────────────────────────────────────

    def set_parameter(self, handle: int, index: int, value: float) -> None:
        """Set a parameter by index (normalized 0-1)."""
        if handle not in self._handles:
            raise ValueError(f"Invalid plugin handle: {handle}")
        value = max(0.0, min(1.0, value))
        self._handles[handle]["parameters"][index] = value

    def get_parameter(self, handle: int, index: int) -> float:
        """Get a parameter value by index."""
        if handle not in self._handles:
            raise ValueError(f"Invalid plugin handle: {handle}")
        return self._handles[handle]["parameters"].get(index, 0.0)

    def get_parameter_name(self, handle: int, index: int) -> str:
        """Get a parameter name by index."""
        if handle not in self._handles:
            raise ValueError(f"Invalid plugin handle: {handle}")
        param_info = self._handles[handle].get("param_info", [])
        if 0 <= index < len(param_info):
            return param_info[index].name
        return f"Param {index}"

    def get_parameter_count(self, handle: int) -> int:
        """Get the number of parameters."""
        if handle not in self._handles:
            raise ValueError(f"Invalid plugin handle: {handle}")
        return len(self._handles[handle].get("param_info", []))

    def get_all_parameters(self, handle: int) -> list[PluginParameterInfo]:
        """Get info for all parameters."""
        if handle not in self._handles:
            raise ValueError(f"Invalid plugin handle: {handle}")
        return list(self._handles[handle].get("param_info", []))

    def set_param_info(self, handle: int, params: list[PluginParameterInfo]) -> None:
        """Set parameter info (for mock/testing)."""
        if handle not in self._handles:
            raise ValueError(f"Invalid plugin handle: {handle}")
        self._handles[handle]["param_info"] = params

    # ── Audio Processing ───────────────────────────────────────────────────

    def process_audio(
        self,
        handle: int,
        input_audio: np.ndarray,
        num_channels: int = 2,
    ) -> np.ndarray:
        """
        Process audio through the plugin.

        Args:
            handle: Plugin handle.
            input_audio: Input audio buffer (1D or 2D float32).
            num_channels: Number of output channels.

        Returns:
            Processed audio buffer.
        """
        if handle not in self._handles:
            raise ValueError(f"Invalid plugin handle: {handle}")

        if not self._handles[handle].get("prepared", False):
            raise RuntimeError("Plugin not prepared for processing")

        if self._is_mock:
            # Mock: passthrough with slight gain (simulates processing)
            output = input_audio.copy().astype(np.float32)
            # Apply parameter modifications as simple gain
            for idx, val in self._handles[handle]["parameters"].items():
                if idx == 0 and val != 0.0:
                    output = output * (0.5 + val)
            return output
        else:
            # Native: would call C++ function
            return input_audio.copy()

    # ── State Management ───────────────────────────────────────────────────

    def get_state(self, handle: int) -> bytes:
        """
        Get the current plugin state (for save/preset).

        Returns:
            Serialized state as bytes.
        """
        if handle not in self._handles:
            raise ValueError(f"Invalid plugin handle: {handle}")

        import json
        state = {
            "path": self._handles[handle]["path"],
            "parameters": {
                str(k): v for k, v in self._handles[handle]["parameters"].items()
            },
        }
        return json.dumps(state).encode("utf-8")

    def set_state(self, handle: int, state: bytes) -> None:
        """
        Restore plugin state (for load/preset).

        Args:
            handle: Plugin handle.
            state: Serialized state bytes.
        """
        if handle not in self._handles:
            raise ValueError(f"Invalid plugin handle: {handle}")

        import json
        data = json.loads(state.decode("utf-8"))
        self._handles[handle]["parameters"] = {
            int(k): v for k, v in data.get("parameters", {}).items()
        }

    # ── Utility ────────────────────────────────────────────────────────────

    def get_loaded_plugins(self) -> list[int]:
        """Get list of loaded plugin handles."""
        return list(self._handles.keys())

    def is_plugin_loaded(self, handle: int) -> bool:
        """Check if a plugin handle is valid."""
        return handle in self._handles

    def close(self) -> None:
        """Close the bridge and unload all plugins."""
        self._handles.clear()
        if self._lib is not None:
            # Would call vst3_host_destroy in native mode
            self._lib = None
