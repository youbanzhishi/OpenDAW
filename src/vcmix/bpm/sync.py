"""
sync.py — BPM note-value to millisecond conversion for VCMix.

Converts musical note values to timing in milliseconds at a given BPM.
This is the core utility for BPM-synced delay times and other timing.

Supported note value formats:
    "1/1"   — whole note
    "1/2"   — half note
    "1/4"   — quarter note
    "1/8"   — eighth note
    "1/16"  — sixteenth note
    "1/8d"  — dotted eighth (×1.5)
    "1/8t"  — eighth triplet (×2/3)
    "1/4."  — dotted quarter (alternative notation)

Formula:
    quarter_ms = 60000 / BPM
    note_ms    = quarter_ms × (4 / denominator) × numerator
    dotted     = note_ms × 1.5
    triplet    = note_ms × (2/3)

Usage:
    from vcmix.bpm.sync import note_to_ms, resolve_bpm_times
    ms = note_to_ms("1/8d", bpm=62)  # 181.5 ms
    params = resolve_bpm_times({"time": "1/8d", "fb": 12}, bpm=62)
    # {"time": 181.5, "fb": 12}

Dependencies: re (standard library)
"""

from __future__ import annotations

import re
from typing import Any

# Pattern: "N/D", "N/Dd", "N/Dt", "N/D."
_NOTE_RE = re.compile(r"^(\d+)/(\d+)([dt]?)\.?$")


def note_to_ms(bpm: float, note_value: str) -> float:
    """
    Convert a BPM note value to milliseconds.

    Args:
        bpm: Beats per minute.
        note_value: Note string like "1/4", "1/8d", "1/16t".

    Returns:
        Duration in milliseconds (1 decimal place).

    Raises:
        ValueError: If note_value format is unrecognized.

    Examples:
        >>> note_to_ms(120, "1/4")
        500.0
        >>> note_to_ms(62, "1/8d")
        181.5
    """
    if isinstance(note_value, (int, float)):
        return float(note_value)

    value_str = str(note_value).strip()

    # Try plain number first
    try:
        return float(value_str)
    except ValueError:
        pass

    m = _NOTE_RE.match(value_str)
    if not m:
        raise ValueError(
            f"Invalid note value: '{note_value}'. "
            f"Expected number (ms) or note like '1/4', '1/8d', '1/8t'"
        )

    numerator = int(m.group(1))
    denominator = int(m.group(2))
    modifier = m.group(3)

    if denominator == 0:
        raise ValueError(f"Denominator cannot be zero: '{note_value}'")

    quarter_ms = 60000.0 / bpm
    base_ms = quarter_ms * (4.0 * numerator / denominator)

    if modifier == "d":
        base_ms *= 1.5
    elif modifier == "t":
        base_ms *= 2.0 / 3.0

    return round(base_ms, 1)


def resolve_bpm_times(
    params: dict[str, Any],
    bpm: float = 120.0,
    time_keys: list[str] | None = None,
) -> dict[str, Any]:
    """
    Resolve note-value parameters in a dict to milliseconds.

    Only converts values matching the N/D[d|t] pattern.
    Numbers and other strings are left unchanged.

    Args:
        params: Effect parameters dict.
        bpm: Project BPM.
        time_keys: Parameter names to convert (default: ["time", "predelay"]).

    Returns:
        New dict with note values replaced by ms floats.

    Examples:
        >>> resolve_bpm_times({"time": "1/8d", "feedback": 12}, bpm=62)
        {'time': 181.5, 'feedback': 12}
    """
    if time_keys is None:
        time_keys = ["time", "predelay"]

    resolved = dict(params)
    for key in time_keys:
        if key in resolved:
            val = resolved[key]
            if isinstance(val, str) and _NOTE_RE.match(val.strip()):
                try:
                    resolved[key] = note_to_ms(bpm, val)
                except ValueError:
                    pass  # Leave unchanged if unrecognizable
    return resolved
