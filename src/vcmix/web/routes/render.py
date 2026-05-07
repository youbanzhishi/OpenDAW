"""
render.py — /api/render endpoints for VCMix Web UI.

Triggers rendering and provides job status tracking.
Shares the same Renderer engine as the CLI.
"""

from __future__ import annotations

import uuid
import threading
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field

from vcmix.config.parser import parse_project
from vcmix.engine.renderer import Renderer

router = APIRouter()

# ── In-memory job store (simple; use Redis/DB for production) ────────────

_jobs: dict[str, dict[str, Any]] = {}
_job_lock = threading.Lock()


# ── Request/Response Models ──────────────────────────────────────────────

class RenderRequest(BaseModel):
    """Request body for triggering a render."""
    project_yaml: str = Field(
        ..., description="YAML project configuration as string"
    )
    report: bool = Field(default=False, description="Generate per-step analysis report")
    auto_fix: bool = Field(default=False, description="Enable auto-fix for gain staging")
    ab_mode: bool = Field(default=False, description="Render A/B comparison versions")
    ab_diff: bool = Field(default=False, description="Include difference analysis in A/B mode")
    arrangement_aware: bool = Field(
        default=False, description="Enable arrangement-aware rendering (Phase 7)"
    )


class RenderResponse(BaseModel):
    """Response for a render request."""
    job_id: str
    status: str
    message: str


class RenderStatusResponse(BaseModel):
    """Response for render job status."""
    job_id: str
    status: str  # pending | running | completed | failed
    output_path: str | None = None
    elapsed_s: float | None = None
    events: list[dict[str, Any]] = []
    error: str | None = None


# ── Background render task ───────────────────────────────────────────────

def _run_render(job_id: str, yaml_path: Path, options: dict[str, Any]) -> None:
    """Execute rendering in a background thread."""
    import time

    with _job_lock:
        _jobs[job_id]["status"] = "running"

    t0 = time.time()
    try:
        cfg = parse_project(yaml_path)
        cfg.__dict__["_project_dir"] = yaml_path.parent.resolve()

        engine = Renderer(
            cfg,
            report=options.get("report", False),
            auto_fix=options.get("auto_fix", False),
            stream="dict",  # accumulate events for status polling
            ab_mode=options.get("ab_mode", False),
            ab_diff=options.get("ab_diff", False),
            arrangement_aware=options.get("arrangement_aware", False),
        )
        output_path = engine.run()
        events = engine.get_stream_events()
        elapsed = round(time.time() - t0, 2)

        with _job_lock:
            _jobs[job_id]["status"] = "completed"
            _jobs[job_id]["output_path"] = str(output_path)
            _jobs[job_id]["elapsed_s"] = elapsed
            _jobs[job_id]["events"] = [e.to_dict() for e in events]

    except Exception as e:
        with _job_lock:
            _jobs[job_id]["status"] = "failed"
            _jobs[job_id]["error"] = str(e)
            _jobs[job_id]["elapsed_s"] = round(time.time() - t0, 2)


# ── Endpoints ────────────────────────────────────────────────────────────

@router.post("/render", response_model=RenderResponse)
async def trigger_render(
    request: RenderRequest,
    background_tasks: BackgroundTasks,
):
    """
    Trigger a rendering job from YAML configuration.

    The YAML is written to a temp file and rendered asynchronously.
    Poll /api/render/{job_id} for status.
    """
    import tempfile
    import os

    job_id = str(uuid.uuid4())[:8]

    # Write YAML to temp directory
    tmp_dir = Path(tempfile.mkdtemp(prefix="vcmix_render_"))
    yaml_path = tmp_dir / "project.yaml"
    yaml_path.write_text(request.project_yaml, encoding="utf-8")

    with _job_lock:
        _jobs[job_id] = {
            "status": "pending",
            "output_path": None,
            "elapsed_s": None,
            "events": [],
            "error": None,
            "tmp_dir": str(tmp_dir),
        }

    options = {
        "report": request.report,
        "auto_fix": request.auto_fix,
        "ab_mode": request.ab_mode,
        "ab_diff": request.ab_diff,
        "arrangement_aware": request.arrangement_aware,
    }

    # Run in background thread
    thread = threading.Thread(
        target=_run_render,
        args=(job_id, yaml_path, options),
        daemon=True,
    )
    thread.start()

    return RenderResponse(
        job_id=job_id,
        status="pending",
        message="Render job started. Poll /api/render/{job_id} for status.",
    )


@router.post("/render/file", response_model=RenderResponse)
async def trigger_render_file(
    project_path: str,
    report: bool = False,
    auto_fix: bool = False,
    ab_mode: bool = False,
    ab_diff: bool = False,
    arrangement_aware: bool = False,
    background_tasks: BackgroundTasks = None,
):
    """
    Trigger a rendering job from a file path on the server.

    This is useful for AI Agents that have file-system access.
    """
    yaml_path = Path(project_path)
    if not yaml_path.exists():
        raise HTTPException(status_code=404, detail=f"Project file not found: {project_path}")

    job_id = str(uuid.uuid4())[:8]

    with _job_lock:
        _jobs[job_id] = {
            "status": "pending",
            "output_path": None,
            "elapsed_s": None,
            "events": [],
            "error": None,
            "tmp_dir": None,
        }

    options = {
        "report": report,
        "auto_fix": auto_fix,
        "ab_mode": ab_mode,
        "ab_diff": ab_diff,
        "arrangement_aware": arrangement_aware,
    }

    thread = threading.Thread(
        target=_run_render,
        args=(job_id, yaml_path, options),
        daemon=True,
    )
    thread.start()

    return RenderResponse(
        job_id=job_id,
        status="pending",
        message="Render job started. Poll /api/render/{job_id} for status.",
    )


@router.get("/render/{job_id}", response_model=RenderStatusResponse)
async def get_render_status(job_id: str):
    """Get the status of a rendering job."""
    with _job_lock:
        job = _jobs.get(job_id)

    if job is None:
        raise HTTPException(status_code=404, detail=f"Job not found: {job_id}")

    return RenderStatusResponse(
        job_id=job_id,
        status=job["status"],
        output_path=job.get("output_path"),
        elapsed_s=job.get("elapsed_s"),
        events=job.get("events", []),
        error=job.get("error"),
    )


@router.get("/render/{job_id}/events")
async def get_render_events(job_id: str):
    """Get DataStream events for a completed or running job."""
    with _job_lock:
        job = _jobs.get(job_id)

    if job is None:
        raise HTTPException(status_code=404, detail=f"Job not found: {job_id}")

    return {"job_id": job_id, "events": job.get("events", [])}
