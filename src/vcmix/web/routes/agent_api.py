"""
agent_api.py — AI Agent API endpoints for VCMix (Phase 11).

REST API under /api/v1/ for AI Agent project CRUD, track operations,
rendering control, audio analysis, and AI mixing decisions.

WebSocket endpoints under /ws/ for real-time render progress and
AI decision log streaming.
"""

from __future__ import annotations

import asyncio
import json
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Optional

from vcmix.web.websocket import emit_stream_event_sync
from vcmix.web.websocket import (
    EVENT_PROJECT_CREATED, EVENT_PROJECT_UPDATED, EVENT_PROJECT_DELETED,
    EVENT_TRACK_ADDED, EVENT_TRACK_UPDATED, EVENT_TRACK_REMOVED,
    EVENT_EFFECT_ADDED, EVENT_EFFECT_UPDATED, EVENT_EFFECT_REMOVED,
    EVENT_AI_MIX_APPLIED, EVENT_AI_MASTER_APPLIED,
)

from fastapi import APIRouter, BackgroundTasks, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

from vcmix.web.ai_engine import AIEngine
from vcmix.web.analysis_service import AnalysisService
from vcmix.web.project_manager import ProjectManager

router = APIRouter()

# ── Shared service instances ────────────────────────────────────────────────

_pm = ProjectManager()
_analysis = AnalysisService()
_ai = AIEngine()

# ── Render job tracking ─────────────────────────────────────────────────────

_render_jobs: dict[str, dict[str, Any]] = {}
_render_lock = threading.Lock()

# ── WebSocket connection managers ────────────────────────────────────────────


class RenderProgressManager:
    """Manages WebSocket connections for render progress."""

    def __init__(self) -> None:
        self._connections: dict[str, list[WebSocket]] = {}

    async def connect(self, project_id: str, ws: WebSocket) -> None:
        await ws.accept()
        self._connections.setdefault(project_id, []).append(ws)

    def disconnect(self, project_id: str, ws: WebSocket) -> None:
        conns = self._connections.get(project_id, [])
        if ws in conns:
            conns.remove(ws)

    async def broadcast(self, project_id: str, message: dict[str, Any]) -> None:
        conns = self._connections.get(project_id, [])
        data = json.dumps(message, ensure_ascii=False)
        dead = []
        for ws in conns:
            try:
                await ws.send_text(data)
            except Exception:
                dead.append(ws)
        for ws in dead:
            conns.remove(ws)


class AIDecisionManager:
    """Manages WebSocket connections for AI decision streaming."""

    def __init__(self) -> None:
        self._connections: dict[str, list[WebSocket]] = {}

    async def connect(self, project_id: str, ws: WebSocket) -> None:
        await ws.accept()
        self._connections.setdefault(project_id, []).append(ws)

    def disconnect(self, project_id: str, ws: WebSocket) -> None:
        conns = self._connections.get(project_id, [])
        if ws in conns:
            conns.remove(ws)

    async def broadcast(self, project_id: str, message: dict[str, Any]) -> None:
        conns = self._connections.get(project_id, [])
        data = json.dumps(message, ensure_ascii=False)
        dead = []
        for ws in conns:
            try:
                await ws.send_text(data)
            except Exception:
                dead.append(ws)
        for ws in dead:
            conns.remove(ws)


_render_ws = RenderProgressManager()
_ai_ws = AIDecisionManager()


# ── Pydantic Models ─────────────────────────────────────────────────────────

class ProjectCreate(BaseModel):
    """Request body for creating a project."""
    name: str = Field(..., min_length=1, max_length=100, description="Project name")
    yaml_content: Optional[str] = Field(default=None, description="YAML content string")
    json_data: Optional[dict[str, Any]] = Field(default=None, description="Project config as JSON dict")


class ProjectUpdate(BaseModel):
    """Request body for updating a project."""
    yaml_content: Optional[str] = Field(default=None, description="New YAML content")
    json_data: Optional[dict[str, Any]] = Field(default=None, description="New config as JSON dict")


class TrackCreate(BaseModel):
    """Request body for adding a track."""
    name: str = Field(..., description="Track name")
    file: str = Field(default="", description="Audio file path")
    type: str = Field(default="audio", description="Track type: audio/midi/vst3/sampler")
    effects: list[dict[str, Any]] = Field(default_factory=list)
    volume: float = Field(default=1.0, ge=0.0)
    mute: bool = Field(default=False)
    solo: bool = Field(default=False)


class TrackUpdate(BaseModel):
    """Request body for updating a track."""
    file: Optional[str] = None
    type: Optional[str] = None
    effects: list[dict[str, Any]] | None = None
    volume: Optional[float] = None
    mute: Optional[bool] = None
    solo: Optional[bool] = None


class EffectCreate(BaseModel):
    """Request body for adding an effect."""
    name: str = Field(..., description="Plugin name")
    params: dict[str, Any] = Field(default_factory=dict, description="Plugin parameters")


class EffectUpdate(BaseModel):
    """Request body for updating effect parameters."""
    params: dict[str, Any] = Field(..., description="Updated parameters")


class RenderTrigger(BaseModel):
    """Request body for triggering a render."""
    report: bool = Field(default=False, description="Generate analysis report")
    auto_fix: bool = Field(default=False, description="Enable auto-fix")
    arrangement_aware: bool = Field(default=False, description="Arrangement-aware mode")
    parallel: int = Field(default=1, ge=1, description="Parallel render threads")


class AIMixRequest(BaseModel):
    """Request body for AI mixing suggestions."""
    mode: str = Field(default="step", description="step or one_click")
    apply: bool = Field(default=False, description="Auto-apply suggestions")


class AIMasterRequest(BaseModel):
    """Request body for AI mastering suggestions."""
    mode: str = Field(default="step", description="step or one_click")
    apply: bool = Field(default=False, description="Auto-apply suggestions")


# ── Project CRUD ─────────────────────────────────────────────────────────────

@router.get("/projects")
async def list_projects():
    """List all projects."""
    projects = _pm.list_projects()
    return {"projects": projects, "count": len(projects)}


@router.post("/projects", status_code=201)
async def create_project(request: ProjectCreate):
    """Create a new project from YAML or JSON."""
    try:
        pid = _pm.create(
            name=request.name,
            yaml_content=request.yaml_content,
            json_data=request.json_data,
        )
        project = _pm.read(pid)
        try:
            emit_stream_event_sync({
                "type": EVENT_PROJECT_CREATED,
                "project_id": pid,
                "action": "project_created",
                "detail": {"name": request.name},
                "ts": time.time() * 1000,
            })
        except Exception:
            pass
        return {"id": pid, "name": request.name, "status": "created", "project": project}
    except ValueError as e:
        if "already exists" in str(e):
            raise HTTPException(status_code=409, detail=str(e))
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/projects/{project_id}")
async def get_project(project_id: str):
    """Get project details by ID."""
    try:
        return _pm.read(project_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Project not found: {project_id}")


@router.put("/projects/{project_id}")
async def update_project(project_id: str, request: ProjectUpdate):
    """Update a project's configuration."""
    try:
        result = _pm.update(
            project_id,
            yaml_content=request.yaml_content,
            json_data=request.json_data,
        )
        try:
            emit_stream_event_sync({
                "type": EVENT_PROJECT_UPDATED,
                "project_id": project_id,
                "action": "project_updated",
                "detail": {"project_id": project_id},
                "ts": time.time() * 1000,
            })
        except Exception:
            pass
        return {"id": project_id, "status": "updated", "project": result}
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Project not found: {project_id}")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/projects/{project_id}")
async def delete_project(project_id: str):
    """Delete a project."""
    deleted = _pm.delete(project_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Project not found: {project_id}")
    try:
        emit_stream_event_sync({
            "type": EVENT_PROJECT_DELETED,
            "project_id": project_id,
            "action": "project_deleted",
            "detail": {"project_id": project_id},
            "ts": time.time() * 1000,
        })
    except Exception:
        pass
    return {"id": project_id, "status": "deleted"}


# ── Track Operations ─────────────────────────────────────────────────────────

@router.post("/projects/{project_id}/tracks", status_code=201)
async def add_track(project_id: str, request: TrackCreate):
    """Add a track to a project."""
    track_data = {
        "name": request.name,
        "file": request.file,
        "type": request.type,
        "effects": request.effects,
        "volume": request.volume,
        "mute": request.mute,
        "solo": request.solo,
    }
    try:
        result = _pm.add_track(project_id, track_data)
        try:
            emit_stream_event_sync({
                "type": EVENT_TRACK_ADDED,
                "project_id": project_id,
                "action": "track_added",
                "detail": {"track": request.name},
                "ts": time.time() * 1000,
            })
        except Exception:
            pass
        return {"status": "added", "track": request.name, "project": result}
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.put("/projects/{project_id}/tracks/{track_name}")
async def update_track(project_id: str, track_name: str, request: TrackUpdate):
    """Update a track in a project."""
    updates = {k: v for k, v in request.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")
    try:
        result = _pm.update_track(project_id, track_name, updates)
        try:
            emit_stream_event_sync({
                "type": EVENT_TRACK_UPDATED,
                "project_id": project_id,
                "action": "track_updated",
                "detail": {"track": track_name},
                "ts": time.time() * 1000,
            })
        except Exception:
            pass
        return {"status": "updated", "track": track_name, "project": result}
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.delete("/projects/{project_id}/tracks/{track_name}")
async def delete_track(project_id: str, track_name: str):
    """Delete a track from a project."""
    try:
        result = _pm.delete_track(project_id, track_name)
        try:
            emit_stream_event_sync({
                "type": EVENT_TRACK_REMOVED,
                "project_id": project_id,
                "action": "track_removed",
                "detail": {"track": track_name},
                "ts": time.time() * 1000,
            })
        except Exception:
            pass
        return {"status": "deleted", "track": track_name, "project": result}
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ── Effect Operations ────────────────────────────────────────────────────────

@router.post("/projects/{project_id}/tracks/{track_name}/effects", status_code=201)
async def add_effect(project_id: str, track_name: str, request: EffectCreate):
    """Add an effect to a track's insert chain."""
    effect_data = {"name": request.name, "params": request.params}
    try:
        result = _pm.add_effect(project_id, track_name, effect_data)
        try:
            emit_stream_event_sync({
                "type": EVENT_EFFECT_ADDED,
                "project_id": project_id,
                "action": "effect_added",
                "detail": {"track": track_name, "effect": request.name},
                "ts": time.time() * 1000,
            })
        except Exception:
            pass
        return {"status": "added", "effect": request.name, "track": track_name, "project": result}
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.put("/projects/{project_id}/tracks/{track_name}/effects/{fx_idx}")
async def update_effect(project_id: str, track_name: str, fx_idx: int, request: EffectUpdate):
    """Update an effect's parameters."""
    try:
        result = _pm.update_effect(project_id, track_name, fx_idx, request.params)
        try:
            emit_stream_event_sync({
                "type": EVENT_EFFECT_UPDATED,
                "project_id": project_id,
                "action": "effect_updated",
                "detail": {"track": track_name, "effect_idx": fx_idx},
                "ts": time.time() * 1000,
            })
        except Exception:
            pass
        return {"status": "updated", "effect_idx": fx_idx, "track": track_name, "project": result}
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except IndexError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/projects/{project_id}/tracks/{track_name}/effects/{fx_idx}")
async def delete_effect(project_id: str, track_name: str, fx_idx: int):
    """Delete an effect from a track's insert chain."""
    try:
        result = _pm.delete_effect(project_id, track_name, fx_idx)
        try:
            emit_stream_event_sync({
                "type": EVENT_EFFECT_REMOVED,
                "project_id": project_id,
                "action": "effect_removed",
                "detail": {"track": track_name, "effect_idx": fx_idx},
                "ts": time.time() * 1000,
            })
        except Exception:
            pass
        return {"status": "deleted", "effect_idx": fx_idx, "track": track_name, "project": result}
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except IndexError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ── Rendering Control ────────────────────────────────────────────────────────

def _run_render(job_id: str, yaml_path: Path, options: dict[str, Any], project_id: str) -> None:
    """Execute rendering in a background thread."""
    from vcmix.config.parser import parse_project
    from vcmix.engine.renderer import Renderer

    with _render_lock:
        _render_jobs[job_id]["status"] = "running"
        _render_jobs[job_id]["progress"] = 0

    t0 = time.time()
    try:
        cfg = parse_project(yaml_path)
        cfg.__dict__["_project_dir"] = yaml_path.parent.resolve()

        engine = Renderer(
            cfg,
            report=options.get("report", False),
            auto_fix=options.get("auto_fix", False),
            stream="dict",
            arrangement_aware=options.get("arrangement_aware", False),
            parallel=options.get("parallel", 1),
        )
        output_path = engine.run()
        events = engine.get_stream_events()
        elapsed = round(time.time() - t0, 2)

        with _render_lock:
            _render_jobs[job_id]["status"] = "completed"
            _render_jobs[job_id]["output_path"] = str(output_path)
            _render_jobs[job_id]["elapsed_s"] = elapsed
            _render_jobs[job_id]["progress"] = 100
            _render_jobs[job_id]["events"] = [e.to_dict() for e in events]

    except Exception as e:
        with _render_lock:
            _render_jobs[job_id]["status"] = "failed"
            _render_jobs[job_id]["error"] = str(e)
            _render_jobs[job_id]["elapsed_s"] = round(time.time() - t0, 2)


@router.post("/projects/{project_id}/render")
async def trigger_render(project_id: str, request: RenderTrigger, background_tasks: BackgroundTasks):
    """Trigger a render for a project."""
    filepath = _pm.get_filepath(project_id)
    if filepath is None:
        raise HTTPException(status_code=404, detail=f"Project not found: {project_id}")

    job_id = str(uuid.uuid4())[:8]

    with _render_lock:
        _render_jobs[job_id] = {
            "project_id": project_id,
            "status": "pending",
            "output_path": None,
            "elapsed_s": None,
            "progress": 0,
            "events": [],
            "error": None,
        }

    options = {
        "report": request.report,
        "auto_fix": request.auto_fix,
        "arrangement_aware": request.arrangement_aware,
        "parallel": request.parallel,
    }

    thread = threading.Thread(
        target=_run_render,
        args=(job_id, filepath, options, project_id),
        daemon=True,
    )
    thread.start()

    return {"job_id": job_id, "project_id": project_id, "status": "pending"}


@router.get("/projects/{project_id}/render/status")
async def get_render_status(project_id: str):
    """Get render status for a project."""
    # Find the most recent job for this project
    with _render_lock:
        project_jobs = [
            (jid, job) for jid, job in _render_jobs.items()
            if job.get("project_id") == project_id
        ]

    if not project_jobs:
        return {"project_id": project_id, "status": "no_render_jobs"}

    # Return the latest job
    job_id, job = project_jobs[-1]
    return {
        "project_id": project_id,
        "job_id": job_id,
        "status": job["status"],
        "progress": job.get("progress", 0),
        "output_path": job.get("output_path"),
        "elapsed_s": job.get("elapsed_s"),
        "error": job.get("error"),
    }


# ── Audio Analysis ───────────────────────────────────────────────────────────

@router.get("/projects/{project_id}/analysis")
async def get_analysis(project_id: str):
    """Get audio analysis data for a project."""
    filepath = _pm.get_filepath(project_id)
    if filepath is None:
        raise HTTPException(status_code=404, detail=f"Project not found: {project_id}")

    try:
        report = _analysis.analyze_project(filepath)
        return {"project_id": project_id, "analysis": report}
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Project file not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── AI Mixing ────────────────────────────────────────────────────────────────

@router.post("/ai/mix")
async def ai_mix(request: AIMixRequest, project_id: Optional[str] = None):
    """
    Generate AI mixing suggestions.

    If project_id is provided, analyzes that project.
    Otherwise, requires analysis data in request body.
    """
    analysis_data: dict[str, Any] = {}
    config_data: Optional[dict[str, Any]] = None

    if project_id:
        filepath = _pm.get_filepath(project_id)
        if filepath is None:
            raise HTTPException(status_code=404, detail=f"Project not found: {project_id}")
        try:
            analysis_data = _analysis.analyze_project(filepath)
            import yaml
            content = filepath.read_text(encoding="utf-8")
            config_data = yaml.safe_load(content)
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    else:
        analysis_data = {"tracks": [], "master": {}}

    mode = "one_click" if request.apply else request.mode
    result = _ai.mix(analysis_data, mode=mode, config=config_data)

    return {
        "mode": result.mode,
        "summary": result.summary,
        "suggestions": result.suggestions,
        "decision_log": result.decision_log,
        "applied": result.applied,
        "updated_config": result.updated_config,
    }


@router.post("/ai/mix/{project_id}")
async def ai_mix_project(project_id: str, request: AIMixRequest):
    """Generate AI mixing suggestions for a specific project."""
    filepath = _pm.get_filepath(project_id)
    if filepath is None:
        raise HTTPException(status_code=404, detail=f"Project not found: {project_id}")

    try:
        analysis_data = _analysis.analyze_project(filepath)
        import yaml
        content = filepath.read_text(encoding="utf-8")
        config_data = yaml.safe_load(content)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    mode = "one_click" if request.apply else request.mode
    result = _ai.mix(analysis_data, mode=mode, config=config_data)

    try:
        emit_stream_event_sync({
            "type": EVENT_AI_MIX_APPLIED,
            "project_id": project_id,
            "action": "ai_mix_applied",
            "detail": {"mode": mode, "applied": result.applied},
            "ts": time.time() * 1000,
        })
    except Exception:
        pass

    return {
        "project_id": project_id,
        "mode": result.mode,
        "summary": result.summary,
        "suggestions": result.suggestions,
        "decision_log": result.decision_log,
        "applied": result.applied,
        "updated_config": result.updated_config,
    }


@router.post("/ai/master")
async def ai_master(request: AIMasterRequest, project_id: Optional[str] = None):
    """
    Generate AI mastering suggestions.

    If project_id is provided, analyzes that project.
    Otherwise, returns generic mastering guidelines.
    """
    analysis_data: dict[str, Any] = {}
    config_data: Optional[dict[str, Any]] = None

    if project_id:
        filepath = _pm.get_filepath(project_id)
        if filepath is None:
            raise HTTPException(status_code=404, detail=f"Project not found: {project_id}")
        try:
            analysis_data = _analysis.analyze_project(filepath)
            import yaml
            content = filepath.read_text(encoding="utf-8")
            config_data = yaml.safe_load(content)
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    else:
        analysis_data = {"tracks": [], "master": {}}

    mode = "one_click" if request.apply else request.mode
    result = _ai.master(analysis_data, mode=mode, config=config_data)

    return {
        "mode": result.mode,
        "summary": result.summary,
        "suggestions": result.suggestions,
        "decision_log": result.decision_log,
        "applied": result.applied,
        "updated_config": result.updated_config,
    }


@router.post("/ai/master/{project_id}")
async def ai_master_project(project_id: str, request: AIMasterRequest):
    """Generate AI mastering suggestions for a specific project."""
    filepath = _pm.get_filepath(project_id)
    if filepath is None:
        raise HTTPException(status_code=404, detail=f"Project not found: {project_id}")

    try:
        analysis_data = _analysis.analyze_project(filepath)
        import yaml
        content = filepath.read_text(encoding="utf-8")
        config_data = yaml.safe_load(content)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    mode = "one_click" if request.apply else request.mode
    result = _ai.master(analysis_data, mode=mode, config=config_data)

    try:
        emit_stream_event_sync({
            "type": EVENT_AI_MASTER_APPLIED,
            "project_id": project_id,
            "action": "ai_master_applied",
            "detail": {"mode": mode, "applied": result.applied},
            "ts": time.time() * 1000,
        })
    except Exception:
        pass

    return {
        "project_id": project_id,
        "mode": result.mode,
        "summary": result.summary,
        "suggestions": result.suggestions,
        "decision_log": result.decision_log,
        "applied": result.applied,
        "updated_config": result.updated_config,
    }


# ── WebSocket: Render Progress ───────────────────────────────────────────────

@router.websocket("/ws/render/{project_id}")
async def ws_render_progress(websocket: WebSocket, project_id: str):
    """
    WebSocket endpoint for real-time render progress.

    Protocol:
        - Server sends JSON events: {"type": "progress", "percent": N, ...}
        - Client can send: {"action": "subscribe"} to start receiving
        - Heartbeat every 30 seconds
    """
    await _render_ws.connect(project_id, websocket)

    await websocket.send_text(json.dumps({
        "type": "connected",
        "project_id": project_id,
        "message": "Render progress WebSocket connected",
    }))

    try:
        while True:
            try:
                data = await asyncio.wait_for(websocket.receive_text(), timeout=30.0)
                try:
                    msg = json.loads(data)
                except json.JSONDecodeError:
                    await websocket.send_text(json.dumps({"type": "error", "message": "Invalid JSON"}))
                    continue

                action = msg.get("action", "")
                if action == "ping":
                    await websocket.send_text(json.dumps({"type": "pong"}))
                elif action == "status":
                    with _render_lock:
                        project_jobs = [
                            job for job in _render_jobs.values()
                            if job.get("project_id") == project_id
                        ]
                    status = "idle"
                    progress = 0
                    if project_jobs:
                        latest = project_jobs[-1]
                        status = latest["status"]
                        progress = latest.get("progress", 0)
                    await websocket.send_text(json.dumps({
                        "type": "render_status",
                        "status": status,
                        "progress": progress,
                    }))
                else:
                    await websocket.send_text(json.dumps({
                        "type": "error",
                        "message": f"Unknown action: {action}",
                    }))

            except asyncio.TimeoutError:
                await websocket.send_text(json.dumps({"type": "heartbeat"}))

    except WebSocketDisconnect:
        _render_ws.disconnect(project_id, websocket)


# ── WebSocket: AI Decision Stream ────────────────────────────────────────────

@router.websocket("/ws/ai/{project_id}")
async def ws_ai_decisions(websocket: WebSocket, project_id: str):
    """
    WebSocket endpoint for AI decision log streaming.

    Protocol:
        - Server sends AI decision events in real-time
        - Client can send: {"action": "mix"} to trigger AI analysis
        - Client can send: {"action": "master"} to trigger mastering analysis
    """
    await _ai_ws.connect(project_id, websocket)

    await websocket.send_text(json.dumps({
        "type": "connected",
        "project_id": project_id,
        "message": "AI decision WebSocket connected",
    }))

    try:
        while True:
            try:
                data = await asyncio.wait_for(websocket.receive_text(), timeout=30.0)
                try:
                    msg = json.loads(data)
                except json.JSONDecodeError:
                    await websocket.send_text(json.dumps({"type": "error", "message": "Invalid JSON"}))
                    continue

                action = msg.get("action", "")

                if action == "ping":
                    await websocket.send_text(json.dumps({"type": "pong"}))

                elif action == "mix":
                    filepath = _pm.get_filepath(project_id)
                    if filepath is None:
                        await websocket.send_text(json.dumps({
                            "type": "error",
                            "message": f"Project not found: {project_id}",
                        }))
                        continue
                    try:
                        analysis_data = _analysis.analyze_project(filepath)
                        result = _ai.mix(analysis_data, mode="step")
                        for log_entry in result.decision_log:
                            await websocket.send_text(json.dumps({
                                "type": "ai_decision",
                                "step": log_entry["step"],
                                "target": log_entry["target"],
                                "action": log_entry["action"],
                                "reason": log_entry["reason"],
                            }))
                        await websocket.send_text(json.dumps({
                            "type": "mix_complete",
                            "summary": result.summary,
                            "suggestion_count": len(result.suggestions),
                        }))
                    except Exception as e:
                        await websocket.send_text(json.dumps({
                            "type": "error",
                            "message": str(e),
                        }))

                elif action == "master":
                    filepath = _pm.get_filepath(project_id)
                    if filepath is None:
                        await websocket.send_text(json.dumps({
                            "type": "error",
                            "message": f"Project not found: {project_id}",
                        }))
                        continue
                    try:
                        analysis_data = _analysis.analyze_project(filepath)
                        result = _ai.master(analysis_data, mode="step")
                        for log_entry in result.decision_log:
                            await websocket.send_text(json.dumps({
                                "type": "ai_decision",
                                "step": log_entry["step"],
                                "target": log_entry["target"],
                                "action": log_entry["action"],
                                "reason": log_entry["reason"],
                            }))
                        await websocket.send_text(json.dumps({
                            "type": "master_complete",
                            "summary": result.summary,
                            "suggestion_count": len(result.suggestions),
                        }))
                    except Exception as e:
                        await websocket.send_text(json.dumps({
                            "type": "error",
                            "message": str(e),
                        }))

                else:
                    await websocket.send_text(json.dumps({
                        "type": "error",
                        "message": f"Unknown action: {action}",
                    }))

            except asyncio.TimeoutError:
                await websocket.send_text(json.dumps({"type": "heartbeat"}))

    except WebSocketDisconnect:
        _ai_ws.disconnect(project_id, websocket)


# ── Phase 12: Arrangement Template & Mix Preset Endpoints ────────────────────

class ArrangementSuggestRequest(BaseModel):
    """Request body for AI arrangement suggestions."""
    genre: str = Field(default="pop", description="Target genre")
    duration: Optional[float] = Field(default=None, description="Target duration in seconds")
    mood: str = Field(default="neutral", description="Mood: neutral/upbeat/mellow/dark/epic")


class MixPresetSuggestRequest(BaseModel):
    """Request body for mix preset suggestions."""
    genre: str = Field(default="pop", description="Target genre")
    track_types: Optional[list[str]] = Field(default=None, description="Track types present")


@router.post("/ai/arrangement")
async def ai_arrangement_suggestion(request: ArrangementSuggestRequest):
    """
    Get AI arrangement template suggestion.

    Recommends an arrangement template based on genre, duration, and mood,
    including suggested BPM, key, and section structure.
    """
    result = _ai.suggest_arrangement(
        genre=request.genre,
        duration=request.duration,
        mood=request.mood,
    )
    return result


@router.get("/presets/arrangement")
async def list_arrangement_presets():
    """
    List all available arrangement templates.

    Returns template names, genres, section counts, and BPM ranges.
    """
    from vcmix.arrangement.templates import TEMPLATE_REGISTRY, list_templates

    templates = []
    for key in list_templates():
        tmpl = TEMPLATE_REGISTRY[key]
        templates.append({
            "key": key,
            "name": tmpl.name,
            "genre": tmpl.genre,
            "sections": len(tmpl.structure),
            "section_names": tmpl.section_names,
            "total_bars": tmpl.total_bars,
            "bpm_range": list(tmpl.bpm_range),
            "default_key": tmpl.default_key,
            "description": tmpl.description,
        })
    return {"templates": templates, "count": len(templates)}


@router.get("/presets/arrangement/{key}")
async def get_arrangement_preset(key: str):
    """Get detailed arrangement template by key."""
    from vcmix.arrangement.templates import get_template

    tmpl = get_template(key)
    if tmpl is None:
        raise HTTPException(status_code=404, detail=f"Arrangement template not found: {key}")

    return {
        "key": key,
        "template": tmpl.to_dict(),
    }


@router.get("/presets/mix")
async def list_mix_presets_endpoint():
    """
    List all available mix presets.

    Returns preset names, genres, track types, and descriptions.
    """
    from vcmix.presets.mix_presets import MIX_PRESET_REGISTRY, list_mix_presets

    presets = []
    for key in list_mix_presets():
        preset = MIX_PRESET_REGISTRY[key]
        presets.append({
            "key": key,
            "name": preset.name,
            "genre": preset.genre,
            "description": preset.description,
            "track_types": preset.track_types,
            "master_target_lufs": preset.master.target_lufs,
        })
    return {"presets": presets, "count": len(presets)}


@router.get("/presets/mix/{key}")
async def get_mix_preset_detail(key: str):
    """Get detailed mix preset by key."""
    from vcmix.presets.mix_presets import get_mix_preset

    preset = get_mix_preset(key)
    if preset is None:
        raise HTTPException(status_code=404, detail=f"Mix preset not found: {key}")

    return {
        "key": key,
        "preset": preset.to_dict(),
    }


@router.post("/ai/mix-preset")
async def ai_mix_preset_suggestion(request: MixPresetSuggestRequest):
    """
    Get AI mix preset suggestion.

    Recommends a mix preset based on genre and track types.
    """
    result = _ai.suggest_mix_preset(
        genre=request.genre,
        track_types=request.track_types,
    )
    return result


# ── Phase 15: AI Composition & Smart Mixing Endpoints ──────────────────────

class ComposeRequest(BaseModel):
    """Request body for AI composition."""
    genre: str = Field(default="pop", description="Genre: pop/rock/edm/hiphop/rnb/ballad")
    duration: float = Field(default=180.0, ge=10.0, le=600.0, description="Target duration in seconds")
    bpm: float = Field(default=120.0, ge=40.0, le=300.0, description="Tempo in BPM")
    key: str = Field(default="C", description="Musical key (e.g. C, Am, D Major)")
    mood: str = Field(default="happy", description="Mood: happy/sad/energetic/calm/dark/bright")
    reference: Optional[str] = Field(default=None, description="Reference track path")


class AutoMixRequest(BaseModel):
    """Request body for smart mixing closed-loop."""
    max_iterations: int = Field(default=3, ge=1, le=10, description="Maximum mixing iterations")
    target_lufs: float = Field(default=-14.0, description="Target LUFS")


class ComposeAndMixRequest(BaseModel):
    """Request body for one-click compose + mix."""
    genre: str = Field(default="pop", description="Genre")
    duration: float = Field(default=180.0, ge=10.0, le=600.0, description="Target duration in seconds")
    bpm: float = Field(default=120.0, ge=40.0, le=300.0, description="Tempo in BPM")
    key: str = Field(default="C", description="Musical key")
    mood: str = Field(default="happy", description="Mood")
    max_mix_iterations: int = Field(default=3, ge=1, le=10, description="Maximum mixing iterations")


@router.post("/ai/compose")
async def ai_compose(request: ComposeRequest):
    """
    AI composition engine — generate a complete arrangement.

    Creates a VCMix project configuration with chord progression, melody,
    drum patterns, bass lines, and instrument assignments based on the
    specified genre, key, BPM, and mood.
    """
    from vcmix.ai.composer import AIComposer

    try:
        composer = AIComposer()
        result = composer.compose(
            genre=request.genre,
            duration=request.duration,
            bpm=request.bpm,
            key=request.key,
            mood=request.mood,
            reference=request.reference,
        )
        return {
            "status": "success",
            "composition": result.to_dict(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/ai/auto-mix/{project_id}")
async def ai_auto_mix(project_id: str, request: AutoMixRequest):
    """
    Smart mixing closed-loop — auto-iterate to optimize a project's mix.

    Runs render→analyze→diagnose→adjust→verify iterations to optimize
    the mix toward target loudness, spectral balance, and dynamic range.
    """
    from vcmix.ai.smart_mixer import SmartMixer

    filepath = _pm.get_filepath(project_id)
    if filepath is None:
        raise HTTPException(status_code=404, detail=f"Project not found: {project_id}")

    try:
        mixer = SmartMixer(target_lufs=request.target_lufs)
        result = mixer.auto_mix(
            project_config=str(filepath),
            max_iterations=request.max_iterations,
        )
        return {
            "status": "success",
            "project_id": project_id,
            "mix_result": result.to_dict(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/ai/compose-and-mix")
async def ai_compose_and_mix(request: ComposeAndMixRequest):
    """
    One-click compose + mix — AI composition with smart mixing.

    Generates a complete arrangement and automatically optimizes the mix
    in a single pipeline.
    """
    from vcmix.ai.arrangement_mixer import ArrangementMixer

    try:
        am = ArrangementMixer()
        result = am.compose_and_mix(
            genre=request.genre,
            duration=request.duration,
            bpm=request.bpm,
            key=request.key,
            mood=request.mood,
            max_mix_iterations=request.max_mix_iterations,
        )
        return {
            "status": result.status,
            "result": result.to_dict(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
