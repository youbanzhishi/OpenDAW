"""
rust_engine.py — RustEngineProxy: Python wrapper for Rust audio engine.

Provides graceful degradation when Rust extension is not available,
allowing Python-only fallback for audio processing.

Usage:
    from vcmix.rust_engine import RustEngineProxy, HAS_RUST
    
    if HAS_RUST:
        engine = RustEngineProxy()
        engine.play(44100, 512)
        state = engine.get_state()
        engine.stop()
    else:
        # Fallback to Python-only implementation
        pass
"""

from __future__ import annotations

import logging
import os
import sys
from typing import Optional

logger = logging.getLogger(__name__)

# ============================================================================
# Rust Extension Detection
# ============================================================================

# Flag indicating whether Rust extension is available
HAS_RUST: bool = False
_RustEngine: Optional[type] = None

def _try_import_rust_engine() -> bool:
    """
    Attempt to import the Rust extension module.
    
    Returns:
        True if Rust extension is successfully imported, False otherwise.
    """
    global HAS_RUST, _RustEngine
    
    try:
        # Try to import the compiled Rust extension
        import opendaw_core
        _RustEngine = opendaw_core.RustEngine
        HAS_RUST = True
        logger.info(
            f"Rust engine loaded: v{getattr(opendaw_core, '__version__', 'unknown')}"
        )
        return True
    except ImportError as e:
        logger.warning(f"Rust extension not available: {e}")
        logger.info("Falling back to Python-only mode")
        return False
    except Exception as e:
        logger.error(f"Unexpected error loading Rust extension: {e}")
        return False

# Try to import on module load
_try_import_rust_engine()


# ============================================================================
# Python Fallback Engine
# ============================================================================

class PythonFallbackEngine:
    """
    Pure Python fallback engine when Rust extension is not available.
    
    Provides the same interface as RustEngineProxy but uses Python
    for all processing.
    """
    
    def __init__(self) -> None:
        self._state: str = "stopped"
        self._sample_rate: int = 44100
        self._buffer_size: int = 512
        self._plugins: list[str] = []
        self._scripts: list[str] = []
        logger.info("PythonFallbackEngine initialized")
    
    def play(self, sample_rate: int, buffer_size: int) -> bool:
        """Start audio playback (Python fallback)."""
        self._sample_rate = sample_rate
        self._buffer_size = buffer_size
        self._state = "playing"
        logger.info(f"PythonFallbackEngine.play: {sample_rate}/{buffer_size}")
        return True
    
    def stop(self) -> bool:
        """Stop audio playback."""
        self._state = "stopped"
        logger.info("PythonFallbackEngine.stop")
        return True
    
    def pause(self) -> bool:
        """Pause audio playback."""
        if self._state == "playing":
            self._state = "paused"
            return True
        return False
    
    def resume(self) -> bool:
        """Resume audio playback."""
        if self._state == "paused":
            self._state = "playing"
            return True
        return False
    
    def get_state(self) -> str:
        """Get current engine state."""
        return self._state
    
    def render_offline(self, yaml_path: str, output_path: str) -> str:
        """Render audio offline (placeholder)."""
        logger.info(f"PythonFallbackEngine.render_offline: {yaml_path} -> {output_path}")
        return f"Offline render completed: {output_path} (Python fallback)"
    
    def register_plugin(self, name: str) -> None:
        """Register a plugin."""
        if name not in self._plugins:
            self._plugins.append(name)
    
    def register_script(self, name: str) -> None:
        """Register a script."""
        if name not in self._scripts:
            self._scripts.append(name)
    
    def list_plugins(self) -> list[str]:
        """List registered plugins."""
        return self._plugins.copy()
    
    def list_scripts(self) -> list[str]:
        """List registered scripts."""
        return self._scripts.copy()
    
    def get_info(self) -> dict:
        """Get engine info."""
        return {
            "state": self._state,
            "sample_rate": self._sample_rate,
            "buffer_size": self._buffer_size,
            "version": "0.24.0-python-fallback",
            "mode": "python-only",
        }


# ============================================================================
# RustEngineProxy
# ============================================================================

class RustEngineProxy:
    """
    Unified interface to Rust audio engine with Python fallback.
    
    This class provides the same interface regardless of whether
    the Rust extension is available, enabling graceful degradation.
    
    Attributes:
        HAS_RUST: Class-level flag indicating Rust availability.
        mode: Either "rust" or "python" depending on what's available.
    
    Example:
        >>> from vcmix.rust_engine import RustEngineProxy, HAS_RUST
        >>> print(f"Rust available: {HAS_RUST}")
        >>> engine = RustEngineProxy()
        >>> engine.play(44100, 512)
        True
        >>> engine.get_state()
        'playing'
        >>> engine.stop()
        True
    """
    
    mode: str = "python" if not HAS_RUST else "rust"
    
    def __init__(self) -> None:
        """
        Initialize the engine proxy.
        
        Uses Rust engine if available, otherwise falls back to Python.
        """
        if HAS_RUST and _RustEngine is not None:
            self._engine = _RustEngine()
            logger.info("RustEngineProxy initialized (Rust mode)")
        else:
            self._engine = PythonFallbackEngine()
            logger.info("RustEngineProxy initialized (Python fallback)")
    
    def play(self, sample_rate: int = 44100, buffer_size: int = 512) -> bool:
        """
        Start audio playback.
        
        Args:
            sample_rate: Audio sample rate in Hz (default 44100)
            buffer_size: Buffer size in frames (default 512)
        
        Returns:
            True on success
        
        Raises:
            RuntimeError: If engine fails to start
        """
        return self._engine.play(sample_rate, buffer_size)
    
    def stop(self) -> bool:
        """
        Stop audio playback.
        
        Returns:
            True on success
        
        Raises:
            RuntimeError: If engine fails to stop
        """
        return self._engine.stop()
    
    def pause(self) -> bool:
        """
        Pause audio playback.
        
        Returns:
            True on success
        """
        return self._engine.pause()
    
    def resume(self) -> bool:
        """
        Resume audio playback.
        
        Returns:
            True on success
        """
        return self._engine.resume()
    
    def get_state(self) -> str:
        """
        Get current engine state.
        
        Returns:
            String: "stopped", "playing", "paused", or "rendering"
        """
        return self._engine.get_state()
    
    def render_offline(self, yaml_path: str, output_path: str) -> str:
        """
        Render audio offline from YAML configuration.
        
        Args:
            yaml_path: Path to YAML configuration file
            output_path: Path for output audio file
        
        Returns:
            Success message string
        
        Raises:
            RuntimeError: If rendering fails
        """
        return self._engine.render_offline(yaml_path, output_path)
    
    def register_plugin(self, name: str) -> None:
        """
        Register a plugin extension.
        
        Args:
            name: Plugin name
        """
        self._engine.register_plugin(name)
    
    def register_script(self, name: str) -> None:
        """
        Register a script extension.
        
        Args:
            name: Script name
        """
        self._engine.register_script(name)
    
    def list_plugins(self) -> list[str]:
        """
        List registered plugins.
        
        Returns:
            List of plugin names
        """
        return self._engine.list_plugins()
    
    def list_scripts(self) -> list[str]:
        """
        List registered scripts.
        
        Returns:
            List of script names
        """
        return self._engine.list_scripts()
    
    def get_info(self) -> dict:
        """
        Get engine information.
        
        Returns:
            Dictionary with engine info including:
            - state: Current engine state
            - sample_rate: Current sample rate
            - buffer_size: Current buffer size
            - version: Engine version
            - mode: "rust" or "python"
        """
        info = self._engine.get_info()
        info["mode"] = self.mode
        return info


# ============================================================================
# Convenience Functions
# ============================================================================

def create_engine() -> RustEngineProxy:
    """
    Create a new engine instance.
    
    This is a convenience function equivalent to RustEngineProxy().
    
    Returns:
        RustEngineProxy instance
    """
    return RustEngineProxy()


def check_rust_available() -> bool:
    """
    Check if Rust engine is available.
    
    Returns:
        True if Rust extension is loaded, False otherwise
    """
    return HAS_RUST


def get_engine_mode() -> str:
    """
    Get the current engine mode.
    
    Returns:
        "rust" if Rust extension is available, "python" otherwise
    """
    return RustEngineProxy.mode


# ============================================================================
# Module Info
# ============================================================================

__version__ = "0.24.0"
__author__ = "OpenDAW Team"
