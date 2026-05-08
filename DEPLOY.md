# VCMix Deployment Guide

One-command deployment of VCMix on low-resource cloud servers (2-core, 1GB RAM).

---

## Quick Start (One Command)

```bash
# Clone and deploy in core mode (recommended for 1GB servers)
git clone https://github.com/your-org/OpenDAW.git && cd OpenDAW
cp .env.example .env
docker compose up -d
```

That's it. VCMix will be running at `http://your-server:8000`.

---

## Configuration

### Environment Variables

Copy `.env.example` to `.env` and customize:

| Variable | Default | Description |
|---|---|---|
| `VCMIX_PROFILE` | `core` | `core` (lightweight) or `full` (all features) |
| `VCMIX_PORT` | `8000` | Host port mapping |
| `VCMIX_MEMORY_LIMIT` | `512M` | Container memory limit |
| `VCMIX_CPU_LIMIT` | `1.0` | Container CPU limit (cores) |
| `VCMIX_PROJECTS_DIR` | `./projects` | Host path for project files |
| `VCMIX_OUTPUT_DIR` | `./output` | Host path for render output |
| `VCMIX_LOG_LEVEL` | `info` | Logging verbosity |

### Profile Selection

#### Core Mode (default, recommended for 1GB servers)

```bash
# Using env variable
VCMIX_PROFILE=core docker compose up -d

# Or edit .env
echo "VCMIX_PROFILE=core" >> .env
docker compose up -d
```

#### Full Mode (requires 4GB+ RAM)

```bash
# Using env variable
VCMIX_PROFILE=full docker compose up -d

# Or edit .env
echo "VCMIX_PROFILE=full" >> .env
docker compose up -d
```

### Without Docker

```bash
# Core profile (no AI deps)
pip install ".[web]"
vcmix serve --profile core --host 0.0.0.0 --port 8000

# Full profile (with AI deps)
pip install ".[web,ai]"
vcmix serve --profile full --host 0.0.0.0 --port 8000

# Default is full (backward compatible)
vcmix serve
```

---

## Core vs Full Mode Comparison

| Feature | Core | Full |
|---|:---:|:---:|
| **Render API** (`/api/render`) | ✅ | ✅ |
| **Plugin Management** (`/api/plugins`) | ✅ | ✅ |
| **Preset Browser** (`/api/presets`) | ✅ | ✅ |
| **MIDI Scanning** (`/api/midi`) | ✅ | ✅ |
| **Automation** (`/api/automation`) | ✅ | ✅ |
| **Arrangement Analysis** (`/api/arrangement`) | ✅ | ✅ |
| **Auto-Mixing** (`/api/automix`) | ✅ | ✅ |
| **Agent API** (`/api/v1/projects`) | ✅ | ✅ |
| **AI Mixing Suggestions** (`/api/v1/ai/mix`) | ✅ | ✅ |
| **AI Mastering Suggestions** (`/api/v1/ai/master`) | ✅ | ✅ |
| **Render WebSocket** (`/ws/render/{id}`) | ✅ | ✅ |
| **AI Decision WebSocket** (`/ws/ai/{id}`) | ✅ | ✅ |
| **AI Transcription** (`/api/v1/ai/transcribe`) | ❌ | ✅ |
| **Style Match/Transfer** (`/api/v1/ai/style-*`) | ❌ | ✅ |
| **One-Click Remix** (`/api/v1/ai/remix`) | ❌ | ✅ |
| **Collaboration WebSocket** (`/ws/collab/{id}`) | ❌ | ✅ |
| **Multi-format Export** (`/api/v1/projects/{id}/export`) | ❌ | ✅ |
| **Stem Export** (`/api/v1/projects/{id}/export-stems`) | ❌ | ✅ |
| **Project Snapshots** (`/api/v1/projects/{id}/snapshots`) | ❌ | ✅ |
| **Waveform Visualization** (`/api/v1/waveform/`) | ❌ | ✅ |
| **Spectrum Analysis** (`/api/v1/spectrum/`) | ❌ | ✅ |
| **Piano Roll** (`/api/v1/midi/{id}/{track}`) | ❌ | ✅ |
| **Estimated RAM (idle)** | ~180MB | ~450MB |
| **Estimated Image Size** | ~300MB | ~2GB |
| **Demucs/Torch loaded** | No | Yes |

> In core mode, disabled endpoints return HTTP 501 with instructions to switch to full profile.

---

## Memory Optimization Tips

### For 1GB servers (core profile)

The default `docker-compose.yml` is configured for 1GB servers:
- Container memory limit: 512MB (leaves ~512MB for OS)
- CPU limit: 1 core
- Core profile: no demucs/torch loaded

If you still encounter memory issues:

1. **Reduce Python overhead**: Set `--workers 1` (already default)
2. **Monitor usage**: `docker stats vcmix-server`
3. **Add swap** (if not already):
   ```bash
   sudo fallocate -l 1G /swapfile
   sudo chmod 600 /swapfile
   sudo mkswap /swapfile
   sudo swapon /swapfile
   ```

### Upgrading to Full Mode

Full mode requires **4GB+ RAM** due to demucs/torch:

```bash
# 1. Install AI dependencies
pip install ".[ai]"

# 2. Switch profile
vcmix serve --profile full

# Or with Docker:
# Edit .env: VCMIX_PROFILE=full
# Edit .env: VCMIX_MEMORY_LIMIT=2G
docker compose up -d --build
```

---

## Troubleshooting

### Container won't start / OOM killed

```bash
# Check if OOM killed
dmesg | grep -i oom

# Reduce memory or switch to core profile
echo "VCMIX_PROFILE=core" >> .env
echo "VCMIX_MEMORY_LIMIT=512M" >> .env
docker compose up -d
```

### Health check failing

```bash
# Check container logs
docker compose logs vcmix

# Manual health check
curl http://localhost:8000/api/health
```

### Port already in use

```bash
# Change port in .env
echo "VCMIX_PORT=8080" >> .env
docker compose up -d
```

### Render fails with ffmpeg error

The Docker image includes ffmpeg. If running without Docker:

```bash
# Ubuntu/Debian
sudo apt-get install ffmpeg

# macOS
brew install ffmpeg
```

---

## Architecture

```
┌──────────────────────────────────────────┐
│              VCMix Container              │
│                                          │
│  ┌────────────────────────────────────┐  │
│  │         FastAPI Application        │  │
│  │                                    │  │
│  │  [core routes]  [full routes]      │  │
│  │   render         ai_transcription  │  │
│  │   plugins        collaboration     │  │
│  │   presets        waveform          │  │
│  │   midi           piano_roll        │  │
│  │   automation                       │  │
│  │   arrangement                      │  │
│  │   automix                          │  │
│  │   agent_api                        │  │
│  └────────────────────────────────────┘  │
│                                          │
│  /app/projects  /app/output  /app/presets│
└──────────────────────────────────────────┘
       ↕              ↕            ↕
  host:projects  host:output  host:presets
```

---

## CLI Profile Reference

```bash
# Core: lightweight, no AI modules
vcmix serve --profile core

# Full: all features (default, backward compatible)
vcmix serve --profile full

# Same as --profile full
vcmix serve

# With custom host/port
vcmix serve --profile core --host 0.0.0.0 --port 8080

# Environment variable alternative
VCMIX_PROFILE=core vcmix serve
```

---

## Plugin Architecture

```
┌──────────────────────────────────────────────┐
│              VCMix Plugin System              │
│                                              │
│  vc_plugins.py                               │
│    ├─ VC CLI subprocess adapter (default)    │
│    │   Path: /app/plugins/VC-{Name}/...      │
│    │   Env: VC_AUDIOFX_DIR=/app/plugins      │
│    │                                         │
│    └─ Native Python adapter (planned)        │
│        numpy/scipy implementations           │
│                                              │
│  23 VC Plugins:                              │
│    20 effects: EQ, Comp, Gain, DeEsser,      │
│      Saturator, Limiter, Delay, Reverb,      │
│      DynamicEQ, Smooth, SurgicalDeEsser,     │
│      Distortion, Noise, Tune, Gate, Chorus,  │
│      MultiBand, Harmonizer, PitchShift,      │
│      Stereo                                  │
│    3 instruments: Synth, Drum, Arp           │
│                                              │
│  Total CLI binary size: ~2.9MB               │
└──────────────────────────────────────────────┘
```

### Plugin Path Resolution (priority order)

1. `params["cli_path"]` — per-effect override
2. Environment variable `VC_{NAME}_CLI` — e.g. `VC_REVERB_CLI`
3. YAML config `plugin_paths` section
4. Default: `$VC_AUDIOFX_DIR/VC-{Name}/VC-{Name}-CLI-Standalone`

### Docker Build: CLI Binary Strategy

| Method | How | Use Case |
|--------|-----|----------|
| **GitHub Release download** (default) | Build auto-downloads from AudioFX releases | CI/CD, cloud deployment |
| **Local docker/plugins/** | Place pre-built binaries before `docker build` | Air-gapped, custom builds |
