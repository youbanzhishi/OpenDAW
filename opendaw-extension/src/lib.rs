//! OpenDAW 扩展注册中心
//!
//! 四根柱子：Plugin API + Script Runtime + Model Bus + Hook System
//! 所有扩展通过 ExtensionRegistry 统一管理

pub mod config;
pub mod error;
pub mod hook_system;
pub mod model_bus;
pub mod plugin_api;
pub mod plugin_param;
pub mod registry;
pub mod script_runtime;
pub mod types;

// 公共接口重导出
pub use config::ExtensionConfig;
pub use error::{ExtensionError, HookError, ModelError, PluginError, ScriptError};
pub use hook_system::{HookContext, HookInfo, HookSystem};
pub use model_bus::{LocalBackend, ModelBackend};
pub use plugin_api::{PluginEntry, PluginInfo, VcPlugin};
pub use plugin_param::{ParameterType, ParameterValue, PluginParameter};
pub use registry::ExtensionRegistry;
pub use script_runtime::{ScriptEngine, SimpleScriptEngine};
pub use types::{AudioBuffer, ModelInput, ModelOutput, ParamInfo, PluginType, ScriptValue};
