"""
collaboration.py — Collaboration and export API routes for VCMix (Phase 18).

REST endpoints:
    POST /api/v1/projects/{id}/export         — Export project audio
    POST /api/v1/projects/{id}/export-stems    — Export stems
    POST /api/v1/projects/{id}/snapshots       — Create snapshot
    GET  /api/v1/projects/{id}/snapshots       — List snapshots
    POST /api/v1/projects/{id}/snapshots/{sid}/restore — Restore snapshot
    WS   /ws/collab/{project_id}              — Collaboration WebSocket
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Optional, Union

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

from vcmix.export.exporter import AudioExporter
from vcmix.project.version_manager import ProjectVersionManager
from vcmix.web.collaboration import get_collaboration_manager
from vcmix.web.project_manager import ProjectManager

router = APIRouter()

# ── Shared service instances ──────────────────────────────────────────────

_pm = ProjectManager()
_exporter = AudioExporter()
_vm = ProjectVersionManager()


# ── Pydantic Models ──────────────────────────────────────────────────────

class ExportRequest(BaseModel):
    """Request body for project audio export."""
    format: str = Field(default="wav", description="Output format: wav/mp3/flac/ogg")
    quality: Optional[dict[str, Any]] = Field(default=None, description="Quality settings")
    output_path: Optional[str] = Field(default=None, description="Output file path")


class ExportStemsRequest(BaseModel):
    """Request body for stem export."""
    format: str = Field(default="wav", description="Output format: wav/mp3/flac/ogg")
    quality: Optional[dict[str, Any]] = Field(default=None, description="Quality settings")
    output_dir: Optional[str] = Field(default=None, description="Output directory")
    by_bus: bool = Field(default=False, description="Group by bus instead of per-track")


class SnapshotCreateRequest(BaseModel):
    """Request body for creating a snapshot."""
    message: str = Field(default="", description="Snapshot description")


# ── Export Endpoints ──────────────────────────────────────────────────────

@router.post("/projects/{project_id}/export")
async def export_project(project_id: str, request: ExportRequest):
    """Export a project to the specified audio format.

    Renders the project and converts to the target format.
    """
    filepath = _pm.get_filepath(project_id)
    if filepath is None:
        raise HTTPException(status_code=404, detail=f"Project not found: {project_id}")

    try:
        # First render the project to WAV
        from vcmix.config.parser import parse_project
        from vcmix.engine.renderer import Renderer

        cfg = parse_project(filepath)
        cfg.__dict__["_project_dir"] = filepath.parent.resolve()

        engine = Renderer(cfg, stream="none")
        wav_output = engine.run()

        if wav_output is None:
            raise HTTPException(status_code=500, detail="Render produced no output")

        # Export to target format
        fmt = request.format.lower()
        if request.output_path:
            output_path = request.output_path
        else:
            output_path = str(Path(wav_output).with_suffix(f".{fmt}"))

        result = _exporter.export(
            input_wav=str(wav_output),
            output_path=output_path,
            format=fmt,
            quality=request.quality,
        )

        return {
            "status": "exported",
            "project_id": project_id,
            "format": fmt,
            "output_path": result,
        }

    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/projects/{project_id}/export-stems")
async def export_stems(project_id: str, request: ExportStemsRequest):
    """Export project stems (per-track or per-bus).

    Each track or bus is exported as a separate audio file.
    """
    filepath = _pm.get_filepath(project_id)
    if filepath is None:
        raise HTTPException(status_code=404, detail=f"Project not found: {project_id}")

    try:
        fmt = request.format.lower()
        if request.output_dir:
            output_dir = request.output_dir
        else:
            output_dir = str(Path(filepath).parent / "stems")

        if request.by_bus:
            results = _exporter.export_stems_by_bus(
                project_yaml=str(filepath),
                output_dir=output_dir,
                format=fmt,
                quality=request.quality,
            )
        else:
            results = _exporter.export_stems(
                project_yaml=str(filepath),
                output_dir=output_dir,
                format=fmt,
                quality=request.quality,
            )

        return {
            "status": "exported",
            "project_id": project_id,
            "format": fmt,
            "by_bus": request.by_bus,
            "stems": results,
            "count": len(results),
        }

    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Snapshot Endpoints ────────────────────────────────────────────────────

@router.post("/projects/{project_id}/snapshots", status_code=201)
async def create_snapshot(project_id: str, request: SnapshotCreateRequest):
    """Create a project snapshot (version save)."""
    filepath = _pm.get_filepath(project_id)
    if filepath is None:
        raise HTTPException(status_code=404, detail=f"Project not found: {project_id}")

    try:
        snapshot_id = _vm.create_snapshot(
            project_yaml=str(filepath),
            message=request.message,
        )
        return {
            "status": "created",
            "project_id": project_id,
            "snapshot_id": snapshot_id,
            "message": request.message,
        }
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/projects/{project_id}/snapshots")
async def list_snapshots(project_id: str):
    """List all snapshots for a project."""
    snapshots = _vm.list_snapshots(project_id)
    return {
        "project_id": project_id,
        "snapshots": snapshots,
        "count": len(snapshots),
    }


@router.post("/projects/{project_id}/snapshots/{snapshot_id}/restore")
async def restore_snapshot(project_id: str, snapshot_id: str):
    """Restore a project to a specific snapshot."""
    try:
        restored_path = _vm.restore_snapshot(
            project_id=project_id,
            snapshot_id=snapshot_id,
            projects_dir=_pm.projects_dir,
        )
        return {
            "status": "restored",
            "project_id": project_id,
            "snapshot_id": snapshot_id,
            "restored_path": restored_path,
        }
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Collaboration WebSocket ───────────────────────────────────────────────

@router.websocket("/collab/{project_id}")
async def collaboration_websocket(websocket: WebSocket, project_id: str):
    """WebSocket endpoint for real-time collaborative editing.

    Protocol:
        Client → Server messages:
            {"type": "join", "user_id": "alice"}
            {"type": "change", "user_id": "alice", "change": {...}}
            {"type": "leave", "user_id": "alice"}
            {"type": "sync_request", "user_id": "alice"}

        Server → Client messages:
            {"type": "joined", "users": [...], "state": {...}}
            {"type": "user_joined", "user_id": "bob", "users": [...]}
            {"type": "user_left", "user_id": "bob", "users": [...]}
            {"type": "change", "change": {...}}
            {"type": "sync", "state": {...}, "history": [...]}
            {"type": "conflict", "resolution": "...", ...}
    """
    collab = get_collaboration_manager()

    await websocket.accept()

    user_id = None

    try:
        while True:
            import asyncio
            try:
                data = await asyncio.wait_for(websocket.receive_text(), timeout=30.0)
                try:
                    msg = json.loads(data)
                except json.JSONDecodeError:
                    await websocket.send_text(json.dumps({
                        "type": "error",
                        "message": "Invalid JSON",
                    }))
                    continue

                msg_type = msg.get("type", "")

                if msg_type == "join":
                    user_id = msg.get("user_id", "anonymous")
                    result = await collab.join_room(project_id, user_id, websocket)
                    # Send acknowledgment
                    await websocket.send_text(json.dumps({
                        "type": "join_ack",
                        "user_id": user_id,
                        "room_info": result,
                    }))

                elif msg_type == "change":
                    if user_id is None:
                        await websocket.send_text(json.dumps({
                            "type": "error",
                            "message": "Must join room before sending changes",
                        }))
                        continue
                    change = msg.get("change", {})
                    result = await collab.broadcast_change(
                        project_id, user_id, change,
                    )
                    # Send acknowledgment to sender
                    await websocket.send_text(json.dumps({
                        "type": "change_ack",
                        "status": result.get("status"),
                        "timestamp": time.time(),
                    }))

                elif msg_type == "sync_request":
                    if user_id is None:
                        await websocket.send_text(json.dumps({
                            "type": "error",
                            "message": "Must join room before requesting sync",
                        }))
                        continue
                    await collab.sync_room(project_id, user_id)

                elif msg_type == "leave":
                    if user_id:
                        await collab.leave_room(project_id, user_id)
                        user_id = None

                elif msg_type == "ping":
                    await websocket.send_text(json.dumps({"type": "pong"}))

                else:
                    await websocket.send_text(json.dumps({
                        "type": "error",
                        "message": f"Unknown message type: {msg_type}",
                    }))

            except asyncio.TimeoutError:
                # Heartbeat
                await websocket.send_text(json.dumps({
                    "type": "heartbeat",
                    "timestamp": time.time(),
                }))

    except WebSocketDisconnect:
        if user_id:
            await collab.leave_room(project_id, user_id)
    except Exception:
        if user_id:
            await collab.leave_room(project_id, user_id)
