# Changelog

## v0.7.0 — Phase 6-7 Complete (2025-05-07)

### Phase 6: AutoMix Engine
- **automix.py** (450 lines): Full auto-mixing engine with spectral analysis, gain riding, dynamic range optimization
- **reference_matcher.py**: Reference track matching with spectral comparison and adjustment suggestions
- AutoFix v2: Corrective actions (de-ess, de-plosive, noise gate) integrated into rendering pipeline

### Phase 7: Arrangement-Aware Mixing
- **arrangement_strategy.py** (379 lines): Section-aware mixing strategy with per-section reverb/delay/compression/gain
- Crossfade interpolation between sections (intro→verse→chorus→bridge→outro)
- CLI: `vcmix arrangement project.yaml --strategy` and `vcmix render --arrangement-aware`
- YAML override export for arrangement-aware parameter adjustments

### Gen2 Plugin Registry
- 18 plugins registered (16 Gen1 + VC-Stereo + VC-PitchShift)
- Dynamic plugin loading with fallback for missing modules

### Testing
- 256/256 pytest tests passing
- 36 new arrangement strategy tests
- 17 reference matcher tests
- 24 automix tests

## v0.6.0 — Phase 5 + Gen2 Progress (2025-05-07)

### Phase 5: Arrangement Extraction
- ArrangementExtractor with section detection (intro/verse/chorus/bridge/outro)
- Energy-based and silence-based section boundary detection

### Phase 4: DataStream Integration
- Real-time event streaming (6 event types: level, warning, decision, state, progress, custom)
- DataStreamEmitter integrated into renderer pipeline

## v0.5.0 — Phase 2-3 (2025-05-07)

### Phase 3: Presets
- 7 built-in presets: pop, rock, podcast, ballad, rap, choir, acoustic

### Phase 2: Send/Return + Sidechain
- Send/Return bus routing
- Sidechain routing for compressor
- A/B comparison

## v0.1.0 — Phase 1 MVP (2025-05-07)
- YAML-driven rendering pipeline
- Plugin chain with 16 Gen1 plugins
- CLI: render, plugins, validate commands
