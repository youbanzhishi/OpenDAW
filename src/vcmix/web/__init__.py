"""
web — Phase 8: Web UI for VCMix.

FastAPI-based REST API + WebSocket DataStream forwarding,
providing both AI Agent (CLI) and human (GUI) interfaces.

Architecture:
    web/app.py              — FastAPI application factory
    web/routes/render.py    — /api/render endpoints
    web/routes/plugins.py   — /api/plugins endpoints
    web/routes/presets.py   — /api/presets endpoints
    web/routes/arrangement.py — /api/arrangement endpoints
    web/routes/automix.py   — /api/automix endpoints
    web/websocket.py        — WebSocket DataStream forwarding
    web/static/             — Minimal HTML/CSS/JS frontend

Shares the same engine as CLI (no code duplication).
"""
