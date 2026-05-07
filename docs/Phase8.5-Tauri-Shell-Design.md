# Phase 8.5: Tauri Shell Design Document

**Version:** 0.8.5  
**Date:** 2025-07-11  
**Status:** Design + Code Complete (PoC pending Rust toolchain)  
**Depends on:** Phase 8 (Web UI)  
**Enables:** Phase 9 (Native Desktop Evolution)

## 1. Overview

Phase 8.5 is a **transition layer** that wraps the existing VCMix FastAPI Web UI
inside a Tauri 2.0 desktop application shell. The core principle:

> **Zero frontend changes.** The same index.html / style.css / app.js
> that runs in Chrome at localhost:8000 now runs inside a native OS window.

The Tauri shell's only job is:
1. **Spawn** the Python FastAPI backend as a child process
2. **Health-check** it until it responds
3. **Load** the web UI URL in a native webview
4. **Cleanup** the Python process on exit

---

## 2. Architecture

```
+---------------------------------------------------------------+
|                    Tauri Desktop Shell                        |
|  +---------------------------------------------------------+  |
|  |              Native OS Window (WebView)                  |  |
|  |                                                         |  |
|  |   +-------------------------------------------------+   |  |
|  |   |         VCMix Web UI (Phase 8 frontend)          |   |  |
|  |   |   index.html + style.css + app.js                |   |  |
|  |   |   Tabs: Editor / Render / Plugins / Presets / WS |   |  |
|  |   +------------------------+------------------------+   |  |
|  |                            | HTTP / WebSocket            |  |
|  |                            | http://localhost:8000        |  |
|  +----------------------------+-----------------------------+  |
|                                |                              |
|  +----------------------------v-----------------------------+  |
|  |           Rust Main (main.rs)                             |  |
|  |  +--------------+  +--------------+  +---------------+  |  |
|  |  | spawn_backend|  | health_check |  | kill_backend  |  |  |
|  |  | (child proc) |  | (HTTP poll)  |  | (on exit)     |  |  |
|  |  +------+-------+  +--------------+  +---------------+  |  |
|  +---------+------------------------------------------------+  |
|            | child process                                        |
|  +---------v------------------------------------------------+  |
|  |        Python FastAPI Backend (uvicorn)                   |  |
|  |  +----------+ +-----------+ +----------+ +-----------+  |  |
|  |  | REST API | | WebSocket | | Renderer | | AutoMixer |  |  |
|  |  | Routes   | | Stream    | | Pipeline | | Engine    |  |  |
|  |  +----+-----+ +-----+-----+ +----+-----+ +-----+-----+  |  |
|  +-------+-------------+------------+------------+----------+  |
|          +-------------+------------+------------+              |
|                    VCMix Core Engine                           |
|                    (Python -- shared with CLI)                  |
+---------------------------------------------------------------+
```

### Data Flow

```
User clicks Render in Tauri window
  -> app.js sends POST /api/render to localhost:8000
  -> FastAPI route calls VCMix renderer
  -> Renderer emits DataStream events
  -> WebSocket /api/stream pushes events back to app.js
  -> UI updates level meters and log
```

No Tauri-specific IPC is used in Phase 8.5 -- all communication goes through
the local HTTP/WS loopback, exactly as in the browser version.

---

## 3. Startup Flow

```
  +---------------+
  | User launches |
  | VCMix Desktop |
  +-------+-------+
          |
          v
  +------------------------------+
  | Rust main() executes         |
  | spawn_backend()              |
  |   -> python -m vcmix.web     |
  |   -> Store PID in Mutex      |
  +------+-----------------------+
         |
         v
  +------------------------------+
  | wait_for_backend()           |
  |   Loop up to 30s:            |
  |     GET /api/health          |
  |     If 200 OK -> proceed     |
  |     Else -> sleep 1s, retry  |
  +------+-----------------------+
         |
         v (healthy)
  +------------------------------+
  | Tauri Builder::run()         |
  |   -> Open WebView window     |
  |   -> Load http://localhost:8000
  |   -> Native window: 1280x800 |
  |   -> Title: VCMix            |
  +------+-----------------------+
         |
         v
  +------------------------------+
  | App running...               |
  |   Webview <-> FastAPI        |
  |   All Phase 8 features work  |
  +------+-----------------------+
         |
         v (user closes window)
  +------------------------------+
  | kill_backend()               |
  |   -> child.kill()            |
  |   -> child.wait() (reap)     |
  |   -> Process exits cleanly   |
  +------------------------------+
```

### Startup Timing Budget

| Phase | Expected Duration | Timeout |
|-------|------------------|---------|
| Python import + uvicorn init | 1-3s | -- |
| Health check polling | 1-5s (2-5 polls) | 30s |
| WebView load + render | 0.5-1s | -- |
| **Total cold start** | **2-9s** | -- |

---

## 4. Project Structure

```
desktop/
  package.json              # npm config (Tauri CLI + API deps)
  src/                      # Frontend, symlinked to web/static
    index.html -> /src/vcmix/web/static/index.html
    style.css  -> /src/vcmix/web/static/style.css
    app.js     -> /src/vcmix/web/static/app.js
  src-tauri/                # Rust/Tauri backend
    Cargo.toml              # Rust dependencies
    build.rs                # Tauri build hook
    tauri.conf.json         # Tauri window + bundle configuration
    src/
      main.rs               # Entry: spawn Python -> health check -> run Tauri
      lib.rs                # Tauri commands + plugin registration
    icons/                  # App icons (placeholder)
      README.md
```

### Key Design Decisions

1. **Symlink, not copy** -- desktop/src/ symlinks to web/static/ so any
   Phase 8 frontend changes are immediately reflected in the desktop app.
   In release builds, the files are copied into the bundle.

2. **Two-file Rust split** -- main.rs handles process lifecycle (spawn/health/cleanup),
   lib.rs handles Tauri integration (commands, state, plugin registration).
   This follows Tauri 2.0 conventions and enables mobile targets in the future.

3. **No Tauri IPC in Phase 8.5** -- All UI<->Backend communication goes through
   HTTP/WebSocket on localhost. This is intentional: zero frontend changes means
   the same app.js works in both browser and desktop.

---

## 5. Tauri Configuration

### Window Settings

| Property | Value | Rationale |
|----------|-------|-----------|
| Title | VCMix -- AI-native DAW | Clear branding |
| Default size | 1280 x 800 | Fits 5-tab layout comfortably |
| Minimum size | 960 x 600 | Prevents layout breakage |
| Resizable | Yes | User preference |
| Centered | Yes | Professional feel |

### Content Security Policy

```
default-src 'self';
connect-src 'self' ws://localhost:* http://localhost:*;
style-src 'self' 'unsafe-inline';
script-src 'self' 'unsafe-inline';
```

- connect-src allows WebSocket connections to the local backend
- unsafe-inline required for the vanilla JS approach (Phase 9 can tighten this)

### Bundle Configuration

- Resources: Includes python-dist/ directory containing the PyInstaller binary
- Shell scope: Allows python command with any args (for dev mode)
- Icon set: 32x32, 128x128, 256x256, .icns, .ico (macOS/Windows/Linux)

---

## 6. Rust Implementation Details

### Backend Process Management (main.rs)

Dev mode: Uses system Python -- requires `pip install -e .`
Release mode: Uses PyInstaller binary from `resources/`

```rust
// Spawn: detect dev vs release
if cfg!(debug_assertions) {
    Command::new("python").args(["-m", "vcmix.web"])
} else {
    Command::new(get_bundled_backend_path())
}
```

### Health Check (main.rs)

Uses reqwest::blocking to poll GET /api/health:
- 1-second intervals
- 30-second timeout (fails with error message)
- On success, proceeds to Tauri launch

### Cleanup (main.rs)

On window close or Ctrl+C:
1. child.kill() -- sends SIGTERM (Unix) or TerminateProcess (Windows)
2. child.wait() -- reaps the zombie process
3. Mutex guard ensures no double-kill

### Tauri Commands (lib.rs)

| Command | Purpose |
|---------|---------|
| check_backend_health(port) | Frontend can verify backend liveness |
| set_backend_pid(pid) | Record the Python process PID |
| get_backend_pid() | Retrieve the stored PID |

These commands are not used by the Phase 8.5 frontend but exist for
Phase 9 integration where Tauri IPC replaces HTTP for local calls.


---

## 7. Packaging Strategy

### Phase 8.5 (Current): Sidecar Python

VCMix.app / .exe contains:
- Tauri WebView (Rust) at the top layer
- vcmix-backend (PyInstaller) containing Python 3.11 runtime + vcmix + deps + uvicorn + fastapi

Steps to build:

1. PyInstaller bundle the Python backend:
   cd /tmp/OpenDAW && pyinstaller --onefile --name vcmix-backend src/vcmix/web/app.py

2. Place binary in Tauri resources:
   - desktop/python-dist/vcmix-backend (Linux/macOS)
   - desktop/python-dist/vcmix-backend.exe (Windows)

3. Build Tauri app:
   cd desktop && npm install && npm run tauri build

### Output Artifacts

| Platform | Output | Size (est.) |
|----------|--------|-------------|
| macOS | VCMix.app + .dmg | ~150 MB |
| Windows | VCMix.exe + .msi | ~120 MB |
| Linux | vcmix AppImage / .deb | ~100 MB |

Size is dominated by the PyInstaller Python runtime (~60 MB).
Phase 9 will eliminate this by replacing Python with Rust.

---

## 8. Cross-Platform Considerations

### macOS

| Concern | Solution |
|---------|----------|
| Code signing | Requires Apple Developer cert for distribution outside App Store |
| Notarization | xcrun notarytool submit after signing |
| Universal binary | Build separate arm64 + x86_64, then lipo combine |
| Python paths | PyInstaller bundles Python -- no system dependency |
| Background audio | Needs com.apple.security.cs.allow-unsigned-executable-memory entitlement |

### Windows

| Concern | Solution |
|----------|---------|
| Process kill | TerminateProcess + WaitForSingleObject -- handled by Rust child.kill() |
| Port conflicts | Allow user to configure port via env var VCMIX_PORT |
| Firewall popup | First launch of Python backend may trigger Windows Defender |
| Installer | Tauri generates MSI or NSIS installer |
| Console window | PyInstaller --noconsole flag to suppress |

### Linux

| Concern | Solution |
|----------|---------|
| WebView dependency | Tauri uses webkit2gtk -- must be installed on user system |
| AppImage | Best distribution format -- no install needed |
| Process signals | SIGTERM for graceful shutdown, SIGKILL as fallback |
| Audio permissions | Pipewire/PulseAudio -- no special permissions needed |

### Port Binding Conflict

If port 8000 is already in use, strategy: try default port, then increment
up to 100 ports. The frontend URL dynamically adjusts.

---

## 9. Phase 9 Evolution Path

Phase 8.5 is a stepping stone. The full desktop evolution:

Phase 8.5 (Now): Tauri Shell with WebView (HTML/JS) over HTTP to Python FastAPI Backend
Phase 9.0: Tauri + Rust with WebView + Tauri IPC over direct calls to Rust Backend (Axum/Actix)
Phase 9.5: Tauri + Rust + Native Widgets with Custom Renderers (Waveform, Spectrum, Meter) over IPC to Rust Backend (Audio Core)

### Phase 9.0: Rust Backend Replacement

| Component | Phase 8.5 | Phase 9.0 |
|-----------|-----------|-----------|
| HTTP Server | Python/uvicorn | Rust (Axum/Actix) |
| Audio Engine | Python (soundfile/numpy) | Rust (cpal + dasp) |
| IPC | HTTP loopback | Tauri Commands (zero-copy) |
| Process model | Parent-child (Python subprocess) | Single process |
| Startup time | 2-9s | <500ms |
| Binary size | ~150 MB (with Python) | ~15 MB |

Migration steps:
1. Port REST API to Axum -- Same endpoints, Rust handlers
2. Port VCMix engine to Rust -- Core DSP, YAML parsing, plugin system
3. Replace HTTP IPC with Tauri Commands -- Direct function calls, no serialization
4. Keep WebSocket -- For real-time audio metering data
5. Remove Python dependency entirely

### Phase 9.5: Native GUI Components

Replace HTML/JS rendering with native Tauri widgets:
- Waveform display: Rust-rendered canvas (skia or piet)
- Spectrum analyzer: GPU-accelerated via wgpu
- Level meters: Custom native widget
- Plugin rack: Native drag-and-drop UI
- Timeline/arrangement: Custom timeline widget

---

## 10. Development Setup

### Prerequisites

1. Rust toolchain: curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
2. Node.js (for Tauri CLI) -- typically available
3. Tauri prerequisites (platform-specific):
   - macOS: xcode-select --install
   - Ubuntu/Debian: sudo apt install libwebkit2gtk-4.1-dev build-essential curl wget file libssl-dev libgtk-3-dev libayatana-appindicator3-dev librsvg2-dev
   - Windows: Install Visual Studio C++ Build Tools

### Running in Dev Mode

cd /tmp/OpenDAW/desktop
npm install
npm run tauri dev

### Building for Production

Step 1: Create PyInstaller bundle
cd /tmp/OpenDAW && pip install pyinstaller
pyinstaller --onefile --name vcmix-backend src/vcmix/web/app.py
cp dist/vcmix-backend desktop/python-dist/

Step 2: Build Tauri app
cd desktop && npm run tauri build

---

## 11. Known Limitations (Phase 8.5)

| Limitation | Impact | Resolution |
|------------|--------|------------|
| Requires Python installed (dev mode) | Developer friction | PyInstaller bundle for release |
| Startup latency 2-9s | User experience | Phase 9: Rust backend |
| HTTP loopback overhead | Negligible for current UI | Phase 9: Tauri IPC |
| No system tray | No background mode | Phase 9 feature |
| No auto-update | Manual distribution | Tauri updater plugin |
| Symlinks break if project moved | Dev environment only | Release copies files |
| Single window only | No multi-window DAW | Phase 9.5 feature |

---

## 12. Testing Strategy

### Unit Tests (Rust)

test_backend_spawn_and_health: Requires vcmix installed, skip in CI without Python

### Integration Tests

| Test | Method | Pass Criteria |
|------|--------|---------------|
| Cold start | Launch app, time to interactive | < 10s |
| Backend health | GET /api/health after launch | 200 OK |
| WebSocket | Connect ws://localhost:8000/api/stream | Receive welcome message |
| Tab switching | Click each tab button | Content visible, no JS errors |
| Render flow | Paste YAML -> Validate -> Render | Status updates appear |
| Clean exit | Close window | Python process terminated (no zombie) |
| Crash recovery | Kill Python mid-render | Tauri shows error, not crash |

---

## 13. File Manifest

| File | Purpose | Status |
|------|---------|--------|
| desktop/package.json | npm config + Tauri CLI | Created |
| desktop/src/ (symlinks) | Frontend -> web/static | Linked |
| desktop/src-tauri/Cargo.toml | Rust dependencies | Created |
| desktop/src-tauri/build.rs | Tauri build hook | Created |
| desktop/src-tauri/tauri.conf.json | Window + bundle config | Created |
| desktop/src-tauri/src/main.rs | Process lifecycle | Created |
| desktop/src-tauri/src/lib.rs | Tauri commands + plugin | Created |
| desktop/src-tauri/icons/ | App icons (placeholder) | Needs assets |
| docs/Phase8.5-Tauri-Shell-Design.md | This document | Created |
