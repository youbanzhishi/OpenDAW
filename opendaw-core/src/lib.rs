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

pub mod project;
pub mod mixer;
pub mod render;
pub mod bridge;

// 桥接函数重导出
pub use bridge::{engine_to_ext, ext_to_engine};

// 重导出核心类型
pub use opendaw_extension::{
    ExtensionRegistry, VcPlugin, ScriptEngine, ModelBackend,
    HookSystem, HookContext, AudioBuffer, ParamInfo, PluginType,
    ModelInput, ModelOutput, ScriptValue,
    SimpleScriptEngine, LocalBackend,
};
pub use audio_engine::{
    AudioEngine, EngineAudioBuffer, Scheduler, Track, EngineState,
};
pub use plugin_host::{
    PluginHost, PluginChain, ParamManager, PresetManager, VcPluginAdapter,
};
pub use project::Project;
pub use mixer::Mixer;
pub use render::OfflineRenderer;
