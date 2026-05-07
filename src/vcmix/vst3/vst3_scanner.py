"""
vst3_scanner.py — Scan system VST3 plugin directories.

Discovers installed VST3 plugins by:
1. Calling vst3_host list CLI (if available)
2. Fallback: scanning standard VST3 directories with file system glob

Returns structured VST3PluginInfo for each found plugin.
"""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass
class VST3PluginInfo:
    """Information about a discovered VST3 plugin."""
    name: str
    path: str                        # absolute path to .vst3 bundle
    manufacturer: str = ""
    category: str = ""
    is_instrument: bool = False
    num_params: int = 0
    source: str = "unknown"          # "cli" or "filesystem"


# ── Standard VST3 search paths per OS ──────────────────────────────────────

def _get_default_search_paths() -> list[Path]:
    """Return OS-specific VST3 plugin search directories."""
    paths: list[Path] = []
    home = Path.home()

    # Common paths (Linux)
    paths.extend([
        Path("/usr/lib/vst3"),
        Path("/usr/local/lib/vst3"),
        home / ".vst3",
    ])

    # macOS
    paths.extend([
        Path("/Library/Audio/Plug-Ins/VST3"),
        home / "Library" / "Audio" / "Plug-Ins" / "VST3",
    ])

    # Windows
    pf = os.environ.get("PROGRAMFILES", "C:\\Program Files")
    paths.extend([
        Path(pf) / "Common Files" / "VST3",
    ])

    return paths


class VST3Scanner:
    """
    Scanner for system VST3 plugins.

    Usage:
        scanner = VST3Scanner()
        plugins = scanner.scan()
        for p in plugins:
            print(f"{p.name} @ {p.path}")
    """

    def __init__(
        self,
        cli_path: str | None = None,
        extra_paths: list[str] | None = None,
    ) -> None:
        """
        Args:
            cli_path: Path to vst3_host binary. If None, auto-detect.
            extra_paths: Additional VST3 search directories.
        """
        self.cli_path = cli_path or self._find_cli()
        self.extra_paths = [Path(p) for p in (extra_paths or [])]

    @staticmethod
    def _find_cli() -> str | None:
        """Find vst3_host CLI on PATH."""
        import shutil
        found = shutil.which("vst3_host")
        return found

    def scan(self) -> list[VST3PluginInfo]:
        """
        Scan for VST3 plugins.

        Tries CLI scan first, falls back to filesystem scan.
        """
        # Try CLI-based scan
        if self.cli_path and Path(self.cli_path).exists():
            cli_results = self._scan_via_cli()
            if cli_results:
                return cli_results

        # Fallback: filesystem scan
        return self._scan_filesystem()

    def _scan_via_cli(self) -> list[VST3PluginInfo]:
        """Scan using vst3_host list CLI."""
        try:
            result = subprocess.run(
                [self.cli_path, "list"],
                capture_output=True,
                text=True,
                timeout=30,
            )
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            return []

        if result.returncode != 0:
            return []

        plugins: list[VST3PluginInfo] = []
        # Parse CLI output (structured text format)
        current: dict[str, str] = {}

        for line in result.stdout.splitlines():
            line = line.strip()
            if line.startswith("Name:"):
                if current.get("name"):
                    plugins.append(VST3PluginInfo(
                        name=current.get("name", ""),
                        path=current.get("path", ""),
                        manufacturer=current.get("mfr", ""),
                        isInstrument=current.get("type") == "Instrument",
                        source="cli",
                    ))
                current = {"name": line[5:].strip()}
            elif line.startswith("Path:"):
                current["path"] = line[5:].strip()
            elif line.startswith("Type:"):
                current["type"] = line[5:].strip()
            elif line.startswith("Mfr:"):
                current["mfr"] = line[4:].strip()

        # Don't forget the last one
        if current.get("name"):
            plugins.append(VST3PluginInfo(
                name=current.get("name", ""),
                path=current.get("path", ""),
                manufacturer=current.get("mfr", ""),
                isInstrument=current.get("type") == "Instrument",
                source="cli",
            ))

        return plugins

    def _scan_filesystem(self) -> list[VST3PluginInfo]:
        """Scan VST3 directories by filesystem glob."""
        plugins: list[VST3PluginInfo] = []
        search_paths = _get_default_search_paths() + self.extra_paths

        seen_paths: set[str] = set()

        for search_dir in search_paths:
            if not search_dir.exists():
                continue

            for vst3_file in search_dir.rglob("*.vst3"):
                abs_path = str(vst3_file.resolve())
                if abs_path in seen_paths:
                    continue
                seen_paths.add(abs_path)

                plugins.append(VST3PluginInfo(
                    name=vst3_file.stem,
                    path=abs_path,
                    source="filesystem",
                ))

        return plugins

    def get_plugin_info(self, plugin_path: str) -> VST3PluginInfo | None:
        """
        Get detailed info for a specific plugin by loading it.

        Calls vst3_host params --plugin to get parameter count and type.
        """
        if not self.cli_path or not Path(self.cli_path).exists():
            # Filesystem-only info
            p = Path(plugin_path)
            if p.exists():
                return VST3PluginInfo(
                    name=p.stem,
                    path=str(p.resolve()),
                    source="filesystem",
                )
            return None

        try:
            result = subprocess.run(
                [self.cli_path, "params", "--plugin", plugin_path],
                capture_output=True,
                text=True,
                timeout=30,
            )
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            return None

        if result.returncode != 0:
            return None

        try:
            info = json.loads(result.stdout)
            return VST3PluginInfo(
                name=info.get("plugin", Path(plugin_path).stem),
                path=plugin_path,
                is_instrument=info.get("is_instrument", False),
                num_params=info.get("num_params", 0),
                source="cli",
            )
        except json.JSONDecodeError:
            return None
