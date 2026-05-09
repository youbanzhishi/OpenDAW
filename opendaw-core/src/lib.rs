//! OpenDAW Core — 核心胶水层
//!
//! 统一入口，组合所有crate：
//! - opendaw-extension: 扩展注册中心
//! - audio-engine: 音频引擎
//! - plugin-host: 插件宿主
//!
//! 提供：
//! - 项目管理（加载YAML、组织Track/Plugin）
//! - 混音器（Track -> PluginChain -> Bus -> Master）
//! - 离线渲染
//! - AudioBuffer 桥接层
//! - PyO3 Python绑定（需要python feature）

pub mod project;
pub mod mixer;
pub mod render;
pub mod bridge;

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
pub use project::Project;
pub use mixer::Mixer;
pub use render::OfflineRenderer;

// 兼容性别名
#[deprecated(since = "0.24.0", note = "使用 ExtAudioBuffer 或 EngineAudioBuffer")]
pub type AudioBuffer = opendaw_extension::AudioBuffer;
