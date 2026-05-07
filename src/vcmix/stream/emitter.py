"""
emitter.py — Real-time data stream emitter for VCMix.

Emits structured data events during the rendering pipeline:
    - Per-track level data (RMS, Peak, True Peak)
    - Per-effect before/after analysis
    - Master bus data
    - Warning events (clipping, low SNR, excessive sibilance)
    - Decision events (auto-fix applied, parameter adjusted)

Output formats:
    - JSON (one event per line, newline-delimited JSON)
    - Python dict (for in-process consumers)
    - Callback (for custom handlers)

This enables the closed-loop control system:
    render → stream data → AI analyzes → adjust params → re-render

Usage:
    from vcmix.stream.emitter import DataStream, StreamEvent
    ds = DataStream(format="json")
    ds.emit_track_level("vocal", rms=-12.3, peak=-3.2)
    ds.emit_warning("vocal", "clipping", "Peak exceeds -1 dBFS")
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable


class EventLevel(Enum):
    """Event severity level."""
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


@dataclass
class StreamEvent:
    """A single data event in the rendering stream."""
    event_type: str
    timestamp_ms: float
    level: EventLevel = EventLevel.INFO
    track: str = ""
    data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.event_type,
            "ts": round(self.timestamp_ms, 1),
            "level": self.level.value,
            "track": self.track,
            **self.data,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False)


class DataStream:
    """
    Real-time data stream emitter for VCMix rendering pipeline.

    Args:
        format: Output format — "json" (stdout), "dict" (accumulate),
                "callback" (call handler function).
        callback: Custom handler function (for format="callback").
        output: Output file handle (default: sys.stdout for JSON mode).
    """

    def __init__(
        self,
        format: str = "json",
        callback: Callable[[StreamEvent], None] | None = None,
        output: Any = None,
    ) -> None:
        self.format = format
        self.callback = callback
        self.output = output or sys.stdout
        self._events: list[StreamEvent] = []
        self._start_ms: float = 0.0
        self._track_levels: dict[str, dict[str, float]] = {}

    def start(self) -> None:
        """Mark rendering start time."""
        import time
        self._start_ms = time.time() * 1000

    def _now(self) -> float:
        """Current timestamp in ms since start."""
        import time
        return time.time() * 1000 - self._start_ms

    def _emit(self, event: StreamEvent) -> None:
        """Emit an event through the configured output."""
        if self.format == "json":
            self.output.write(event.to_json() + "\n")
            self.output.flush()
        elif self.format == "dict":
            self._events.append(event)
        elif self.format == "callback" and self.callback:
            self.callback(event)

    def emit_track_level(
        self,
        track: str,
        rms_db: float,
        peak_db: float,
        true_peak_db: float = 0.0,
        lufs: float = 0.0,
    ) -> None:
        """Emit per-track level data."""
        level_data = {
            "rms_db": round(rms_db, 2),
            "peak_db": round(peak_db, 2),
            "true_peak_db": round(true_peak_db, 2),
            "lufs": round(lufs, 1),
        }
        self._track_levels[track] = level_data
        self._emit(StreamEvent(
            event_type="track_level",
            timestamp_ms=self._now(),
            track=track,
            data=level_data,
        ))

    def emit_effect_delta(
        self,
        track: str,
        effect: str,
        before_rms: float,
        after_rms: float,
        before_peak: float,
        after_peak: float,
        delta_db: float = 0.0,
    ) -> None:
        """Emit per-effect before/after analysis."""
        self._emit(StreamEvent(
            event_type="effect_delta",
            timestamp_ms=self._now(),
            track=track,
            data={
                "effect": effect,
                "before_rms_db": round(before_rms, 2),
                "after_rms_db": round(after_rms, 2),
                "before_peak_db": round(before_peak, 2),
                "after_peak_db": round(after_peak, 2),
                "delta_db": round(delta_db, 2),
            },
        ))

    def emit_master_level(
        self,
        rms_db: float,
        peak_db: float,
        true_peak_db: float = 0.0,
        lufs: float = 0.0,
    ) -> None:
        """Emit master bus level data."""
        self._emit(StreamEvent(
            event_type="master_level",
            timestamp_ms=self._now(),
            track="master",
            data={
                "rms_db": round(rms_db, 2),
                "peak_db": round(peak_db, 2),
                "true_peak_db": round(true_peak_db, 2),
                "lufs": round(lufs, 1),
            },
        ))

    def emit_warning(
        self,
        track: str,
        warning_type: str,
        message: str,
    ) -> None:
        """Emit a warning event (clipping, low SNR, etc.)."""
        self._emit(StreamEvent(
            event_type="warning",
            timestamp_ms=self._now(),
            level=EventLevel.WARNING,
            track=track,
            data={"warning_type": warning_type, "message": message},
        ))

    def emit_decision(
        self,
        track: str,
        action: str,
        params: dict[str, Any],
        reason: str,
    ) -> None:
        """Emit a decision event (auto-fix, parameter adjustment)."""
        self._emit(StreamEvent(
            event_type="decision",
            timestamp_ms=self._now(),
            level=EventLevel.INFO,
            track=track,
            data={
                "action": action,
                "params": params,
                "reason": reason,
            },
        ))

    def emit_sibilance(
        self,
        track: str,
        sibilance_db: float,
        threshold_db: float = -20.0,
    ) -> None:
        """Emit sibilance detection data."""
        level = (
            EventLevel.WARNING
            if sibilance_db > threshold_db
            else EventLevel.INFO
        )
        self._emit(StreamEvent(
            event_type="sibilance",
            timestamp_ms=self._now(),
            level=level,
            track=track,
            data={
                "sibilance_db": round(sibilance_db, 2),
                "threshold_db": threshold_db,
                "exceeds": sibilance_db > threshold_db,
            },
        ))

    def get_events(self) -> list[StreamEvent]:
        """Get all accumulated events (for format='dict')."""
        return list(self._events)

    def get_latest_levels(self) -> dict[str, dict[str, float]]:
        """Get the latest level data for all tracks."""
        return dict(self._track_levels)
