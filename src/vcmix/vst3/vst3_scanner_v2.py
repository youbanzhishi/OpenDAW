"""
vst3_scanner_v2.py — Enhanced VST3 plugin scanner.

Features over v1:
- Reads plugin metadata (name, vendor, version, param count, category)
- Caches scan results to JSON file
- Incremental scanning (only checks new/modified plugins)
- Cross-platform VST3 path detection
- AudioUnit scan support on macOS (experimental)

Scan paths by platform:
- Windows: C:\\Program Files\\Common Files\\VST3\\
- macOS: /Library/Audio/Plug-Ins/VST3/
- Linux: /usr/lib/vst3/, ~/.vst3/
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import stat
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional

from vcmix.vst3.vst3_scanner import VST3PluginInfo, VST3Scanner


@dataclass
class PluginMetadata:
    """Extended plugin metadata."""
    name: str
    path: str
    manufacturer: str = ""
    version: str = ""
    category: str = ""
    is_instrument: bool = False
    num_params: int = 0
    num_input_channels: int = 0
    num_output_channels: int = 0
    file_size: int = 0
    last_modified: float = 0.0
    checksum: str = ""
    scan_time: float = 0.0


@dataclass
class ScanCache:
    """Cached scan results."""
    version: int = 2
    scan_time: float = 0.0
    plugins: list[dict] = None

    def __post_init__(self) -> None:
        if self.plugins is None:
            self.plugins = []


class VST3ScannerV2:
    """
    Enhanced VST3 plugin scanner with caching and incremental scanning.

    Usage:
        scanner = VST3ScannerV2()
        plugins = scanner.scan()
        for p in plugins:
            print(f"{p.name} by {p.manufacturer} ({p.version})")
    """

    CACHE_FILENAME = ".opendaw_vst3_cache.json"

    def __init__(
        self,
        cache_dir: Optional[str] = None,
        cli_path: Optional[str] = None,
        extra_paths: Optional[list[str]] = None,
    ) -> None:
        self.cli_path = cli_path
        self.extra_paths = extra_paths or []
        self._cache_dir = Path(cache_dir or Path.home() / ".opendaw")
        self._cache_path = self._cache_dir / self.CACHE_FILENAME
        self._scanner = VST3Scanner(
            cli_path=cli_path,
            extra_paths=extra_paths,
        )

    # ── Scan Paths ─────────────────────────────────────────────────────────

    @staticmethod
    def get_default_search_paths() -> list[Path]:
        """Get OS-specific VST3 plugin search directories."""
        paths: list[Path] = []
        home = Path.home()
        system = platform.system()

        if system == "Linux":
            paths.extend([
                Path("/usr/lib/vst3"),
                Path("/usr/local/lib/vst3"),
                home / ".vst3",
            ])
        elif system == "Darwin":
            paths.extend([
                Path("/Library/Audio/Plug-Ins/VST3"),
                home / "Library" / "Audio" / "Plug-Ins" / "VST3",
            ])
        elif system == "Windows":
            pf = os.environ.get("PROGRAMFILES", "C:\\Program Files")
            paths.extend([
                Path(pf) / "Common Files" / "VST3",
            ])
            pf86 = os.environ.get("PROGRAMFILES(X86)", "")
            if pf86:
                paths.append(Path(pf86) / "Common Files" / "VST3")

        return paths

    @staticmethod
    def get_au_search_paths() -> list[Path]:
        """Get macOS AudioUnit search directories."""
        if platform.system() != "Darwin":
            return []
        home = Path.home()
        return [
            Path("/Library/Audio/Plug-Ins/Components"),
            home / "Library" / "Audio" / "Plug-Ins" / "Components",
        ]

    def get_all_search_paths(self) -> list[Path]:
        """Get all search paths (default + extra)."""
        paths = self.get_default_search_paths()
        for p in self.extra_paths:
            paths.append(Path(p))
        return paths

    # ── Scanning ───────────────────────────────────────────────────────────

    def scan(self, force_rescan: bool = False) -> list[PluginMetadata]:
        """
        Scan for VST3 plugins.

        Args:
            force_rescan: If True, ignore cache and rescan everything.

        Returns:
            List of PluginMetadata for found plugins.
        """
        # Load cache
        cache = self._load_cache()

        if not force_rescan and cache and cache.plugins:
            # Check if cache is recent enough (< 1 hour old)
            if time.time() - cache.scan_time < 3600:
                return [PluginMetadata(**p) for p in cache.plugins]

        # Perform scan
        all_paths = self.get_all_search_paths()
        found_plugins: list[PluginMetadata] = []
        cached_map: dict[str, dict] = {}

        if cache and cache.plugins:
            cached_map = {p["path"]: p for p in cache.plugins}

        for search_dir in all_paths:
            if not search_dir.exists():
                continue
            found_plugins.extend(
                self._scan_directory(search_dir, cached_map)
            )

        # Also try CLI scan for metadata
        cli_plugins = self._scanner.scan()
        cli_map = {p.path: p for p in cli_plugins}

        # Merge CLI metadata
        for plugin in found_plugins:
            if plugin.path in cli_map:
                cli_info = cli_map[plugin.path]
                if cli_info.manufacturer:
                    plugin.manufacturer = cli_info.manufacturer
                if cli_info.category:
                    plugin.category = cli_info.category
                if cli_info.is_instrument:
                    plugin.is_instrument = True
                if cli_info.num_params > 0:
                    plugin.num_params = cli_info.num_params

        # Update cache
        self._save_cache(found_plugins)

        return found_plugins

    def _scan_directory(
        self,
        directory: Path,
        cached_map: dict[str, dict],
    ) -> list[PluginMetadata]:
        """Scan a single directory for VST3 plugins."""
        results: list[PluginMetadata] = []

        try:
            for item in directory.rglob("*.vst3"):
                if not item.is_dir() and not item.is_file():
                    continue

                abs_path = str(item.resolve())
                metadata = self._get_plugin_metadata(abs_path, cached_map)
                if metadata is not None:
                    results.append(metadata)
        except (PermissionError, OSError):
            pass

        return results

    def _get_plugin_metadata(
        self,
        path: str,
        cached_map: dict[str, dict],
    ) -> Optional[PluginMetadata]:
        """Get metadata for a single plugin, using cache if available."""
        p = Path(path)

        if not p.exists():
            return None

        # Get file stats
        try:
            stat_info = p.stat()
            file_size = stat_info.st_size
            last_modified = stat_info.st_mtime
        except OSError:
            file_size = 0
            last_modified = 0.0

        # Check cache (incremental: skip if unchanged)
        if path in cached_map:
            cached = cached_map[path]
            if abs(cached.get("last_modified", 0) - last_modified) < 1.0:
                # File unchanged, use cached data
                return PluginMetadata(**cached)

        # Build metadata from filesystem
        metadata = PluginMetadata(
            name=p.stem,
            path=path,
            file_size=file_size,
            last_modified=last_modified,
            scan_time=time.time(),
        )

        # Try to compute checksum for small files
        if file_size < 100_000_000:  # < 100MB
            metadata.checksum = self._compute_checksum(path)

        return metadata

    @staticmethod
    def _compute_checksum(path: str, block_size: int = 8192) -> str:
        """Compute MD5 checksum of a file."""
        hasher = hashlib.md5()
        try:
            with open(path, "rb") as f:
                while True:
                    block = f.read(block_size)
                    if not block:
                        break
                    hasher.update(block)
        except (IOError, OSError):
            return ""
        return hasher.hexdigest()

    # ── AudioUnit Scan (macOS) ─────────────────────────────────────────────

    def scan_audio_units(self) -> list[PluginMetadata]:
        """
        Scan for AudioUnit plugins on macOS.

        Returns:
            List of PluginMetadata for found AU plugins.
        """
        au_paths = self.get_au_search_paths()
        results: list[PluginMetadata] = []

        for search_dir in au_paths:
            if not search_dir.exists():
                continue
            try:
                for item in search_dir.rglob("*.component"):
                    abs_path = str(item.resolve())
                    stat_info = item.stat()
                    results.append(PluginMetadata(
                        name=item.stem,
                        path=abs_path,
                        category="AudioUnit",
                        file_size=stat_info.st_size,
                        last_modified=stat_info.st_mtime,
                        scan_time=time.time(),
                    ))
            except (PermissionError, OSError):
                pass

        return results

    # ── Cache Management ───────────────────────────────────────────────────

    def _load_cache(self) -> Optional[ScanCache]:
        """Load scan cache from disk."""
        if not self._cache_path.exists():
            return None

        try:
            with open(self._cache_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            return ScanCache(
                version=data.get("version", 1),
                scan_time=data.get("scan_time", 0.0),
                plugins=data.get("plugins", []),
            )
        except (json.JSONDecodeError, IOError, OSError):
            return None

    def _save_cache(self, plugins: list[PluginMetadata]) -> None:
        """Save scan cache to disk."""
        self._cache_dir.mkdir(parents=True, exist_ok=True)

        cache_data = {
            "version": 2,
            "scan_time": time.time(),
            "plugins": [asdict(p) for p in plugins],
        }

        try:
            with open(self._cache_path, "w", encoding="utf-8") as f:
                json.dump(cache_data, f, indent=2)
        except (IOError, OSError):
            pass

    def clear_cache(self) -> None:
        """Clear the scan cache."""
        if self._cache_path.exists():
            try:
                self._cache_path.unlink()
            except OSError:
                pass

    def get_cache_info(self) -> Optional[dict]:
        """Get information about the scan cache."""
        cache = self._load_cache()
        if cache is None:
            return None
        return {
            "version": cache.version,
            "scan_time": cache.scan_time,
            "num_plugins": len(cache.plugins),
            "cache_path": str(self._cache_path),
        }
