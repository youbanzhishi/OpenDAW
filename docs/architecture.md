# OpenDAW Architecture

## Overview

OpenDAW (codename: **VCMix**) is an AI-native, YAML-driven, cross-platform
Digital Audio Workshop engine. It operates without a GUI, making it ideal
for AI agent control, batch processing, and headless server deployment.

## Design Principles

1. **YAML-First** — Every project is a declarative YAML file. No binary project files.
2. **CLI-Driven** — All operations via `vcmix` CLI. Zero GUI dependency.
3. **Streaming Rendering** — Process audio incrementally to handle large projects.
4. **Plugin Ecosystem** — Native Python plugins + VC CLI adapters for AudioFX plugins.

## Module Architecture

```
┌─────────────────────────────────────────────┐
│                   CLI (click)                │
│  render | validate | graph | analyze        │
└──────────────────┬──────────────────────────┘
                   │
┌──────────────────▼──────────────────────────┐
│              Config Layer                    │
│  parser.py ── YAML → dict                   │
│  validator.py ── Schema checks              │
└──────────────────┬──────────────────────────┘
                   │
┌──────────────────▼──────────────────────────┐
│            Engine Layer                      │
│  renderer.py ── Pipeline orchestrator       │
│  analyzer.py ── RMS/Peak/Spectrum           │
│  autofix.py ── Gain staging correction      │
└──────────────────┬──────────────────────────┘
                   │
┌──────────────────▼──────────────────────────┐
│           Audio Layer                        │
│  io.py ── WAV/FLAC read/write               │
│  mixer.py ── Multi-track mixing             │
│  meter.py ── Metering utilities             │
└──────────────────┬──────────────────────────┘
                   │
┌──────────────────▼──────────────────────────┐
│          Plugin Layer                        │
│  adapter.py ── PluginAdapter ABC            │
│  registry.py ── Dynamic plugin loading      │
│  vc_plugins.py ── VC CLI wrappers           │
└──────────────────┬──────────────────────────┘
                   │
┌──────────────────▼──────────────────────────┐
│           BPM Layer                          │
│  detector.py ── Tempo detection             │
│  sync.py ── Beat grid & stretch ratio       │
└─────────────────────────────────────────────┘
```

## Signal Flow (Phase 1)

```
Track Audio → [Insert Chain] → Mixer → [Master Inserts] → Output File
```

Each track has an insert chain of plugins processed sequentially.
All tracks are mixed together, then the master insert chain is applied.

## YAML Project Schema (Phase 1)

```yaml
name: "My Song"
bpm: 120
time_signature: "4/4"
sample_rate: 44100

tracks:
  - name: "Vocal"
    file: "vocal.wav"
    gain: -3.0       # dB
    pan: 0.0         # -1.0 to 1.0
    inserts:
      - plugin: "vc-eq"
        parameters: { high_shelf_db: -2.0 }

master:
  inserts:
    - plugin: "vc-comp"
      parameters: { threshold_db: -6.0, ratio: 2.0 }

output:
  path: "output/mix.wav"
  format: "wav"
```

## Phase Roadmap

| Phase | Key Addition | Architecture Impact |
|-------|-------------|-------------------|
| 1 | Insert chain + Master + Multi-track + BPM | Core pipeline |
| 2 | Send/Return + Sidechain + A/B + Auto-fix | Bus routing layer |
| 3 | AI Reference Analysis (stem separation) | Analysis extensions |
| 4 | Smart Arrangement + Arrange-Mix | Timeline + arrangement |
| 5 | Full DAW (GUI + VST3 + MIDI + Agent API) | UI + hosting layer |

## Dependencies

| Package | Purpose | Required |
|---------|---------|----------|
| numpy | Audio buffer operations | Yes |
| soundfile | WAV/FLAC I/O | Yes |
| pyyaml | YAML parsing | Yes |
| pydantic | Schema validation | Yes |
| click | CLI framework | Yes |
| rich | Terminal formatting | Yes |
| librosa | BPM detection, advanced analysis | Optional |
