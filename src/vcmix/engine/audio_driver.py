"""
audio_driver.py — Abstract audio driver interface for OpenDAW.

Provides a unified interface for audio I/O backends:
- sounddevice (default, cross-platform)
- JACK (Linux pro audio)
- PortAudio (low-level)

Each driver implements:
- open() / close() — start/stop audio stream
- get_input_buffer() — read from input
- write_output() — write to output
- get_latency() — report current latency
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum, auto
from typing import Callable, Optional

import numpy as np

logger = logging.getLogger(__name__)


class DriverType(Enum):
    """Audio driver backend type."""
    SOUNDDEVICE = auto()
    JACK = auto()
    PORTAUDIO = auto()
    MOCK = auto()


@dataclass
class DriverConfig:
    """Configuration for an audio driver."""
    sample_rate: int = 44100
    buffer_size: int = 512
    num_input_channels: int = 2
    num_output_channels: int = 2
    input_device: Optional[int] = None
    output_device: Optional[int] = None
    driver_type: DriverType = DriverType.SOUNDDEVICE


@dataclass
class DriverInfo:
    """Information about the current driver state."""
    name: str
    sample_rate: int
    buffer_size: int
    input_channels: int
    output_channels: int
    input_latency_ms: float
    output_latency_ms: float
    is_running: bool


class AudioDriverBase(ABC):
    """Abstract base class for audio drivers."""

    def __init__(self, config: DriverConfig) -> None:
        self.config = config
        self._is_running = False
        self._callback: Optional[Callable] = None

    @property
    def is_running(self) -> bool:
        return self._is_running

    @abstractmethod
    def open(self) -> None:
        """Open and start the audio stream."""
        ...

    @abstractmethod
    def close(self) -> None:
        """Close and stop the audio stream."""
        ...

    @abstractmethod
    def get_info(self) -> DriverInfo:
        """Get current driver information."""
        ...

    @abstractmethod
    def get_input_devices(self) -> list[dict]:
        """List available input devices."""
        ...

    @abstractmethod
    def get_output_devices(self) -> list[dict]:
        """List available output devices."""
        ...

    def set_callback(self, callback: Callable) -> None:
        """Set the audio processing callback.

        Callback signature: callback(outdata, indata, frames, time_info, status)
        """
        self._callback = callback

    def get_latency_ms(self) -> float:
        """Get total round-trip latency in milliseconds."""
        info = self.get_info()
        return info.input_latency_ms + info.output_latency_ms


class SoundDeviceDriver(AudioDriverBase):
    """Audio driver using the sounddevice (PortAudio) library."""

    def __init__(self, config: DriverConfig) -> None:
        super().__init__(config)
        self._stream = None

    def open(self) -> None:
        """Open sounddevice stream."""
        try:
            import sounddevice as sd

            self._stream = sd.Stream(
                samplerate=self.config.sample_rate,
                blocksize=self.config.buffer_size,
                channels=(self.config.num_input_channels, self.config.num_output_channels),
                dtype='float32',
                callback=self._callback,
                device=(self.config.input_device, self.config.output_device),
            )
            self._stream.start()
            self._is_running = True
            logger.info("SoundDevice stream opened: %d Hz, %d buffer",
                       self.config.sample_rate, self.config.buffer_size)
        except Exception as e:
            logger.error("Failed to open SoundDevice stream: %s", e)
            raise

    def close(self) -> None:
        """Close sounddevice stream."""
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
            self._stream = None
        self._is_running = False

    def get_info(self) -> DriverInfo:
        """Get current driver information."""
        input_latency = 0.0
        output_latency = 0.0
        if self._stream is not None:
            try:
                lat = self._stream.latency
                input_latency = (lat[0] or 0) * 1000  # seconds to ms
                output_latency = (lat[1] or 0) * 1000
            except Exception:
                pass
        else:
            # Estimate from buffer size
            input_latency = self.config.buffer_size / self.config.sample_rate * 1000
            output_latency = self.config.buffer_size / self.config.sample_rate * 1000

        return DriverInfo(
            name="SoundDevice",
            sample_rate=self.config.sample_rate,
            buffer_size=self.config.buffer_size,
            input_channels=self.config.num_input_channels,
            output_channels=self.config.num_output_channels,
            input_latency_ms=input_latency,
            output_latency_ms=output_latency,
            is_running=self._is_running,
        )

    def get_input_devices(self) -> list[dict]:
        """List available input devices."""
        try:
            import sounddevice as sd
            devices = sd.query_devices()
            return [
                {"id": i, "name": d["name"], "channels": d["max_input_channels"]}
                for i, d in enumerate(devices)
                if d["max_input_channels"] > 0
            ]
        except Exception:
            return []

    def get_output_devices(self) -> list[dict]:
        """List available output devices."""
        try:
            import sounddevice as sd
            devices = sd.query_devices()
            return [
                {"id": i, "name": d["name"], "channels": d["max_output_channels"]}
                for i, d in enumerate(devices)
                if d["max_output_channels"] > 0
            ]
        except Exception:
            return []


class MockDriver(AudioDriverBase):
    """Mock audio driver for testing (no actual audio I/O)."""

    def __init__(self, config: DriverConfig) -> None:
        super().__init__(config)
        self._generated_frames = 0

    def open(self) -> None:
        self._is_running = True

    def close(self) -> None:
        self._is_running = False

    def get_info(self) -> DriverInfo:
        buf_ms = self.config.buffer_size / self.config.sample_rate * 1000
        return DriverInfo(
            name="Mock",
            sample_rate=self.config.sample_rate,
            buffer_size=self.config.buffer_size,
            input_channels=self.config.num_input_channels,
            output_channels=self.config.num_output_channels,
            input_latency_ms=buf_ms,
            output_latency_ms=buf_ms,
            is_running=self._is_running,
        )

    def get_input_devices(self) -> list[dict]:
        return [{"id": 0, "name": "Mock Input", "channels": 2}]

    def get_output_devices(self) -> list[dict]:
        return [{"id": 0, "name": "Mock Output", "channels": 2}]

    def process_block(self, num_frames: int) -> np.ndarray:
        """Process a block of audio through the mock driver.

        Returns:
            Output audio buffer (channels, frames).
        """
        out = np.zeros(
            (self.config.num_output_channels, num_frames), dtype=np.float32
        )
        inp = np.zeros(
            (self.config.num_input_channels, num_frames), dtype=np.float32
        )
        if self._callback:
            self._callback(out.T, inp.T, num_frames, None, None)
        self._generated_frames += num_frames
        return out


def create_driver(config: Optional[DriverConfig] = None) -> AudioDriverBase:
    """
    Create an audio driver based on configuration.

    Args:
        config: Driver configuration. If None, uses defaults.

    Returns:
        AudioDriverBase instance.
    """
    if config is None:
        config = DriverConfig()

    if config.driver_type == DriverType.SOUNDDEVICE:
        return SoundDeviceDriver(config)
    elif config.driver_type == DriverType.MOCK:
        return MockDriver(config)
    elif config.driver_type == DriverType.JACK:
        # JACK driver: fallback to sounddevice with JACK backend
        logger.warning("JACK driver not yet implemented, falling back to SoundDevice")
        return SoundDeviceDriver(config)
    elif config.driver_type == DriverType.PORTAUDIO:
        # PortAudio is the same as sounddevice
        return SoundDeviceDriver(config)
    else:
        raise ValueError(f"Unknown driver type: {config.driver_type}")
