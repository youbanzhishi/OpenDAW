# Changelog

## [0.5.0] — 2025-05-07

### Phase 5: Arrangement Structure Extraction
- `arrangement.py` — Section detection from separated stems (intro/verse/chorus/bridge/outro)
- Per-stem energy envelope computation (RMS per beat)
- Energy-based boundary detection with smoothing
- Section labeling heuristics (energy level + instrument activity)
- Short section merging (configurable min beats)
- Convenience function `extract_arrangement()`
- 19 tests for arrangement extraction

### Phase 4: DataStream Integration
- `renderer.py` now integrates DataStream for closed-loop control
- Real-time events: track_level, effect_delta, master_level, warning, sibilance, decision
- Warning detection: clipping, low SNR, sibilance threshold
- Decision events: auto-fix gain applied
- `get_stream_events()` method for dict-format retrieval

### Phase 3: Built-in Presets
- 7 preset profiles: pop_vocal, rock_vocal, podcast, ballad_vocal, rap_vocal, choir, acoustic
- CLI command: `vcmix presets` — list/apply presets
- Plugin registry updated to 16 Gen1 plugins with param maps

### Phase 2: Send/Return + Sidechain + A/B
- `bus.py` — Send/Return bus system (multiple buses per track, level control)
- Sidechain routing with topological sort render order
- A/B comparison rendering (`--ab`, `--ab --diff`)
- AutoFix v2: chain-level gain staging analysis + auto gain insertion
- CLI options: `--ab`, `--diff`
- 82 new Phase 2 tests

### Bug Fixes & Improvements
- Ruff lint compliance (3 rounds of fixes)
- All 149 tests passing

## [0.1.0] — 2025-05-07

### Phase 1: MVP
- YAML-driven mixing engine
- Insert chain processing
- Multi-track mixing
- BPM note value sync
- Plugin registry (10 plugins initially)
- Audio analysis (RMS/Peak/spectrum/sibilance)
- AutoFix gain staging
- CLI: render/validate/graph/analyze
- 48 tests
