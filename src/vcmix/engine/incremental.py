"""
incremental.py — Incremental rendering for VCMix.

Tracks which tracks have been rendered and their content hashes,
so that only changed tracks need re-rendering on subsequent runs.

Features:
    - Content hash based on YAML config + source file mtime
    - Dependency-aware invalidation (sidechain sources changed → downstream too)
    - Rendered audio cache on disk (.vcmix_cache/)
    - Integration with Renderer for transparent incremental mode

Usage:
    from vcmix.engine.incremental import IncrementalRenderer

    inc = IncrementalRenderer(renderer)
    output = inc.run(changed_tracks=None)  # auto-detect changes
    output = inc.run(changed_tracks=["vocal"])  # force re-render specific tracks

Dependencies: numpy, soundfile, hashlib
"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any

import numpy as np
import soundfile as sf


class IncrementalRenderer:
    """
    Wrapper around Renderer that adds incremental rendering.

    Caches rendered track audio to disk and tracks content hashes.
    On re-run, only tracks whose content has changed (or whose
    dependencies have changed) are re-rendered.

    Args:
        renderer: A configured Renderer instance.
    """

    def __init__(self, renderer: Any) -> None:
        self._renderer = renderer
        self._project = renderer.config
        self._project_dir = getattr(self._project, "_project_dir", Path("."))
        self._cache_dir = self._project_dir / ".vcmix_cache"
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        self._manifest_path = self._cache_dir / "manifest.json"
        self._manifest = self._load_manifest()

    # ── Manifest management ──────────────────────────────────────────

    def _load_manifest(self) -> dict:
        """Load the cache manifest from disk."""
        if self._manifest_path.exists():
            try:
                return json.loads(self._manifest_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                return {}
        return {}

    def _save_manifest(self) -> None:
        """Save the cache manifest to disk."""
        self._manifest_path.write_text(
            json.dumps(self._manifest, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    # ── Content hashing ──────────────────────────────────────────────

    def _compute_track_hash(self, track: Any) -> str:
        """
        Compute a content hash for a track.

        Includes:
            - Track name + volume + mute
            - Effect chain (names + params)
            - Source file mtime + size (for audio tracks)
            - MIDI file mtime + size (for MIDI/sampler tracks)
            - Sidechain source reference
            - Automation config
        """
        hasher = hashlib.sha256()

        # Track identity
        hasher.update(track.name.encode("utf-8"))
        hasher.update(struct_pack_float(track.volume))
        hasher.update(struct_pack_bool(track.mute))

        # Source file info
        track_type = getattr(track, 'type', 'audio')
        hasher.update(track_type.encode("utf-8"))

        if track_type == 'audio':
            track_path = self._project_dir / track.file
            _hash_file_info(hasher, track_path)
        elif track_type == 'midi' and track.midi_file:
            _hash_file_info(hasher, self._project_dir / track.midi_file)
        elif track_type == 'sampler':
            for zone in getattr(track, 'zones', []):
                _hash_file_info(hasher, self._project_dir / zone.file)
            if getattr(track, 'midi_file', None):
                _hash_file_info(hasher, self._project_dir / track.midi_file)
        elif track_type == 'vst3':
            _hash_file_info(hasher, Path(getattr(track, 'plugin_path', '')))
            if track.file:
                _hash_file_info(hasher, self._project_dir / track.file)

        # Effect chain
        for effect in track.effects:
            hasher.update(effect.name.encode("utf-8"))
            if effect.sidechain:
                hasher.update(effect.sidechain.encode("utf-8"))
            # Hash params dict
            params_str = json.dumps(effect.params, sort_keys=True)
            hasher.update(params_str.encode("utf-8"))

        # Automation
        automation = getattr(track, 'automation', None)
        if automation:
            auto_str = json.dumps(automation, sort_keys=True, default=str)
            hasher.update(auto_str.encode("utf-8"))

        # Sends
        if track.sends:
            sends_str = json.dumps(track.sends, sort_keys=True, default=str)
            hasher.update(sends_str.encode("utf-8"))

        return hasher.hexdigest()[:16]  # 16 chars is plenty for cache key

    # ── Dependency-aware invalidation ────────────────────────────────

    def _get_dependents(self, track_name: str) -> set[str]:
        """
        Get all tracks that depend on the given track (sidechain or send).

        Args:
            track_name: The source track name.

        Returns:
            Set of track names that depend on this track.
        """
        dependents: set[str] = set()
        for track in self._project.tracks:
            # Check sidechain dependencies
            for effect in track.effects:
                if effect.sidechain == track_name:
                    dependents.add(track.name)
            # Check send dependencies
            if track.sends and track_name in track.sends:
                dependents.add(track.name)
        return dependents

    def _get_all_affected(self, changed_tracks: set[str]) -> set[str]:
        """
        Get all tracks affected by changes, including transitive dependents.

        Args:
            changed_tracks: Initially changed track names.

        Returns:
            All affected track names (including changed tracks themselves).
        """
        affected = set(changed_tracks)
        # BFS through dependency graph
        queue = list(changed_tracks)
        while queue:
            current = queue.pop(0)
            for dep in self._get_dependents(current):
                if dep not in affected:
                    affected.add(dep)
                    queue.append(dep)
        return affected

    # ── Cached audio I/O ─────────────────────────────────────────────

    def _cache_path(self, track_name: str, content_hash: str) -> Path:
        """Get the cache file path for a rendered track."""
        return self._cache_dir / f"{track_name}_{content_hash}.wav"

    def _save_cached_audio(
        self, track_name: str, content_hash: str, audio: np.ndarray, sr: int
    ) -> None:
        """Save rendered audio to cache."""
        cache_path = self._cache_path(track_name, content_hash)
        # Normalize to (samples, channels) for soundfile
        if audio.ndim == 1:
            data = audio
        else:
            data = audio.T
        sf.write(str(cache_path), data, sr, subtype="FLOAT")

        # Update manifest
        self._manifest[track_name] = {
            "hash": content_hash,
            "cache_file": cache_path.name,
            "timestamp": time.time(),
        }
        self._save_manifest()

    def _load_cached_audio(self, track_name: str, content_hash: str) -> np.ndarray | None:
        """Load cached audio if available and hash matches."""
        entry = self._manifest.get(track_name)
        if entry is None or entry.get("hash") != content_hash:
            return None

        cache_path = self._cache_dir / entry["cache_file"]
        if not cache_path.exists():
            return None

        try:
            data, sr = sf.read(str(cache_path), dtype="float32", always_2d=False)
            if data.ndim == 2:
                data = data.T  # (channels, samples)
            return data
        except Exception:
            return None

    # ── Main incremental run ─────────────────────────────────────────

    def run(self, changed_tracks: set[str] | None = None) -> Path:
        """
        Run incremental rendering.

        If changed_tracks is None, auto-detect by comparing content hashes
        against the manifest. Otherwise, force the specified tracks (and
        their dependents) to re-render.

        Args:
            changed_tracks: Set of track names that have changed, or None
                for auto-detection.

        Returns:
            Path to the rendered output file.
        """
        project = self._project
        renderer = self._renderer

        # Compute current hashes for all tracks
        current_hashes: dict[str, str] = {}
        for track in project.tracks:
            current_hashes[track.name] = self._compute_track_hash(track)

        # Determine which tracks need re-rendering
        if changed_tracks is not None:
            # Explicit change set → also invalidate dependents
            affected = self._get_all_affected(changed_tracks)
            needs_rerender = affected
        else:
            # Auto-detect by comparing hashes with manifest
            needs_rerender = set()
            for track in project.tracks:
                old_hash = self._manifest.get(track.name, {}).get("hash")
                if old_hash != current_hashes[track.name]:
                    needs_rerender.add(track.name)

            # Also add dependents of changed tracks
            if needs_rerender:
                needs_rerender = self._get_all_affected(needs_rerender)

        # Emit incremental info
        renderer._emit("incremental", {
            "total_tracks": len(project.tracks),
            "needs_rerender": len(needs_rerender),
            "cached_tracks": len(project.tracks) - len(needs_rerender),
        })

        # Always use _run_partial to ensure caching works
        # (even when all tracks need re-rendering on first run)
        return self._run_partial(needs_rerender, current_hashes)

    def _run_partial(self, needs_rerender: set[str], current_hashes: dict[str, str]) -> Path:
        """
        Run partial re-render: re-render changed tracks, load cached
        audio for unchanged tracks, then mix normally.

        Args:
            needs_rerender: Set of track names that need re-rendering.
            current_hashes: Current content hashes for all tracks.

        Returns:
            Path to the rendered output file.
        """
        from vcmix.audio.io import write_audio
        from vcmix.audio.mixer import Mixer
        from vcmix.plugins.registry import PluginRegistry

        project = self._project
        renderer = self._renderer
        sr = project.sample_rate
        project_dir = getattr(project, "_project_dir", Path("."))

        renderer.data_stream.start()

        # Step 1-3: Standard pipeline
        renderer._emit("1_parse", {"name": project.name, "bpm": project.bpm})

        # Validate
        for track in project.tracks:
            track_type = getattr(track, 'type', 'audio')
            if track_type == 'audio':
                track_path = project_dir / track.file
                if not track_path.exists():
                    raise FileNotFoundError(f"Track audio not found: {track_path}")
        renderer._emit("2_validate", {"tracks": len(project.tracks), "ok": True})

        has_sends = len(project.sends) > 0 or any(t.sends for t in project.tracks)
        renderer._emit("3_dag", {
            "topology": "send_return" if has_sends else "linear_insert_chain",
        })

        # Step 4: Render tracks (re-render only changed, cache-load rest)
        registry = PluginRegistry()
        render_order = renderer._resolve_render_order(project)
        rendered_tracks: dict[str, np.ndarray] = {}

        # Pre-load cached tracks first (they may be sidechain sources)
        for track_name in render_order:
            track = next((t for t in project.tracks if t.name == track_name), None)
            if track is None or track.mute:
                continue

            if track_name not in needs_rerender:
                # Try to load from cache
                cached = self._load_cached_audio(track_name, current_hashes[track_name])
                if cached is not None:
                    rendered_tracks[track.name] = cached
                    renderer._emit("4_render", {"track": track.name, "status": "cached"})
                    continue

            # Re-render this track
            prev_audio = renderer._render_track(track, registry, sr, project_dir, rendered_tracks)
            rendered_tracks[track.name] = prev_audio

            # Cache the result
            self._save_cached_audio(track.name, current_hashes[track_name], prev_audio, sr)
            renderer._emit("4_render", {"track": track.name, "status": "done"})

        # Step 4.5: Send/Return buses
        bus_return_audio = np.zeros(1, dtype=np.float32)
        if has_sends and project.sends:
            from vcmix.engine.bus import BusManager
            bus_manager = BusManager.from_config(
                [s.model_dump() for s in project.sends],
                bpm=project.bpm,
            )
            all_returns: list = []
            for track in project.tracks:
                if track.name not in rendered_tracks or not track.sends:
                    continue
                track_returns = bus_manager.process_sends(
                    track.name, rendered_tracks[track.name],
                    track.sends, registry, sr,
                )
                all_returns.append(track_returns)

            if all_returns:
                max_len = max(
                    max(len(a.flatten()) for a in returns.values())
                    for returns in all_returns if returns
                )
                for audio in rendered_tracks.values():
                    max_len = max(max_len, len(audio.flatten()))
                bus_return_audio = bus_manager.mix_returns(all_returns, max_len)

        # Step 5: Mix
        mixer = Mixer(sample_rate=sr)
        track_names = list(rendered_tracks.keys())
        track_audios = [rendered_tracks[n] for n in track_names]
        track_levels = [project.master.levels.get(n, 1.0) for n in track_names]
        mixed = mixer.mix(track_audios, levels=track_levels)

        if has_sends and len(bus_return_audio) > 1:
            mixed_flat = mixed.flatten().astype(np.float64)
            bus_flat = bus_return_audio.flatten().astype(np.float64)
            min_len = min(len(mixed_flat), len(bus_flat))
            mixed_flat[:min_len] += bus_flat[:min_len]
            mixed = mixed_flat.astype(np.float32)

        renderer._emit_master_level(mixed, sr)

        # Step 6: Master insert chain
        prev_audio = mixed
        for effect in project.master.effects:
            plugin = registry.get(effect.name)
            if plugin is None:
                continue
            processed = plugin.process(prev_audio, effect.params, sr)
            renderer._emit_effect_delta("master", effect.name, prev_audio, processed, sr)
            prev_audio = processed

        renderer._emit_master_level(prev_audio, sr)
        renderer._check_warnings("master", prev_audio, sr)
        renderer._emit("6_master", {"effects": len(project.master.effects)})

        # Step 7: Output
        output_path = project_dir / project.master.output
        write_audio(prev_audio, output_path, sr)

        renderer._emit("7_output", {"path": str(output_path), "incremental": True})
        return output_path

    # ── Cache management ─────────────────────────────────────────────

    def clean_cache(self, keep_current: bool = True) -> int:
        """
        Remove stale cache entries.

        Args:
            keep_current: If True, keep entries for current project tracks.

        Returns:
            Number of entries removed.
        """
        current_files = set()
        if keep_current:
            for entry in self._manifest.values():
                current_files.add(entry.get("cache_file", ""))

        removed = 0
        for cache_file in self._cache_dir.glob("*.wav"):
            if cache_file.name not in current_files:
                cache_file.unlink()
                removed += 1

        return removed

    def get_cache_info(self) -> dict:
        """Return information about the current cache state."""
        total_size = sum(
            f.stat().st_size for f in self._cache_dir.glob("*.wav")
        )
        return {
            "entries": len(self._manifest),
            "cache_dir": str(self._cache_dir),
            "total_size_mb": round(total_size / (1024 * 1024), 2),
            "manifest_entries": list(self._manifest.keys()),
        }


# ── Module-level helpers ─────────────────────────────────────────────

def _hash_file_info(hasher: hashlib._Hash, path: Path) -> None:
    """Hash file mtime and size into the hasher."""
    try:
        if path.exists():
            stat = path.stat()
            hasher.update(str(stat.st_mtime).encode("utf-8"))
            hasher.update(str(stat.st_size).encode("utf-8"))
    except OSError:
        pass


def struct_pack_float(v: float) -> bytes:
    """Pack a float into bytes for hashing."""
    import struct
    return struct.pack("d", v)


def struct_pack_bool(v: bool) -> bytes:
    """Pack a bool into bytes for hashing."""
    import struct
    return struct.pack("?", v)
