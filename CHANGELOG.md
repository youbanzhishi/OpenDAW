# Changelog

## [0.14.0] - 2026-05-15

### Added
#### Phase 12: 编曲智能模板
- 8个编曲模板：Pop / EDM / Rock / Hip-Hop / R&B / Progressive / Lo-fi / Orchestral
- 每个模板包含：段落结构、乐器配置、节奏模式、推荐BPM范围

#### 混音预设系统
- 6个混音预设：Clean Pop / Warm Vintage / Punchy EDM / Tight Hip-Hop / Airy Ballad / Lo-fi Chill
- 每个预设包含：EQ曲线、压缩参数、混响设置、立体声宽度、母带链

#### 编曲-混音一体化
- 编曲模板自动匹配对应混音预设
- 模板驱动效果参数自动配置（EQ/压缩/混响/立体声）
- 一键从模板生成完整VCMix配置

#### 新API端点
- 6个新REST端点：模板列表/详情、预设列表/详情、一键生成配置

#### 新CLI命令
- `arrangement-templates`：查看/应用编曲模板
- `mix-presets`：查看/应用混音预设
- `arrangement-mix`：编曲-混音一体化生成

### Tests
- 141新测试
- 总计864测试全绿


## [0.13.0] - 2026-05-14

### Added
#### Phase 11: AI Agent API
- 16 REST端点 + 2 WebSocket端点
- 项目管理：创建/打开/保存/关闭DAW项目
- 渲染控制：启动/停止/查询渲染任务
- AI混音决策：自动分析+建议+应用混音参数
- WebSocket实时通知：渲染进度+AI决策流

#### Demucs音源分离集成
- 逆向混音分析：Demucs模型分离音源→分析各轨处理参数
- 编曲结构分析：基于分离音源的段落检测+能量/频谱特征提取
- VCMix配置生成：从Demucs分析结果自动生成VCMix YAML配置

#### CLI新命令
- `analyze-mix`：Demucs逆向混音分析
- `analyze-arrangement`：Demucs编曲结构分析
- `generate-config`：从分析结果生成VCMix配置

### Tests
- 167新测试（97 Agent API + 70 Demucs）
- 总计723测试全绿

## [0.12.0] - 2026-05-08

### Added
#### Phase 10: Performance Optimization
- AudioCache: LRU音频文件缓存（线程安全+mtime校验+预加载）
- 依赖图分析：自动检测轨道间侧链/发送依赖
- 并行渲染：ThreadPoolExecutor层级并行（--parallel N）
- 增量渲染：SHA-256变更检测+依赖级联失效（--incremental）
- 流式写入：长音频分块写入（>20s自动分块）
- CLI新参数：--parallel/--cache-size/--incremental
- 28个性能测试

### Tests
- 556 tests passed (from 528)
- E2E demo project "Neon Lights" for showcase and integration testing

### Fixed
- MIDI轨道验证误报：MIDI track validator false positive on valid tracks
- Sampler info KeyError: missing key access in zone info display
- ruff lint: line-too-long in sampler info display (cli.py:870)

### Tests
- 528 tests passed


## [0.11.0] - 2026-05-08

### Added
#### Phase 9.5: Sampler Module
- SampleZone: 键位/力度映射+循环模式(forward/reverse/alternate)+触发模式(gate/one-shot)
- SamplerEngine: 多区域映射+线性插值音高偏移+ActiveVoice管理
- SamplerTrack: VCMix集成+MIDI文件解析+逐块渲染
- YAML sampler轨道类型+CLI sampler命令(info/render)
- 45个新测试

#### Web UI Phase 9 Extension
- 3个新tab: MIDI🎹 / Chains🔗 / Auto🎚️
- MIDI API: scan/parse/synths
- Chain Presets API: list/detail/apply
- Automation API: preview/apply
- 14个新API测试
- 曲线可视化(Canvas)

### Tests
- 528 tests passed (from 483)

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
- 466测试全绿（从315增长到466）


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
