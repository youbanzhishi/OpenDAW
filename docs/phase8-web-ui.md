# Phase 8: Web UI Design Document

**Version:** 0.8.0  
**Date:** 2025-07-11  
**Status:** Implemented  

---

## Overview

Phase 8 introduces a **dual-track UI** for VCMix:

| Interface | Target User | Protocol |
|-----------|------------|----------|
| CLI | AI Agents, automation scripts | Terminal, exit codes, JSON output |
| Web UI | Human users, visual interaction | REST API + WebSocket |

Both interfaces share the **same rendering engine** — no code duplication. The Web UI is a thin HTTP/WS layer over the existing core.

---

## Architecture

```
┌──────────────────────────────────────────────────────┐
│                    Client Layer                       │
│  ┌────────────┐              ┌────────────────────┐  │
│  │ AI Agent   │              │ Browser (HTML/JS)  │  │
│  │ (CLI/API)  │              │ Vanilla JS + WS    │  │
│  └─────┬──────┘              └────────┬───────────┘  │
└────────┼──────────────────────────────┼──────────────┘
         │ HTTP/JSON             HTTP/WS│
┌────────┼──────────────────────────────┼──────────────┐
│        ▼                              ▼              │
│  ┌─────────────────────────────────────────────┐     │
│  │         FastAPI Application Layer            │     │
│  │  ┌──────────┐ ┌───────────┐ ┌────────────┐  │     │
│  │  │ REST API │ │ WebSocket │ │ Static     │  │     │
│  │  │ Routes   │ │ DataStream│ │ Frontend   │  │     │
│  │  └────┬─────┘ └─────┬─────┘ └────────────┘  │     │
│  └───────┼─────────────┼────────────────────────┘     │
│          │             │                               │
│  ┌───────▼─────────────▼────────────────────────┐     │
│  │           VCMix Core Engine                   │     │
│  │  (Shared by CLI and Web UI — no duplication)  │     │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────────┐  │     │
│  │  │Renderer  │ │AutoMixer │ │Arrangement   │  │     │
│  │  │          │ │          │ │Strategy      │  │     │
│  │  ├──────────┤ ├──────────┤ ├──────────────┤  │     │
│  │  │DataStream│ │Presets   │ │Plugins       │  │     │
│  │  │          │ │Manager   │ │Registry      │  │     │
│  │  └──────────┘ └──────────┘ └──────────────┘  │     │
│  └──────────────────────────────────────────────┘     │
│                    OpenDAW                              │
└───────────────────────────────────────────────────────┘
```

---

## REST API Endpoints

### System

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/health` | Health check |
| GET | `/api/docs` | OpenAPI/Swagger documentation |
| GET | `/` | Serve frontend index.html |

### Render

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/render` | Trigger render from YAML string |
| POST | `/api/render/file` | Trigger render from server file path |
| GET | `/api/render/{job_id}` | Get render job status |
| GET | `/api/render/{job_id}/events` | Get DataStream events for job |

**POST /api/render** body:
```json
{
  "project_yaml": "name: MyProject\nbpm: 120\n...",
  "report": false,
  "auto_fix": false,
  "ab_mode": false,
  "ab_diff": false,
  "arrangement_aware": false
}
```

**Render response:**
```json
{
  "job_id": "a1b2c3d4",
  "status": "pending",
  "message": "Render job started. Poll /api/render/{job_id} for status."
}
```

**Render status response:**
```json
{
  "job_id": "a1b2c3d4",
  "status": "completed",
  "output_path": "/path/to/output.wav",
  "elapsed_s": 3.42,
  "events": [...],
  "error": null
}
```

### Plugins

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/plugins` | List all plugins |
| GET | `/api/plugins/{name}` | Get plugin details |

### Presets

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/presets` | List all presets |
| GET | `/api/presets/{name}` | Get preset effect chain |
| POST | `/api/presets` | Save custom preset |

### Validation

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/validate` | Validate YAML config |

### Arrangement

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/arrangement` | Analyze arrangement structure |
| GET | `/api/arrangement/strategy` | Get arrangement mixing strategy |

### AutoMix

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/automix` | Run auto-mixing analysis |
| POST | `/api/automix/dry-run` | Dry-run auto-mix (suggestions only) |

### WebSocket

| Protocol | Path | Description |
|----------|------|-------------|
| WS | `/api/stream` | Real-time DataStream events |

**WebSocket protocol:**
- Server sends `connected` on open
- Client sends `{"action": "ping"}` → Server responds `{"type": "pong"}`
- Client sends `{"action": "status"}` → Server responds `{"type": "status", "connections": N}`
- Server broadcasts render events in real-time during rendering
- Heartbeat every 30s if no client activity

---

## File Structure

```
src/vcmix/web/
├── __init__.py              # Package docstring
├── app.py                   # FastAPI application factory
├── routes/
│   ├── __init__.py
│   ├── render.py            # /api/render endpoints
│   ├── plugins.py           # /api/plugins endpoints
│   ├── presets.py           # /api/presets endpoints
│   ├── arrangement.py       # /api/arrangement endpoints
│   └── automix.py           # /api/automix + /api/validate endpoints
├── websocket.py             # WebSocket DataStream forwarding
└── static/
    ├── index.html           # Main frontend page
    ├── style.css            # Minimal dark-theme stylesheet
    └── app.js               # Vanilla JS frontend logic
```

---

## Frontend Design

### Principles
- **No framework** — pure HTML + CSS + vanilla JavaScript
- **Minimal viable UI** — 5 tabs covering core workflows
- **Dark theme** — comfortable for audio production environments
- **Responsive** — works on desktop and tablet

### Tab Layout

| Tab | Function |
|-----|----------|
| 📝 YAML Editor | Write/paste YAML, validate, render |
| ▶️ Render | File-path render, status polling, event viewer |
| 🔌 Plugins | Browse available plugins |
| 🎵 Presets | Browse/apply effect chain presets |
| 📡 Live Stream | WebSocket connection, real-time level meters |

### Key Features
1. **YAML Editor**: Textarea with validate + render buttons
2. **Render Control**: Trigger renders, poll status, view DataStream events
3. **Level Meters**: Real-time RMS/Peak display via WebSocket
4. **Preset Browser**: Click to see full effect chain details
5. **Plugin Browser**: Grid display of all 18 VC plugins

---

## Engine Sharing Strategy

The Web UI **shares** the same engine code as the CLI:

| Component | CLI Usage | Web Usage |
|-----------|-----------|-----------|
| `Renderer` | `Renderer(cfg).run()` | `Renderer(cfg, stream="dict").run()` |
| `AutoMixer` | `AutoMixer().analyze(events)` | Same call in `/api/automix` |
| `ArrangementExtractor` | `extractor.extract(stems, sr, bpm)` | Same call in `/api/arrangement` |
| `ArrangementStrategy` | `strategy.from_sections(sections)` | Same call in `/api/arrangement/strategy` |
| `PluginRegistry` | `registry.get("vc-eq")` | Same instance in `/api/plugins` |
| `PresetManager` | `list_presets()`, `get_preset()` | Same calls in `/api/presets` |
| `DataStream` | `stream="json"` → stdout | `stream="dict"` → accumulate for API |

**Zero code duplication** — the web routes import and call the same functions.

---

## Async Architecture

```
Client POST /api/render
    │
    ▼
FastAPI endpoint creates job_id
    │
    ▼
Background thread calls Renderer.run()
    │
    ├── Renderer emits DataStream events (format="dict")
    │
    ├── Events accumulated in job store
    │
    └── On completion: job status updated
    │
Client GET /api/render/{job_id}
    │
    ▼
Returns current status + accumulated events
```

WebSocket broadcasting is available for real-time event streaming during renders.

---

## Dependencies

### Required (core)
- `fastapi>=0.100.0` — REST API framework with auto OpenAPI docs
- `uvicorn>=0.20.0` — ASGI server
- `websockets>=11.0` — WebSocket support

### Optional (development)
- `httpx>=0.24.0` — FastAPI TestClient dependency

These are in `[project.optional-dependencies]` as `web` and `dev` extras:
```bash
pip install vcmix[web]      # Install with web dependencies
pip install vcmix[dev]      # Install with dev + web dependencies
```

---

## Testing

**21 new tests** in `tests/test_web_api.py`:

| Test Class | Tests | Coverage |
|------------|-------|----------|
| TestHealthCheck | 1 | Health endpoint |
| TestPlugins | 3 | List, detail, 404 |
| TestPresets | 4 | List, detail, 404, create |
| TestValidate | 2 | Valid/invalid YAML |
| TestRender | 5 | Trigger, 404, lifecycle, events |
| TestWebSocket | 3 | Connect, status, unknown action |
| TestArrangement | 2 | 404 cases |
| TestAutoMix | 1 | 404 case |

All 277 tests pass (256 existing + 21 new).

---

## Running

```bash
# Start the web server
pip install vcmix[web]
uvicorn vcmix.web.app:app --reload --port 8000

# Or via Python
python -m vcmix.web.app  # (if __main__ added)

# Open browser
open http://localhost:8000

# API documentation
open http://localhost:8000/api/docs
```

---

## Future Enhancements (Phase 9+)

1. **Audio playback** — Stream rendered audio back to browser
2. **Waveform display** — Canvas-based waveform visualization
3. **Spectrum analyzer** — Real-time FFT display via WebSocket
4. **Drag-and-drop** — File upload for audio stems
5. **Session management** — Multiple projects, persistent storage
6. **Authentication** — API key or OAuth for multi-user scenarios
7. **Plugin parameter editor** — Interactive sliders for effect parameters
8. **Arrangement timeline** — Visual section editor with drag-to-resize
9. **A/B comparison player** — Side-by-side audio comparison in browser
10. **Collaborative editing** — Real-time YAML editing via CRDT/WebSocket
