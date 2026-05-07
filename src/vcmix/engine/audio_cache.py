"""
audio_cache.py — Audio file caching for VCMix renderer.

Avoids redundant disk I/O when the same WAV file is referenced
by multiple tracks (e.g. re-imported stems, layered samples).

Features:
    - LRU-style eviction when max_size is exceeded
    - Thread-safe for parallel rendering (threading.Lock)
    - Cache hit/miss statistics for performance monitoring
    - Per-path integrity check via mtime + size

Usage:
    from vcmix.engine.audio_cache import AudioCache

    cache = AudioCache(max_size_mb=500)
    audio, sr = cache.load("vocal.wav")

    stats = cache.stats()
    # {"hits": 12, "misses": 3, "entries": 3, "size_mb": 45.2}

Dependencies: numpy, soundfile
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Tuple

import numpy as np
import soundfile as sf


@dataclass
class _CacheEntry:
    """Internal cache entry with metadata."""
    audio: np.ndarray
    sr: int
    size_bytes: int
    mtime: float
    fsize: int  # file size in bytes


@dataclass
class AudioCache:
    """
    LRU audio file cache for the VCMix renderer.

    Avoids redundant soundfile reads when the same file is loaded
    multiple times across tracks. Thread-safe for parallel rendering.

    Args:
        max_size_mb: Maximum cache size in megabytes (default 500).
            When exceeded, least-recently-used entries are evicted.
    """

    max_size_mb: int = 500

    # Internal state (not part of constructor)
    _cache: dict = field(default_factory=dict, init=False, repr=False)
    _access_order: list = field(default_factory=list, init=False, repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False)
    _hits: int = field(default=0, init=False, repr=False)
    _misses: int = field(default=0, init=False, repr=False)
    _current_size_bytes: int = field(default=0, init=False, repr=False)

    @property
    def max_size_bytes(self) -> int:
        return self.max_size_mb * 1024 * 1024

    def load(self, path: str | Path) -> Tuple[np.ndarray, int]:
        """
        Load an audio file, returning cached data if available.

        Performs an integrity check: if the file's mtime or size has
        changed since caching, the entry is invalidated and re-read.

        Args:
            path: Path to audio file.

        Returns:
            Tuple of (audio_array, sample_rate).
        """
        path_str = str(Path(path).resolve())

        with self._lock:
            if path_str in self._cache:
                entry = self._cache[path_str]
                # Integrity check: verify file hasn't changed
                if self._is_valid(path_str, entry):
                    self._hits += 1
                    # Move to end of LRU order
                    self._access_order.remove(path_str)
                    self._access_order.append(path_str)
                    return entry.audio, entry.sr
                else:
                    # File changed, invalidate
                    self._evict_entry(path_str)

            self._misses += 1

        # Load outside the lock to allow concurrent reads
        data, sr = sf.read(path_str, dtype="float32", always_2d=False)

        # Normalize shape: soundfile returns (samples, channels)
        # We want (channels, samples) for multi-channel, (samples,) for mono
        if data.ndim == 2:
            data = data.T  # (channels, samples)

        size_bytes = data.nbytes
        file_stat = Path(path_str).stat()

        with self._lock:
            # Evict if needed
            while (
                self._current_size_bytes + size_bytes > self.max_size_bytes
                and self._access_order
            ):
                oldest = self._access_order[0]
                self._evict_entry(oldest)

            entry = _CacheEntry(
                audio=data,
                sr=sr,
                size_bytes=size_bytes,
                mtime=file_stat.st_mtime,
                fsize=file_stat.st_size,
            )
            self._cache[path_str] = entry
            self._access_order.append(path_str)
            self._current_size_bytes += size_bytes

        return data, sr

    def _is_valid(self, path_str: str, entry: _CacheEntry) -> bool:
        """Check if cached entry is still valid (file unchanged)."""
        try:
            stat = Path(path_str).stat()
            return stat.st_mtime == entry.mtime and stat.st_size == entry.fsize
        except OSError:
            return False

    def _evict_entry(self, path_str: str) -> None:
        """Remove a single entry from the cache. Must be called with lock held."""
        if path_str in self._cache:
            entry = self._cache.pop(path_str)
            self._current_size_bytes -= entry.size_bytes
            if path_str in self._access_order:
                self._access_order.remove(path_str)

    def invalidate(self, path: str | Path) -> None:
        """
        Manually invalidate a cached entry.

        Args:
            path: Path to invalidate.
        """
        path_str = str(Path(path).resolve())
        with self._lock:
            self._evict_entry(path_str)

    def clear(self) -> None:
        """Clear all cached entries."""
        with self._lock:
            self._cache.clear()
            self._access_order.clear()
            self._current_size_bytes = 0

    def stats(self) -> dict:
        """
        Return cache statistics.

        Returns:
            Dict with hits, misses, entries, size_mb, hit_rate.
        """
        with self._lock:
            total = self._hits + self._misses
            hit_rate = self._hits / total if total > 0 else 0.0
            return {
                "hits": self._hits,
                "misses": self._misses,
                "entries": len(self._cache),
                "size_mb": round(self._current_size_bytes / (1024 * 1024), 2),
                "hit_rate": round(hit_rate, 4),
            }

    def reset_stats(self) -> None:
        """Reset hit/miss counters without clearing cache."""
        with self._lock:
            self._hits = 0
            self._misses = 0

    def preload(self, paths: list) -> None:
        """
        Pre-load a list of audio files into the cache.

        Useful for warming the cache before parallel rendering starts.

        Args:
            paths: List of file paths to pre-load.
        """
        for p in paths:
            try:
                self.load(p)
            except Exception:
                pass  # Skip files that can't be loaded
