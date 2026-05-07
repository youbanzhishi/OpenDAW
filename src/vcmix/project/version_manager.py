"""
version_manager.py — Project version/snapshot management for VCMix (Phase 18).

Provides snapshot creation, listing, restoration, and diff comparison
for VCMix project YAML files. Snapshots are stored as timestamped copies
in the .snapshots/ directory within the project tree.

Architecture:
    - Snapshots stored in projects/.snapshots/{project_id}/
    - Each snapshot is a full YAML copy with metadata
    - Snapshot ID = timestamp + short hash
    - Diff compares YAML content semantically (tracks, effects, params)
    - Restore overwrites current project YAML with snapshot content
    - Backup is created before restore (safety net)

Usage:
    from vcmix.project.version_manager import ProjectVersionManager
    vm = ProjectVersionManager()
    sid = vm.create_snapshot("project.yaml", "v1 baseline")
    snapshots = vm.list_snapshots("proj_abc")
    vm.restore_snapshot("proj_abc", sid)
    diff = vm.diff_snapshots(sid1, sid2)
"""

from __future__ import annotations

import hashlib
import json
import shutil
import threading
import time
from pathlib import Path
from typing import Any

import yaml


class ProjectVersionManager:
    """Project version/snapshot manager.

    Manages project snapshots for version control, enabling
    users to save, list, compare, and restore project states.

    Args:
        base_dir: Base directory for snapshot storage.
            Defaults to projects/.snapshots/.
    """

    def __init__(self, base_dir: Path | str | None = None) -> None:
        if base_dir is None:
            self._base_dir = Path(__file__).resolve().parent.parent.parent.parent / "projects" / ".snapshots"
        else:
            self._base_dir = Path(base_dir)
        self._base_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    # ── Snapshot CRUD ──────────────────────────────────────────────────────

    def create_snapshot(
        self,
        project_yaml: str | Path,
        message: str = "",
    ) -> str:
        """Create a project snapshot.

        Copies the current project YAML into the snapshot directory
        with a unique ID and metadata.

        Args:
            project_yaml: Path to project YAML file.
            message: Human-readable snapshot description.

        Returns:
            Snapshot ID string.

        Raises:
            FileNotFoundError: If project YAML doesn't exist.
        """
        project_path = Path(project_yaml)
        if not project_path.exists():
            raise FileNotFoundError(f"Project not found: {project_yaml}")

        content = project_path.read_text(encoding="utf-8")
        content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()[:8]
        timestamp = int(time.time())
        # Add random suffix to avoid collisions when same content saved within same second
        import random
        nonce = f"{random.randint(0, 0xFFFF):04x}"
        snapshot_id = f"snap_{timestamp}_{content_hash}_{nonce}"

        # Determine project_id from filename
        project_name = project_path.stem
        project_id = hashlib.sha256(project_name.encode("utf-8")).hexdigest()[:12]

        snapshot_dir = self._base_dir / project_id
        snapshot_dir.mkdir(parents=True, exist_ok=True)

        # Save snapshot YAML
        snapshot_file = snapshot_dir / f"{snapshot_id}.yaml"
        snapshot_file.write_text(content, encoding="utf-8")

        # Save metadata
        metadata = {
            "snapshot_id": snapshot_id,
            "project_id": project_id,
            "project_name": project_name,
            "message": message,
            "timestamp": timestamp,
            "content_hash": content_hash,
            "created_at": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(timestamp)),
        }
        meta_file = snapshot_dir / f"{snapshot_id}.meta.yaml"
        meta_file.write_text(
            yaml.dump(metadata, default_flow_style=False, allow_unicode=True),
            encoding="utf-8",
        )

        return snapshot_id

    def list_snapshots(self, project_id: str) -> list[dict[str, Any]]:
        """List all snapshots for a project.

        Args:
            project_id: Project identifier.

        Returns:
            List of snapshot metadata dicts, sorted by timestamp (newest first).
        """
        snapshot_dir = self._base_dir / project_id
        if not snapshot_dir.exists():
            return []

        snapshots = []
        for meta_file in snapshot_dir.glob("*.meta.yaml"):
            try:
                content = meta_file.read_text(encoding="utf-8")
                meta = yaml.safe_load(content)
                if isinstance(meta, dict):
                    snapshots.append(meta)
            except Exception:
                continue

        # Sort by timestamp, newest first
        snapshots.sort(key=lambda s: s.get("timestamp", 0), reverse=True)
        return snapshots

    def restore_snapshot(
        self,
        project_id: str,
        snapshot_id: str,
        projects_dir: Path | str | None = None,
    ) -> str:
        """Restore a project to a specific snapshot.

        Creates a backup of the current project before overwriting.

        Args:
            project_id: Project identifier.
            snapshot_id: Snapshot to restore.
            projects_dir: Directory containing project YAML files.
                Defaults to the projects/ directory.

        Returns:
            Path to the restored project file.

        Raises:
            FileNotFoundError: If snapshot or project not found.
        """
        snapshot_dir = self._base_dir / project_id
        snapshot_file = snapshot_dir / f"{snapshot_id}.yaml"

        if not snapshot_file.exists():
            raise FileNotFoundError(f"Snapshot not found: {snapshot_id}")

        # Find the project file
        if projects_dir is None:
            projects_dir = Path(__file__).resolve().parent.parent.parent.parent / "projects"
        else:
            projects_dir = Path(projects_dir)

        # Find project by ID
        project_file = self._find_project_file(project_id, projects_dir)
        if project_file is None:
            raise FileNotFoundError(f"Project file not found for ID: {project_id}")

        # Backup current project before restore
        backup = project_file.with_suffix(".yaml.bak")
        shutil.copy2(str(project_file), str(backup))

        # Restore from snapshot
        snapshot_content = snapshot_file.read_text(encoding="utf-8")
        project_file.write_text(snapshot_content, encoding="utf-8")

        return str(project_file)

    def diff_snapshots(
        self,
        snapshot_id_1: str,
        snapshot_id_2: str,
    ) -> dict[str, Any]:
        """Compare two snapshots and return the differences.

        Performs semantic comparison of project YAML content,
        identifying changes in tracks, effects, and parameters.

        Args:
            snapshot_id_1: First snapshot ID.
            snapshot_id_2: Second snapshot ID.

        Returns:
            Dict with diff details:
                - added_tracks: list of track names added
                - removed_tracks: list of track names removed
                - modified_tracks: dict of track_name -> changes
                - param_changes: list of parameter change descriptions

        Raises:
            FileNotFoundError: If either snapshot not found.
        """
        snap1 = self._load_snapshot_content(snapshot_id_1)
        snap2 = self._load_snapshot_content(snapshot_id_2)

        if snap1 is None:
            raise FileNotFoundError(f"Snapshot not found: {snapshot_id_1}")
        if snap2 is None:
            raise FileNotFoundError(f"Snapshot not found: {snapshot_id_2}")

        config1 = yaml.safe_load(snap1)
        config2 = yaml.safe_load(snap2)

        tracks1 = {t.get("name", f"track_{i}"): t for i, t in enumerate(config1.get("tracks", []))}
        tracks2 = {t.get("name", f"track_{i}"): t for i, t in enumerate(config2.get("tracks", []))}

        names1 = set(tracks1.keys())
        names2 = set(tracks2.keys())

        added_tracks = sorted(names2 - names1)
        removed_tracks = sorted(names1 - names2)
        modified_tracks: dict[str, dict[str, Any]] = {}
        param_changes: list[str] = []

        for name in names1 & names2:
            changes = self._diff_track(tracks1[name], tracks2[name])
            if changes:
                modified_tracks[name] = changes
                for key, (old_val, new_val) in changes.items():
                    param_changes.append(
                        f"{name}.{key}: {old_val} -> {new_val}"
                    )

        # Compare top-level settings
        top_level_changes: dict[str, Any] = {}
        for key in ["bpm", "sample_rate", "name"]:
            v1 = config1.get(key)
            v2 = config2.get(key)
            if v1 != v2:
                top_level_changes[key] = (v1, v2)
                param_changes.append(f"{key}: {v1} -> {v2}")

        return {
            "snapshot_1": snapshot_id_1,
            "snapshot_2": snapshot_id_2,
            "added_tracks": added_tracks,
            "removed_tracks": removed_tracks,
            "modified_tracks": modified_tracks,
            "top_level_changes": top_level_changes,
            "param_changes": param_changes,
            "summary": (
                f"+{len(added_tracks)} tracks, "
                f"-{len(removed_tracks)} tracks, "
                f"~{len(modified_tracks)} modified, "
                f"{len(param_changes)} param changes"
            ),
        }

    # ── Internal helpers ───────────────────────────────────────────────────

    def _load_snapshot_content(self, snapshot_id: str) -> str | None:
        """Load a snapshot's YAML content by searching all project dirs."""
        for project_dir in self._base_dir.iterdir():
            if not project_dir.is_dir():
                continue
            snapshot_file = project_dir / f"{snapshot_id}.yaml"
            if snapshot_file.exists():
                return snapshot_file.read_text(encoding="utf-8")
        return None

    def _find_project_file(self, project_id: str, projects_dir: Path) -> Path | None:
        """Find a project YAML file by project ID."""
        for filepath in projects_dir.glob("*.yaml"):
            name = filepath.stem
            pid = hashlib.sha256(name.encode("utf-8")).hexdigest()[:12]
            if pid == project_id:
                return filepath
        return None

    @staticmethod
    def _diff_track(track1: dict, track2: dict) -> dict[str, tuple[Any, Any]]:
        """Compare two track configs and return differences."""
        changes: dict[str, tuple[Any, Any]] = {}

        # Compare scalar fields
        scalar_keys = ["file", "volume", "mute", "solo", "pan", "type"]
        for key in scalar_keys:
            v1 = track1.get(key)
            v2 = track2.get(key)
            if v1 != v2:
                changes[key] = (v1, v2)

        # Compare effects
        fx1 = track1.get("effects", [])
        fx2 = track2.get("effects", [])

        if len(fx1) != len(fx2):
            changes["effects_count"] = (len(fx1), len(fx2))
        else:
            for i, (e1, e2) in enumerate(zip(fx1, fx2)):
                if e1 != e2:
                    changes[f"effects[{i}]"] = (e1, e2)

        # Compare sends
        s1 = track1.get("sends", {})
        s2 = track2.get("sends", {})
        if s1 != s2:
            changes["sends"] = (s1, s2)

        return changes

    def get_snapshot_path(self, project_id: str, snapshot_id: str) -> Path | None:
        """Get the file path for a snapshot.

        Args:
            project_id: Project identifier.
            snapshot_id: Snapshot identifier.

        Returns:
            Path to the snapshot YAML file, or None if not found.
        """
        snapshot_file = self._base_dir / project_id / f"{snapshot_id}.yaml"
        if snapshot_file.exists():
            return snapshot_file
        return None

    def delete_snapshot(self, project_id: str, snapshot_id: str) -> bool:
        """Delete a snapshot.

        Args:
            project_id: Project identifier.
            snapshot_id: Snapshot identifier.

        Returns:
            True if deleted, False if not found.
        """
        snapshot_dir = self._base_dir / project_id
        snapshot_file = snapshot_dir / f"{snapshot_id}.yaml"
        meta_file = snapshot_dir / f"{snapshot_id}.meta.yaml"

        if not snapshot_file.exists():
            return False

        # Move to recycle bin instead of deleting
        recycle_dir = self._base_dir / ".recycle"
        recycle_dir.mkdir(parents=True, exist_ok=True)
        date_prefix = time.strftime("%Y%m%d")

        for f in [snapshot_file, meta_file]:
            if f.exists():
                dest = recycle_dir / f"{date_prefix}_{f.name}"
                if dest.exists():
                    dest = recycle_dir / f"{date_prefix}_{f.stem}_{int(time.time())}{f.suffix}"
                shutil.move(str(f), str(dest))

        return True
