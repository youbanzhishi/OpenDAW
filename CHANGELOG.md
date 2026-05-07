# Changelog

All notable changes to OpenDAW/VCMix will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-05-07

### Added
- **VCMix Phase 1 MVP** — YAML-driven headless mixing host
  - YAML project config parser with pydantic validation
  - BPM note-value to millisecond conversion (`1/4`, `1/8d`, `1/8t` etc.)
  - BPM detection from audio (librosa beat_track with slow-song correction)
  - Multi-track audio I/O (WAV read/write via soundfile)
  - Audio mixer with per-track level control
  - Signal routing: Track → Insert Chain → Master
  - VC plugin CLI adapter (calls VC-*-CLI-Standalone executables)
  - Plugin registry (10 VC plugins registered)
  - Audio analyzer: RMS, Peak, True Peak, spectrum bands, sibilance ratio
  - Real-time progress streaming (--stream log|json)
  - Auto-fix gain staging (--auto-fix)
  - Analysis report mode (--report)
  - CLI commands: render, validate, graph, analyze
  - Mermaid graph output (vcmix graph -f mermaid)
  - JSON structured output for AI Agent consumption

### Testing
- 48 pytest cases covering: BPM sync, YAML parsing, audio I/O, mixer, analyzer, plugin registry, meter, renderer
- CI workflow: 3 OS × 4 Python versions = 12 matrix
- Release workflow: test → auto-generate changelog → GitHub Release

### Documentation
- README with quick start and example YAML
- Example project: `examples/jiuwanzi.yaml`
- 知识沉淀: VCMix测试体系与CI实践.md

### Architecture
- Three Core Principles: Cross-platform / Lightweight & Fast / AI Agent Friendly
- 双轨UI规划: CLI(AI) + GUI(人类), Phase 1纯CLI先行
- Python调度层 + C++ DSP核心(AudioFX仓库VC插件系列)
