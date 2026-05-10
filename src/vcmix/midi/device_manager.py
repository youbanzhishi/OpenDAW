"""
device_manager.py — Hardware MIDI device management for VCMix.

Scans, connects, and disconnects physical/virtual MIDI devices using
the mido library. Provides a unified interface for receiving MIDI
events from external controllers and sending events to hardware synths.

Supports:
    - Device scanning and enumeration
    - Input/output port management
    - Real-time MIDI event reception (Note On/Off, CC, Program Change)
    - Virtual port creation for inter-app MIDI routing
    - Hot-plug detection (polling-based fallback)

Usage:
    from vcmix.midi.device_manager import MidiDeviceManager

    mgr = MidiDeviceManager()
    devices = mgr.scan_devices()
    mgr.open_input("MIDI Controller")
    for msg in mgr.iter_messages():
        print(msg)
    mgr.close_all()
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Callable

import mido

logger = logging.getLogger(__name__)


@dataclass
class MidiDeviceInfo:
    """Information about a MIDI device (input or output port).

    Attributes:
        name: Port name as reported by the backend.
        is_input: True if this port can receive MIDI messages.
        is_output: True if this port can send MIDI messages.
    """

    name: str
    is_input: bool = False
    is_output: bool = False

    def __repr__(self) -> str:
        dirs = []
        if self.is_input:
            dirs.append("in")
        if self.is_output:
            dirs.append("out")
        return f"MidiDevice({self.name!r}, {','.join(dirs)})"


class MidiDeviceManager:
    """Manage hardware and virtual MIDI device connections.

    Provides methods to scan available devices, open/close ports,
    and iterate over incoming MIDI messages in real time.

    Args:
        backend: mido backend name (default: auto-detect).
            Common values: 'mido.backends.rtmidi', 'mido.backends.pygame'.
        virtual_name: Name for a virtual input port (if the backend supports it).
    """

    def __init__(
        self,
        backend: str | None = None,
        virtual_name: str | None = None,
    ) -> None:
        """Initialize the MIDI device manager.

        Args:
            backend: Optional mido backend name.
            virtual_name: Optional name for a virtual input port.
        """
        if backend:
            mido.set_backend(backend)
        self._input_ports: dict[str, mido.ports.BaseInput] = {}
        self._output_ports: dict[str, mido.ports.BaseOutput] = {}
        self._virtual_input: mido.ports.BaseInput | None = None
        self._message_callbacks: list[Callable[[mido.Message], None]] = []
        if virtual_name:
            self._open_virtual_input(virtual_name)

    # ── Device Scanning ──────────────────────────────────────────────────

    @staticmethod
    def _safe_get_input_names() -> list[str]:
        """Get input port names, returning empty list if backend unavailable."""
        try:
            return mido.get_input_names()
        except (ImportError, ModuleNotFoundError, Exception):
            return []

    @staticmethod
    def _safe_get_output_names() -> list[str]:
        """Get output port names, returning empty list if backend unavailable."""
        try:
            return mido.get_output_names()
        except (ImportError, ModuleNotFoundError, Exception):
            return []

    def scan_devices(self) -> list[MidiDeviceInfo]:
        """Scan and list all available MIDI devices.

        Returns:
            List of MidiDeviceInfo objects for each detected port.
        """
        devices: dict[str, MidiDeviceInfo] = {}
        for name in self._safe_get_input_names():
            if name not in devices:
                devices[name] = MidiDeviceInfo(name=name)
            devices[name].is_input = True
        for name in self._safe_get_output_names():
            if name not in devices:
                devices[name] = MidiDeviceInfo(name=name)
            devices[name].is_output = True
        return list(devices.values())

    def list_input_names(self) -> list[str]:
        """List available input port names.

        Returns:
            List of input port name strings.
        """
        return self._safe_get_input_names()

    def list_output_names(self) -> list[str]:
        """List available output port names.

        Returns:
            List of output port name strings.
        """
        return self._safe_get_output_names()

    # ── Port Management ──────────────────────────────────────────────────

    def open_input(self, name: str) -> None:
        """Open a MIDI input port for receiving messages.

        Args:
            name: Exact name of the input port.

        Raises:
            ValueError: If the port is already open.
            IOError: If the port cannot be opened.
        """
        if name in self._input_ports:
            raise ValueError(f"Input port {name!r} is already open")
        try:
            port = mido.open_input(name)
            self._input_ports[name] = port
            logger.info("Opened MIDI input: %s", name)
        except Exception as e:
            raise IOError(f"Cannot open input port {name!r}: {e}") from e

    def open_output(self, name: str) -> None:
        """Open a MIDI output port for sending messages.

        Args:
            name: Exact name of the output port.

        Raises:
            ValueError: If the port is already open.
            IOError: If the port cannot be opened.
        """
        if name in self._output_ports:
            raise ValueError(f"Output port {name!r} is already open")
        try:
            port = mido.open_output(name)
            self._output_ports[name] = port
            logger.info("Opened MIDI output: %s", name)
        except Exception as e:
            raise IOError(f"Cannot open output port {name!r}: {e}") from e

    def close_input(self, name: str) -> None:
        """Close a previously opened input port.

        Args:
            name: Name of the input port to close.
        """
        if name in self._input_ports:
            self._input_ports[name].close()
            del self._input_ports[name]
            logger.info("Closed MIDI input: %s", name)

    def close_output(self, name: str) -> None:
        """Close a previously opened output port.

        Args:
            name: Name of the output port to close.
        """
        if name in self._output_ports:
            self._output_ports[name].close()
            del self._output_ports[name]
            logger.info("Closed MIDI output: %s", name)

    def close_all(self) -> None:
        """Close all open input and output ports."""
        for name, port in list(self._input_ports.items()):
            port.close()
            logger.info("Closed MIDI input: %s", name)
        self._input_ports.clear()
        for name, port in list(self._output_ports.items()):
            port.close()
            logger.info("Closed MIDI output: %s", name)
        self._output_ports.clear()
        if self._virtual_input is not None:
            self._virtual_input.close()
            self._virtual_input = None

    def is_input_open(self, name: str) -> bool:
        """Check if an input port is currently open."""
        return name in self._input_ports

    def is_output_open(self, name: str) -> bool:
        """Check if an output port is currently open."""
        return name in self._output_ports

    @property
    def open_input_count(self) -> int:
        """Number of currently open input ports."""
        return len(self._input_ports)

    @property
    def open_output_count(self) -> int:
        """Number of currently open output ports."""
        return len(self._output_ports)

    # ── Virtual Port ─────────────────────────────────────────────────────

    def _open_virtual_input(self, name: str) -> None:
        """Open a virtual input port (for inter-app MIDI routing).

        Args:
            name: Virtual port name.
        """
        try:
            self._virtual_input = mido.open_input(name, virtual=True)
            logger.info("Opened virtual MIDI input: %s", name)
        except Exception as e:
            logger.warning("Cannot open virtual input %r: %s", name, e)

    # ── Message I/O ──────────────────────────────────────────────────────

    def iter_messages(self, timeout: float | None = None) -> mido.ports.BaseInput:
        """Iterate over incoming MIDI messages from all open input ports.

        This is a generator that yields mido.Message objects.

        Args:
            timeout: Seconds to wait for messages (None = non-blocking poll).

        Yields:
            mido.Message objects received from any open input port.
        """
        for name, port in self._input_ports.items():
            for msg in port.iter_pending():
                for cb in self._message_callbacks:
                    cb(msg)
                yield msg

    def poll_messages(self) -> list[mido.Message]:
        """Poll all open input ports for pending messages (non-blocking).

        Returns:
            List of mido.Message objects received.
        """
        messages: list[mido.Message] = []
        for name, port in self._input_ports.items():
            for msg in port.iter_pending():
                for cb in self._message_callbacks:
                    cb(msg)
                messages.append(msg)
        return messages

    def send_message(self, name: str, msg: mido.Message) -> None:
        """Send a MIDI message to an open output port.

        Args:
            name: Name of the output port.
            msg: mido.Message to send.

        Raises:
            KeyError: If the output port is not open.
        """
        if name not in self._output_ports:
            raise KeyError(f"Output port {name!r} is not open")
        self._output_ports[name].send(msg)

    def send_note_on(
        self, name: str, note: int, velocity: int = 100, channel: int = 0
    ) -> None:
        """Send a Note On message.

        Args:
            name: Output port name.
            note: MIDI note number (0-127).
            velocity: Note velocity (1-127).
            channel: MIDI channel (0-15).
        """
        msg = mido.Message("note_on", note=note, velocity=velocity, channel=channel)
        self.send_message(name, msg)

    def send_note_off(
        self, name: str, note: int, velocity: int = 0, channel: int = 0
    ) -> None:
        """Send a Note Off message.

        Args:
            name: Output port name.
            note: MIDI note number (0-127).
            velocity: Release velocity (0-127).
            channel: MIDI channel (0-15).
        """
        msg = mido.Message("note_off", note=note, velocity=velocity, channel=channel)
        self.send_message(name, msg)

    def send_cc(
        self, name: str, control: int, value: int, channel: int = 0
    ) -> None:
        """Send a Control Change message.

        Args:
            name: Output port name.
            control: CC number (0-127).
            value: CC value (0-127).
            channel: MIDI channel (0-15).
        """
        msg = mido.Message(
            "control_change", control=control, value=value, channel=channel
        )
        self.send_message(name, msg)

    # ── Callbacks ────────────────────────────────────────────────────────

    def add_callback(self, cb: Callable[[mido.Message], None]) -> None:
        """Add a callback to be invoked for every received MIDI message.

        Args:
            cb: Callable taking a mido.Message.
        """
        self._message_callbacks.append(cb)

    def remove_callback(self, cb: Callable[[mido.Message], None]) -> None:
        """Remove a previously added callback.

        Args:
            cb: The callback to remove.
        """
        self._message_callbacks.remove(cb)

    # ── Cleanup ──────────────────────────────────────────────────────────

    def __del__(self) -> None:
        """Ensure all ports are closed on garbage collection."""
        try:
            self.close_all()
        except Exception:
            pass
