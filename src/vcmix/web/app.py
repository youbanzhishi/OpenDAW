"""
app.py — FastAPI application for VCMix Web UI (Phase 13).

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

Phase 13 — Visualization API (heavy, lazy-loaded in core profile):
    GET  /api/v1/waveform/{project_id}/{track} — Waveform peak data
    GET  /api/v1/spectrum/{project_id}/{track}  — FFT spectrum data
    GET  /api/v1/midi/{project_id}/{track}      — MIDI note data

Phase 17 — AI Transcription API (heavy, lazy-loaded in core profile):
    POST /api/v1/ai/transcribe    — AI transcription
    POST /api/v1/ai/style-match   — Reference style matching
    POST /api/v1/ai/style-transfer — Style transfer
    POST /api/v1/ai/remix         — One-click Remix

Phase 18 — Collaboration API (heavy, lazy-loaded in core profile):
    POST /api/v1/projects/{id}/export         — Export project audio
    POST /api/v1/projects/{id}/export-stems    — Export stems
    POST /api/v1/projects/{id}/snapshots       — Create snapshot
    GET  /api/v1/projects/{id}/snapshots       — List snapshots
    POST /api/v1/projects/{id}/snapshots/{sid}/restore — Restore snapshot
    WS   /ws/collab/{project_id}              — Collaboration WebSocket

Profile support:
    profile="core" — Only lightweight routes (render/plugins/presets/midi/
                     automation/arrangement/automix + agent_api basic endpoints)
    profile="full" — All routes including heavy AI/collaboration/visualization

The frontend is served from /static/ (minimal HTML+JS, no framework).

Usage:
    uvicorn vcmix.web.app:app --reload --port 8000

Dependencies: fastapi, uvicorn, websockets
"""

from __future__ import annotations

import os as _os
from pathlib import Path
from typing import Literal

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

# ── Lightweight routes: always imported ───────────────────────────────────
from vcmix.web.routes import arrangement, automation, automix, midi, plugins, presets, render
from vcmix.web.routes.agent_api import router as agent_router
from vcmix.web.websocket import router as ws_router

# ── Heavy routes: only imported when profile="full" ──────────────────────
# These import heavy dependencies (numpy waveform, collaboration manager,
# AI transcription modules) and are deferred in core profile.

_HEAVY_ROUTES_AVAILABLE: bool = True

try:
    from vcmix.web.routes.ai_transcription import router as ai_transcription_router
    from vcmix.web.routes.collaboration import router as collab_router
    from vcmix.web.routes.piano_roll import router as piano_roll_router
    from vcmix.web.routes.waveform import router as waveform_router
except ImportError:
    _HEAVY_ROUTES_AVAILABLE = False


# ── Application Factory ──────────────────────────────────────────────────

def create_app(
    profile: Literal["core", "full"] = "full",
) -> FastAPI:
    """Create and configure the VCMix FastAPI application.

    Args:
        profile: "core" for lightweight mode (no AI/collaboration/visualization
                 routes, ~40% less memory), "full" for all features.
                 Default is "full" for backward compatibility.
    """
    app = FastAPI(
        title="VCMix Web API",
        description=(
            f"AI-native open-source DAW — REST API + WebSocket. "
            f"Phase 18: Collaboration, multi-format export, stem export, and project versioning. "
            f"[Profile: {profile}]"
        ),
        version="0.18.0",
        docs_url="/api/docs",
        redoc_url="/api/redoc",
    )

    # Store profile on app state for introspection
    app.state.profile = profile

    # ── Register API routers (Phase 8-9) — always loaded ──
    app.include_router(render.router, prefix="/api", tags=["render"])
    app.include_router(plugins.router, prefix="/api", tags=["plugins"])
    app.include_router(presets.router, prefix="/api", tags=["presets"])
    app.include_router(arrangement.router, prefix="/api", tags=["arrangement"])
    app.include_router(automix.router, prefix="/api", tags=["automix"])
    app.include_router(midi.router, prefix="/api", tags=["midi"])
    app.include_router(automation.router, prefix="/api", tags=["automation"])
    app.include_router(ws_router, prefix="/api", tags=["stream"])

    # ── Register Phase 11 AI Agent API — always loaded ──
    app.include_router(agent_router, prefix="/api/v1", tags=["agent-api"])

    # ── Register heavy routes — only in full profile ──
    if profile == "full":
        if _HEAVY_ROUTES_AVAILABLE:
            # Phase 17 AI Transcription API
            app.include_router(ai_transcription_router, prefix="/api/v1", tags=["ai-transcription"])
            # Phase 18 Collaboration & Export API
            app.include_router(collab_router, prefix="/api/v1", tags=["collaboration-export"])
            # Phase 13 Visualization API
            app.include_router(waveform_router, prefix="/api/v1", tags=["visualization"])
            app.include_router(piano_roll_router, prefix="/api/v1", tags=["visualization"])
        else:
            import logging
            logging.getLogger("vcmix").warning(
                "Heavy route dependencies not available — "
                "AI transcription, collaboration, and visualization endpoints disabled. "
                "Install with: pip install vcmix[web,ai]"
            )
    else:
        # core profile: register stub endpoints that return 501 for heavy routes
        _register_core_stubs(app)

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
        return {"status": "ok", "version": "0.17.0", "profile": profile}

    return app


def _register_core_stubs(app: FastAPI) -> None:
    """Register stub endpoints for heavy routes in core profile.

    Returns HTTP 501 Not Implemented with a message explaining how
    to enable the feature by switching to full profile.
    """
    from fastapi import APIRouter
    from fastapi.responses import JSONResponse

    stub_router = APIRouter()

    # AI Transcription stubs
    @stub_router.post("/ai/transcribe", include_in_schema=False)
    @stub_router.post("/ai/style-match", include_in_schema=False)
    @stub_router.post("/ai/style-transfer", include_in_schema=False)
    @stub_router.post("/ai/remix", include_in_schema=False)
    async def _ai_stub():
        return JSONResponse(
            status_code=501,
            content={
                "detail": "AI endpoints not available in core profile. "
                          "Use --profile full or VCMIX_PROFILE=full to enable.",
            },
        )

    # Collaboration stubs
    @stub_router.post("/projects/{project_id}/export", include_in_schema=False)
    @stub_router.post("/projects/{project_id}/export-stems", include_in_schema=False)
    @stub_router.post("/projects/{project_id}/snapshots", include_in_schema=False)
    @stub_router.get("/projects/{project_id}/snapshots", include_in_schema=False)
    @stub_router.post("/projects/{project_id}/snapshots/{snapshot_id}/restore", include_in_schema=False)
    async def _collab_stub():
        return JSONResponse(
            status_code=501,
            content={
                "detail": "Collaboration/export endpoints not available in core profile. "
                          "Use --profile full or VCMIX_PROFILE=full to enable.",
            },
        )

    # Visualization stubs
    @stub_router.get("/waveform/{project_id}/{track}", include_in_schema=False)
    @stub_router.get("/spectrum/{project_id}/{track}", include_in_schema=False)
    @stub_router.get("/midi/{project_id}/{track}", include_in_schema=False)
    async def _viz_stub():
        return JSONResponse(
            status_code=501,
            content={
                "detail": "Visualization endpoints not available in core profile. "
                          "Use --profile full or VCMIX_PROFILE=full to enable.",
            },
        )

    app.include_router(stub_router, prefix="/api/v1", tags=["core-stubs"])


# ── Module-level app instance for uvicorn ──
# Uses VCMIX_PROFILE environment variable; defaults to "full" for backward compat.
_profile = _os.environ.get("VCMIX_PROFILE", "full")
app = create_app(profile=_profile)  # type: ignore[arg-type]
