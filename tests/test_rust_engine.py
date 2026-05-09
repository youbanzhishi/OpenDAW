"""
test_rust_engine.py — Integration tests for RustEngineProxy.

Tests both Rust and Python fallback modes with pytest.

Usage:
    # Run all tests
    pytest tests/test_rust_engine.py -v

    # Run with coverage
    pytest tests/test_rust_engine.py --cov=src.vcmix.rust_engine --cov-report=html

    # Run only unit tests (no Rust required)
    pytest tests/test_rust_engine.py -v -k "not integration"
"""

import os
import sys

import pytest

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from vcmix.rust_engine import (
    HAS_RUST,
    PythonFallbackEngine,
    RustEngineProxy,
    check_rust_available,
    create_engine,
    get_engine_mode,
)

# ============================================================================
# Test Fixtures
# ============================================================================

@pytest.fixture
def engine() -> RustEngineProxy:
    """Create a fresh engine instance for each test."""
    return RustEngineProxy()


@pytest.fixture
def python_engine() -> PythonFallbackEngine:
    """Create a Python fallback engine for testing."""
    return PythonFallbackEngine()


# ============================================================================
# Mode Detection Tests
# ============================================================================

class TestModeDetection:
    """Tests for Rust availability detection."""

    def test_has_rust_is_boolean(self):
        """HAS_RUST should be a boolean."""
        assert isinstance(HAS_RUST, bool)

    def test_check_rust_available(self):
        """check_rust_available() should return HAS_RUST value."""
        assert check_rust_available() == HAS_RUST

    def test_get_engine_mode(self):
        """get_engine_mode() should return correct mode string."""
        expected_mode = "rust" if HAS_RUST else "python"
        assert get_engine_mode() == expected_mode

    def test_engine_proxy_mode(self):
        """RustEngineProxy should have correct mode attribute."""
        proxy = RustEngineProxy()
        expected_mode = "rust" if HAS_RUST else "python"
        assert proxy.mode == expected_mode


# ============================================================================
# Python Fallback Engine Tests
# ============================================================================

class TestPythonFallbackEngine:
    """Tests for PythonFallbackEngine."""

    def test_initial_state(self, python_engine):
        """Engine should start in stopped state."""
        assert python_engine.get_state() == "stopped"

    def test_play(self, python_engine):
        """play() should transition to playing state."""
        result = python_engine.play(48000, 256)
        assert result is True
        assert python_engine.get_state() == "playing"

    def test_play_sets_params(self, python_engine):
        """play() should set sample rate and buffer size."""
        python_engine.play(96000, 1024)
        assert python_engine._sample_rate == 96000
        assert python_engine._buffer_size == 1024

    def test_stop(self, python_engine):
        """stop() should transition to stopped state."""
        python_engine.play()
        result = python_engine.stop()
        assert result is True
        assert python_engine.get_state() == "stopped"

    def test_pause(self, python_engine):
        """pause() should transition to paused state when playing."""
        python_engine.play()
        result = python_engine.pause()
        assert result is True
        assert python_engine.get_state() == "paused"

    def test_pause_when_stopped(self, python_engine):
        """pause() should return False when stopped."""
        result = python_engine.pause()
        assert result is False

    def test_resume(self, python_engine):
        """resume() should transition to playing when paused."""
        python_engine.play()
        python_engine.pause()
        result = python_engine.resume()
        assert result is True
        assert python_engine.get_state() == "playing"

    def test_resume_when_stopped(self, python_engine):
        """resume() should return False when stopped."""
        result = python_engine.resume()
        assert result is False

    def test_render_offline(self, python_engine):
        """render_offline() should return success message."""
        result = python_engine.render_offline("input.yaml", "output.wav")
        assert "Offline render completed" in result
        assert "output.wav" in result

    def test_register_plugin(self, python_engine):
        """register_plugin() should add plugin to list."""
        python_engine.register_plugin("VC-EQ")
        assert "VC-EQ" in python_engine.list_plugins()

    def test_register_plugin_once(self, python_engine):
        """register_plugin() should not add duplicates."""
        python_engine.register_plugin("VC-EQ")
        python_engine.register_plugin("VC-EQ")
        assert python_engine.list_plugins().count("VC-EQ") == 1

    def test_register_script(self, python_engine):
        """register_script() should add script to list."""
        python_engine.register_script("mixdown.eel")
        assert "mixdown.eel" in python_engine.list_scripts()

    def test_get_info(self, python_engine):
        """get_info() should return engine info dict."""
        info = python_engine.get_info()
        assert "state" in info
        assert "sample_rate" in info
        assert "buffer_size" in info
        assert "version" in info
        assert info["state"] == "stopped"


# ============================================================================
# RustEngineProxy Tests
# ============================================================================

class TestRustEngineProxy:
    """Tests for RustEngineProxy unified interface."""

    def test_initial_state(self, engine):
        """Engine should start in stopped state."""
        assert engine.get_state() == "stopped"

    def test_play(self, engine):
        """play() should work with default parameters."""
        result = engine.play()
        assert result is True
        # State should be playing (or rendering for offline)
        assert engine.get_state() in ("playing", "stopped")

    def test_play_with_params(self, engine):
        """play() should accept custom sample rate and buffer size."""
        result = engine.play(sample_rate=48000, buffer_size=256)
        assert result is True

    def test_stop(self, engine):
        """stop() should return to stopped state."""
        engine.play()
        result = engine.stop()
        assert result is True
        assert engine.get_state() == "stopped"

    def test_pause_resume(self, engine):
        """pause() and resume() should work."""
        engine.play()
        engine.pause()
        assert engine.get_state() == "paused"
        engine.resume()
        assert engine.get_state() == "playing"

    def test_register_plugin(self, engine):
        """register_plugin() should work."""
        engine.register_plugin("VC-Compressor")
        plugins = engine.list_plugins()
        assert "VC-Compressor" in plugins

    def test_register_script(self, engine):
        """register_script() should work."""
        engine.register_script("normalize.eel")
        scripts = engine.list_scripts()
        assert "normalize.eel" in scripts

    def test_render_offline(self, engine, tmp_path):
        """render_offline() should work with file paths."""
        yaml_path = tmp_path / "test.yaml"
        output_path = tmp_path / "output.wav"

        # Create minimal YAML config
        yaml_path.write_text("sample_rate: 44100\nchannels: 2\n")

        result = engine.render_offline(str(yaml_path), str(output_path))
        assert "Offline render completed" in result

    def test_get_info(self, engine):
        """get_info() should return complete info."""
        info = engine.get_info()
        assert "state" in info
        assert "sample_rate" in info
        assert "buffer_size" in info
        assert "version" in info
        assert "mode" in info
        # Mode should match current mode
        assert info["mode"] == engine.mode


# ============================================================================
# create_engine Tests
# ============================================================================

class TestCreateEngine:
    """Tests for create_engine convenience function."""

    def test_create_engine_returns_proxy(self):
        """create_engine() should return RustEngineProxy instance."""
        engine = create_engine()
        assert isinstance(engine, RustEngineProxy)

    def test_create_engine_works(self):
        """create_engine() should create a working engine."""
        engine = create_engine()
        assert engine.play() is True
        assert engine.stop() is True


# ============================================================================
# Integration Tests (require full setup)
# ============================================================================

class TestIntegration:
    """Integration tests for full workflow."""

    @pytest.mark.integration
    def test_full_playback_workflow(self, engine):
        """Test complete playback workflow."""
        # Start playback
        assert engine.play(44100, 512) is True
        assert engine.get_state() == "playing"

        # Pause
        assert engine.pause() is True
        assert engine.get_state() == "paused"

        # Resume
        assert engine.resume() is True
        assert engine.get_state() == "playing"

        # Stop
        assert engine.stop() is True
        assert engine.get_state() == "stopped"

    @pytest.mark.integration
    def test_plugin_registration_workflow(self, engine):
        """Test plugin registration workflow."""
        # Register plugins
        plugins = ["VC-EQ", "VC-Compressor", "VC-Reverb"]
        for plugin in plugins:
            engine.register_plugin(plugin)

        # Verify all registered
        registered = engine.list_plugins()
        for plugin in plugins:
            assert plugin in registered

    @pytest.mark.integration
    def test_info_consistency(self, engine):
        """Test that get_info is consistent with individual methods."""
        engine.play(48000, 256)

        info = engine.get_info()
        assert info["sample_rate"] == 48000
        assert info["buffer_size"] == 256
        assert info["state"] == "playing"


# ============================================================================
# Performance Tests (optional)
# ============================================================================

class TestPerformance:
    """Basic performance tests."""

    def test_engine_creation_speed(self):
        """Creating engines should be fast."""
        import time
        start = time.perf_counter()
        for _ in range(100):
            RustEngineProxy()
        elapsed = time.perf_counter() - start
        # Should create 100 engines in under 1 second
        assert elapsed < 1.0

    def test_state_query_speed(self, engine):
        """State queries should be fast."""
        import time
        start = time.perf_counter()
        for _ in range(1000):
            engine.get_state()
        elapsed = time.perf_counter() - start
        # Should handle 1000 queries in under 0.1 seconds
        assert elapsed < 0.1


# ============================================================================
# Main
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
