"""
automation_curve.py — Automation curve data structure for VCMix.

Represents a parameter automation curve as a sequence of control points
with interpolation modes. Supports:
    - step:    Hold value until next point (zero-order hold)
    - linear:  Linear interpolation between points
    - smooth:  Cosine/ease interpolation for smooth transitions

The curve can be queried at any beat position to get the interpolated
parameter value, enabling time-varying plugin parameters during rendering.

Data structure:
    AutomationPoint — (time_beat, value, curve_type) triple
    AutomationCurve — Ordered list of AutomationPoints with interpolation

Usage:
    from vcmix.automation.automation_curve import AutomationCurve, AutomationPoint

    curve = AutomationCurve(points=[
        AutomationPoint(time_beat=0.0, value=-6.0, curve_type="linear"),
        AutomationPoint(time_beat=8.0, value=0.0, curve_type="linear"),
        AutomationPoint(time_beat=32.0, value=0.0, curve_type="step"),
        AutomationPoint(time_beat=40.0, value=-12.0, curve_type="smooth"),
    ])

    # Query at any beat
    value = curve.value_at(4.0)   # -3.0 (linear interpolation)
    value = curve.value_at(36.0)  # 0.0 (step hold)

Dependencies: numpy (optional, for vectorized queries)
"""

from __future__ import annotations

import math as _math
from dataclasses import dataclass
from enum import Enum
from typing import Any


class CurveType(str, Enum):
    """Interpolation type between automation points.

    Values:
        STEP:    Hold value until next point (zero-order hold).
        LINEAR:  Linear interpolation between adjacent points.
        SMOOTH:  Cosine/ease-in-out interpolation for smooth curves.
    """

    STEP = "step"
    LINEAR = "linear"
    SMOOTH = "smooth"


@dataclass(frozen=True)
class AutomationPoint:
    """A single control point on an automation curve.

    Attributes:
        time_beat: Position in beats (quarter notes).
        value: Parameter value at this point.
        curve_type: Interpolation mode from this point to the next.
    """

    time_beat: float
    value: float
    curve_type: CurveType = CurveType.LINEAR

    def __post_init__(self) -> None:
        """Validate point values."""
        if self.time_beat < 0:
            raise ValueError(f"Time beat cannot be negative: {self.time_beat}")

    @classmethod
    def from_list(cls, data: list[Any]) -> AutomationPoint:
        """Create an AutomationPoint from a list [time, value, curve_type].

        Args:
            data: List of [time_beat, value, curve_type] or [time_beat, value].

        Returns:
            AutomationPoint instance.

        Raises:
            ValueError: If data format is invalid.
        """
        if len(data) < 2:
            raise ValueError(f"AutomationPoint needs at least [time, value], got {data}")
        curve_type = CurveType(data[2]) if len(data) > 2 else CurveType.LINEAR
        return cls(time_beat=float(data[0]), value=float(data[1]), curve_type=curve_type)


class AutomationCurve:
    """An automation curve defined by ordered control points.

    Points must be in ascending time order. The curve can be queried
    at any beat position; values before the first point use the first
    point's value, and values after the last point hold the last value.

    Args:
        points: Ordered list of AutomationPoint instances.
        default_value: Fallback value when no points are defined.
    """

    def __init__(
        self,
        points: list[AutomationPoint] | None = None,
        default_value: float = 0.0,
    ) -> None:
        """Initialize the automation curve.

        Args:
            points: Control points (will be sorted by time).
            default_value: Value returned when no points exist.
        """
        self.default_value = default_value
        self._points: list[AutomationPoint] = sorted(
            points or [], key=lambda p: p.time_beat
        )

    @property
    def points(self) -> list[AutomationPoint]:
        """Return the sorted list of control points."""
        return list(self._points)

    @property
    def point_count(self) -> int:
        """Number of control points."""
        return len(self._points)

    @property
    def start_beat(self) -> float:
        """Beat position of the first control point."""
        return self._points[0].time_beat if self._points else 0.0

    @property
    def end_beat(self) -> float:
        """Beat position of the last control point."""
        return self._points[-1].time_beat if self._points else 0.0

    @property
    def value_range(self) -> tuple[float, float]:
        """Min and max values across all control points."""
        if not self._points:
            return (self.default_value, self.default_value)
        values = [p.value for p in self._points]
        return (min(values), max(values))

    def add_point(self, point: AutomationPoint) -> None:
        """Add a control point and re-sort by time.

        Args:
            point: AutomationPoint to add.
        """
        self._points.append(point)
        self._points.sort(key=lambda p: p.time_beat)

    def value_at(self, beat: float) -> float:
        """Query the automation value at a given beat position.

        Interpolation behavior:
            - Before first point: use first point's value
            - After last point: hold last point's value
            - Between points: interpolate using the left point's curve_type

        Args:
            beat: Position in beats to query.

        Returns:
            Interpolated parameter value.
        """
        if not self._points:
            return self.default_value

        # Before first point
        if beat <= self._points[0].time_beat:
            return self._points[0].value

        # After last point — hold value
        if beat >= self._points[-1].time_beat:
            return self._points[-1].value

        # Find the segment containing this beat
        for i in range(len(self._points) - 1):
            left = self._points[i]
            right = self._points[i + 1]

            if left.time_beat <= beat < right.time_beat:
                return self._interpolate(left, right, beat)

        # Exact match on last point
        return self._points[-1].value

    def values_at_beats(self, beats: list[float]) -> list[float]:
        """Query automation values at multiple beat positions.

        Args:
            beats: List of beat positions.

        Returns:
            List of interpolated values.
        """
        return [self.value_at(b) for b in beats]

    def _interpolate(
        self, left: AutomationPoint, right: AutomationPoint, beat: float
    ) -> float:
        """Interpolate between two control points at a given beat.

        Args:
            left: Left (earlier) control point.
            right: Right (later) control point.
            beat: Position to interpolate at.

        Returns:
            Interpolated value.
        """
        if left.curve_type == CurveType.STEP:
            return left.value

        span = right.time_beat - left.time_beat
        if span <= 0:
            return left.value

        t = (beat - left.time_beat) / span  # Normalized 0..1

        if left.curve_type == CurveType.LINEAR:
            return left.value + t * (right.value - left.value)

        if left.curve_type == CurveType.SMOOTH:
            # Cosine interpolation (ease-in-out)
            t_smooth = (1.0 - _math.cos(_math.pi * t)) / 2.0
            return left.value + t_smooth * (right.value - left.value)

        # Fallback to linear
        return left.value + t * (right.value - left.value)

    def to_list(self) -> list[list[Any]]:
        """Serialize the curve to a list of [time, value, curve_type] lists.

        Returns:
            Serializable list representation.
        """
        return [
            [p.time_beat, p.value, p.curve_type.value]
            for p in self._points
        ]

    @classmethod
    def from_list(cls, data: list[list[Any]], default_value: float = 0.0) -> AutomationCurve:
        """Create an AutomationCurve from a list of [time, value, curve_type].

        Args:
            data: List of [time_beat, value, curve_type] lists.
            default_value: Fallback value.

        Returns:
            AutomationCurve instance.
        """
        points = [AutomationPoint.from_list(item) for item in data]
        return cls(points=points, default_value=default_value)

    def __repr__(self) -> str:
        return f"AutomationCurve(points={self.point_count}, range={self.value_range})"



