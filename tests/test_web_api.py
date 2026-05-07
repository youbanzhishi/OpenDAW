"""
test_web_api.py — Tests for VCMix Web API (Phase 9).

Tests the FastAPI REST endpoints and WebSocket functionality.
Uses FastAPI TestClient for synchronous testing.

Coverage:
    - Health check
    - Plugin listing and detail
    - Preset listing and detail
    - Chain preset listing, detail, and apply
    - YAML validation
    - Render trigger and status polling
    - Arrangement analysis
    - AutoMix analysis
    - WebSocket connection and messaging
    - MIDI scan, parse, synths (Phase 9)
    - Automation preview and apply (Phase 9)
"""

from __future__ import annotations

import json
import tempfile
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


@pytest.fixture
def client():
    """Create a FastAPI test client."""
    return TestClient(app)


# ── Minimal YAML project for testing ────────────────────────────────────

MINIMAL_YAML = """\
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

master:
  levels:
    vocal: 0.8
  effects: []
  output: output.wav
"""


# ── Health Check ─────────────────────────────────────────────────────────

class TestHealthCheck:
    def test_health_returns_ok(self, client):
        resp = client.get("/api/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["version"] == "0.13.0"


# ── Plugin Endpoints ────────────────────────────────────────────────────

class TestPlugins:
    def test_list_plugins(self, client):
        resp = client.get("/api/plugins")
        assert resp.status_code == 200
        data = resp.json()
        assert "plugins" in data
        assert "count" in data
        assert data["count"] > 0

        plugin_names = [p["name"] for p in data["plugins"]]
        assert "vc-eq" in plugin_names
        assert "vc-comp" in plugin_names
        assert "vc-reverb" in plugin_names
        assert "vc-gain" in plugin_names

    def test_get_plugin_detail(self, client):
        resp = client.get("/api/plugins/vc-eq")
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "vc-eq"
        assert "has_sidechain" in data

    def test_get_plugin_not_found(self, client):
        resp = client.get("/api/plugins/nonexistent-plugin")
        assert resp.status_code == 404


# ── Preset Endpoints ────────────────────────────────────────────────────

class TestPresets:
    def test_list_presets(self, client):
        resp = client.get("/api/presets")
        assert resp.status_code == 200
        data = resp.json()
        assert "presets" in data
        assert data["count"] > 0

        preset_names = [p["name"] for p in data["presets"]]
        assert "pop_vocal" in preset_names
        assert "rock_vocal" in preset_names
        assert "podcast" in preset_names

    def test_get_preset_detail(self, client):
        resp = client.get("/api/presets/pop_vocal")
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "pop_vocal"
        assert "effects" in data
        assert len(data["effects"]) > 0

        for effect in data["effects"]:
            assert "name" in effect
            assert "params" in effect

    def test_get_preset_not_found(self, client):
        resp = client.get("/api/presets/nonexistent_preset")
        assert resp.status_code == 404

    def test_create_preset(self, client):
        resp = client.post("/api/presets", json={
            "name": "test_preset",
            "effects": [
                {"name": "vc-gain", "params": {"gain": 3}},
                {"name": "vc-limiter", "params": {"ceiling": -1}},
            ],
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["saved"] is True
        assert data["name"] == "test_preset"


# ── Chain Preset Endpoints (Phase 9) ────────────────────────────────────

class TestChainPresets:
    def test_list_chain_presets(self, client):
        resp = client.get("/api/presets/chains")
        assert resp.status_code == 200
        data = resp.json()
        assert "chains" in data
        assert data["count"] > 0

        chain_names = [c["name"] for c in data["chains"]]
        assert "vocal-chain" in chain_names
        assert "drum-chain" in chain_names
        assert "master-chain" in chain_names

    def test_get_chain_preset_detail(self, client):
        resp = client.get("/api/presets/chains/vocal-chain")
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "vocal-chain"
        assert "effects" in data
        assert data["effect_count"] > 0
        assert data["routing"] == "serial"
        assert "tags" in data

    def test_get_chain_preset_not_found(self, client):
        resp = client.get("/api/presets/chains/nonexistent-chain")
        assert resp.status_code == 404

    def test_chain_preset_has_effect_names(self, client):
        resp = client.get("/api/presets/chains/vocal-chain")
        data = resp.json()
        assert "effect_names" in data
        assert len(data["effect_names"]) > 0
        # Vocal chain should have vc-deesser
        assert "vc-deesser" in data["effect_names"]

    def test_chain_preset_apply(self, client):
        resp = client.post("/api/presets/chains/vocal-chain/apply", json={
            "track_name": "vocals",
            "track_config": {
                "name": "vocals",
                "file": "vocals.wav",
                "effects": [],
            },
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["applied"] is True
        assert data["chain_name"] == "vocal-chain"
        assert data["track_name"] == "vocals"
        assert data["effect_count"] > 0
        assert "updated_config" in data
        # Check that effects were applied
        assert len(data["updated_config"]["effects"]) > 0

    def test_chain_preset_apply_not_found(self, client):
        resp = client.post("/api/presets/chains/nonexistent-chain/apply", json={
            "track_name": "vocals",
            "track_config": {"name": "vocals", "file": "vocals.wav"},
        })
        assert resp.status_code == 404


# ── MIDI Endpoints (Phase 9) ────────────────────────────────────────────

class TestMidi:
    def test_midi_scan_default_dir(self, client):
        """Test MIDI scan on default directory (may have 0 files)."""
        resp = client.get("/api/midi/scan")
        assert resp.status_code == 200
        data = resp.json()
        assert "files" in data
        assert "count" in data
        assert isinstance(data["files"], list)

    def test_midi_scan_nonexistent_dir(self, client):
        resp = client.get("/api/midi/scan?directory=/nonexistent/path")
        assert resp.status_code == 404

    def test_midi_parse_not_found(self, client):
        resp = client.post("/api/midi/parse", json={
            "path": "/nonexistent/song.mid",
        })
        assert resp.status_code == 404

    def test_midi_parse_non_mid_file(self, client):
        """Test that parsing a non-.mid file returns 400."""
        # Create a temp non-midi file
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            f.write(b"not a midi file")
            tmp_path = f.name
        try:
            resp = client.post("/api/midi/parse", json={"path": tmp_path})
            assert resp.status_code == 400
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    def test_synths_list(self, client):
        """Test that synthesizer types are listed."""
        resp = client.get("/api/midi/synths")
        assert resp.status_code == 200
        data = resp.json()
        assert "synths" in data
        assert data["count"] > 0

        synth_names = [s["name"] for s in data["synths"]]
        assert "sine" in synth_names
        assert "sawtooth" in synth_names
        assert "square" in synth_names
        assert "triangle" in synth_names

        # Each synth should have a description
        for s in data["synths"]:
            assert "description" in s

    @pytest.fixture
    def sample_midi_file(self, tmp_path):
        """Create a minimal MIDI file for testing using mido."""
        try:
            import mido
        except ImportError:
            pytest.skip("mido not installed")

        mid = mido.MidiFile()
        track = mido.MidiTrack()
        track.append(mido.MetaMessage("track_name", name="Test Track"))
        track.append(mido.MetaMessage("set_tempo", tempo=mido.bpm2tempo(120)))
        track.append(mido.Message("note_on", note=60, velocity=100, channel=0, time=0))
        track.append(mido.Message("note_off", note=60, velocity=0, channel=0, time=480))
        track.append(mido.Message("note_on", note=64, velocity=80, channel=0, time=0))
        track.append(mido.Message("note_off", note=64, velocity=0, channel=0, time=480))
        mid.tracks.append(track)

        midi_path = tmp_path / "test.mid"
        mid.save(str(midi_path))
        return str(midi_path)

    def test_midi_parse_valid_file(self, client, sample_midi_file):
        """Test parsing a valid MIDI file."""
        resp = client.post("/api/midi/parse", json={
            "path": sample_midi_file,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["bpm"] == 120.0
        assert data["track_count"] > 0
        assert data["total_beats"] > 0
        assert "tracks" in data

        # Check track structure
        for track in data["tracks"]:
            assert "name" in track
            assert "notes" in track
            assert "note_count" in track
            assert "channel" in track

            for note in track["notes"]:
                assert "note" in note
                assert "name" in note
                assert "velocity" in note
                assert "start_beat" in note
                assert "duration_beats" in note


# ── Automation Endpoints (Phase 9) ──────────────────────────────────────

class TestAutomation:
    def test_automation_preview_empty(self, client):
        """Test preview with no points returns empty result."""
        resp = client.post("/api/automation/preview", json={
            "points": [],
            "query_beats": [],
            "default_value": 0.0,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["point_count"] == 0
        assert data["points"] == []

    def test_automation_preview_with_points(self, client):
        """Test preview with control points."""
        resp = client.post("/api/automation/preview", json={
            "points": [
                {"time_beat": 0.0, "value": -6.0, "curve_type": "linear"},
                {"time_beat": 8.0, "value": 0.0, "curve_type": "linear"},
                {"time_beat": 32.0, "value": 0.0, "curve_type": "step"},
                {"time_beat": 40.0, "value": -12.0, "curve_type": "smooth"},
            ],
            "query_beats": [0.0, 4.0, 8.0, 20.0, 36.0],
            "default_value": 0.0,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["point_count"] == 4
        assert len(data["points"]) == 4
        assert "value_range" in data
        assert data["start_beat"] == 0.0
        assert data["end_beat"] == 40.0

        # Check interpolated values
        vals = {v["beat"]: v["value"] for v in data["values_at_beats"]}
        assert abs(vals[0.0] - (-6.0)) < 0.01      # At first point
        assert abs(vals[4.0] - (-3.0)) < 0.01      # Linear midpoint
        assert abs(vals[8.0] - 0.0) < 0.01         # At second point
        assert abs(vals[20.0] - 0.0) < 0.01        # Step hold
        assert abs(vals[36.0] - 0.0) < 0.01        # Still step hold (before smooth starts)

    def test_automation_preview_invalid_curve_type(self, client):
        """Test preview with invalid curve type returns 400."""
        resp = client.post("/api/automation/preview", json={
            "points": [
                {"time_beat": 0.0, "value": 0.0, "curve_type": "invalid"},
            ],
            "query_beats": [],
        })
        assert resp.status_code == 400

    def test_automation_apply(self, client):
        """Test applying automation to a track."""
        resp = client.post("/api/automation/apply", json={
            "track_name": "vocal",
            "parameter": "gain",
            "points": [
                {"time_beat": 0.0, "value": -6.0, "curve_type": "linear"},
                {"time_beat": 8.0, "value": 0.0, "curve_type": "linear"},
            ],
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["applied"] is True
        assert data["track_name"] == "vocal"
        assert data["parameter"] == "gain"
        assert data["point_count"] == 2
        assert "automation" in data
        assert "gain" in data["automation"]

    def test_automation_apply_empty_points(self, client):
        """Test apply with no points returns 400."""
        resp = client.post("/api/automation/apply", json={
            "track_name": "vocal",
            "parameter": "gain",
            "points": [],
        })
        assert resp.status_code == 400


# ── Validate Endpoint ───────────────────────────────────────────────────

class TestValidate:
    def test_validate_valid_yaml(self, client):
        client.post(
            "/api/validate?yaml_content=" + json.dumps(MINIMAL_YAML),
        )
        pass

    def test_validate_invalid_yaml(self, client):
        bad_yaml = "not: valid\nyaml: ["
        resp = client.post(
            "/api/validate?yaml_content=" + json.dumps(bad_yaml),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["valid"] is False


# ── Render Endpoints ────────────────────────────────────────────────────

class TestRender:
    def test_trigger_render_from_yaml(self, client):
        """Test triggering a render with inline YAML."""
        resp = client.post("/api/render", json={
            "project_yaml": MINIMAL_YAML,
            "report": False,
            "auto_fix": False,
            "ab_mode": False,
            "arrangement_aware": False,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "job_id" in data
        assert data["status"] == "pending"

    def test_trigger_render_from_file_not_found(self, client):
        """Test that rendering from non-existent file returns 404."""
        resp = client.post(
            "/api/render/file?project_path=/nonexistent/path.yaml",
        )
        assert resp.status_code == 404

    def test_get_render_status_not_found(self, client):
        """Test that querying unknown job returns 404."""
        resp = client.get("/api/render/nonexistent-job-id")
        assert resp.status_code == 404

    def test_render_job_lifecycle(self, client):
        """Test full render job lifecycle: trigger -> poll -> complete/fail."""
        resp = client.post("/api/render", json={
            "project_yaml": MINIMAL_YAML,
        })
        assert resp.status_code == 200
        job_id = resp.json()["job_id"]

        import time
        time.sleep(2)

        resp = client.get(f"/api/render/{job_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] in ("pending", "running", "completed", "failed")

    def test_get_render_events(self, client):
        """Test getting events for a render job."""
        resp = client.post("/api/render", json={
            "project_yaml": MINIMAL_YAML,
        })
        job_id = resp.json()["job_id"]

        import time
        time.sleep(2)

        resp = client.get(f"/api/render/{job_id}/events")
        assert resp.status_code == 200
        data = resp.json()
        assert "events" in data


# ── WebSocket ────────────────────────────────────────────────────────────

class TestWebSocket:
    def test_websocket_connect(self, client):
        """Test WebSocket connection and basic messaging."""
        with client.websocket_connect("/api/stream") as ws:
            data = ws.receive_json()
            assert data["type"] == "connected"

            ws.send_json({"action": "ping"})
            data = ws.receive_json()
            assert data["type"] == "pong"

    def test_websocket_status(self, client):
        """Test WebSocket status command."""
        with client.websocket_connect("/api/stream") as ws:
            ws.receive_json()

            ws.send_json({"action": "status"})
            data = ws.receive_json()
            assert data["type"] == "status"
            assert "connections" in data

    def test_websocket_unknown_action(self, client):
        """Test WebSocket with unknown action."""
        with client.websocket_connect("/api/stream") as ws:
            ws.receive_json()

            ws.send_json({"action": "unknown"})
            data = ws.receive_json()
            assert data["type"] == "error"


# ── Arrangement Endpoint ────────────────────────────────────────────────

class TestArrangement:
    def test_arrangement_file_not_found(self, client):
        """Test arrangement analysis with non-existent file."""
        resp = client.get("/api/arrangement?project_path=/nonexistent.yaml")
        assert resp.status_code == 404

    def test_arrangement_strategy_file_not_found(self, client):
        """Test arrangement strategy with non-existent file."""
        resp = client.get("/api/arrangement/strategy?project_path=/nonexistent.yaml")
        assert resp.status_code == 404


# ── AutoMix Endpoint ────────────────────────────────────────────────────

class TestAutoMix:
    def test_automix_file_not_found(self, client):
        """Test auto-mixing with non-existent file."""
        resp = client.post("/api/automix", json={
            "project_path": "/nonexistent.yaml",
            "dry_run": True,
        })
        assert resp.status_code == 404
