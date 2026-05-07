"""
app.py — FastAPI application for VCMix Web UI (Phase 11).

Provides REST API endpoints that wrap the VCMix core engine,
sharing the same rendering pipeline as the CLI — no code duplication.

Endpoints:
    POST /api/render           — Trigger a render
    GET  /api/render/{job_id}  — Get render job status
    GET  /api/plugins          — List all plugins + parameters
    GET  /api/plugins/{name}   — Get plugin details
    GET  /api/presets          — List all presets
    GET  /api/presets/{name}   — Get preset details
    GET  /api/presets/chains   — List chain presets (Phase 9)
    GET  /api/presets/chains/{name} — Chain preset detail (Phase 9)
    POST /api/presets/chains/{name}/apply — Apply chain preset (Phase 9)
    GET  /api/midi/scan        — Scan for MIDI files (Phase 9)
    POST /api/midi/parse       — Parse MIDI file (Phase 9)
    GET  /api/midi/synths      — List synthesizers (Phase 9)
    POST /api/automation/preview — Preview automation curve (Phase 9)
    POST /api/automation/apply   — Apply automation to track (Phase 9)
    POST /api/validate         — Validate a YAML config
    GET  /api/arrangement      — Analyze arrangement structure
    GET  /api/arrangement/strategy — Get arrangement mixing strategy
    POST /api/automix          — Run auto-mixing
    WS   /api/stream           — WebSocket DataStream forwarding

Phase 11 — AI Agent API:
    GET  /api/v1/projects      — List projects
    POST /api/v1/projects      — Create project
    GET  /api/v1/projects/{id} — Get project
    PUT  /api/v1/projects/{id} — Update project
    DELETE /api/v1/projects/{id} — Delete project
    POST /api/v1/projects/{id}/tracks — Add track
    PUT  /api/v1/projects/{id}/tracks/{name} — Update track
    DELETE /api/v1/projects/{id}/tracks/{name} — Delete track
    POST /api/v1/projects/{id}/tracks/{name}/effects — Add effect
    PUT  /api/v1/projects/{id}/tracks/{name}/effects/{idx} — Update effect
    DELETE /api/v1/projects/{id}/tracks/{name}/effects/{idx} — Delete effect
    POST /api/v1/projects/{id}/render — Trigger render
    GET  /api/v1/projects/{id}/render/status — Render status
    GET  /api/v1/projects/{id}/analysis — Audio analysis
    POST /api/v1/ai/mix        — AI mixing suggestions
    POST /api/v1/ai/master     — AI mastering suggestions
    WS   /ws/render/{id}       — Render progress WebSocket
    WS   /ws/ai/{id}           — AI decision WebSocket

The frontend is served from /static/ (minimal HTML+JS, no framework).

Usage:
    uvicorn vcmix.web.app:app --reload --port 8000

Dependencies: fastapi, uvicorn, websockets
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from vcmix.web.routes import arrangement, automation, automix, midi, plugins, presets, render
from vcmix.web.routes.agent_api import router as agent_router
from vcmix.web.websocket import router as ws_router

# ── Application Factory ──────────────────────────────────────────────────

def create_app() -> FastAPI:
    """Create and configure the VCMix FastAPI application."""
    app = FastAPI(
        title="VCMix Web API",
        description=(
            "AI-native open-source DAW — REST API + WebSocket. "
            "Phase 11: AI Agent API with project CRUD, rendering control, and AI mixing decisions."
        ),
        version="0.11.0",
        docs_url="/api/docs",
        redoc_url="/api/redoc",
    )

    # ── Register API routers (Phase 8-9) ──
    app.include_router(render.router, prefix="/api", tags=["render"])
    app.include_router(plugins.router, prefix="/api", tags=["plugins"])
    app.include_router(presets.router, prefix="/api", tags=["presets"])
    app.include_router(arrangement.router, prefix="/api", tags=["arrangement"])
    app.include_router(automix.router, prefix="/api", tags=["automix"])
    app.include_router(midi.router, prefix="/api", tags=["midi"])
    app.include_router(automation.router, prefix="/api", tags=["automation"])
    app.include_router(ws_router, prefix="/api", tags=["stream"])

    # ── Register Phase 11 AI Agent API ──
    app.include_router(agent_router, prefix="/api/v1", tags=["agent-api"])

    # ── Static frontend ──
    static_dir = Path(__file__).parent / "static"
    if static_dir.exists():
        app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    # ── Root → index.html ──
    @app.get("/", include_in_schema=False)
    async def root():
        index = static_dir / "index.html"
        if index.exists():
            return FileResponse(str(index))
        return {"message": "VCMix Web API running. See /api/docs for documentation."}

    # ── Health check ──
    @app.get("/api/health", tags=["system"])
    async def health():
        return {"status": "ok", "version": "0.11.0"}

    return app


# ── Module-level app instance for uvicorn ──
app = create_app()
