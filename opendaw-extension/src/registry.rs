//! Extension Registry — 扩展注册中心
//!
//! 四根柱子的统一入口，管理所有插件、脚本、模型和钩子

use std::collections::HashMap;
use std::path::Path;

use crate::config::ExtensionConfig;
use crate::error::ExtensionError;
use crate::hook_system::HookSystem;
use crate::model_bus::ModelBackend;
use crate::plugin_api::VcPlugin;
use crate::script_runtime::ScriptEngine;
use crate::types::ModelInput;

/// 扩展注册中心 — OpenDAW扩展体系的统一入口
///
/// 管理所有插件、脚本、模型后端和钩子处理器
/// 支持：手动注册、从YAML配置加载、动态发现
pub struct ExtensionRegistry {
    /// 已注册的插件
    plugins: HashMap<String, Box<dyn VcPlugin>>,
    /// 已注册的脚本引擎
    scripts: HashMap<String, Box<dyn ScriptEngine>>,
    /// 已注册的模型后端
    models: HashMap<String, Box<dyn ModelBackend>>,
    /// 钩子系统
    hooks: HookSystem,
}

impl ExtensionRegistry {
    /// 创建空注册中心
    pub fn new() -> Self {
        Self {
            plugins: HashMap::new(),
            scripts: HashMap::new(),
            models: HashMap::new(),
            hooks: HookSystem::new(),
        }
    }

    /// 从YAML配置文件创建注册中心
    ///
    /// 注意：此方法仅解析配置，不实际加载插件/脚本/模型二进制
    /// 需要通过 register_* 方法手动注册具体实例
    pub fn from_config(path: &Path) -> Result<Self, ExtensionError> {
        let _config = ExtensionConfig::from_file(path)?;
        // 配置解析成功，但实际加载需要手动完成
        // 因为不同类型的扩展需要不同的加载逻辑
        Ok(Self::new())
    }

    // === 插件管理 ===

    /// 注册插件
    pub fn register_plugin(&mut self, plugin: Box<dyn VcPlugin>) -> Result<(), ExtensionError> {
        let id = plugin.plugin_id().to_string();
        if self.plugins.contains_key(&id) {
            return Err(ExtensionError::AlreadyExists(format!("插件: {}", id)));
        }
        self.plugins.insert(id, plugin);
        Ok(())
    }

    /// 获取插件引用
    pub fn get_plugin(&self, id: &str) -> Option<&dyn VcPlugin> {
        self.plugins.get(id).map(|p| p.as_ref())
    }

    /// 获取插件可变引用
    pub fn get_plugin_mut(&mut self, id: &str) -> Option<&mut dyn VcPlugin> {
        self.plugins.get_mut(id).map(|p| p.as_mut())
    }

    /// 列出所有已注册插件ID
    pub fn list_plugins(&self) -> Vec<String> {
        self.plugins.keys().cloned().collect()
    }

    /// 注销插件
    pub fn unregister_plugin(&mut self, id: &str) -> Result<(), ExtensionError> {
        self.plugins
            .remove(id)
            .map(|_| ())
            .ok_or_else(|| ExtensionError::NotFound(format!("插件: {}", id)))
    }

    // === 脚本管理 ===

    /// 注册脚本引擎
    pub fn register_script(&mut self, script: Box<dyn ScriptEngine>) -> Result<(), ExtensionError> {
        let id = format!("{}-{}", script.lang(), self.scripts.len());
        self.scripts.insert(id, script);
        Ok(())
    }

    /// 注册脚本引擎（带指定ID）
    pub fn register_script_with_id(&mut self, id: &str, script: Box<dyn ScriptEngine>) -> Result<(), ExtensionError> {
        if self.scripts.contains_key(id) {
            return Err(ExtensionError::AlreadyExists(format!("脚本: {}", id)));
        }
        self.scripts.insert(id.to_string(), script);
        Ok(())
    }

    /// 获取脚本引擎可变引用
    pub fn get_script_mut(&mut self, id: &str) -> Option<&mut dyn ScriptEngine> {
        self.scripts.get_mut(id).map(|s| s.as_mut())
    }

    /// 列出所有已注册脚本ID
    pub fn list_scripts(&self) -> Vec<String> {
        self.scripts.keys().cloned().collect()
    }

    // === 模型管理 ===

    /// 注册模型后端
    pub fn register_model(&mut self, model: Box<dyn ModelBackend>) -> Result<(), ExtensionError> {
        let id = model.backend_id().to_string();
        if self.models.contains_key(&id) {
            return Err(ExtensionError::AlreadyExists(format!("模型后端: {}", id)));
        }
        self.models.insert(id, model);
        Ok(())
    }

    /// 获取模型后端可变引用
    pub fn get_model_mut(&mut self, id: &str) -> Option<&mut dyn ModelBackend> {
        self.models.get_mut(id).map(|m| m.as_mut())
    }

    /// 列出所有已注册模型后端ID
    pub fn list_models(&self) -> Vec<String> {
        self.models.keys().cloned().collect()
    }

    /// 查找支持指定任务的模型后端
    pub fn find_model_for_task(&self, task: &str) -> Option<String> {
        for (id, model) in &self.models {
            if model.supports_task(task) {
                return Some(id.clone());
            }
        }
        None
    }

    /// 使用指定模型后端进行推理
    pub fn predict(&mut self, backend_id: &str, input: &ModelInput) -> Result<crate::types::ModelOutput, ExtensionError> {
        let model = self.models
            .get_mut(backend_id)
            .ok_or_else(|| ExtensionError::NotFound(format!("模型后端: {}", backend_id)))?;
        model.predict(input).map_err(ExtensionError::Model)
    }

    // === 钩子管理 ===

    /// 注册钩子处理器
    pub fn register_hook(
        &mut self,
        event: &str,
        handler: Box<dyn Fn(&crate::hook_system::HookContext) -> Result<(), crate::error::HookError> + Send + Sync>,
        priority: i32,
    ) -> String {
        self.hooks.register(event, handler, priority)
    }

    /// 触发钩子事件
    pub fn emit_hook(
        &self,
        event: &str,
        context: &mut crate::hook_system::HookContext,
    ) -> Result<(), ExtensionError> {
        self.hooks.emit(event, context).map_err(ExtensionError::Hook)
    }

    /// 列出指定事件的钩子
    pub fn list_hooks(&self, event: &str) -> Vec<crate::hook_system::HookInfo> {
        self.hooks.list_hooks(event)
    }

    /// 获取钩子系统引用
    pub fn hooks(&self) -> &HookSystem {
        &self.hooks
    }

    /// 获取钩子系统可变引用
    pub fn hooks_mut(&mut self) -> &mut HookSystem {
        &mut self.hooks
    }

    // === 统计 ===

    /// 注册中心是否为空
    pub fn is_empty(&self) -> bool {
        self.plugins.is_empty() && self.scripts.is_empty() && self.models.is_empty()
    }

    /// 获取各类型扩展数量
    pub fn stats(&self) -> RegistryStats {
        RegistryStats {
            plugins: self.plugins.len(),
            scripts: self.scripts.len(),
            models: self.models.len(),
            hook_events: self.hooks.list_hooks("*").len(),
        }
    }
}

impl Default for ExtensionRegistry {
    fn default() -> Self {
        Self::new()
    }
}

/// 注册中心统计信息
#[derive(Debug, Clone)]
pub struct RegistryStats {
    pub plugins: usize,
    pub scripts: usize,
    pub models: usize,
    pub hook_events: usize,
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::types::PluginType;

    /// 测试用Gain插件
    struct TestGainPlugin {
        gain: f64,
        initialized: bool,
    }

    impl TestGainPlugin {
        fn new() -> Self {
            Self { gain: 1.0, initialized: false }
        }
    }

    impl VcPlugin for TestGainPlugin {
        fn plugin_id(&self) -> &str { "test-gain" }
        fn plugin_name(&self) -> &str { "测试增益" }
        fn plugin_type(&self) -> PluginType { PluginType::Effect }
        fn version(&self) -> &str { "0.1.0" }
        fn init(&mut self, _sr: f64, _bs: usize) -> Result<(), crate::error::PluginError> {
            self.initialized = true;
            Ok(())
        }
        fn process(&mut self, input: &crate::types::AudioBuffer, output: &mut crate::types::AudioBuffer) {
            for (i, &s) in input.data.iter().enumerate() {
                output.data[i] = s * self.gain;
            }
        }
        fn get_params(&self) -> Vec<crate::types::ParamInfo> {
            vec![crate::types::ParamInfo::new("gain", "增益", 0.0, 10.0, 1.0, "")]
        }
        fn set_param(&mut self, id: &str, value: f64) -> Result<(), crate::error::PluginError> {
            if id == "gain" { self.gain = value; Ok(()) }
            else { Err(crate::error::PluginError::ParamNotFound(id.to_string())) }
        }
        fn get_param(&self, id: &str) -> Option<f64> {
            if id == "gain" { Some(self.gain) } else { None }
        }
        fn destroy(&mut self) { self.initialized = false; }
    }

    #[test]
    fn test_registry_plugin() {
        let mut registry = ExtensionRegistry::new();
        assert!(registry.is_empty());

        // 注册插件
        registry.register_plugin(Box::new(TestGainPlugin::new())).unwrap();
        assert_eq!(registry.list_plugins(), vec!["test-gain"]);

        // 重复注册应报错
        assert!(registry.register_plugin(Box::new(TestGainPlugin::new())).is_err());

        // 初始化并处理
        let plugin = registry.get_plugin_mut("test-gain").unwrap();
        plugin.init(44100.0, 256).unwrap();
    }

    #[test]
    fn test_registry_model() {
        let mut registry = ExtensionRegistry::new();
        let backend = crate::model_bus::LocalBackend::default_tasks();
        registry.register_model(Box::new(backend)).unwrap();

        assert_eq!(registry.list_models(), vec!["local"]);
        assert_eq!(registry.find_model_for_task("auto_mix"), Some("local".to_string()));
        assert_eq!(registry.find_model_for_task("unknown"), None);
    }
}
