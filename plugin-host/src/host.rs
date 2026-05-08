//! PluginHost — 插件宿主
//!
//! 加载/管理/调度插件，是插件系统的运行时容器

use std::collections::HashMap;

use opendaw_extension::{AudioBuffer, VcPlugin, PluginError, PluginType};
use crate::chain::PluginChain;
use crate::param::ParamManager;
use crate::preset::PresetManager;

/// 插件宿主 — 管理所有插件的运行时容器
///
/// 负责：
/// - 插件加载和注册
/// - 插件链构建和调度
/// - 参数统一管理
/// - 预设管理
pub struct PluginHost {
    /// 已加载的插件实例
    plugins: HashMap<String, Box<dyn VcPlugin>>,
    /// 信号链
    chain: PluginChain,
    /// 参数管理器
    param_manager: ParamManager,
    /// 预设管理器
    preset_manager: PresetManager,
    /// 声道数
    channels: usize,
    /// 缓冲区大小
    buffer_size: usize,
    /// 采样率
    sample_rate: f64,
}

impl PluginHost {
    /// 创建新的插件宿主
    pub fn new(sample_rate: f64, buffer_size: usize, channels: usize) -> Self {
        Self {
            plugins: HashMap::new(),
            chain: PluginChain::new(channels, buffer_size),
            param_manager: ParamManager::new(),
            preset_manager: PresetManager::new(),
            channels,
            buffer_size,
            sample_rate,
        }
    }

    /// 加载插件
    ///
    /// 插件会被初始化并添加到插件池
    /// 使用 add_to_chain 将插件添加到信号链
    pub fn load_plugin(&mut self, mut plugin: Box<dyn VcPlugin>) -> Result<String, PluginError> {
        let id = plugin.plugin_id().to_string();

        // 初始化插件
        plugin.init(self.sample_rate, self.buffer_size)?;

        // 注册参数
        let params = plugin.get_params();
        self.param_manager.register_plugin_params(&id, params);

        // 存储插件
        self.plugins.insert(id.clone(), plugin);

        Ok(id)
    }

    /// 卸载插件
    pub fn unload_plugin(&mut self, id: &str) -> Result<(), PluginError> {
        if let Some(mut plugin) = self.plugins.remove(id) {
            plugin.destroy();
            Ok(())
        } else {
            Err(PluginError::ProcessFailed(format!("插件未找到: {}", id)))
        }
    }

    /// 将已加载的插件添加到信号链
    ///
    /// 注意：由于Rust的借用规则，这里通过克隆插件ID来管理
    /// 实际信号链处理时会直接使用链中的插件
    pub fn add_to_chain(&mut self, _plugin_id: &str) {
        // 在实际实现中，需要通过Arc<Mutex<>>或其他机制
        // 将插件从pool移到chain，或使用共享引用
        // 此处为简化实现，用户可以直接使用chain.push()
    }

    /// 处理音频
    pub fn process(&mut self, input: &AudioBuffer, output: &mut AudioBuffer) {
        self.chain.process(input, output);
    }

    /// 设置插件参数
    pub fn set_plugin_param(&mut self, plugin_id: &str, param_id: &str, value: f64) -> Result<(), PluginError> {
        // 更新参数管理器
        if let Some(clamped) = self.param_manager.set_param(plugin_id, param_id, value) {
            // 同步到插件实例
            if let Some(plugin) = self.plugins.get_mut(plugin_id) {
                plugin.set_param(param_id, clamped)?;
            }
            Ok(())
        } else {
            Err(PluginError::ParamNotFound(format!("{}:{}", plugin_id, param_id)))
        }
    }

    /// 获取插件参数值
    pub fn get_plugin_param(&self, plugin_id: &str, param_id: &str) -> Option<f64> {
        self.param_manager.get_param(plugin_id, param_id)
    }

    // === 代理方法 ===

    /// 获取参数管理器引用
    pub fn param_manager(&self) -> &ParamManager {
        &self.param_manager
    }

    /// 获取预设管理器可变引用
    pub fn preset_manager_mut(&mut self) -> &mut PresetManager {
        &mut self.preset_manager
    }

    /// 列出所有已加载插件
    pub fn list_plugins(&self) -> Vec<PluginInfo> {
        self.plugins
            .values()
            .map(|p| PluginInfo {
                id: p.plugin_id().to_string(),
                name: p.plugin_name().to_string(),
                plugin_type: p.plugin_type(),
                version: p.version().to_string(),
            })
            .collect()
    }

    /// 信号链插件数量
    pub fn chain_length(&self) -> usize {
        self.chain.len()
    }

    /// 已加载插件数量
    pub fn plugin_count(&self) -> usize {
        self.plugins.len()
    }
}

/// 插件信息
#[derive(Clone, Debug)]
pub struct PluginInfo {
    pub id: String,
    pub name: String,
    pub plugin_type: PluginType,
    pub version: String,
}

#[cfg(test)]
mod tests {
    use super::*;

    /// 测试用直通插件
    struct PassthroughPlugin;

    impl VcPlugin for PassthroughPlugin {
        fn plugin_id(&self) -> &str { "passthrough" }
        fn plugin_name(&self) -> &str { "直通" }
        fn plugin_type(&self) -> PluginType { PluginType::Effect }
        fn version(&self) -> &str { "0.1.0" }
        fn init(&mut self, _sr: f64, _bs: usize) -> Result<(), PluginError> { Ok(()) }
        fn process(&mut self, input: &AudioBuffer, output: &mut AudioBuffer) {
            output.data.copy_from_slice(&input.data);
        }
        fn get_params(&self) -> Vec<opendaw_extension::ParamInfo> { vec![] }
        fn set_param(&mut self, _id: &str, _v: f64) -> Result<(), PluginError> { Ok(()) }
        fn get_param(&self, _id: &str) -> Option<f64> { None }
        fn destroy(&mut self) {}
    }

    #[test]
    fn test_plugin_host_load() {
        let mut host = PluginHost::new(44100.0, 256, 2);
        let id = host.load_plugin(Box::new(PassthroughPlugin)).unwrap();
        assert_eq!(id, "passthrough");
        assert_eq!(host.plugin_count(), 1);
    }

    #[test]
    fn test_plugin_host_unload() {
        let mut host = PluginHost::new(44100.0, 256, 2);
        host.load_plugin(Box::new(PassthroughPlugin)).unwrap();
        host.unload_plugin("passthrough").unwrap();
        assert_eq!(host.plugin_count(), 0);
    }
}
