//! OpenDAW 扩展注册中心
//!
//! 四根柱子：Plugin API + Script Runtime + Model Bus + Hook System
//! 所有扩展通过 ExtensionRegistry 统一管理

pub mod error;
pub mod types;
pub mod plugin_api;
pub mod script_runtime;
pub mod model_bus;
pub mod hook_system;
pub mod config;
pub mod registry;

// 公共接口重导出
pub use error::{ExtensionError, PluginError, ScriptError, ModelError, HookError};
pub use types::{AudioBuffer, ParamInfo, PluginType, ModelInput, ModelOutput, ScriptValue};
pub use plugin_api::VcPlugin;
pub use script_runtime::{ScriptEngine, SimpleScriptEngine};
pub use model_bus::{ModelBackend, LocalBackend};
pub use hook_system::{HookSystem, HookContext, HookInfo};
pub use registry::ExtensionRegistry;
pub use config::ExtensionConfig;
