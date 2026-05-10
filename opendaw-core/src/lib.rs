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

// Phase 20-25: 核心引擎层
pub mod project;
pub mod mixer;
pub mod render;
pub mod bridge;

// Phase 26: 项目格式升级
pub mod project_format;
pub mod command;

// Phase 27: 高级混音功能
pub mod sidechain;
pub mod bus;
pub mod automation;

// Phase 28: 编曲引擎增强
pub mod pattern;
pub mod chord;
pub mod timeline;

// PyO3 Python bindings (optional, requires python feature)
#[cfg(feature = "python")]
pub mod python;

// 桥接函数重导出
pub use bridge::{
    engine_to_ext, ext_to_engine,
    engine_to_ext_full, ext_to_engine_full,
    engine_to_ext_new, ext_to_engine_new,
};

// 重导出核心类型
pub use opendaw_extension::{
    ExtensionRegistry, VcPlugin, ScriptEngine, ModelBackend,
    HookSystem, HookContext, AudioBuffer as ExtAudioBuffer, ParamInfo, PluginType,
    ModelInput, ModelOutput, ScriptValue,
};
pub use audio_engine::{
    AudioEngine, AudioBuffer as EngineAudioBuffer, Scheduler, Track, EngineState,
};
pub use plugin_host::{
    PluginHost, PluginChain, ParamManager, PresetManager, VcPluginAdapter,
    PluginScanner, ScannedPlugin, PluginFormat,
};

// Phase 20-25 重导出
pub use project::Project;
pub use mixer::Mixer;
pub use render::OfflineRenderer;

// Phase 26 重导出
pub use project_format::{
    ProjectFormat, ProjectSerializer, YamlSerializer, JsonSerializer, BinarySerializer,
    FormatConverter, ProjectLoader, ProjectFormatError,
};
pub use command::{
    Command, CommandContext, CommandHistory, MergeStrategy, Transaction,
    AddTrackCommand, RemoveTrackCommand, MoveClipCommand,
    SetVolumeCommand, SetPanCommand, AddPluginCommand, RemovePluginCommand,
};

// Phase 27 重导出
pub use sidechain::{
    SidechainRouter, SidechainBus, SidechainLink, SidechainSource,
    SidechainBuffer, SidechainBusSource,
};
pub use bus::{Bus, BusType, BusConfig, BusRouter, BusTemplate, RouteConnection};
pub use automation::{
    AutomationLane, AutomationPoint, AutomationEnvelope, CurveType, ParameterAutomation,
};

// Phase 28 重导出
pub use pattern::{
    Pattern, PatternType, PatternLibrary, PatternInstance,
    MidiNote, AudioRegion,
};
pub use chord::{
    Chord, ChordType, ChordProgression, ChordGenerator, VoicingStrategy,
    NoteName, Mode,
};
pub use timeline::{
    Timeline, TimelineCursor, TimeSignature, TimeSignatureChange,
    TempoChange, TempoChangeType, TimePosition,
};

// 兼容性别名
#[deprecated(since = "0.24.0", note = "使用 ExtAudioBuffer 或 EngineAudioBuffer")]
pub type AudioBuffer = opendaw_extension::AudioBuffer;
