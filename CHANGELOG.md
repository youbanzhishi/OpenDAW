# Changelog

All notable changes to OpenDAW/VCMix will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.0] - 2026-05-14

### Added
- **VCMix Phase 2** — From "works" to "works well"
  - **Send/Return Bus System** (`engine/bus.py`)
    - `SendReturnBus` class with independent effect chain and return_level
    - `BusManager` for coordinating send/return routing across tracks
    - YAML `sends` section with bus definitions
    - Track-level `sends: {bus_name: level}` routing
    - BPM note-value auto-conversion in bus effects
    - Bus returns mixed back into master output
  - **Sidechain Routing** (`plugins/adapter.py`)
    - `process_with_sidechain()` method on PluginAdapter
    - Sidechain simulation via gain envelope analysis
    - Effect-level `sidechain: track_name` in YAML config
    - Automatic render order resolution via topological sort (Kahn's algorithm)
    - Sidechain source tracks rendered before consumers
  - **A/B Comparison** (`config/parser.py` + `engine/renderer.py` + `cli.py`)
    - `effects_a` / `effects_b` on TrackConfig
    - `--ab` CLI flag renders both versions → `output_a.wav` + `output_b.wav`
    - `--ab --diff` adds difference analysis (RMS delta, peak delta, diff spectrum)
    - Tracks with only one chain defined use default `effects` for the other
  - **AutoFix Gain Staging v2** (`engine/autofix.py`)
    - `GainStageInfo` dataclass: per-effect input/output analysis
    - `ChainAnalysis` dataclass: full chain gain flow report
    - `analyze_chain()`: per-effect gain stage analysis with rendered audio
    - Gain accumulation detection (consecutive boost → clip, consecutive cut → SNR)
    - `fix_gain_staging()`: auto-inserts vc-gain nodes at problematic points
    - Rules: input ≤ -6dBFS headroom, output ≥ -24dBFS SNR floor, final ≤ -1dBFS
    - Phase 1 API fully backward compatible
  - **YAML Config Extensions** (`config/parser.py`)
    - `SendBusConfig` pydantic model for send bus definitions
    - `sidechain` field on `EffectConfig`
    - `effects_a` / `effects_b` on `TrackConfig`
    - `sends: {bus_name: level}` on `TrackConfig`
    - `ProjectConfig.has_ab` and `has_sidechain` properties
    - Note-value conversion across all chains (effects, effects_a, effects_b, sends)
  - **CLI Enhancements** (`cli.py`)
    - `--ab` flag for A/B comparison rendering
    - `--diff` flag for difference analysis
    - Validate checks for send bus references and sidechain references
  - **82 new pytest cases** across 4 test files
    - `test_bus.py` — Send/Return bus tests (15 tests)
    - `test_sidechain.py` — Sidechain routing tests (10 tests)
    - `test_ab_compare.py` — A/B comparison tests (12 tests)
    - `test_autofix_v2.py` — Gain staging v2 tests (15 tests)
  - Total: 130/130 pytest passing (48 Phase 1 + 82 Phase 2)

### Changed
- `engine/renderer.py` — Full pipeline rewrite to support sends, sidechain, AB
- `plugins/adapter.py` — Added `process_with_sidechain()` with simulation
- `engine/autofix.py` — Added chain analysis API (Phase 1 API unchanged)
- `config/parser.py` — Extended models for Phase 2 features
- `engine/__init__.py` — Export BusManager, SendReturnBus
- `README.md` — Updated with Phase 2 features, YAML examples, CLI commands

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
