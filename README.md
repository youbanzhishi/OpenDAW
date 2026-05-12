# OpenDAW 🎵

**AI-native open-source DAW** — Rust-powered, cross-platform, AI Agent friendly.

> Reaper有的我们要有，Reaper没有的我们也要有。

> **历史名称**: 本项目前身为 VCMix（Python 版本），现已使用 Rust 完全重写。以下文档中的 Python/VCMix 功能描述对应历史版本。

**v1.0.0 Released** — 9 crate Rust workspace, 499 tests all green, cross-platform CI + Release + Desktop Build.

![Rust](https://img.shields.io/badge/Rust-1.86+-orange?logo=rust)
![Tests](https://img.shields.io/badge/tests-499%20%E2%9C%85-brightgreen)
![License](https://img.shields.io/badge/license-MIT-blue)
![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-informational)

## Three Core Principles

1. **Cross-platform** — Windows / macOS / Linux (AppImage / dmg / exe / msi)
2. **High Performance** — Rust native engine + real-time audio + zero-copy pipeline
3. **AI Agent Friendly** — YAML config + CLI zero-GUI + structured JSON output + REST API + WebSocket

## Core Components

OpenDAW consists of three major components built on a shared Rust workspace:

| Component | Binary | Description |
|-----------|--------|-------------|
| **CLI** | `opendaw-cli` | Project management, offline rendering, mixing, plugin management, audio transcription, REPL |
| **API Server** | `opendaw-api` | REST API + WebSocket for remote control and AI Agent integration |
| **Desktop App** | Tauri v2 | Cross-platform desktop application (AppImage / dmg / exe / msi) |

### CLI (opendaw-cli)

```bash
# Project management
opendaw init my-project
opendaw render project.yaml
opendaw mix project.yaml

# Plugin management
opendaw plugin list
opendaw plugin install VC-EQ

# Audio transcription
opendaw transcribe input.wav --output midi

# Interactive REPL
opendaw repl

# JSON structured output (AI Agent friendly)
opendaw render project.yaml --stream json
```

### API Server (opendaw-api)

```bash
# Start API server with WebSocket support
opendaw serve --port 3000

# REST API endpoints
# GET  /api/v1/projects          — List projects
# POST /api/v1/projects          — Create project
# GET  /api/v1/projects/:id      — Get project
# POST /api/v1/render/:id        — Trigger render
# WebSocket /ws                   — Real-time events
```

### Desktop App (Tauri v2)

Download the latest release for your platform:

| Platform | Download |
|----------|----------|
| Linux | [AppImage](https://github.com/youbanzhishi/OpenDAW/releases/latest) |
| macOS | [dmg](https://github.com/youbanzhishi/OpenDAW/releases/latest) |
| Windows | [exe / msi](https://github.com/youbanzhishi/OpenDAW/releases/latest) |

## Rust Workspace Members

```
opendaw/
├── audio-engine/          # Real-time audio engine
├── jsfx-engine/           # JSFX plugin engine
├── opendaw-core/          # Core abstractions and data structures
├── opendaw-extension/     # Extension registry and plugin system
├── plugin-host/           # Plugin hosting and sandboxing
├── opendaw-api/           # REST API + WebSocket server
├── opendaw-ws/            # WebSocket protocol layer
├── opendaw-cli/           # Command-line interface
└── desktop/src-tauri/     # Tauri v2 desktop application
```

## Build Requirements

- **Rust** 1.86+ (required for `icu` dependency which needs edition 2024)
- **C/C++ compiler** (gcc or clang)
- **Node.js** 18+ (for Tauri desktop app build only)

```bash
# Install Rust via rustup
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
```

## Quick Start

### Download Pre-built Binary

```bash
# Download pre-built binary
curl -L https://github.com/youbanzhishi/OpenDAW/releases/latest/download/opendaw-linux-amd64.tar.gz | tar xz
./opendaw serve
```

### Build from Source

```bash
# Build CLI
cargo build --release -p opendaw-cli
./target/release/opendaw serve

# Build Desktop App
cd desktop && npm install && npm run tauri build
```

### Docker Deployment

```bash
docker run -d -p 3000:3000 ghcr.io/youbanzhishi/opendaw/opendaw:latest
```

📖 For full deployment options, see [部署指南](docs/deployment.md) (Docker, binary, source build, systemd, production config).

## Feature Overview

| Feature | Status |
|---------|--------|
| YAML-driven rendering | ✅ |
| Insert chain processing | ✅ |
| Multi-track mixing | ✅ |
| BPM note value sync | ✅ |
| Send/Return buses | ✅ |
| Sidechain routing | ✅ |
| A/B comparison | ✅ |
| AutoFix gain staging | ✅ |
| Built-in presets | ✅ |
| DataStream closed-loop | ✅ |
| Source separation | ✅ |
| Arrangement extraction | ✅ |
| AutoMix engine | ✅ |
| Reference matching | ✅ |
| Arrangement-aware mixing | ✅ |
| Web UI (REST API + WebSocket) | ✅ |
| Native GUI (Tauri Desktop) | ✅ |
| VC Plugins (built-in effect chain) | ✅ |
| Full DAW | 🔮 Ultimate Goal |

## Built-in Effect Chain (VC Plugins)

OpenDAW includes 20 built-in effects, available as the internal effect chain:

### Gen 1 (16 plugins)
| Plugin | Key Parameters |
|--------|---------------|
| VC-EQ | low_cut, high_shelf, peak_freq, peak_gain |
| VC-Comp | threshold, ratio, attack, release, makeup |
| VC-Smooth | amount |
| VC-DeEsser | threshold, reduction, frequency |
| VC-Gain | gain |
| VC-Saturator | drive, mix |
| VC-Limiter | ceiling, release |
| VC-Delay | time, feedback, mix |
| VC-Reverb | room, decay, damping, mix, predelay, wetlpf |
| VC-DynamicEQ | frequency, threshold, q, attack, release |
| VC-Distortion | drive, tone, mix |
| VC-Noise | threshold, reduction |
| VC-SurgicalDeEsser | threshold, frequency, reduction |
| VC-Tune | speed, scale, transpose, autokey |
| VC-Gate | threshold, ratio, attack, hold, release, range |
| VC-Chorus | rate, depth, voices, mix, width |

### Gen 2 (4 plugins)
| Plugin | Type | Key Parameters |
|--------|------|---------------|
| VC-Stereo | 🆕 New | width, pan, mono_bass, bass_freq |
| VC-PitchShift | 🆕 New | semitones, cents, formant |
| VC-Reverb | ⬆️ FDN升级 | room, decay, damping, mix, predelay, wetlpf (8-delay FDN) |
| VC-Comp | ⬆️ 多段升级 | threshold, ratio, --multiband, --band-threshold, --band-ratio |

## DataStream Events (AI Agent API)

| Event | Data | Use Case |
|-------|------|----------|
| track_level | rms_db, peak_db, true_peak_db | Monitor per-track levels |
| effect_delta | before_rms, after_rms, delta_db | Track effect impact |
| master_level | rms_db, peak_db, true_peak_db | Master bus monitoring |
| warning | type (clipping/low_snr/sibilance), message | Problem detection |
| decision | action, params, reason | Auto-fix logging |

## Standardized Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | Config error |
| 2 | Plugin error |
| 3 | Audio I/O error |
| 4 | Render error |
| 5 | Cache error |
| 6 | Missing dependency |

## Python Version (Historical — VCMix)

The original Python implementation provided:

```bash
pip install -e .

# Render a mix project
vcmix render examples/jiuwanzi.yaml

# Validate config
vcmix validate examples/jiuwanzi.yaml

# View signal routing graph
vcmix graph examples/jiuwanzi.yaml

# Render with real-time analysis report
vcmix render examples/jiuwanzi.yaml --report

# Render with auto-fix gain staging
vcmix render examples/jiuwanzi.yaml --auto-fix --stream log

# JSON structured output
vcmix render examples/jiuwanzi.yaml --stream json

# A/B comparison rendering
vcmix render project.yaml --ab

# Auto-mix: analyze + suggest + apply
vcmix automix project.yaml
```

These features have been superseded by the Rust-based `opendaw-cli`.

### Rendering Pipeline (Python Version)

```
1. Parse YAML → ProjectConfig
2. Validate config & check audio files
3. Build signal routing DAG (tracks → inserts → sends → master)
4. Render each track through insert chain (sidechain routing)
5. Process Send/Return buses
6. Mix tracks with master level balancing + bus returns
7. Apply master insert chain + DataStream events
8. Write output + optional A/B versions + analysis report
```

## Related Projects

- [OpenLink](https://github.com/youbanzhishi/OpenLink) — 智能体时代的通用路由与编排协议
- [OpenVault](https://github.com/youbanzhishi/OpenVault) — 3-2-1 backup strategy with self-healing
- [AudioFX](https://github.com/youbanzhishi/AudioFX) — VC Plugin Series (VST3 effects + CLI tools)

## License

MIT
