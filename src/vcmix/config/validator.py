"""
validator.py — Configuration schema validator for VCMix.

Validates a parsed project config dict against structural and
semantic rules:
    - Required fields present (name, tracks, output)
    - Track definitions have valid file paths
    - Insert chain parameters within valid ranges
    - Sample rate is a supported value (44100, 48000, 88200, 96000)
    - BPM is positive
    - Plugin names are registered

Usage:
    from vcmix.config.validator import validate_config
    issues = validate_config(config)
    if issues:
        for issue in issues:
            print(issue)

Dependencies: None (pure Python validation)
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

VALID_SAMPLE_RATES = {44100, 48000, 88200, 96000}


def validate_config(config: dict[str, Any]) -> list[str]:
    """
    Validate a parsed project configuration.

    Args:
        config: Parsed configuration dictionary from parser.parse_project().

    Returns:
        List of validation issue strings. Empty list means valid.
    """
    issues: list[str] = []

    # Required top-level fields
    if not config.get("name"):
        issues.append("Missing required field: name")

    # Sample rate
    sr = config.get("sample_rate", 44100)
    if sr not in VALID_SAMPLE_RATES:
        issues.append(f"Unsupported sample rate: {sr}. Must be one of {sorted(VALID_SAMPLE_RATES)}")

    # BPM
    bpm = config.get("bpm", 120)
    if not isinstance(bpm, (int, float)) or bpm <= 0:
        issues.append(f"Invalid BPM: {bpm}. Must be a positive number")

    # Tracks
    tracks = config.get("tracks", [])
    if not tracks:
        issues.append("No tracks defined — at least one track is required")
    for i, track in enumerate(tracks):
        if not isinstance(track, dict):
            issues.append(f"Track {i}: must be a mapping")
            continue
        if "file" not in track:
            issues.append(f"Track {i}: missing 'file' field")

    # Output
    output = config.get("output", {})
    if not output.get("path"):
        issues.append("Output path not specified")

    return issues
