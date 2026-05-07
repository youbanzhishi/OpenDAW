# Changelog

## [0.10.0] - 2026-05-08

### Added
#### Phase 9: MIDI + Automation + Chain Presets
- MIDI文件解析（MidiParser，支持Format 0/1，tick→beat转换）
- 音符调度与内置合成器（NoteScheduler，sine/sawtooth/square/triangle）
- 自动化曲线（AutomationCurve，step/linear/smooth三种插值）
- 自动化引擎（AutomationEngine，gain+插件参数自动化）
- 插件链预设（ChainPresetManager，4个内置链：vocal/drum/master/guitar）
- CLI chain-presets命令组（list/show/apply/save）
- Renderer集成：MIDI轨道渲染+自动化参数实时应用
- Web UI Phase 9扩展：MIDI tab + Chains tab
- VST3 Hosting架构设计文档（docs/VST3-Hosting-Design.md + vst3_host/原型）

### Fixed
- ruff lint 100错误→0（import排序+未使用变量+长行+重复定义）
- MIDI parser bug：set_tempo事件在time=0时被忽略
- Automation STEP曲线语义测试修正

### Tests
- 439测试全绿（从315增长到439）


## [0.9.0] - 2026-05-08

### Added
- 38个端到端集成测试（tests/integration/test_e2e.py）
  - Render/Validate/Graph/Analyze/Automix/Arrangement/Presets/CLI基本/Exit Codes 9个测试类
- Tauri桌面壳设计文档（Phase 8.5）

### Fixed
- arrangement CLI命令6个Bug修复：
  - ArrangementExtractor不接受bpm参数
  - extract()需要音频数据而非文件路径
  - Section字段名section_type→name, confidence→energy_level
  - SectionMixParams字段名gain_offset_db→gain_db
  - ArrangementStrategy.from_sections()不接受bpm参数

## v0.8.0 — Phase 8 Web UI (2025-05-08)

### Phase 8: Web UI
- **FastAPI backend**: REST API + WebSocket DataStream
  - POST /api/render — Async render with job tracking
  - GET /api/plugins — 20 VC plugins listing
  - GET /api/presets — Built-in + custom presets
  - GET /api/arrangement + /api/arrangement/strategy
  - POST /api/automix + /api/validate
  - WS /api/stream — Real-time DataStream forwarding
- **Pure HTML/JS frontend**: 5-tab UI (YAML editor, render, plugins, presets, live stream)
- **WebSocket level meters**: Real-time audio level display
- **Auto-generated API docs**: /api/docs (Swagger) + /api/redoc
- **pip install vcmix[web]**: Optional web dependencies

### Other Changes
- 315/315 pytest tests (21 new web API tests + E2E integration tests)
- Plugin registry: 20 plugins (added vc-multiband, vc-harmonizer)
- CLI: arrangement command + --arrangement-aware render flag
- E2E integration test suite (tests/integration/)

## v0.7.0 — Phase 6-7 Complete (2025-05-07)

### Phase 6: AutoMix Engine
- automix.py (450 lines): Full auto-mixing with spectral analysis
- reference_matcher.py: Reference track matching
- AutoFix v2 integrated into rendering pipeline

### Phase 7: Arrangement-Aware Mixing
- arrangement_strategy.py (379 lines): Section-aware mixing
- CLI: vcmix arrangement + --arrangement-aware
- 36 new arrangement strategy tests

## v0.6.0 — Phase 5 + Gen2 (2025-05-07)
- Phase 5: ArrangementExtractor
- Phase 4: DataStream (6 event types)
- Gen2 plugin registry (18 plugins)

## v0.5.0 — Phase 2-3 (2025-05-07)
- Phase 3: 7 built-in presets
- Phase 2: Send/Return + Sidechain + A/B

## v0.1.0 — Phase 1 MVP (2025-05-07)
- YAML-driven rendering pipeline
- 16 Gen1 plugins
