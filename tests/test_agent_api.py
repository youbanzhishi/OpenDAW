"""
test_agent_api.py — Tests for VCMix AI Agent API (Phase 11).

Tests all REST API endpoints and WebSocket functionality for
the AI Agent interface.

Coverage:
    - Project CRUD (create, read, update, delete, list)
    - Track operations (add, update, delete)
    - Effect operations (add, update, delete)
    - Rendering control (trigger, status)
    - Audio analysis
    - AI mixing suggestions
    - AI mastering suggestions
    - WebSocket render progress
    - WebSocket AI decisions
    - Project manager internals
    - Analysis service
    - AI engine
"""

from __future__ import annotations

import json
import shutil
import tempfile
import uuid
from pathlib import Path

import pytest

# ── Test Client Setup ────────────────────────────────────────────────────

try:
    from fastapi.testclient import TestClient
    from vcmix.web.app import app
    HAS_FASTAPI = True
except ImportError:
    HAS_FASTAPI = False

pytestmark = pytest.mark.skipif(
    not HAS_FASTAPI,
    reason="FastAPI not installed; install with: pip install fastapi uvicorn websockets"
)


def _unique_name(prefix: str = "proj") -> str:
    """Generate a unique project name."""
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


@pytest.fixture
def client():
    """Create a FastAPI test client."""
    return TestClient(app)


@pytest.fixture
def sample_yaml():
    """Return a minimal valid YAML project string."""
    return """\
name: TestProject
bpm: 120
sample_rate: 44100

tracks:
  - name: vocal
    file: vocal.wav
    effects:
      - name: vc-gain
        params:
          gain: 0
      - name: vc-comp
        params:
          threshold: -20
          ratio: 3

master:
  levels:
    vocal: 0.8
  effects: []
  output: output.wav
"""


@pytest.fixture
def sample_json():
    """Return a minimal valid project config as JSON dict."""
    return {
        "name": "JsonProject",
        "bpm": 128,
        "sample_rate": 44100,
        "tracks": [
            {
                "name": "drums",
                "file": "drums.wav",
                "effects": [
                    {"name": "vc-eq", "params": {"low_cut_hz": 80}},
                ],
            }
        ],
        "master": {
            "levels": {"drums": 0.7},
            "effects": [],
            "output": "output.wav",
        },
    }


@pytest.fixture
def created_project(client, sample_yaml):
    """Create a project with a unique name and return its ID."""
    name = _unique_name("test")
    resp = client.post("/api/v1/projects", json={
        "name": name,
        "yaml_content": sample_yaml,
    })
    assert resp.status_code == 201, f"Failed to create project: {resp.json()}"
    return resp.json()["id"]


# ══════════════════════════════════════════════════════════════════════════
# Project CRUD Tests
# ══════════════════════════════════════════════════════════════════════════

class TestProjectCreate:
    def test_create_project_from_yaml(self, client, sample_yaml):
        resp = client.post("/api/v1/projects", json={
            "name": _unique_name("yaml"),
            "yaml_content": sample_yaml,
        })
        assert resp.status_code == 201
        data = resp.json()
        assert "id" in data
        assert data["status"] == "created"
        assert "project" in data

    def test_create_project_from_json(self, client, sample_json):
        resp = client.post("/api/v1/projects", json={
            "name": _unique_name("json"),
            "json_data": sample_json,
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["project"]["config"]["name"] == "JsonProject"

    def test_create_project_no_content(self, client):
        resp = client.post("/api/v1/projects", json={
            "name": _unique_name("empty"),
        })
        assert resp.status_code in (400, 422)

    def test_create_duplicate_project(self, client, sample_yaml):
        name = _unique_name("dup")
        client.post("/api/v1/projects", json={
            "name": name,
            "yaml_content": sample_yaml,
        })
        resp = client.post("/api/v1/projects", json={
            "name": name,
            "yaml_content": sample_yaml,
        })
        assert resp.status_code == 409

    def test_create_project_invalid_yaml(self, client):
        resp = client.post("/api/v1/projects", json={
            "name": _unique_name("bad"),
            "yaml_content": "not: valid\nyaml: [",
        })
        assert resp.status_code in (400, 409, 422)

    def test_create_project_name_required(self, client):
        resp = client.post("/api/v1/projects", json={
            "yaml_content": "name: test",
        })
        assert resp.status_code == 422


class TestProjectRead:
    def test_get_project(self, client, created_project):
        resp = client.get(f"/api/v1/projects/{created_project}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == created_project
        assert "yaml_content" in data
        assert "config" in data

    def test_get_project_not_found(self, client):
        resp = client.get("/api/v1/projects/nonexistent1234")
        assert resp.status_code == 404

    def test_get_project_has_tracks(self, client, created_project):
        resp = client.get(f"/api/v1/projects/{created_project}")
        data = resp.json()
        config = data["config"]
        assert "tracks" in config
        assert len(config["tracks"]) == 1


class TestProjectUpdate:
    def test_update_project_yaml(self, client, created_project):
        new_yaml = """\
name: UpdatedProject
bpm: 140
sample_rate: 48000

tracks:
  - name: bass
    file: bass.wav
    effects: []

master:
  levels:
    bass: 0.9
  effects: []
  output: output.wav
"""
        resp = client.put(f"/api/v1/projects/{created_project}", json={
            "yaml_content": new_yaml,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "updated"
        assert data["project"]["config"]["name"] == "UpdatedProject"
        assert data["project"]["config"]["bpm"] == 140

    def test_update_project_json(self, client, created_project):
        resp = client.put(f"/api/v1/projects/{created_project}", json={
            "json_data": {
                "name": "JsonUpdated",
                "bpm": 100,
                "sample_rate": 44100,
                "tracks": [],
                "master": {"levels": {}, "effects": [], "output": "out.wav"},
            },
        })
        assert resp.status_code == 200
        assert resp.json()["project"]["config"]["name"] == "JsonUpdated"

    def test_update_project_not_found(self, client):
        resp = client.put("/api/v1/projects/nonexistent1234", json={
            "yaml_content": "name: test",
        })
        assert resp.status_code == 404

    def test_update_project_no_content(self, client, created_project):
        resp = client.put(f"/api/v1/projects/{created_project}", json={})
        assert resp.status_code == 400


class TestProjectDelete:
    def test_delete_project(self, client, sample_yaml):
        name = _unique_name("del")
        resp = client.post("/api/v1/projects", json={
            "name": name,
            "yaml_content": sample_yaml,
        })
        pid = resp.json()["id"]

        resp = client.delete(f"/api/v1/projects/{pid}")
        assert resp.status_code == 200
        assert resp.json()["status"] == "deleted"

        resp = client.get(f"/api/v1/projects/{pid}")
        assert resp.status_code == 404

    def test_delete_project_not_found(self, client):
        resp = client.delete("/api/v1/projects/nonexistent1234")
        assert resp.status_code == 404


class TestProjectList:
    def test_list_projects(self, client):
        resp = client.get("/api/v1/projects")
        assert resp.status_code == 200
        data = resp.json()
        assert "projects" in data
        assert "count" in data

    def test_list_projects_after_create(self, client, sample_yaml):
        client.post("/api/v1/projects", json={
            "name": _unique_name("list"),
            "yaml_content": sample_yaml,
        })
        resp = client.get("/api/v1/projects")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] >= 1

    def test_list_projects_has_fields(self, client, sample_yaml):
        client.post("/api/v1/projects", json={
            "name": _unique_name("fields"),
            "yaml_content": sample_yaml,
        })
        resp = client.get("/api/v1/projects")
        data = resp.json()
        if data["count"] > 0:
            project = data["projects"][0]
            assert "id" in project
            assert "name" in project


# ══════════════════════════════════════════════════════════════════════════
# Track Operations Tests
# ══════════════════════════════════════════════════════════════════════════

class TestTrackAdd:
    def test_add_track(self, client, created_project):
        resp = client.post(f"/api/v1/projects/{created_project}/tracks", json={
            "name": "bass",
            "file": "bass.wav",
            "type": "audio",
            "effects": [],
            "volume": 0.8,
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["status"] == "added"
        assert data["track"] == "bass"

    def test_add_track_with_effects(self, client, created_project):
        resp = client.post(f"/api/v1/projects/{created_project}/tracks", json={
            "name": "guitar",
            "file": "guitar.wav",
            "effects": [
                {"name": "vc-gain", "params": {"gain": 3}},
                {"name": "vc-reverb", "params": {"mix": 15}},
            ],
        })
        assert resp.status_code == 201

    def test_add_duplicate_track(self, client, created_project):
        # "vocal" already exists in sample_yaml
        resp = client.post(f"/api/v1/projects/{created_project}/tracks", json={
            "name": "vocal",
            "file": "vocal2.wav",
        })
        assert resp.status_code == 409

    def test_add_track_nonexistent_project(self, client):
        resp = client.post("/api/v1/projects/nonexistent1234/tracks", json={
            "name": "test",
            "file": "test.wav",
        })
        assert resp.status_code == 404


class TestTrackUpdate:
    def test_update_track_volume(self, client, created_project):
        resp = client.put(f"/api/v1/projects/{created_project}/tracks/vocal", json={
            "volume": 0.5,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "updated"

    def test_update_track_mute(self, client, created_project):
        resp = client.put(f"/api/v1/projects/{created_project}/tracks/vocal", json={
            "mute": True,
        })
        assert resp.status_code == 200

    def test_update_track_not_found(self, client, created_project):
        resp = client.put(f"/api/v1/projects/{created_project}/tracks/nonexistent", json={
            "volume": 0.5,
        })
        assert resp.status_code == 404

    def test_update_track_no_fields(self, client, created_project):
        resp = client.put(f"/api/v1/projects/{created_project}/tracks/vocal", json={})
        assert resp.status_code == 400


class TestTrackDelete:
    def test_delete_track(self, client, created_project):
        resp = client.delete(f"/api/v1/projects/{created_project}/tracks/vocal")
        assert resp.status_code == 200
        assert resp.json()["status"] == "deleted"

    def test_delete_track_not_found(self, client, created_project):
        resp = client.delete(f"/api/v1/projects/{created_project}/tracks/nonexistent")
        assert resp.status_code == 404

    def test_delete_track_removes_from_master_levels(self, client, created_project):
        resp = client.delete(f"/api/v1/projects/{created_project}/tracks/vocal")
        assert resp.status_code == 200
        project = resp.json()["project"]
        levels = project["config"].get("master", {}).get("levels", {})
        assert "vocal" not in levels


# ══════════════════════════════════════════════════════════════════════════
# Effect Operations Tests
# ══════════════════════════════════════════════════════════════════════════

class TestEffectAdd:
    def test_add_effect(self, client, created_project):
        resp = client.post(
            f"/api/v1/projects/{created_project}/tracks/vocal/effects",
            json={"name": "vc-reverb", "params": {"mix": 10, "room": 30}},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["status"] == "added"
        assert data["effect"] == "vc-reverb"

    def test_add_effect_track_not_found(self, client, created_project):
        resp = client.post(
            f"/api/v1/projects/{created_project}/tracks/nonexistent/effects",
            json={"name": "vc-gain", "params": {"gain": 0}},
        )
        assert resp.status_code == 404

    def test_add_effect_project_not_found(self, client):
        resp = client.post(
            "/api/v1/projects/nonexistent1234/tracks/vocal/effects",
            json={"name": "vc-gain", "params": {"gain": 0}},
        )
        assert resp.status_code == 404


class TestEffectUpdate:
    def test_update_effect_params(self, client, created_project):
        # vocal has vc-gain at index 0, vc-comp at index 1
        resp = client.put(
            f"/api/v1/projects/{created_project}/tracks/vocal/effects/0",
            json={"params": {"gain": 5}},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "updated"

    def test_update_effect_out_of_range(self, client, created_project):
        resp = client.put(
            f"/api/v1/projects/{created_project}/tracks/vocal/effects/99",
            json={"params": {"gain": 5}},
        )
        assert resp.status_code == 400

    def test_update_effect_track_not_found(self, client, created_project):
        resp = client.put(
            f"/api/v1/projects/{created_project}/tracks/nonexistent/effects/0",
            json={"params": {"gain": 5}},
        )
        assert resp.status_code == 404

    def test_update_negative_index(self, client, created_project):
        resp = client.put(
            f"/api/v1/projects/{created_project}/tracks/vocal/effects/-1",
            json={"params": {"gain": 5}},
        )
        assert resp.status_code == 400


class TestEffectDelete:
    def test_delete_effect(self, client, created_project):
        resp = client.delete(
            f"/api/v1/projects/{created_project}/tracks/vocal/effects/0",
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "deleted"

    def test_delete_effect_out_of_range(self, client, created_project):
        resp = client.delete(
            f"/api/v1/projects/{created_project}/tracks/vocal/effects/99",
        )
        assert resp.status_code == 400

    def test_delete_effect_track_not_found(self, client, created_project):
        resp = client.delete(
            f"/api/v1/projects/{created_project}/tracks/nonexistent/effects/0",
        )
        assert resp.status_code == 404


# ══════════════════════════════════════════════════════════════════════════
# Rendering Control Tests
# ══════════════════════════════════════════════════════════════════════════

class TestRenderControl:
    def test_trigger_render(self, client, created_project):
        resp = client.post(f"/api/v1/projects/{created_project}/render", json={
            "report": False,
            "auto_fix": False,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "job_id" in data
        assert data["status"] == "pending"
        assert data["project_id"] == created_project

    def test_trigger_render_not_found(self, client):
        resp = client.post("/api/v1/projects/nonexistent1234/render", json={})
        assert resp.status_code == 404

    def test_get_render_status(self, client, created_project):
        render_resp = client.post(f"/api/v1/projects/{created_project}/render", json={})
        assert render_resp.status_code == 200

        status_resp = client.get(f"/api/v1/projects/{created_project}/render/status")
        assert status_resp.status_code == 200
        data = status_resp.json()
        assert data["project_id"] == created_project
        assert data["status"] in ("pending", "running", "completed", "failed", "no_render_jobs")

    def test_get_render_status_no_jobs(self, client, sample_yaml):
        name = _unique_name("norender")
        resp = client.post("/api/v1/projects", json={
            "name": name,
            "yaml_content": sample_yaml,
        })
        pid = resp.json()["id"]

        status_resp = client.get(f"/api/v1/projects/{pid}/render/status")
        assert status_resp.status_code == 200
        assert status_resp.json()["status"] == "no_render_jobs"


# ══════════════════════════════════════════════════════════════════════════
# Audio Analysis Tests
# ══════════════════════════════════════════════════════════════════════════

class TestAnalysis:
    def test_get_analysis(self, client, created_project):
        resp = client.get(f"/api/v1/projects/{created_project}/analysis")
        assert resp.status_code == 200
        data = resp.json()
        assert "project_id" in data
        assert "analysis" in data
        analysis = data["analysis"]
        assert "tracks" in analysis
        assert "master" in analysis
        assert "project" in analysis

    def test_analysis_has_track_metrics(self, client, created_project):
        resp = client.get(f"/api/v1/projects/{created_project}/analysis")
        data = resp.json()
        tracks = data["analysis"]["tracks"]
        assert len(tracks) >= 1
        track = tracks[0]
        assert "name" in track
        assert "rms_db" in track
        assert "peak_db" in track

    def test_analysis_not_found(self, client):
        resp = client.get("/api/v1/projects/nonexistent1234/analysis")
        assert resp.status_code == 404


# ══════════════════════════════════════════════════════════════════════════
# AI Mixing Tests
# ══════════════════════════════════════════════════════════════════════════

class TestAIMix:
    def test_ai_mix_step_mode(self, client, created_project):
        resp = client.post(f"/api/v1/ai/mix/{created_project}", json={
            "mode": "step",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "suggestions" in data
        assert "decision_log" in data
        assert "summary" in data
        assert data["mode"] == "step"
        assert data["applied"] is False

    def test_ai_mix_one_click_mode(self, client, created_project):
        resp = client.post(f"/api/v1/ai/mix/{created_project}", json={
            "mode": "one_click",
            "apply": True,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "suggestions" in data
        assert "decision_log" in data

    def test_ai_mix_project_not_found(self, client):
        resp = client.post("/api/v1/ai/mix/nonexistent1234", json={
            "mode": "step",
        })
        assert resp.status_code == 404

    def test_ai_mix_generic(self, client):
        resp = client.post("/api/v1/ai/mix", json={
            "mode": "step",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "suggestions" in data

    def test_ai_mix_has_decision_log(self, client, created_project):
        resp = client.post(f"/api/v1/ai/mix/{created_project}", json={
            "mode": "step",
        })
        data = resp.json()
        log = data["decision_log"]
        assert len(log) > 0
        entry = log[0]
        assert "step" in entry
        assert "target" in entry
        assert "action" in entry
        assert "reason" in entry


class TestAIMaster:
    def test_ai_master_step_mode(self, client, created_project):
        resp = client.post(f"/api/v1/ai/master/{created_project}", json={
            "mode": "step",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "suggestions" in data
        assert "decision_log" in data
        assert "summary" in data

    def test_ai_master_one_click(self, client, created_project):
        resp = client.post(f"/api/v1/ai/master/{created_project}", json={
            "mode": "one_click",
            "apply": True,
        })
        assert resp.status_code == 200

    def test_ai_master_project_not_found(self, client):
        resp = client.post("/api/v1/ai/master/nonexistent1234", json={
            "mode": "step",
        })
        assert resp.status_code == 404

    def test_ai_master_generic(self, client):
        resp = client.post("/api/v1/ai/master", json={
            "mode": "step",
        })
        assert resp.status_code == 200

    def test_ai_master_suggestions_have_priority(self, client, created_project):
        resp = client.post(f"/api/v1/ai/master/{created_project}", json={
            "mode": "step",
        })
        data = resp.json()
        for s in data["suggestions"]:
            assert "priority" in s
            assert s["priority"] in (1, 2, 3)


# ══════════════════════════════════════════════════════════════════════════
# WebSocket Tests
# ══════════════════════════════════════════════════════════════════════════

class TestRenderWebSocket:
    def test_ws_render_connect(self, client, created_project):
        with client.websocket_connect(f"/api/v1/ws/render/{created_project}") as ws:
            data = ws.receive_json()
            assert data["type"] == "connected"
            assert data["project_id"] == created_project

    def test_ws_render_ping(self, client, created_project):
        with client.websocket_connect(f"/api/v1/ws/render/{created_project}") as ws:
            ws.receive_json()
            ws.send_json({"action": "ping"})
            data = ws.receive_json()
            assert data["type"] == "pong"

    def test_ws_render_status(self, client, created_project):
        with client.websocket_connect(f"/api/v1/ws/render/{created_project}") as ws:
            ws.receive_json()
            ws.send_json({"action": "status"})
            data = ws.receive_json()
            assert data["type"] == "render_status"
            assert "status" in data

    def test_ws_render_unknown_action(self, client, created_project):
        with client.websocket_connect(f"/api/v1/ws/render/{created_project}") as ws:
            ws.receive_json()
            ws.send_json({"action": "unknown"})
            data = ws.receive_json()
            assert data["type"] == "error"

    def test_ws_render_invalid_json(self, client, created_project):
        with client.websocket_connect(f"/api/v1/ws/render/{created_project}") as ws:
            ws.receive_json()
            ws.send_text("not json")
            data = ws.receive_json()
            assert data["type"] == "error"


class TestAIWebSocket:
    def test_ws_ai_connect(self, client, created_project):
        with client.websocket_connect(f"/api/v1/ws/ai/{created_project}") as ws:
            data = ws.receive_json()
            assert data["type"] == "connected"
            assert data["project_id"] == created_project

    def test_ws_ai_ping(self, client, created_project):
        with client.websocket_connect(f"/api/v1/ws/ai/{created_project}") as ws:
            ws.receive_json()
            ws.send_json({"action": "ping"})
            data = ws.receive_json()
            assert data["type"] == "pong"

    def test_ws_ai_unknown_action(self, client, created_project):
        with client.websocket_connect(f"/api/v1/ws/ai/{created_project}") as ws:
            ws.receive_json()
            ws.send_json({"action": "unknown"})
            data = ws.receive_json()
            assert data["type"] == "error"

    def test_ws_ai_invalid_json(self, client, created_project):
        with client.websocket_connect(f"/api/v1/ws/ai/{created_project}") as ws:
            ws.receive_json()
            ws.send_text("bad json")
            data = ws.receive_json()
            assert data["type"] == "error"


# ══════════════════════════════════════════════════════════════════════════
# Project Manager Unit Tests
# ══════════════════════════════════════════════════════════════════════════

class TestProjectManager:
    def test_create_and_read(self, tmp_path):
        from vcmix.web.project_manager import ProjectManager
        mgr = ProjectManager(projects_dir=tmp_path / "pm_test")
        pid = mgr.create("test", yaml_content="name: test\nbpm: 120\n")
        project = mgr.read(pid)
        assert project["name"] == "test"
        assert project["config"]["bpm"] == 120

    def test_create_duplicate_fails(self, tmp_path):
        from vcmix.web.project_manager import ProjectManager
        mgr = ProjectManager(projects_dir=tmp_path / "pm_dup")
        mgr.create("dup_test", yaml_content="name: test\n")
        with pytest.raises(ValueError):
            mgr.create("dup_test", yaml_content="name: test2\n")

    def test_update_creates_backup(self, tmp_path):
        from vcmix.web.project_manager import ProjectManager
        mgr = ProjectManager(projects_dir=tmp_path / "pm_backup")
        pid = mgr.create("backup_test", yaml_content="name: test\nbpm: 120\n")
        mgr.update(pid, yaml_content="name: updated\nbpm: 140\n")
        backup = tmp_path / "pm_backup" / "backup_test.yaml.bak"
        assert backup.exists()

    def test_delete_moves_to_recycle(self, tmp_path):
        from vcmix.web.project_manager import ProjectManager
        mgr = ProjectManager(projects_dir=tmp_path / "pm_delete")
        pid = mgr.create("delete_test", yaml_content="name: test\n")
        mgr.delete(pid)
        assert not (tmp_path / "pm_delete" / "delete_test.yaml").exists()
        recycle_dir = tmp_path / "pm_delete" / ".recycle"
        assert recycle_dir.exists()

    def test_list_projects(self, tmp_path):
        from vcmix.web.project_manager import ProjectManager
        mgr = ProjectManager(projects_dir=tmp_path / "pm_list")
        mgr.create("proj_a", yaml_content="name: A\nbpm: 120\n")
        mgr.create("proj_b", yaml_content="name: B\nbpm: 130\n")
        projects = mgr.list_projects()
        assert len(projects) == 2

    def test_add_track(self, tmp_path):
        from vcmix.web.project_manager import ProjectManager
        mgr = ProjectManager(projects_dir=tmp_path / "pm_track")
        pid = mgr.create("track_test", yaml_content="name: test\ntracks: []\nmaster:\n  levels: {}\n  effects: []\n  output: out.wav\n")
        result = mgr.add_track(pid, {"name": "vocal", "file": "v.wav"})
        assert any(t["name"] == "vocal" for t in result["config"]["tracks"])

    def test_delete_track(self, tmp_path):
        from vcmix.web.project_manager import ProjectManager
        mgr = ProjectManager(projects_dir=tmp_path / "pm_dtrack")
        pid = mgr.create("dtrack_test", yaml_content="name: test\ntracks:\n  - name: vocal\n    file: v.wav\nmaster:\n  levels:\n    vocal: 0.8\n  effects: []\n  output: out.wav\n")
        result = mgr.delete_track(pid, "vocal")
        assert all(t["name"] != "vocal" for t in result["config"]["tracks"])

    def test_add_effect(self, tmp_path):
        from vcmix.web.project_manager import ProjectManager
        mgr = ProjectManager(projects_dir=tmp_path / "pm_fx")
        pid = mgr.create("fx_test", yaml_content="name: test\ntracks:\n  - name: vocal\n    file: v.wav\n    effects: []\nmaster:\n  levels: {}\n  effects: []\n  output: out.wav\n")
        result = mgr.add_effect(pid, "vocal", {"name": "vc-gain", "params": {"gain": 3}})
        vocal = next(t for t in result["config"]["tracks"] if t["name"] == "vocal")
        assert len(vocal["effects"]) == 1

    def test_update_effect(self, tmp_path):
        from vcmix.web.project_manager import ProjectManager
        mgr = ProjectManager(projects_dir=tmp_path / "pm_ufx")
        pid = mgr.create("ufx_test", yaml_content="name: test\ntracks:\n  - name: vocal\n    file: v.wav\n    effects:\n      - name: vc-gain\n        params:\n          gain: 0\nmaster:\n  levels: {}\n  effects: []\n  output: out.wav\n")
        result = mgr.update_effect(pid, "vocal", 0, {"gain": 5})
        vocal = next(t for t in result["config"]["tracks"] if t["name"] == "vocal")
        assert vocal["effects"][0]["params"]["gain"] == 5

    def test_delete_effect(self, tmp_path):
        from vcmix.web.project_manager import ProjectManager
        mgr = ProjectManager(projects_dir=tmp_path / "pm_dfx")
        pid = mgr.create("dfx_test", yaml_content="name: test\ntracks:\n  - name: vocal\n    file: v.wav\n    effects:\n      - name: vc-gain\n        params:\n          gain: 0\nmaster:\n  levels: {}\n  effects: []\n  output: out.wav\n")
        result = mgr.delete_effect(pid, "vocal", 0)
        vocal = next(t for t in result["config"]["tracks"] if t["name"] == "vocal")
        assert len(vocal["effects"]) == 0

    def test_effect_out_of_range(self, tmp_path):
        from vcmix.web.project_manager import ProjectManager
        mgr = ProjectManager(projects_dir=tmp_path / "pm_oor")
        pid = mgr.create("oor_test", yaml_content="name: test\ntracks:\n  - name: vocal\n    file: v.wav\n    effects: []\nmaster:\n  levels: {}\n  effects: []\n  output: out.wav\n")
        with pytest.raises(IndexError):
            mgr.update_effect(pid, "vocal", 0, {"gain": 5})

    def test_create_from_json(self, tmp_path):
        from vcmix.web.project_manager import ProjectManager
        mgr = ProjectManager(projects_dir=tmp_path / "pm_json")
        pid = mgr.create("json_test", json_data={"name": "JsonTest", "bpm": 128})
        project = mgr.read(pid)
        assert project["config"]["name"] == "JsonTest"
        assert project["config"]["bpm"] == 128

    def test_exists(self, tmp_path):
        from vcmix.web.project_manager import ProjectManager
        mgr = ProjectManager(projects_dir=tmp_path / "pm_exists")
        pid = mgr.create("exists_test", yaml_content="name: test\n")
        assert mgr.exists(pid)
        assert not mgr.exists("nonexistent1234")


# ══════════════════════════════════════════════════════════════════════════
# Analysis Service Unit Tests
# ══════════════════════════════════════════════════════════════════════════

class TestAnalysisService:
    def test_analyze_nonexistent_file(self, tmp_path):
        from vcmix.web.analysis_service import AnalysisService
        svc = AnalysisService()
        with pytest.raises(FileNotFoundError):
            svc.analyze_project(tmp_path / "nonexistent.yaml")

    def test_placeholder_metrics(self):
        from vcmix.web.analysis_service import AnalysisService
        metrics = AnalysisService._placeholder_metrics()
        assert metrics["rms_db"] == -120.0
        assert metrics["peak_db"] == -120.0
        assert metrics["lufs"] == -120.0

    def test_analyze_project_with_yaml(self, tmp_path):
        from vcmix.web.analysis_service import AnalysisService
        svc = AnalysisService()
        yaml_path = tmp_path / "analysis_test.yaml"
        yaml_path.write_text(
            "name: AnalysisTest\nbpm: 120\nsample_rate: 44100\n"
            "tracks:\n  - name: vocal\n    file: vocal.wav\nmaster:\n  levels: {}\n  effects: []\n  output: out.wav\n"
        )
        report = svc.analyze_project(yaml_path)
        assert report["project"] == "AnalysisTest"
        assert len(report["tracks"]) == 1
        assert report["tracks"][0]["status"] == "file_not_found"

    def test_analyze_specific_track(self, tmp_path):
        from vcmix.web.analysis_service import AnalysisService
        svc = AnalysisService()
        yaml_path = tmp_path / "track_analysis.yaml"
        yaml_path.write_text(
            "name: TrackTest\nbpm: 120\nsample_rate: 44100\n"
            "tracks:\n  - name: vocal\n    file: vocal.wav\n  - name: bass\n    file: bass.wav\n"
            "master:\n  levels: {}\n  effects: []\n  output: out.wav\n"
        )
        report = svc.analyze_track(yaml_path, "vocal")
        assert report["name"] == "vocal"

    def test_analyze_track_not_found(self, tmp_path):
        from vcmix.web.analysis_service import AnalysisService
        svc = AnalysisService()
        yaml_path = tmp_path / "track_nf.yaml"
        yaml_path.write_text(
            "name: NF\nbpm: 120\ntracks:\n  - name: vocal\n    file: v.wav\n"
            "master:\n  levels: {}\n  effects: []\n  output: out.wav\n"
        )
        with pytest.raises(FileNotFoundError):
            svc.analyze_track(yaml_path, "nonexistent")


# ══════════════════════════════════════════════════════════════════════════
# AI Engine Unit Tests
# ══════════════════════════════════════════════════════════════════════════

class TestAIEngine:
    def test_mix_step_mode(self):
        from vcmix.web.ai_engine import AIEngine
        engine = AIEngine()
        analysis = {
            "tracks": [
                {"name": "vocal", "rms_db": -12.0, "peak_db": -3.0,
                 "true_peak_db": -2.5, "dynamic_range_db": 9.0,
                 "sibilance_ratio": 0.15, "spectrum": {"sub": 0.01, "low": 0.05, "mid": 0.3, "high_mid": 0.2, "high": 0.1, "air": 0.03}},
            ],
            "master": {"lufs": -18.0, "true_peak_db": -0.5, "rms_db": -15.0, "dynamic_range_db": 5.0, "spectrum": {}},
        }
        result = engine.mix(analysis, mode="step")
        assert result.mode == "step"
        assert len(result.suggestions) > 0
        assert len(result.decision_log) > 0
        assert result.applied is False

    def test_mix_one_click(self):
        from vcmix.web.ai_engine import AIEngine
        engine = AIEngine()
        analysis = {
            "tracks": [{"name": "vocal", "rms_db": -12.0, "peak_db": -3.0,
                         "true_peak_db": -2.5, "dynamic_range_db": 9.0,
                         "sibilance_ratio": 0.05, "spectrum": {}}],
            "master": {"lufs": -18.0, "true_peak_db": -0.5, "rms_db": -15.0,
                       "dynamic_range_db": 5.0, "spectrum": {}},
        }
        config = {"name": "test", "tracks": [{"name": "vocal", "effects": []}],
                  "master": {"levels": {"vocal": 0.8}, "effects": [], "output": "out.wav"}}
        result = engine.mix(analysis, mode="one_click", config=config)
        assert result.applied is True
        assert result.updated_config is not None

    def test_master_step_mode(self):
        from vcmix.web.ai_engine import AIEngine
        engine = AIEngine()
        analysis = {
            "tracks": [],
            "master": {"lufs": -10.0, "true_peak_db": 0.5, "rms_db": -12.0,
                       "dynamic_range_db": 2.0, "spectrum": {"sub": 0.1, "low": 0.15, "mid": 0.3, "high_mid": 0.2, "high": 0.1, "air": 0.03}},
        }
        result = engine.master(analysis, mode="step")
        assert len(result.suggestions) > 0

    def test_master_loudness_normalization(self):
        from vcmix.web.ai_engine import AIEngine
        engine = AIEngine()
        analysis = {
            "tracks": [],
            "master": {"lufs": -20.0, "true_peak_db": -3.0, "dynamic_range_db": 8.0, "spectrum": {}},
        }
        result = engine.master(analysis, mode="step")
        loudness_suggestions = [s for s in result.suggestions if s["action"] == "loudness_normalize"]
        assert len(loudness_suggestions) > 0

    def test_master_true_peak_limiting(self):
        from vcmix.web.ai_engine import AIEngine
        engine = AIEngine()
        analysis = {
            "tracks": [],
            "master": {"lufs": -14.0, "true_peak_db": 0.5, "dynamic_range_db": 5.0, "spectrum": {}},
        }
        result = engine.master(analysis, mode="step")
        limiter_suggestions = [s for s in result.suggestions if s["action"] == "limiter"]
        assert len(limiter_suggestions) > 0

    def test_mix_empty_analysis(self):
        from vcmix.web.ai_engine import AIEngine
        engine = AIEngine()
        result = engine.mix({"tracks": [], "master": {}}, mode="step")
        assert result.mode == "step"
        assert isinstance(result.suggestions, list)

    def test_sibilance_detection(self):
        from vcmix.web.ai_engine import AIEngine
        engine = AIEngine()
        analysis = {
            "tracks": [{"name": "vocal", "rms_db": -18.0, "peak_db": -6.0,
                         "true_peak_db": -5.5, "dynamic_range_db": 12.0,
                         "sibilance_ratio": 0.2, "spectrum": {}}],
            "master": {},
        }
        result = engine.mix(analysis, mode="step")
        deesser = [s for s in result.suggestions if s["action"] == "deesser"]
        assert len(deesser) > 0

    def test_decision_log_format(self):
        from vcmix.web.ai_engine import AIEngine
        engine = AIEngine()
        result = engine.mix({"tracks": [], "master": {}}, mode="step")
        for entry in result.decision_log:
            assert "step" in entry
            assert "target" in entry
            assert "action" in entry
            assert "reason" in entry
            assert "timestamp" in entry

    def test_apply_suggestions_adds_limiter(self):
        from vcmix.web.ai_engine import AIEngine, DecisionLog
        engine = AIEngine()
        config = {"name": "test", "tracks": [], "master": {"levels": {}, "effects": [], "output": "out.wav"}}
        suggestions = [{"target": "master", "action": "limiter", "params": {"ceiling": -1}, "reason": "test", "priority": 1}]
        log: list[DecisionLog] = []
        result = engine._apply_suggestions(config, suggestions, log)
        master_effects = result["master"]["effects"]
        assert any(e["name"] == "vc-limiter" for e in master_effects)


# ══════════════════════════════════════════════════════════════════════════
# Integration Tests
# ══════════════════════════════════════════════════════════════════════════

class TestIntegration:
    def test_full_crud_lifecycle(self, client, sample_yaml):
        """Test: create → read → update → add track → add effect → delete."""
        name = _unique_name("life")
        resp = client.post("/api/v1/projects", json={
            "name": name,
            "yaml_content": sample_yaml,
        })
        assert resp.status_code == 201
        pid = resp.json()["id"]

        resp = client.get(f"/api/v1/projects/{pid}")
        assert resp.status_code == 200

        resp = client.post(f"/api/v1/projects/{pid}/tracks", json={
            "name": "bass",
            "file": "bass.wav",
        })
        assert resp.status_code == 201

        resp = client.post(f"/api/v1/projects/{pid}/tracks/bass/effects", json={
            "name": "vc-comp",
            "params": {"threshold": -20, "ratio": 4},
        })
        assert resp.status_code == 201

        resp = client.put(f"/api/v1/projects/{pid}/tracks/bass/effects/0", json={
            "params": {"ratio": 3},
        })
        assert resp.status_code == 200

        resp = client.delete(f"/api/v1/projects/{pid}/tracks/bass/effects/0")
        assert resp.status_code == 200

        resp = client.delete(f"/api/v1/projects/{pid}/tracks/bass")
        assert resp.status_code == 200

        resp = client.delete(f"/api/v1/projects/{pid}")
        assert resp.status_code == 200

    def test_analysis_then_ai_mix(self, client, sample_yaml):
        """Test: create → analyze → AI mix pipeline."""
        name = _unique_name("pipe")
        resp = client.post("/api/v1/projects", json={
            "name": name,
            "yaml_content": sample_yaml,
        })
        pid = resp.json()["id"]

        resp = client.get(f"/api/v1/projects/{pid}/analysis")
        assert resp.status_code == 200

        resp = client.post(f"/api/v1/ai/mix/{pid}", json={"mode": "step"})
        assert resp.status_code == 200

        resp = client.post(f"/api/v1/ai/master/{pid}", json={"mode": "step"})
        assert resp.status_code == 200

    def test_health_check_version_updated(self, client):
        resp = client.get("/api/health")
        data = resp.json()
        assert data["status"] == "ok"
        assert data["version"] == "0.11.0"

    def test_original_api_still_works(self, client):
        resp = client.get("/api/plugins")
        assert resp.status_code == 200

        resp = client.get("/api/presets")
        assert resp.status_code == 200

    def test_create_project_then_render(self, client, sample_yaml):
        name = _unique_name("render")
        resp = client.post("/api/v1/projects", json={
            "name": name,
            "yaml_content": sample_yaml,
        })
        pid = resp.json()["id"]

        resp = client.post(f"/api/v1/projects/{pid}/render", json={})
        assert resp.status_code == 200
        job_id = resp.json()["job_id"]

        import time
        time.sleep(1)
        resp = client.get(f"/api/v1/projects/{pid}/render/status")
        assert resp.status_code == 200
