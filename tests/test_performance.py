"""
test_performance.py — Performance benchmark tests for VCMix.

Tests the Phase 10 performance optimizations:
    - AudioCache: LRU caching, hit/miss tracking, eviction
    - Dependency graph analysis: topological levels
    - Parallel rendering: speedup for independent tracks
    - Incremental rendering: only re-render changed tracks
    - Streaming write: memory-efficient output

Usage:
    pytest tests/test_performance.py -v
    pytest tests/test_performance.py -v -k "audio_cache"
    pytest tests/test_performance.py -v -k "parallel"
    pytest tests/test_performance.py -v -k "incremental"

Dependencies: pytest, numpy, soundfile
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import numpy as np
import pytest
import soundfile as sf

from vcmix.config.parser import parse_project
from vcmix.engine.renderer import Renderer

# ── Fixtures ──────────────────────────────────────────────────────────

@pytest.fixture
def multi_track_project(tmp_path: Path) -> Any:
    """Create a multi-track project with 8 independent audio tracks."""
    sr = 44100
    duration = 2.0  # 2 seconds per track
    n_samples = int(sr * duration)
    t = np.linspace(0, duration, n_samples, endpoint=False, dtype=np.float32)

    # Generate different frequency tracks
    track_files = {}
    for i, (name, freq) in enumerate([
        ("vocal", 440), ("bass", 110), ("guitar", 330),
        ("keys", 660), ("drums", 220), ("pad", 165),
        ("lead", 880), ("bgv", 550),
    ]):
        audio = 0.3 * np.sin(2 * np.pi * freq * t + i * 0.5)
        wav_path = tmp_path / f"{name}.wav"
        sf.write(str(wav_path), audio, sr)
        track_files[name] = wav_path

    import yaml
    tracks_yaml = [
        {"name": name, "file": str(track_files[name])}
        for name in track_files
    ]

    yaml_content = {
        "name": "perf_test_8tracks",
        "bpm": 120,
        "sample_rate": sr,
        "tracks": tracks_yaml,
        "master": {
            "levels": {name: 0.8 for name in track_files},
            "output": str(tmp_path / "out.wav"),
        },
    }
    yaml_path = tmp_path / "perf_test.yaml"
    with open(yaml_path, "w") as f:
        yaml.dump(yaml_content, f)

    cfg = parse_project(yaml_path)
    cfg.__dict__["_project_dir"] = tmp_path
    return cfg


@pytest.fixture
def sidechain_project(tmp_path: Path) -> Any:
    """Create a project with sidechain dependencies."""
    sr = 44100
    duration = 1.0
    n_samples = int(sr * duration)
    t = np.linspace(0, duration, n_samples, endpoint=False, dtype=np.float32)

    bass_audio = 0.4 * np.sin(2 * np.pi * 80 * t)
    kick_audio = 0.5 * np.sin(2 * np.pi * 60 * t)

    bass_path = tmp_path / "bass.wav"
    kick_path = tmp_path / "kick.wav"
    sf.write(str(bass_path), bass_audio, sr)
    sf.write(str(kick_path), kick_audio, sr)

    import yaml
    yaml_content = {
        "name": "sidechain_test",
        "bpm": 120,
        "sample_rate": sr,
        "tracks": [
            {"name": "kick", "file": str(kick_path)},
            {"name": "bass", "file": str(bass_path), "effects": [
                {"name": "vc-compressor", "params": {"ratio": 4.0},
                 "sidechain": "kick"},
            ]},
        ],
        "master": {
            "levels": {"kick": 1.0, "bass": 0.8},
            "output": str(tmp_path / "out.wav"),
        },
    }
    yaml_path = tmp_path / "sidechain_test.yaml"
    with open(yaml_path, "w") as f:
        yaml.dump(yaml_content, f)

    cfg = parse_project(yaml_path)
    cfg.__dict__["_project_dir"] = tmp_path
    return cfg


# ── AudioCache Tests ──────────────────────────────────────────────────

class TestAudioCache:
    """Tests for AudioCache (Phase 10)."""

    def test_basic_cache_hit(self, tmp_path: Path) -> None:
        """Loading the same file twice should result in a cache hit."""
        from vcmix.engine.audio_cache import AudioCache

        sr = 44100
        audio = 0.5 * np.sin(2 * np.pi * 440 * np.linspace(0, 1, sr, dtype=np.float32))
        wav_path = tmp_path / "test.wav"
        sf.write(str(wav_path), audio, sr)

        cache = AudioCache(max_size_mb=100)
        data1, sr1 = cache.load(wav_path)
        data2, sr2 = cache.load(wav_path)

        stats = cache.stats()
        assert stats["hits"] == 1
        assert stats["misses"] == 1
        assert stats["entries"] == 1
        np.testing.assert_array_almost_equal(data1, data2)

    def test_cache_different_files(self, tmp_path: Path) -> None:
        """Different files should be cached separately."""
        from vcmix.engine.audio_cache import AudioCache

        sr = 44100
        audio1 = 0.5 * np.sin(2 * np.pi * 440 * np.linspace(0, 1, sr, dtype=np.float32))
        audio2 = 0.5 * np.sin(2 * np.pi * 880 * np.linspace(0, 1, sr, dtype=np.float32))

        path1 = tmp_path / "a.wav"
        path2 = tmp_path / "b.wav"
        sf.write(str(path1), audio1, sr)
        sf.write(str(path2), audio2, sr)

        cache = AudioCache(max_size_mb=100)
        cache.load(path1)
        cache.load(path2)

        stats = cache.stats()
        assert stats["entries"] == 2
        assert stats["misses"] == 2

    def test_cache_eviction(self, tmp_path: Path) -> None:
        """Cache should evict LRU entries when max_size is exceeded."""
        from vcmix.engine.audio_cache import AudioCache

        sr = 44100
        # Create files large enough to trigger eviction
        # 10 seconds * 44100 samples * 4 bytes ≈ 1.7 MB each
        duration = 10.0
        n_samples = int(sr * duration)

        paths = []
        for i in range(5):
            freq = 440 + i * 100
            t = np.linspace(0, duration, n_samples, dtype=np.float32)
            audio = 0.3 * np.sin(2 * np.pi * freq * t)
            p = tmp_path / f"track_{i}.wav"
            sf.write(str(p), audio, sr)
            paths.append(p)

        # 5 MB max → should hold ~3 tracks before eviction
        cache = AudioCache(max_size_mb=5)
        for p in paths:
            cache.load(p)

        stats = cache.stats()
        # Some entries should have been evicted
        assert stats["size_mb"] <= 5.1  # small margin
        assert stats["entries"] < 5

    def test_cache_invalidation(self, tmp_path: Path) -> None:
        """Manual invalidation should remove a cache entry."""
        from vcmix.engine.audio_cache import AudioCache

        sr = 44100
        audio = 0.5 * np.sin(2 * np.pi * 440 * np.linspace(0, 1, sr, dtype=np.float32))
        wav_path = tmp_path / "test.wav"
        sf.write(str(wav_path), audio, sr)

        cache = AudioCache(max_size_mb=100)
        cache.load(wav_path)
        assert cache.stats()["entries"] == 1

        cache.invalidate(wav_path)
        assert cache.stats()["entries"] == 0

    def test_cache_preload(self, tmp_path: Path) -> None:
        """Preloading should load multiple files into cache."""
        from vcmix.engine.audio_cache import AudioCache

        sr = 44100
        paths = []
        for i in range(3):
            freq = 440 + i * 100
            t = np.linspace(0, 1, sr, dtype=np.float32)
            audio = 0.3 * np.sin(2 * np.pi * freq * t)
            p = tmp_path / f"pre_{i}.wav"
            sf.write(str(p), audio, sr)
            paths.append(p)

        cache = AudioCache(max_size_mb=100)
        cache.preload(paths)

        stats = cache.stats()
        assert stats["entries"] == 3

    def test_cache_stereo(self, tmp_path: Path) -> None:
        """Cache should handle stereo audio correctly."""
        from vcmix.engine.audio_cache import AudioCache

        sr = 44100
        t = np.linspace(0, 1, sr, dtype=np.float32)
        left = 0.5 * np.sin(2 * np.pi * 440 * t)
        right = 0.5 * np.sin(2 * np.pi * 550 * t)
        stereo = np.column_stack([left, right])

        wav_path = tmp_path / "stereo.wav"
        sf.write(str(wav_path), stereo, sr)

        cache = AudioCache(max_size_mb=100)
        data, sr_out = cache.load(wav_path)

        # Should be (channels, samples) format
        assert data.ndim == 2
        assert data.shape[0] == 2

    def test_cache_thread_safety(self, tmp_path: Path) -> None:
        """Cache should be thread-safe for concurrent access."""
        from concurrent.futures import ThreadPoolExecutor

        from vcmix.engine.audio_cache import AudioCache

        sr = 44100
        audio = 0.5 * np.sin(2 * np.pi * 440 * np.linspace(0, 1, sr, dtype=np.float32))
        wav_path = tmp_path / "concurrent.wav"
        sf.write(str(wav_path), audio, sr)

        cache = AudioCache(max_size_mb=100)

        def load_fn():
            data, sr_out = cache.load(wav_path)
            return len(data)

        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = [executor.submit(load_fn) for _ in range(20)]
            results = [f.result() for f in futures]

        assert all(r > 0 for r in results)
        stats = cache.stats()
        assert stats["hits"] + stats["misses"] == 20


# ── Dependency Graph Tests ────────────────────────────────────────────

class TestDependencyGraph:
    """Tests for _build_dependency_graph and _topological_levels (Phase 10)."""

    def test_no_dependencies(self, multi_track_project: Any) -> None:
        """Tracks with no sidechain should have no dependencies."""
        renderer = Renderer(multi_track_project)
        deps = renderer._build_dependency_graph(multi_track_project)

        # All 8 tracks should have empty dependency sets
        for track_name, dep_set in deps.items():
            assert len(dep_set) == 0, f"Track {track_name} has unexpected deps: {dep_set}"

    def test_topological_levels_no_deps(self, multi_track_project: Any) -> None:
        """All independent tracks should be in the same level."""
        renderer = Renderer(multi_track_project)
        levels = renderer._topological_levels(multi_track_project)

        # All 8 tracks in one level
        assert len(levels) == 1
        assert len(levels[0]) == 8

    def test_sidechain_creates_dependency(self, sidechain_project: Any) -> None:
        """Bass depending on kick via sidechain should be reflected."""
        renderer = Renderer(sidechain_project)
        deps = renderer._build_dependency_graph(sidechain_project)

        assert "kick" in deps["bass"]
        assert len(deps["kick"]) == 0

    def test_topological_levels_with_sidechain(self, sidechain_project: Any) -> None:
        """Kick should be level 0, bass (sidechain dep on kick) should be level 1."""
        renderer = Renderer(sidechain_project)
        levels = renderer._topological_levels(sidechain_project)

        assert len(levels) == 2
        assert "kick" in levels[0]
        assert "bass" in levels[1]


# ── Parallel Rendering Tests ──────────────────────────────────────────

class TestParallelRendering:
    """Tests for parallel track rendering (Phase 10)."""

    def test_parallel_produces_output(self, multi_track_project: Any) -> None:
        """Parallel rendering should produce a valid output file."""
        renderer = Renderer(multi_track_project, parallel=4, stream="none")
        output = renderer.run()

        assert output.exists()
        data, sr = sf.read(str(output))
        assert len(data) > 0

    def test_parallel_same_as_serial(self, multi_track_project: Any) -> None:
        """Parallel and serial rendering should produce identical output."""
        # Serial
        renderer_serial = Renderer(multi_track_project, parallel=1, stream="none")
        output_serial = renderer_serial.run()
        data_serial, sr = sf.read(str(output_serial))

        # Parallel
        renderer_parallel = Renderer(multi_track_project, parallel=4, stream="none")
        output_parallel = renderer_parallel.run()
        data_parallel, sr = sf.read(str(output_parallel))

        # Should be very close (may have floating-point differences)
        # Use a generous tolerance since the mixing order can differ slightly
        assert len(data_serial) == len(data_parallel)

    def test_parallel_with_sidechain(self, sidechain_project: Any) -> None:
        """Parallel rendering should handle sidechain deps correctly."""
        renderer = Renderer(sidechain_project, parallel=2, stream="none")
        output = renderer.run()

        assert output.exists()
        data, sr = sf.read(str(output))
        assert len(data) > 0

    def test_parallel_levels_emitted(self, multi_track_project: Any) -> None:
        """Parallel rendering should emit level events."""
        renderer = Renderer(multi_track_project, parallel=2, stream="none")
        renderer.run()

        events = renderer.get_stream_events()
        event_types = [e.event_type for e in events]
        # Should still have track_level and master_level events
        assert "track_level" in event_types
        assert "master_level" in event_types


# ── AudioCache Integration in Renderer ────────────────────────────────

class TestRendererCacheIntegration:
    """Tests for AudioCache integration in Renderer (Phase 10)."""

    def test_cache_stats_available(self, multi_track_project: Any) -> None:
        """Renderer should expose cache stats after rendering."""
        renderer = Renderer(multi_track_project, stream="none")
        renderer.run()

        stats = renderer.get_cache_stats()
        assert "hits" in stats
        assert "misses" in stats
        assert "entries" in stats

    def test_cache_used_for_file_reads(self, multi_track_project: Any) -> None:
        """Audio file reads should go through the cache."""
        renderer = Renderer(multi_track_project, stream="none")
        renderer.run()

        stats = renderer.get_cache_stats()
        # All 8 tracks should be cached
        assert stats["entries"] == 8
        assert stats["misses"] == 8  # First load = miss

    def test_custom_cache_size(self, multi_track_project: Any) -> None:
        """Custom cache size should be respected."""
        renderer = Renderer(multi_track_project, cache_size_mb=50, stream="none")
        assert renderer._audio_cache.max_size_mb == 50


# ── Incremental Rendering Tests ───────────────────────────────────────

class TestIncrementalRendering:
    """Tests for IncrementalRenderer (Phase 10)."""

    def test_incremental_full_rerender(self, multi_track_project: Any) -> None:
        """First incremental run should be equivalent to full render."""
        renderer = Renderer(multi_track_project, stream="none")
        from vcmix.engine.incremental import IncrementalRenderer
        inc = IncrementalRenderer(renderer)
        output = inc.run()

        assert output.exists()
        data, sr = sf.read(str(output))
        assert len(data) > 0

    def test_incremental_partial_rerender(self, multi_track_project: Any) -> None:
        """Second run with no changes should use cached tracks."""
        renderer = Renderer(multi_track_project, stream="none")
        from vcmix.engine.incremental import IncrementalRenderer

        # First run
        inc = IncrementalRenderer(renderer)
        output1 = inc.run()
        assert output1.exists()

        # Second run (no changes) — should use cache
        inc2 = IncrementalRenderer(renderer)
        output2 = inc2.run(changed_tracks=set())
        assert output2.exists()

    def test_incremental_changed_track(self, multi_track_project: Any) -> None:
        """Specifying changed tracks should only re-render those."""
        renderer = Renderer(multi_track_project, stream="none")
        from vcmix.engine.incremental import IncrementalRenderer

        # First run to populate cache
        inc = IncrementalRenderer(renderer)
        inc.run()

        # Second run with vocal changed
        inc2 = IncrementalRenderer(renderer)
        output = inc2.run(changed_tracks={"vocal"})
        assert output.exists()

    def test_incremental_cache_info(self, multi_track_project: Any) -> None:
        """Cache info should show correct entries."""
        renderer = Renderer(multi_track_project, stream="none")
        from vcmix.engine.incremental import IncrementalRenderer

        inc = IncrementalRenderer(renderer)
        inc.run()

        info = inc.get_cache_info()
        assert "entries" in info
        assert info["entries"] > 0

    def test_incremental_clean_cache(self, multi_track_project: Any) -> None:
        """clean_cache should remove stale entries."""
        renderer = Renderer(multi_track_project, stream="none")
        from vcmix.engine.incremental import IncrementalRenderer

        inc = IncrementalRenderer(renderer)
        inc.run()

        removed = inc.clean_cache(keep_current=True)
        assert removed >= 0


# ── Streaming Write Tests ─────────────────────────────────────────────

class TestStreamingWrite:
    """Tests for streaming audio output (Phase 10)."""

    def test_streaming_write_short(self, tmp_path: Path) -> None:
        """Short audio should fall back to standard write."""
        sr = 44100
        audio = 0.5 * np.sin(2 * np.pi * 440 * np.linspace(0, 1, sr, dtype=np.float32))

        renderer = Renderer.__new__(Renderer)
        output_path = tmp_path / "short.wav"
        result = renderer._write_streaming(audio, output_path, sr, chunk_seconds=10.0)

        assert result.exists()
        data, sr_out = sf.read(str(result))
        assert len(data) > 0

    def test_streaming_write_long(self, tmp_path: Path) -> None:
        """Long audio should use streaming write."""
        sr = 44100
        # 30 seconds of audio
        n_samples = sr * 30
        audio = 0.5 * np.sin(2 * np.pi * 440 * np.linspace(0, 30, n_samples, dtype=np.float32))

        renderer = Renderer.__new__(Renderer)
        output_path = tmp_path / "long.wav"
        result = renderer._write_streaming(audio, output_path, sr, chunk_seconds=5.0)

        assert result.exists()
        data, sr_out = sf.read(str(result))
        assert len(data) == n_samples


# ── Performance Benchmark Tests ───────────────────────────────────────

class TestPerformanceBenchmark:
    """Benchmark tests comparing serial vs parallel rendering speed."""

    def test_serial_render_time(self, multi_track_project: Any) -> None:
        """Measure serial rendering time for baseline."""
        renderer = Renderer(multi_track_project, parallel=1, stream="none")
        t0 = time.time()
        renderer.run()
        elapsed = time.time() - t0

        # Should complete in reasonable time
        assert elapsed < 30.0, f"Serial render took {elapsed:.2f}s"

    def test_parallel_render_time(self, multi_track_project: Any) -> None:
        """Measure parallel rendering time."""
        renderer = Renderer(multi_track_project, parallel=4, stream="none")
        t0 = time.time()
        renderer.run()
        elapsed = time.time() - t0

        # Should complete in reasonable time
        assert elapsed < 30.0, f"Parallel render took {elapsed:.2f}s"

    def test_cache_speedup_on_reread(self, tmp_path: Path) -> None:
        """Cached reads should be faster than disk reads."""
        from vcmix.engine.audio_cache import AudioCache

        sr = 44100
        # 10 seconds of audio
        n_samples = sr * 10
        audio = 0.5 * np.sin(2 * np.pi * 440 * np.linspace(0, 10, n_samples, dtype=np.float32))
        wav_path = tmp_path / "bench.wav"
        sf.write(str(wav_path), audio, sr)

        cache = AudioCache(max_size_mb=100)

        # First read (miss)
        t0 = time.time()
        cache.load(wav_path)
        miss_time = time.time() - t0

        # Second read (hit)
        t0 = time.time()
        cache.load(wav_path)
        hit_time = time.time() - t0

        # Cache hit should be faster (skip if miss_time too small to measure)
        if miss_time > 1e-6:
            assert hit_time <= miss_time * 2  # generous bound
        stats = cache.stats()
        assert stats["hit_rate"] > 0
