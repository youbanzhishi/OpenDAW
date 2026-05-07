# Changelog

All notable changes to OpenDAW/VCMix will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- **VCMix Phase 3: Preset Management** — 7 built-in mixing presets
  - pop_vocal, rock_vocal, podcast, ballad_vocal, rap_vocal, choir, acoustic
  - Custom preset save/load (YAML format)
  - CLI: `vcmix presets` command (planned)
- **VCMix Phase 4: Real-time Data Stream** — Structured event streaming
  - DataStream emitter: JSON / dict / callback output formats
  - Event types: track_level, effect_delta, master_level, warning, decision, sibilance
  - Enables closed-loop control: render → stream data → AI analyzes → adjust → re-render
- **VCMix Phase 5: Source Separation & Reverse Analysis** — AI扒带基础
  - Demucs wrapper (API + CLI fallback) for stem separation
  - Reverse analyzer: per-stem mixing technique extraction
  - Auto-generate VCMix YAML config from reference track
- **Plugin Registry: 16 Gen1 plugins** — Full VocalChain suite
  - Added: vc-surgicaldeesser, vc-distortion, vc-noise, vc-tune, vc-gate, vc-chorus
  - All with CLI parameter mappings
- **73 pytest cases** — Full test coverage for all modules

## [0.1.0] - 2026-05-07

### Added
- **VCMix Phase 1 MVP** — YAML-driven headless mixing host
  - YAML project config parser with pydantic validation
  - BPM note-value to millisecond conversion
  - BPM detection from audio (librosa beat_track)
  - Multi-track audio I/O (WAV read/write)
  - Audio mixer with per-track level control
  - Signal routing: Track → Insert Chain → Master
  - VC plugin CLI adapter (10 → 16 plugins)
  - Audio analyzer: RMS, Peak, True Peak, spectrum, sibilance
  - Real-time progress streaming (--stream log|json)
  - Auto-fix gain staging (--auto-fix)
  - CLI commands: render, validate, graph, analyze
  - 48/48 pytest passing

### Architecture
- Three Core Principles: Cross-platform / Lightweight & Fast / AI Agent Friendly
- 双轨UI规划: CLI(AI) + GUI(人类), Phase 1纯CLI先行
