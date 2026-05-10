# Changelog

## [0.25.0] - 2026-05-10

### Added
#### v0.25.0 桌面App音频播放串联

**音频后端集成 (audio-engine)**
- 新增 `channel` feature：通过 crossbeam-channel 传递音频帧
- 新增 `channel_output.rs`：AudioOutputHandle, AudioFrame, AudioRenderer
- AudioEngine 新增：setup_channel_output, send_output_frame, set_output_handle

**Desktop音频输出 (desktop/src-tauri/src/audio_output.rs)**
- DesktopAudioOutput：通过CPAL实现实时音频播放
- 在独立线程中运行CPAL Stream（解决Linux下Stream不是Send的问题）
- AudioOutputState：线程安全的音频输出封装

**Tauri命令增强**
- audio_init：初始化音频输出
- audio_get_status：获取播放状态
- audio_play/stop/pause/resume：播放控制
- audio_load_and_play：加载WAV并播放
- audio_set_master_volume：设置主音量
- audio_get_devices：获取可用音频设备

**前端UI增强**
- 播放/停止按钮绑定到Tauri音频命令
- 音量滑块 → audio_set_master_volume
- Load WAV按钮 → audio_load_and_play
- 播放状态显示

### Changed
- desktop/Cargo.toml：启用 audio-engine/channel feature，添加 cpal + crossbeam-channel 依赖
- desktop/src-tauri/src/state.rs：添加 audio_output 状态
- desktop/src-tauri/src/lib.rs：注册新音频命令

## [0.24.0] - 2026-05-10

### Added
#### v0.24.0 集成：Rust引擎+Plugin Host+PyO3桥接

**Step1: Engine Tauri Commands**
- 14个Tauri命令：engine_start/stop/pause, register_track, load_wav, set_track_volume等
- AudioEngine新增：set_track_volume, toggle_track_mute, set_master_volume, load_wav, set_track_pan

**Step2: WAV加载+实时播放+控制**
- hound库集成：from_wav_file支持8/16/24/32bit PCM和32bit Float
- 声像控制：set_track_pan/get_track_pan (-1.0~1.0)

**Step3+4: PluginChain+JSFX适配器+AudioBuffer桥接**
- PluginChain：process(f64) + process_engine(f32)
- JsfxPlugin实现VcPlugin trait
- AudioBuffer桥接层：ext_to_engine/engine_to_ext (f64<->f32)

**Step5: PyO3桥接+RustEngineProxy**
- RustEngine PyClass + RustEngineProxy (fallback to PythonFallbackEngine)

#### Phase 22b: 多模型+Persona
- EnhancedModelBus：4个LLM后端(OpenAI/Anthropic/Google/Ollama)
- PersonaManager：内置/自定义Persona
- EnhancedRuntime + ModelProvider

### Fixed
- CI: libsoup-3.0-dev + webkit2gtk deps
- chain.rs: EngineAudioBuffer.data private field access
- phase22b: ruff-broken imports restored
- Track::stereo/mono convenience constructors
- EngineAudioBuffer: resize/get/set/data_len public methods


## [0.21.0] - 2026-05-15

### Added
#### Phase 19: CLI负数参数修复
- AudioFX 25个插件parseArgs修复，--threshold -20等负数参数正确解析

#### 完整端到端测试
- 27测试：项目生命周期+AI工作流+扒带工作流

#### 性能基准测试
- 11测试：渲染性能+缓存+并行加速+内存+增量渲染

### Tests
- 38新测试
- 总计1590测试全绿

## [0.20.0] - 2026-05-14

### Added
#### Phase 18: 多用户协作编辑
- WebSocket实时同步+LWW冲突解决+5种变更类型

#### 多格式导出
- WAV/MP3/FLAC/OGG/MIDI

#### Stem导出
- 逐轨+按总线

#### 项目版本管理
- 快照CRUD+差异比较+恢复+回滚

#### 新CLI命令
- export/export-stems/snapshot/snapshots/restore

#### 新API端点
- 6个新API端点+1个协作WebSocket

### Tests
- 114新测试
- 总计1552测试全绿

# Changelog

## [0.19.0] - 2026-05-08

### Added
#### Phase 17: AI扒带管线
- Demucs分离→逆向混音分析→编曲结构→BPM/调性检测→VCMix项目

#### 参考曲风格匹配
- 6频段频率平衡+谱质心+4-on-floor检测+规则分类

#### 风格迁移
- EQ/压缩/混响/增益平衡从参考曲迁移到目标项目

#### 一键Remix
- 参考曲+新素材→自动融合混音

#### 新CLI命令
- transcribe/match-style/style-transfer/remix

#### 新API端点
- 4个新API端点

### Tests
- 92新测试
- 总计1438测试全绿


## [0.18.0] - 2026-05-08

### Added
#### Phase 16: 跨平台打包
- pyproject.toml完善+wheel构建成功（274K）

#### Docker镜像
- Dockerfile+docker-compose+.dockerignore

#### GitHub Actions CI矩阵
- 3OS×4Python版本+PyPI发布+Docker GHCR+Tauri桌面构建

#### Tauri桌面应用配置
- Windows NSIS/macOS DMG/Linux AppImage+deb

#### CLI serve命令
- vcmix serve --host --port --reload

### Tests
- 63新测试
- 总计1346测试全绿

## [0.17.0] - 2026-05-18

### Added
#### Phase 15: AI编曲引擎
- music_theory模块：12音阶+18和弦+22进程+K-S调性检测+composer自动编曲

#### 智能混音闭环
- 渲染→分析→诊断→调参→验证自动迭代

#### 编曲混音一体化
- 一键compose+auto-mix

#### 新CLI命令
- compose / auto-mix / compose-and-mix

#### 新API端点
- /ai/compose, /ai/auto-mix, /ai/compose-and-mix

### Tests
- 183新测试
- 总计1283测试全绿


## [0.16.0] - 2026-05-17

### Added
#### Phase 14: VST3 Hosting深化
- C++ Host完整实现+参数自动化+状态序列化+MIDI处理

#### 实时音频引擎
- RealtimeEngine+AudioDriver+Transport
- 多轨实时混音+播放/暂停/seek/loop/录音

#### VST3 Python接口深化
- ctypes桥接+自动mock回退+参数枚举+预设管理+状态快照undo/redo

#### VST3插件扫描器V2
- JSON缓存+增量扫描+跨平台路径+AU stub

### Tests
- 194新测试（106实时引擎+88 VST3）
- 总计1100测试全绿

## [0.15.0] - 2026-05-16

### Added
#### Phase 13: Tauri原生GUI深化
- 7个Tauri命令：项目操作+渲染控制+音频播放+可视化数据获取
- 窗口配置升级：自定义标题栏+最小尺寸+居中显示+深色主题

#### Waveform波形可视化
- Canvas绘制波形+缩放+选区+时间标尺
- 实时峰值跟踪+RMS包络显示

#### FFT频谱分析
- 1/3倍频程分析
- 电平表实时显示
- 瀑布图频谱历史可视化

#### MIDI钢琴卷帘
- 网格绘制+音符矩形渲染
- 播放指针实时跟踪
- 速度/力度色彩映射

#### Web UI扩展
- 11个Tab（原8+3可视化Tab：Waveform/Spectrum/Piano Roll）

#### 新API端点
- 4个新REST端点：waveform/spectrum/midi数据获取

### Tests
- 42新测试
- 总计906测试全绿

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
