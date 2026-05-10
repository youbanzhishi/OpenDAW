"""
midi_router.py — MIDI event routing and plugin host integration for VCMix.

Routes MIDI events from input sources (hardware, virtual keyboard, file playback)
to plugin instances through the virtual channel system and CC mapping engine.

Pipeline:
    Input → VirtualChannel (routing/mute/solo/transpose) → CC Mapping (parameter control)
                                                        → Plugin Host (note trigger)

Usage:
    from vcmix.midi.midi_router import MidiRouter

    router = MidiRouter()
    router.setup_default_channels()
    router.bind_cc("synth_1", cc=1, param_name="filter_cutoff", min_val=20, max_val=20000, curve="log")
    router.on_note_on(note=60, velocity=100, channel=0)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from vcmix.midi.cc_mapping import CCMap, CCMappingEngine, CCCurve, ParamUpdate
from vcmix.midi.midi_parser import MidiNote
from vcmix.midi.virtual_channel import RoutedEvent, VirtualChannelManager


# Type alias for plugin note callbacks
NoteCallback = Callable[[str, int, int, float, float], None]
# (plugin_id, note, velocity, volume, pan)

# Type alias for plugin param callbacks
ParamCallback = Callable[[str, str, float | bool], None]
# (plugin_id, param_name, value)


@dataclass
class RouterStats:
    """Statistics about the MIDI router.

    Attributes:
        notes_routed: Total notes routed.
        cc_routed: Total CC events routed.
        notes_dropped: Notes dropped (muted/solo filter).
        cc_dropped: CC events dropped (filter).
    """

    notes_routed: int = 0
    cc_routed: int = 0
    notes_dropped: int = 0
    cc_dropped: int = 0


class MidiRouter:
    """Route MIDI events to plugins through channels and CC mappings.

    Integrates VirtualChannelManager and CCMappingEngine to provide
    a complete MIDI routing pipeline from input to plugin.

    Args:
        note_callback: Called when a note should trigger a plugin.
        param_callback: Called when a CC should update a plugin parameter.
    """

    def __init__(
        self,
        note_callback: NoteCallback | None = None,
        param_callback: ParamCallback | None = None,
    ) -> None:
        """Initialize the MIDI router.

        Args:
            note_callback: Optional callback for routed note events.
            param_callback: Optional callback for routed parameter updates.
        """
        self.channels = VirtualChannelManager()
        self.cc_engine = CCMappingEngine()
        self._note_callback = note_callback
        self._param_callback = param_callback
        self._stats = RouterStats()

    # ── Setup ────────────────────────────────────────────────────────────

    def setup_default_channels(self) -> None:
        """Create default 16 MIDI channels (0-15).

        Each channel is named 'Ch_0' through 'Ch_15' with no output routing.
        """
        for i in range(16):
            if self.channels.get_channel(i) is None:
                self.channels.create_channel(i, name=f"Ch_{i}")

    def bind_cc(
        self,
        plugin_id: str,
        cc: int,
        param_name: str,
        min_val: float = 0.0,
        max_val: float = 1.0,
        curve: str = "linear",
        channel: int | None = None,
    ) -> None:
        """Convenience method to bind a CC to a plugin parameter.

        Args:
            plugin_id: Plugin identifier.
            cc: MIDI CC number (0-127).
            param_name: Parameter name in the plugin.
            min_val: Minimum parameter value.
            max_val: Maximum parameter value.
            curve: Curve type ('linear', 'log', 'toggle').
            channel: Optional channel filter.
        """
        curve_enum = CCCurve(curve)
        mapping = CCMap(
            cc=cc,
            param_name=param_name,
            min_val=min_val,
            max_val=max_val,
            curve=curve_enum,
            channel=channel,
        )
        self.cc_engine.add_mapping(plugin_id, mapping)

    # ── Event Processing ─────────────────────────────────────────────────

    def on_note_on(self, note: int, velocity: int, channel: int = 0) -> RoutedEvent | None:
        """Process a Note On event.

        Routes through virtual channel, then triggers the note callback.

        Args:
            note: MIDI note number (0-127).
            velocity: Velocity (1-127).
            channel: MIDI channel (0-15).

        Returns:
            RoutedEvent if routed, None if dropped.
        """
        event = self.channels.route_note_on(note, velocity, channel)
        if event is None:
            self._stats.notes_dropped += 1
            return None

        self._stats.notes_routed += 1

        # Trigger note callback
        if self._note_callback and event.output:
            self._note_callback(
                event.output, event.note, event.velocity, event.volume, event.pan
            )

        return event

    def on_note_off(self, note: int, velocity: int = 0, channel: int = 0) -> RoutedEvent | None:
        """Process a Note Off event.

        Args:
            note: MIDI note number (0-127).
            velocity: Release velocity.
            channel: MIDI channel (0-15).

        Returns:
            RoutedEvent if routed, None if dropped.
        """
        event = self.channels.route_note_off(note, velocity, channel)
        if event is not None:
            # Note off passes through even for muted channels (prevent stuck notes)
            self._stats.notes_routed += 1
        return event

    def on_cc(self, cc: int, value: int, channel: int = 0) -> list[ParamUpdate]:
        """Process a CC event.

        Routes through virtual channel, then through CC mapping engine.

        Args:
            cc: CC number (0-127).
            value: CC value (0-127).
            channel: MIDI channel (0-15).

        Returns:
            List of parameter updates.
        """
        event = self.channels.route_cc(cc, value, channel)
        if event is None:
            self._stats.cc_dropped += 1
            return []

        self._stats.cc_routed += 1

        # Process through CC mapping engine
        updates = self.cc_engine.process_cc(cc, value, channel)

        # Trigger param callbacks
        if self._param_callback:
            for plugin_id, param_name, value in updates:
                self._param_callback(plugin_id, param_name, value)

        return updates

    def on_midi_message(self, msg: Any) -> None:
        """Process a mido.Message object.

        Dispatches to the appropriate handler based on message type.

        Args:
            msg: mido.Message object.
        """
        if msg.type == "note_on" and msg.velocity > 0:
            self.on_note_on(msg.note, msg.velocity, msg.channel)
        elif msg.type == "note_off" or (msg.type == "note_on" and msg.velocity == 0):
            self.on_note_off(msg.note, 0, msg.channel)
        elif msg.type == "control_change":
            self.on_cc(msg.control, msg.value, msg.channel)

    # ── Batch Processing ─────────────────────────────────────────────────

    def route_midi_notes(self, notes: list[MidiNote]) -> list[RoutedEvent]:
        """Route a batch of MidiNote objects through the router.

        Args:
            notes: List of MidiNote objects (from parser).

        Returns:
            List of RoutedEvent objects (note_on only).
        """
        events: list[RoutedEvent] = []
        for note in notes:
            event = self.on_note_on(note.note, note.velocity, note.channel)
            if event:
                events.append(event)
        return events

    # ── Stats ────────────────────────────────────────────────────────────

    @property
    def stats(self) -> RouterStats:
        """Current router statistics."""
        return self._stats

    def reset_stats(self) -> None:
        """Reset router statistics."""
        self._stats = RouterStats()

    # ── Callbacks ────────────────────────────────────────────────────────

    def set_note_callback(self, cb: NoteCallback) -> None:
        """Set the note event callback.

        Args:
            cb: Callback function (plugin_id, note, velocity, volume, pan).
        """
        self._note_callback = cb

    def set_param_callback(self, cb: ParamCallback) -> None:
        """Set the parameter update callback.

        Args:
            cb: Callback function (plugin_id, param_name, value).
        """
        self._param_callback = cb
