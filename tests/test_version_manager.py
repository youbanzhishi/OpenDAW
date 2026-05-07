"""
test_version_manager.py — Tests for project version management (Phase 18).

Tests cover:
    - ProjectVersionManager initialization
    - Snapshot creation
    - Snapshot listing
    - Snapshot restoration
    - Snapshot diff comparison
    - Snapshot deletion
    - Edge cases (missing files, empty projects, etc.)
"""

from __future__ import annotations

import hashlib
import shutil
import time
from pathlib import Path

import pytest
import yaml

from vcmix.project.version_manager import ProjectVersionManager


# ── Fixtures ──────────────────────────────────────────────────────────────


@pytest.fixture
def vm(tmp_path):
    """Create a ProjectVersionManager with a temp snapshot dir."""
    snapshot_dir = tmp_path / ".snapshots"
    return ProjectVersionManager(base_dir=snapshot_dir)


@pytest.fixture
def project_yaml(tmp_path):
    """Create a minimal project YAML file."""
    config = {
        "name": "test_project",
        "bpm": 120,
        "sample_rate": 44100,
        "tracks": [
            {
                "name": "vocals",
                "file": "vocals.wav",
                "volume": 0.8,
                "effects": [
                    {"name": "VC-Compressor", "params": {"threshold": -20, "ratio": 4}},
                ],
            },
            {
                "name": "drums",
                "file": "drums.wav",
                "volume": 0.6,
                "effects": [],
            },
        ],
        "master": {"levels": {"vocals": 0.8, "drums": 0.6}},
    }
    yaml_path = tmp_path / "test_project.yaml"
    yaml_path.write_text(
        yaml.dump(config, default_flow_style=False, allow_unicode=True),
        encoding="utf-8",
    )
    return yaml_path


@pytest.fixture
def project_id(project_yaml):
    """Calculate project ID from project name."""
    name = project_yaml.stem
    return hashlib.sha256(name.encode("utf-8")).hexdigest()[:12]


# ── Initialization Tests ──────────────────────────────────────────────────


class TestVersionManagerInit:
    """Tests for ProjectVersionManager initialization."""

    def test_creates_snapshot_dir(self, tmp_path):
        snapshot_dir = tmp_path / "new_snapshots"
        vm = ProjectVersionManager(base_dir=snapshot_dir)
        assert snapshot_dir.exists()

    def test_default_base_dir(self):
        vm = ProjectVersionManager()
        assert vm._base_dir is not None


# ── Snapshot Creation Tests ───────────────────────────────────────────────


class TestSnapshotCreation:
    """Tests for creating snapshots."""

    def test_create_snapshot(self, vm, project_yaml):
        snapshot_id = vm.create_snapshot(str(project_yaml), "v1 baseline")
        assert snapshot_id.startswith("snap_")
        assert len(snapshot_id) > 10

    def test_create_snapshot_without_message(self, vm, project_yaml):
        snapshot_id = vm.create_snapshot(str(project_yaml))
        assert snapshot_id.startswith("snap_")

    def test_create_snapshot_stores_yaml(self, vm, project_yaml, project_id):
        snapshot_id = vm.create_snapshot(str(project_yaml), "test")
        # Verify the snapshot file exists
        snapshot_file = vm._base_dir / project_id / f"{snapshot_id}.yaml"
        assert snapshot_file.exists()

    def test_create_snapshot_stores_metadata(self, vm, project_yaml, project_id):
        snapshot_id = vm.create_snapshot(str(project_yaml), "test message")
        meta_file = vm._base_dir / project_id / f"{snapshot_id}.meta.yaml"
        assert meta_file.exists()
        meta = yaml.safe_load(meta_file.read_text(encoding="utf-8"))
        assert meta["snapshot_id"] == snapshot_id
        assert meta["message"] == "test message"
        assert meta["project_name"] == "test_project"

    def test_create_snapshot_missing_project(self, vm):
        with pytest.raises(FileNotFoundError):
            vm.create_snapshot("/nonexistent/project.yaml")

    def test_create_multiple_snapshots(self, vm, project_yaml, project_id):
        id1 = vm.create_snapshot(str(project_yaml), "v1")
        time.sleep(0.01)  # Ensure different timestamp
        id2 = vm.create_snapshot(str(project_yaml), "v2")
        assert id1 != id2

    def test_snapshot_id_includes_hash(self, vm, project_yaml):
        snapshot_id = vm.create_snapshot(str(project_yaml), "test")
        # ID should contain a hash component
        parts = snapshot_id.split("_")
        assert len(parts) >= 3  # snap_timestamp_hash


# ── Snapshot Listing Tests ────────────────────────────────────────────────


class TestSnapshotListing:
    """Tests for listing snapshots."""

    def test_list_snapshots_empty(self, vm, project_id):
        snapshots = vm.list_snapshots(project_id)
        assert snapshots == []

    def test_list_snapshots(self, vm, project_yaml, project_id):
        vm.create_snapshot(str(project_yaml), "v1")
        vm.create_snapshot(str(project_yaml), "v2")
        snapshots = vm.list_snapshots(project_id)
        assert len(snapshots) == 2

    def test_list_snapshots_sorted_newest_first(self, vm, project_yaml, project_id):
        id1 = vm.create_snapshot(str(project_yaml), "v1")
        time.sleep(1.1)  # Ensure different timestamp (1s granularity)
        id2 = vm.create_snapshot(str(project_yaml), "v2")
        snapshots = vm.list_snapshots(project_id)
        assert len(snapshots) == 2
        assert snapshots[0]["timestamp"] >= snapshots[1]["timestamp"]  # Newest first

    def test_list_snapshots_includes_metadata(self, vm, project_yaml, project_id):
        vm.create_snapshot(str(project_yaml), "test msg")
        snapshots = vm.list_snapshots(project_id)
        assert len(snapshots) == 1
        snap = snapshots[0]
        assert "snapshot_id" in snap
        assert "message" in snap
        assert "timestamp" in snap
        assert "created_at" in snap
        assert "project_name" in snap

    def test_list_snapshots_nonexistent_project(self, vm):
        snapshots = vm.list_snapshots("nonexistent_id")
        assert snapshots == []


# ── Snapshot Restoration Tests ────────────────────────────────────────────


class TestSnapshotRestoration:
    """Tests for restoring snapshots."""

    def test_restore_snapshot(self, vm, project_yaml, project_id, tmp_path):
        # Create snapshot
        snapshot_id = vm.create_snapshot(str(project_yaml), "v1")

        # Modify project
        config = yaml.safe_load(project_yaml.read_text(encoding="utf-8"))
        config["bpm"] = 140
        project_yaml.write_text(
            yaml.dump(config, default_flow_style=False, allow_unicode=True),
            encoding="utf-8",
        )

        # Restore
        result = vm.restore_snapshot(project_id, snapshot_id, projects_dir=tmp_path)
        assert Path(result).exists()

        # Verify content restored
        restored_config = yaml.safe_load(project_yaml.read_text(encoding="utf-8"))
        assert restored_config["bpm"] == 120  # Original value

    def test_restore_creates_backup(self, vm, project_yaml, project_id, tmp_path):
        snapshot_id = vm.create_snapshot(str(project_yaml), "v1")

        # Modify project
        config = yaml.safe_load(project_yaml.read_text(encoding="utf-8"))
        config["bpm"] = 140
        project_yaml.write_text(
            yaml.dump(config, default_flow_style=False, allow_unicode=True),
            encoding="utf-8",
        )

        # Restore should create backup
        vm.restore_snapshot(project_id, snapshot_id, projects_dir=tmp_path)
        backup = project_yaml.with_suffix(".yaml.bak")
        assert backup.exists()

    def test_restore_missing_snapshot(self, vm, project_id, tmp_path):
        with pytest.raises(FileNotFoundError):
            vm.restore_snapshot(project_id, "nonexistent_snap", projects_dir=tmp_path)


# ── Snapshot Diff Tests ───────────────────────────────────────────────────


class TestSnapshotDiff:
    """Tests for comparing snapshots."""

    def test_diff_identical_snapshots(self, vm, project_yaml):
        id1 = vm.create_snapshot(str(project_yaml), "v1")
        id2 = vm.create_snapshot(str(project_yaml), "v2")
        diff = vm.diff_snapshots(id1, id2)
        assert diff["added_tracks"] == []
        assert diff["removed_tracks"] == []
        assert diff["modified_tracks"] == {}

    def test_diff_added_track(self, vm, project_yaml, project_id):
        # Create first snapshot
        id1 = vm.create_snapshot(str(project_yaml), "v1")

        # Add a track
        config = yaml.safe_load(project_yaml.read_text(encoding="utf-8"))
        config["tracks"].append({"name": "bass", "file": "bass.wav", "volume": 0.7})
        project_yaml.write_text(
            yaml.dump(config, default_flow_style=False, allow_unicode=True),
            encoding="utf-8",
        )

        # Create second snapshot
        id2 = vm.create_snapshot(str(project_yaml), "v2")

        diff = vm.diff_snapshots(id1, id2)
        assert "bass" in diff["added_tracks"]

    def test_diff_removed_track(self, vm, project_yaml):
        # Create first snapshot with full project
        id1 = vm.create_snapshot(str(project_yaml), "v1")

        # Remove a track
        config = yaml.safe_load(project_yaml.read_text(encoding="utf-8"))
        config["tracks"] = [t for t in config["tracks"] if t["name"] != "drums"]
        project_yaml.write_text(
            yaml.dump(config, default_flow_style=False, allow_unicode=True),
            encoding="utf-8",
        )

        id2 = vm.create_snapshot(str(project_yaml), "v2")

        diff = vm.diff_snapshots(id1, id2)
        assert "drums" in diff["removed_tracks"]

    def test_diff_modified_track(self, vm, project_yaml):
        id1 = vm.create_snapshot(str(project_yaml), "v1")

        # Modify a track's volume
        config = yaml.safe_load(project_yaml.read_text(encoding="utf-8"))
        for t in config["tracks"]:
            if t["name"] == "vocals":
                t["volume"] = 0.5  # Changed from 0.8
        project_yaml.write_text(
            yaml.dump(config, default_flow_style=False, allow_unicode=True),
            encoding="utf-8",
        )

        id2 = vm.create_snapshot(str(project_yaml), "v2")

        diff = vm.diff_snapshots(id1, id2)
        assert "vocals" in diff["modified_tracks"]
        assert diff["modified_tracks"]["vocals"]["volume"] == (0.8, 0.5)

    def test_diff_top_level_changes(self, vm, project_yaml):
        id1 = vm.create_snapshot(str(project_yaml), "v1")

        # Change BPM
        config = yaml.safe_load(project_yaml.read_text(encoding="utf-8"))
        config["bpm"] = 140
        project_yaml.write_text(
            yaml.dump(config, default_flow_style=False, allow_unicode=True),
            encoding="utf-8",
        )

        id2 = vm.create_snapshot(str(project_yaml), "v2")

        diff = vm.diff_snapshots(id1, id2)
        assert "bpm" in diff["top_level_changes"]
        assert diff["top_level_changes"]["bpm"] == (120, 140)

    def test_diff_param_changes_list(self, vm, project_yaml):
        id1 = vm.create_snapshot(str(project_yaml), "v1")

        config = yaml.safe_load(project_yaml.read_text(encoding="utf-8"))
        config["bpm"] = 140
        for t in config["tracks"]:
            if t["name"] == "vocals":
                t["volume"] = 0.5
        project_yaml.write_text(
            yaml.dump(config, default_flow_style=False, allow_unicode=True),
            encoding="utf-8",
        )

        id2 = vm.create_snapshot(str(project_yaml), "v2")

        diff = vm.diff_snapshots(id1, id2)
        assert len(diff["param_changes"]) >= 1
        assert any("bpm" in pc for pc in diff["param_changes"])

    def test_diff_summary(self, vm, project_yaml):
        id1 = vm.create_snapshot(str(project_yaml), "v1")

        config = yaml.safe_load(project_yaml.read_text(encoding="utf-8"))
        config["tracks"].append({"name": "bass", "file": "bass.wav"})
        project_yaml.write_text(
            yaml.dump(config, default_flow_style=False, allow_unicode=True),
            encoding="utf-8",
        )

        id2 = vm.create_snapshot(str(project_yaml), "v2")

        diff = vm.diff_snapshots(id1, id2)
        assert "+" in diff["summary"]
        assert "1 tracks" in diff["summary"]

    def test_diff_missing_snapshot(self, vm):
        with pytest.raises(FileNotFoundError):
            vm.diff_snapshots("nonexistent_1", "nonexistent_2")


# ── Snapshot Deletion Tests ───────────────────────────────────────────────


class TestSnapshotDeletion:
    """Tests for deleting snapshots."""

    def test_delete_snapshot(self, vm, project_yaml, project_id):
        snapshot_id = vm.create_snapshot(str(project_yaml), "v1")
        result = vm.delete_snapshot(project_id, snapshot_id)
        assert result is True

    def test_delete_snapshot_moves_to_recycle(self, vm, project_yaml, project_id):
        snapshot_id = vm.create_snapshot(str(project_yaml), "v1")
        vm.delete_snapshot(project_id, snapshot_id)
        # Check recycle bin
        recycle_dir = vm._base_dir / ".recycle"
        assert recycle_dir.exists()

    def test_delete_nonexistent_snapshot(self, vm, project_id):
        result = vm.delete_snapshot(project_id, "nonexistent_snap")
        assert result is False


# ── Helper Method Tests ──────────────────────────────────────────────────


class TestHelperMethods:
    """Tests for helper/utility methods."""

    def test_get_snapshot_path(self, vm, project_yaml, project_id):
        snapshot_id = vm.create_snapshot(str(project_yaml), "v1")
        path = vm.get_snapshot_path(project_id, snapshot_id)
        assert path is not None
        assert path.exists()

    def test_get_snapshot_path_nonexistent(self, vm, project_id):
        path = vm.get_snapshot_path(project_id, "nonexistent")
        assert path is None

    def test_diff_track_identical(self):
        track = {"name": "vocals", "volume": 0.8}
        diff = ProjectVersionManager._diff_track(track, track)
        assert diff == {}

    def test_diff_track_volume_change(self):
        t1 = {"name": "vocals", "volume": 0.8}
        t2 = {"name": "vocals", "volume": 0.5}
        diff = ProjectVersionManager._diff_track(t1, t2)
        assert "volume" in diff
        assert diff["volume"] == (0.8, 0.5)

    def test_diff_track_effects_count_change(self):
        t1 = {"name": "vocals", "effects": [{"name": "comp"}]}
        t2 = {"name": "vocals", "effects": [{"name": "comp"}, {"name": "eq"}]}
        diff = ProjectVersionManager._diff_track(t1, t2)
        assert "effects_count" in diff
        assert diff["effects_count"] == (1, 2)

    def test_diff_track_sends_change(self):
        t1 = {"name": "vocals", "sends": {"reverb": 0.2}}
        t2 = {"name": "vocals", "sends": {"reverb": 0.3, "delay": 0.1}}
        diff = ProjectVersionManager._diff_track(t1, t2)
        assert "sends" in diff
