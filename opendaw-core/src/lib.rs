//! OpenDAW Core — 核心胶水层
//!
//! 统一入口，组合所有crate：
//! - opendaw-extension: 扩展注册中心
//! - audio-engine: 音频引擎
//! - plugin-host: 插件宿主
//!
//! 提供：
//! - 项目管理（加载YAML/JSON/Binary、组织Track/Plugin）
//! - 项目格式互转（YAML↔JSON↔Binary）
//! - 命令模式 Undo/Redo（支持分支历史）
//! - 混音器（Track → PluginChain → Bus → Master）
//! - Sidechain路由
//! - 多级Bus系统
//! - 自动化曲线编辑器
//! - Pattern库
//! - 和弦进行生成器
//! - 时间线管理
//! - 离线渲染
//! - AudioBuffer 桥接层
//! - PyO3 Python绑定（需要python feature）
//!
//! Phase 29: AI引擎深度集成
//! - 扒带引擎（音频→MIDI）
//! - 智能混音v2
//! - 风格迁移v2
//!
//! Phase 30: 跨DAW格式兼容
//! - Reaper RPP导入
//! - Ableton ALS解析
//! - MIDI导出
//! - 导入/导出注册表
//!
//! Phase 33: 插件市场完善
//! - 远程仓库连接 + 索引缓存
//! - 评分与评论系统
//! - 分类体系增强
//! - 平台兼容性检测
//!
//! Phase 35: v1.0发布准备
//! - SDK文档生成（OpenAPI 3.1）
//! - 项目模板系统
//! - 音频导出增强（WAV/FLAC/MP3-stub/OGG-stub）

// Phase 20-25: 核心引擎层
pub mod bridge;
pub mod mixer;
pub mod project;
pub mod render;

// Phase 26: 项目格式升级
pub mod command;
pub mod project_format;

// Phase 27: 高级混音功能
pub mod automation;
pub mod bus;
pub mod sidechain;

// Phase 28: 编曲引擎增强
pub mod chord;
pub mod pattern;
pub mod timeline;

// Phase 29: AI引擎深度集成
pub mod smart_mix;
pub mod style_transfer;
pub mod transcription;

// Phase 30: 跨DAW格式兼容
// Phase 31-32: 接口层后端
// Phase 33: 插件市场完善
pub mod marketplace;

pub mod export;
pub mod import;

// Phase 35: v1.0发布准备
pub mod docs;
pub mod template;

// PyO3 Python bindings (optional, requires python feature)
#[cfg(feature = "python")]
pub mod python;

// 桥接函数重导出
pub use bridge::{
    engine_to_ext, engine_to_ext_full, engine_to_ext_new, ext_to_engine, ext_to_engine_full,
    ext_to_engine_new,
};

// 重导出核心类型
pub use audio_engine::{
    AudioBuffer as EngineAudioBuffer, AudioEngine, EngineState, Scheduler, Track,
};
pub use opendaw_extension::{
    AudioBuffer as ExtAudioBuffer, ExtensionRegistry, HookContext, HookSystem, ModelBackend,
    ModelInput, ModelOutput, ParamInfo, PluginType, ScriptEngine, ScriptValue, VcPlugin,
};
pub use plugin_host::{
    ParamManager, PluginChain, PluginFormat, PluginHost, PluginScanner, PresetManager,
    ScannedPlugin, VcPluginAdapter,
};

// Phase 20-25 重导出
pub use mixer::Mixer;
pub use project::Project;
pub use render::OfflineRenderer;

// Phase 26 重导出
pub use command::{
    AddPluginCommand, AddTrackCommand, Command, CommandContext, CommandHistory, MergeStrategy,
    MoveClipCommand, RemovePluginCommand, RemoveTrackCommand, SetPanCommand, SetVolumeCommand,
    Transaction,
};
pub use project_format::{
    BinarySerializer, FormatConverter, JsonSerializer, ProjectFormat, ProjectFormatError,
    ProjectLoader, ProjectSerializer, YamlSerializer,
};

// Phase 27 重导出
pub use automation::{
    AutomationEnvelope, AutomationLane, AutomationPoint, CurveType, ParameterAutomation,
};
pub use bus::{Bus, BusConfig, BusRouter, BusTemplate, BusType, RouteConnection};
pub use sidechain::{
    SidechainBuffer, SidechainBus, SidechainBusSource, SidechainLink, SidechainRouter,
    SidechainSource,
};

// Phase 28 重导出
pub use chord::{
    Chord, ChordGenerator, ChordProgression, ChordType, Mode, NoteName, VoicingStrategy,
};
pub use pattern::{AudioRegion, MidiNote, Pattern, PatternInstance, PatternLibrary, PatternType};
pub use timeline::{
    TempoChange, TempoChangeType, TimePosition, TimeSignature, TimeSignatureChange, Timeline,
    TimelineCursor,
};

// Phase 29 重导出
pub use smart_mix::{
    AutoMixProfile, CompressionPreset, CompressionSuggestion, EqCharacter, EqSuggestion,
    FrequencyAnalyzer, LoudnessNormalizer, LoudnessResult, MixStyle, MixSuggestion, OctaveAnalysis,
    PanStrategy, SmartMixEngine, SpectrumAnalysis, TrackAnalysis, TrackRole,
};
pub use style_transfer::{
    HarmonyFeatures, MorphParams, RhythmFeatures, StyleFeatures, StyleMorpher, StyleProfile,
    StyleTransferEngine, TimbreFeatures,
};
pub use transcription::{
    BeatDetection, BeatDetector, KeyEstimate, OnsetMethod, PitchDetection, PitchDetector,
    TrackAllocationStrategy, TrackSuggestion, TranscribedNote, TranscriptionConfig,
    TranscriptionEngine, TranscriptionResult, TranscriptionToProject,
};

// Phase 30 重导出
pub use export::{MidiEvent, MidiExportConfig, MidiExporter, MidiTrack};
pub use import::ableton::{
    AbletonClip, AbletonClipContent, AbletonDevice, AbletonDeviceType, AbletonMidiNote,
    AbletonParameter, AbletonParseError, AbletonProject, AbletonProjectParser, AbletonSend,
    AbletonToProject, AbletonTrack, AbletonTrackType,
};
pub use import::reaper::{
    FxMapper, ReaperAudioItem, ReaperFx, ReaperFxType, ReaperMarker, ReaperMidiItem,
    ReaperParseError, ReaperProject, ReaperProjectParser, ReaperSend, ReaperToProject, ReaperTrack,
};
pub use import::{
    ExportError, ExportFormat, ExportRegistry, FormatDetector, ImportError, ImportFormat,
    ImportRegistry,
};

// 兼容性别名
#[deprecated(since = "0.24.0", note = "使用 ExtAudioBuffer 或 EngineAudioBuffer")]
pub type AudioBuffer = opendaw_extension::AudioBuffer;

// Phase 31-33 重导出
pub use marketplace::{
    preset_categories,
    CachedIndex,
    CompatibilityReport,
    Dependency,
    EffectSubcategory,
    InstallProgress,
    InstallStatus,
    InstrumentSubcategory,
    PlatformTarget,
    PluginCategory,
    PluginCompatibility,
    PluginInstaller,
    PluginManifest,
    PluginRegistry,
    // Phase 33 新增
    PluginRepository,
    PluginReview,
    RatingSummary,
    RepositorySource,
    ReviewManager,
    UtilitySubcategory,
};

// Phase 35 重导出
pub use docs::{ApiDocGenerator, ApiEndpoint, HttpMethod};
pub use export::audio_export::{
    AudioExporter, AudioFormat, BitDepth, ExportConfig as AudioExportConfig,
    ExportError as AudioExportError, ExportProgress, ExportResult as AudioExportResult,
    RenderPipeline,
};
pub use template::{PresetName, ProjectTemplate, TemplateTrack, TrackType};
