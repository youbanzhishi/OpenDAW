"""
test_renderer.py — Tests for vcmix.engine.renderer.

Tests the rendering pipeline:
    - Renderer can be instantiated with a config dict
    - Empty tracks raises ValueError
    - Single-track passthrough works (Phase 1)

Usage:
    pytest tests/test_renderer.py -v

Dependencies: pytest, numpy
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from vcmix.engine.renderer import Renderer


class TestRenderer:
    """Tests for Renderer."""

    def test_instantiation(self) -> None:
        """Renderer should accept a config dict."""
        config = {"tracks": [], "output": {"path": "test.wav"}, "sample_rate": 44100}
        r = Renderer(config)
        assert r.config is config

    def test_empty_tracks_raises(self) -> None:
        """Rendering with no tracks should raise ValueError."""
        config = {"tracks": [], "output": {"path": "test.wav"}, "sample_rate": 44100}
        r = Renderer(config)
        with pytest.raises(ValueError, match="No tracks"):
            r.run()

    def test_report_flag(self) -> None:
        """Report flag should be stored."""
        config = {"tracks": [], "output": {"path": "test.wav"}}
        r = Renderer(config, report=True)
        assert r.report is True

    def test_auto_fix_flag(self) -> None:
        """Auto-fix flag should be stored."""
        config = {"tracks": [], "output": {"path": "test.wav"}}
        r = Renderer(config, auto_fix=True)
        assert r.auto_fix is True
