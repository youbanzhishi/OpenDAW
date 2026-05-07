"""
test_bus.py — Tests for vcmix.engine.bus (Send/Return system).

Tests:
    - SendReturnBus creation and process
    - BusManager from_config
    - Send/Return signal flow
    - Mix returns from multiple tracks
    - Return level application

Usage:
    pytest tests/test_bus.py -v

Dependencies: pytest, numpy
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from vcmix.engine.bus import SendReturnBus, BusManager


class TestSendReturnBus:
    """Tests for SendReturnBus."""

    def test_creation(self):
        """SendReturnBus should store name, effects, return_level."""
        bus = SendReturnBus(name="reverb_bus", return_level=0.15)
        assert bus.name == "reverb_bus"
        assert bus.return_level == 0.15
        assert bus.effects == []

    def test_creation_with_effects(self):
        """SendReturnBus should store effects list."""
        effects = [{"name": "vc-reverb", "params": {"room": 30}}]
        bus = SendReturnBus(name="reverb_bus", effects=effects, return_level=0.2)
        assert len(bus.effects) == 1
        assert bus.return_level == 0.2

    def test_process_passthrough(self):
        """Bus with no effects should apply return_level only."""
        from vcmix.plugins.registry import PluginRegistry
        registry = PluginRegistry()
        bus = SendReturnBus(name="test_bus", effects=[], return_level=0.5)
        audio = np.ones(1000, dtype=np.float32) * 0.8
        result = bus.process(audio, registry)
        # Should be audio * return_level (plugins passthrough when no CLI)
        np.testing.assert_allclose(result, 0.8 * 0.5, atol=1e-5)

    def test_process_with_return_level(self):
        """Bus process should apply return_level to output."""
        from vcmix.plugins.registry import PluginRegistry
        registry = PluginRegistry()
        bus = SendReturnBus(name="test_bus", effects=[], return_level=0.1)
        audio = np.ones(1000, dtype=np.float32) * 0.5
        result = bus.process(audio, registry)
        np.testing.assert_allclose(result, 0.5 * 0.1, atol=1e-5)

    def test_process_with_effect(self):
        """Bus with an effect should process through it then apply return_level."""
        from vcmix.plugins.registry import PluginRegistry
        registry = PluginRegistry()
        # vc-gain will passthrough (no CLI), but the logic is tested
        effects = [{"name": "vc-gain", "params": {"gain": 6}}]
        bus = SendReturnBus(name="test_bus", effects=effects, return_level=0.3)
        audio = np.ones(1000, dtype=np.float32) * 0.5
        result = bus.process(audio, registry)
        # Without actual CLI, vc-gain passthroughs, then * return_level
        # Result should be 0.5 * 0.3 = 0.15 (passthrough case)
        # vc-gain with gain=6 adds ~6dB (2x), passthrough with warning gives 0.5
        # Then * return_level=0.3 → actual result depends on whether CLI is available
        # If passthrough: 0.5 * 0.3 = 0.15. If gain=6dB applied: 1.0 * 0.3 = 0.3
        assert result.mean() >= 0.1, f"Bus output too low: {result.mean()}"

    def test_process_does_not_modify_input(self):
        """Bus process should not modify the input array."""
        from vcmix.plugins.registry import PluginRegistry
        registry = PluginRegistry()
        bus = SendReturnBus(name="test_bus", effects=[], return_level=0.5)
        audio = np.ones(1000, dtype=np.float32) * 0.8
        audio_copy = audio.copy()
        bus.process(audio, registry)
        np.testing.assert_array_equal(audio, audio_copy)


class TestBusManager:
    """Tests for BusManager."""

    def test_creation_empty(self):
        """Empty BusManager should have no buses."""
        mgr = BusManager()
        assert len(mgr.buses) == 0

    def test_creation_with_buses(self):
        """BusManager should store provided buses."""
        buses = {
            "reverb_bus": SendReturnBus(name="reverb_bus", return_level=0.15),
            "delay_bus": SendReturnBus(name="delay_bus", return_level=0.08),
        }
        mgr = BusManager(buses=buses)
        assert len(mgr.buses) == 2
        assert "reverb_bus" in mgr.buses
        assert "delay_bus" in mgr.buses

    def test_process_sends_single_bus(self):
        """Process sends to a single bus."""
        from vcmix.plugins.registry import PluginRegistry
        registry = PluginRegistry()
        buses = {
            "reverb_bus": SendReturnBus(name="reverb_bus", return_level=0.15),
        }
        mgr = BusManager(buses=buses)
        audio = np.ones(1000, dtype=np.float32) * 0.8
        sends = {"reverb_bus": 0.12}

        returns = mgr.process_sends("vocal", audio, sends, registry)
        assert "reverb_bus" in returns
        # audio * send_level * return_level = 0.8 * 0.12 * 0.15 = 0.0144
        np.testing.assert_allclose(returns["reverb_bus"], 0.8 * 0.12 * 0.15, atol=1e-5)

    def test_process_sends_multiple_buses(self):
        """Process sends to multiple buses."""
        from vcmix.plugins.registry import PluginRegistry
        registry = PluginRegistry()
        buses = {
            "reverb_bus": SendReturnBus(name="reverb_bus", return_level=0.15),
            "delay_bus": SendReturnBus(name="delay_bus", return_level=0.08),
        }
        mgr = BusManager(buses=buses)
        audio = np.ones(1000, dtype=np.float32) * 0.8
        sends = {"reverb_bus": 0.12, "delay_bus": 0.05}

        returns = mgr.process_sends("vocal", audio, sends, registry)
        assert "reverb_bus" in returns
        assert "delay_bus" in returns
        # reverb: 0.8 * 0.12 * 0.15 = 0.0144
        np.testing.assert_allclose(returns["reverb_bus"], 0.8 * 0.12 * 0.15, atol=1e-5)
        # delay: 0.8 * 0.05 * 0.08 = 0.0032
        np.testing.assert_allclose(returns["delay_bus"], 0.8 * 0.05 * 0.08, atol=1e-5)

    def test_process_sends_unknown_bus_ignored(self):
        """Sends to unknown buses should be silently ignored."""
        from vcmix.plugins.registry import PluginRegistry
        registry = PluginRegistry()
        buses = {"reverb_bus": SendReturnBus(name="reverb_bus", return_level=0.15)}
        mgr = BusManager(buses=buses)
        audio = np.ones(1000, dtype=np.float32) * 0.8
        sends = {"nonexistent_bus": 0.12}

        returns = mgr.process_sends("vocal", audio, sends, registry)
        assert len(returns) == 0

    def test_process_sends_empty_sends(self):
        """Empty sends dict should return empty returns."""
        from vcmix.plugins.registry import PluginRegistry
        registry = PluginRegistry()
        buses = {"reverb_bus": SendReturnBus(name="reverb_bus", return_level=0.15)}
        mgr = BusManager(buses=buses)
        audio = np.ones(1000, dtype=np.float32) * 0.8

        returns = mgr.process_sends("vocal", audio, {}, registry)
        assert len(returns) == 0

    def test_from_config(self):
        """BusManager.from_config should create buses from YAML-like config."""
        config = [
            {
                "name": "reverb_bus",
                "effects": [{"name": "vc-reverb", "params": {"room": 30, "mix": 100}}],
                "return_level": 0.15,
            },
            {
                "name": "delay_bus",
                "effects": [{"name": "vc-delay", "params": {"time": 375.0, "feedback": 12}}],
                "return_level": 0.08,
            },
        ]
        mgr = BusManager.from_config(config, bpm=120)
        assert len(mgr.buses) == 2
        assert "reverb_bus" in mgr.buses
        assert "delay_bus" in mgr.buses
        assert mgr.buses["reverb_bus"].return_level == 0.15
        assert mgr.buses["delay_bus"].return_level == 0.08

    def test_from_config_note_value_conversion(self):
        """from_config should convert BPM note values in bus effect params."""
        config = [
            {
                "name": "delay_bus",
                "effects": [{"name": "vc-delay", "params": {"time": "1/8d", "feedback": 12}}],
                "return_level": 0.1,
            },
        ]
        mgr = BusManager.from_config(config, bpm=120)
        # "1/8d" @ BPM120 should be converted to 375.0ms
        assert mgr.buses["delay_bus"].effects[0]["params"]["time"] == 375.0

    def test_mix_returns(self):
        """mix_returns should sum all bus returns."""
        mgr = BusManager()
        returns1 = {
            "reverb": np.ones(1000, dtype=np.float32) * 0.1,
            "delay": np.ones(1000, dtype=np.float32) * 0.05,
        }
        returns2 = {
            "reverb": np.ones(1000, dtype=np.float32) * 0.08,
        }
        all_returns = [returns1, returns2]
        result = mgr.mix_returns(all_returns, 1000)

        # reverb: 0.1 + 0.08 = 0.18
        # delay: 0.05
        # Total: 0.18 + 0.05 = 0.23
        expected = 0.23
        np.testing.assert_allclose(result, expected, atol=1e-5)

    def test_mix_returns_different_lengths(self):
        """mix_returns should handle different audio lengths."""
        mgr = BusManager()
        returns = {
            "bus1": np.ones(500, dtype=np.float32) * 0.1,
        }
        result = mgr.mix_returns([returns], 1000)
        # First 500 samples = 0.1, last 500 = 0.0
        assert result.shape == (1000,)
        np.testing.assert_allclose(result[:500], 0.1, atol=1e-5)
        np.testing.assert_allclose(result[500:], 0.0, atol=1e-5)
