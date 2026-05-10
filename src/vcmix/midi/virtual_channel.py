"""
virtual_channel.py — Virtual MIDI channel management for VCMix.

Manages multiple virtual MIDI channels that map to logical instruments
or zones within the DAW. Each virtual channel has its own:

    - MIDI channel number (0-15)
    - Name/label
    - Mute/solo state
    - Volume and pan
    - Output routing (which plugin/track it connects to)
    - CC pass-through filter

This enables complex routing like:
    - Channel 0 → Piano plugin
    - Channel 1 → Strings plugin
    - Channel 10 → Drum sampler
    - CC#1 on Channel 0 → Piano filter cutoff

Usage:
    from vcmix.midi.virtual_channel import VirtualChannelManager, VirtualChannel

    vcm = VirtualChannelManager()
    vcm.create_channel(0, name="Piano", output="piano_plugin")
    vcm.create_channel(1, name="Strings", output="strings_plugin")

    # Route a note
    vcm.route_note(note=60, velocity=100, channel=0)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class VirtualChannel:
    """A virtual MIDI channel with routing and mixing controls.

    Attributes:
        number: MIDI channel number (0-15).
        name: Human-readable channel name.
        output: Output routing target (plugin ID or track name).
        muted: Whether the channel is muted.
        solo: Whether the channel is soloed.
        volume: Channel volume (0.0-1.0).
        pan: Channel pan (-1.0 left to 1.0 right).
        transpose: Semitone transpose offset.
        cc_filter: Set of CC numbers to pass through (empty = all).
        enabled: Whether the channel is active.
    """

    number: int
    name: str = ""
    output: str = ""
    muted: bool = False
    solo: bool = False
    volume: float = 1.0
    pan: float = 0.0
    transpose: int = 0
    cc_filter: set[int] = field(default_factory=set)
    enabled: bool = True

    def __post_init__(self) -> None:
        """Validate channel values."""
        if not 0 <= self.number <= 15:
            raise ValueError(f"MIDI channel must be 0-15, got {self.number}")
        self.volume = max(0.0, min(1.0, self.volume))
        self.pan = max(-1.0, min(1.0, self.pan))


@dataclass
class RoutedEvent:
    """A MIDI event that has been routed through a virtual channel.

    Attributes:
        event_type: 'note_on', 'note_off', or 'cc'.
        channel: Virtual channel number.
        output: Output routing target.
        note: Note number (for note_on/note_off).
        velocity: Velocity (for note_on/note_off).
        cc: CC number (for cc events).
        cc_value: CC value (for cc events).
        volume: Channel volume at time of routing.
        pan: Channel pan at time of routing.
        transpose: Transpose offset applied.
    """

    event_type: str
    channel: int
    output: str
    note: int | None = None
    velocity: int | None = None
    cc: int | None = None
    cc_value: int | None = None
    volume: float = 1.0
    pan: float = 0.0
    transpose: int = 0


class VirtualChannelManager:
    """Manage virtual MIDI channels with routing and mixing.

    Provides channel creation, routing of MIDI events, and
    mute/solo logic following standard mixer conventions:
        - If any channel is soloed, only soloed channels produce output.
        - Muted channels never produce output (even if soloed, unless both).
        - Non-soloed, non-muted channels produce output normally.
    """

    def __init__(self) -> None:
        """Initialize the virtual channel manager."""
        self._channels: dict[int, VirtualChannel] = {}
        self._event_buffer: list[RoutedEvent] = []

    # ── Channel Management ───────────────────────────────────────────────

    def create_channel(
        self,
        number: int,
        name: str = "",
        output: str = "",
        muted: bool = False,
        solo: bool = False,
        volume: float = 1.0,
        pan: float = 0.0,
        transpose: int = 0,
        cc_filter: set[int] | None = None,
    ) -> VirtualChannel:
        """Create a new virtual channel.

        Args:
            number: MIDI channel number (0-15).
            name: Channel name.
            output: Output routing target.
            muted: Whether the channel starts muted.
            solo: Whether the channel starts soloed.
            volume: Initial volume (0.0-1.0).
            pan: Initial pan (-1.0 to 1.0).
            transpose: Semitone transpose offset.
            cc_filter: Set of CC numbers to pass through (None = all).

        Returns:
            The created VirtualChannel.

        Raises:
            ValueError: If channel number is already in use.
        """
        if number in self._channels:
            raise ValueError(f"Channel {number} already exists")
        ch = VirtualChannel(
            number=number,
            name=name or f"Ch_{number}",
            output=output,
            muted=muted,
            solo=solo,
            volume=volume,
            pan=pan,
            transpose=transpose,
            cc_filter=cc_filter if cc_filter is not None else set(),
        )
        self._channels[number] = ch
        return ch

    def remove_channel(self, number: int) -> bool:
        """Remove a virtual channel.

        Args:
            number: Channel number to remove.

        Returns:
            True if removed, False if not found.
        """
        if number in self._channels:
            del self._channels[number]
            return True
        return False

    def get_channel(self, number: int) -> VirtualChannel | None:
        """Get a virtual channel by number.

        Args:
            number: Channel number.

        Returns:
            VirtualChannel or None if not found.
        """
        return self._channels.get(number)

    def list_channels(self) -> list[VirtualChannel]:
        """List all virtual channels sorted by number.

        Returns:
            Sorted list of VirtualChannel objects.
        """
        return sorted(self._channels.values(), key=lambda c: c.number)

    @property
    def channel_count(self) -> int:
        """Number of virtual channels."""
        return len(self._channels)

    # ── Channel State ────────────────────────────────────────────────────

    def set_mute(self, number: int, muted: bool) -> None:
        """Set mute state for a channel.

        Args:
            number: Channel number.
            muted: True to mute, False to unmute.
        """
        if number in self._channels:
            self._channels[number].muted = muted

    def set_solo(self, number: int, solo: bool) -> None:
        """Set solo state for a channel.

        Args:
            number: Channel number.
            solo: True to solo, False to un-solo.
        """
        if number in self._channels:
            self._channels[number].solo = solo

    def set_volume(self, number: int, volume: float) -> None:
        """Set volume for a channel.

        Args:
            number: Channel number.
            volume: Volume (0.0-1.0).
        """
        if number in self._channels:
            self._channels[number].volume = max(0.0, min(1.0, volume))

    def set_pan(self, number: int, pan: float) -> None:
        """Set pan for a channel.

        Args:
            number: Channel number.
            pan: Pan (-1.0 to 1.0).
        """
        if number in self._channels:
            self._channels[number].pan = max(-1.0, min(1.0, pan))

    def set_transpose(self, number: int, transpose: int) -> None:
        """Set transpose for a channel.

        Args:
            number: Channel number.
            transpose: Semitone offset.
        """
        if number in self._channels:
            self._channels[number].transpose = transpose

    def set_output(self, number: int, output: str) -> None:
        """Set output routing for a channel.

        Args:
            number: Channel number.
            output: Output target (plugin ID or track name).
        """
        if number in self._channels:
            self._channels[number].output = output

    # ── Event Routing ────────────────────────────────────────────────────

    def _is_channel_active(self, channel: VirtualChannel) -> bool:
        """Determine if a channel should produce output.

        Solo/mute logic:
            - If any channel is soloed, only soloed + non-muted channels are active.
            - If no channels are soloed, all non-muted channels are active.

        Args:
            channel: The channel to check.

        Returns:
            True if the channel should produce output.
        """
        if not channel.enabled:
            return False
        if channel.muted:
            return False
        # Check if any channel is soloed
        any_soloed = any(ch.solo for ch in self._channels.values())
        if any_soloed and not channel.solo:
            return False
        return True

    def route_note_on(
        self, note: int, velocity: int, channel: int
    ) -> RoutedEvent | None:
        """Route a Note On event through a virtual channel.

        Args:
            note: MIDI note number (0-127).
            velocity: Note velocity (1-127).
            channel: Virtual channel number.

        Returns:
            RoutedEvent if the channel is active, None otherwise.
        """
        ch = self._channels.get(channel)
        if ch is None or not self._is_channel_active(ch):
            return None

        transposed = note + ch.transpose
        # Clamp to valid range
        if not 0 <= transposed <= 127:
            return None

        event = RoutedEvent(
            event_type="note_on",
            channel=channel,
            output=ch.output,
            note=transposed,
            velocity=velocity,
            volume=ch.volume,
            pan=ch.pan,
            transpose=ch.transpose,
        )
        self._event_buffer.append(event)
        return event

    def route_note_off(
        self, note: int, velocity: int = 0, channel: int = 0
    ) -> RoutedEvent | None:
        """Route a Note Off event through a virtual channel.

        Args:
            note: MIDI note number (0-127).
            velocity: Release velocity.
            channel: Virtual channel number.

        Returns:
            RoutedEvent if the channel exists, None otherwise.
        """
        ch = self._channels.get(channel)
        if ch is None:
            return None
        # Note Off should always pass through even if muted (to prevent stuck notes)
        # But we skip if channel doesn't exist or is disabled

        transposed = note + ch.transpose
        if not 0 <= transposed <= 127:
            return None

        event = RoutedEvent(
            event_type="note_off",
            channel=channel,
            output=ch.output,
            note=transposed,
            velocity=velocity,
            volume=ch.volume,
            pan=ch.pan,
            transpose=ch.transpose,
        )
        self._event_buffer.append(event)
        return event

    def route_cc(
        self, cc: int, value: int, channel: int
    ) -> RoutedEvent | None:
        """Route a CC event through a virtual channel.

        If the channel has a cc_filter, only CCs in the filter set are passed.

        Args:
            cc: CC number (0-127).
            value: CC value (0-127).
            channel: Virtual channel number.

        Returns:
            RoutedEvent if the channel passes the CC, None otherwise.
        """
        ch = self._channels.get(channel)
        if ch is None:
            return None
        # Apply CC filter
        if ch.cc_filter and cc not in ch.cc_filter:
            return None

        event = RoutedEvent(
            event_type="cc",
            channel=channel,
            output=ch.output,
            cc=cc,
            cc_value=value,
            volume=ch.volume,
            pan=ch.pan,
        )
        self._event_buffer.append(event)
        return event

    def flush_events(self) -> list[RoutedEvent]:
        """Get and clear the event buffer.

        Returns:
            List of RoutedEvent objects since last flush.
        """
        events = list(self._event_buffer)
        self._event_buffer.clear()
        return events

    def clear(self) -> None:
        """Remove all channels and clear the event buffer."""
        self._channels.clear()
        self._event_buffer.clear()
