//! PluginHost — 插件宿主
//!
//! 加载/管理/调度插件，是插件系统的运行时容器

use std::collections::HashMap;

use opendaw_extension::{
    AudioBuffer, VcPlugin, PluginError, PluginType,
    PluginParameter, ParameterValue, ParameterType,
};
use audio_engine::buffer::AudioBuffer as EngineAudioBuffer;
use crate::chain::PluginChain;
use crate::param::ParamManager;
use crate::preset::PresetManager;
use crate::loader::PluginLoader;
use crate::scanner::{PluginFormat, ScannedPlugin};

/// 插件宿主 — 管理所有插件的运行时容器
///
/// 负责：
/// - 插件加载和注册
/// - 插件链构建和调度
/// - 参数统一管理（支持 PluginParameter 多类型模型）
/// - 预设管理
pub struct PluginHost {
    /// 已加载的插件实例
    plugins: HashMap<String, Box<dyn VcPlugin>>,
    /// 信号链
    chain: PluginChain,
    /// 参数管理器（传统 ParamInfo 兼容层）
    param_manager: ParamManager,
    /// 预设管理器
    preset_manager: PresetManager,
    /// 增强参数模型（PluginParameter 多类型）
    plugin_params: HashMap<String, Vec<PluginParameter>>,
    /// 插件加载器
    loader: PluginLoader,
    /// 声道数
    #[allow(dead_code)]
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
            plugin_params: HashMap::new(),
            loader: PluginLoader::new(),
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

        // 注册参数（传统 ParamInfo 兼容层）
        let params = plugin.get_params();
        self.param_manager.register_plugin_params(&id, params);

        // 注册增强参数模型
        let enhanced_params: Vec<PluginParameter> = plugin.get_params()
            .iter()
            .map(|p| {
                // 尝试推断更精确的参数类型
                if p.step == 1.0 && p.min == 0.0 && p.max == 1.0 {
                    PluginParameter::bool_param(&p.id, &p.name, p.value >= 0.5)
                } else if p.step == 1.0 && p.min == p.min.floor() && p.max == p.max.floor() {
                    PluginParameter::int(&p.id, &p.name, p.min as i64, p.max as i64, p.value as i64, &p.unit)
                } else {
                    PluginParameter::from_param_info(p)
                }
            })
            .collect();
        self.plugin_params.insert(id.clone(), enhanced_params);

        // 存储插件
        self.plugins.insert(id.clone(), plugin);

        Ok(id)
    }

    /// 通过路径加载插件（自动检测格式）
    pub fn load_plugin_from_path(
        &mut self,
        path: &std::path::Path,
    ) -> Result<String, PluginError> {
        let plugin = self.loader.load_from_path(path)?;
        self.load_plugin(plugin)
    }

    /// 通过扫描结果加载插件
    pub fn load_plugin_from_scanned(
        &mut self,
        info: &ScannedPlugin,
    ) -> Result<String, PluginError> {
        let plugin = self.loader.load_from_scanned(info)?;
        self.load_plugin(plugin)
    }

    /// 卸载插件
    pub fn unload_plugin(&mut self, id: &str) -> Result<(), PluginError> {
        if let Some(mut plugin) = self.plugins.remove(id) {
            plugin.destroy();
            self.plugin_params.remove(id);
            Ok(())
        } else {
            Err(PluginError::ProcessFailed(format!("插件未找到: {}", id)))
        }
    }

    /// 将已加载的插件添加到信号链
    ///
    /// 插件会从插件池中移出并追加到信号链末尾。
    /// 添加后插件的process()将参与chain.process()的调度。
    pub fn add_to_chain(&mut self, plugin_id: &str) -> Result<(), PluginError> {
        let plugin = self.plugins.remove(plugin_id)
            .ok_or_else(|| PluginError::ProcessFailed(format!("插件未找到: {}", plugin_id)))?;
        self.chain.push(plugin);
        Ok(())
    }

    /// 将已加载的插件插入到信号链的指定位置
    pub fn insert_to_chain(&mut self, index: usize, plugin_id: &str) -> Result<(), PluginError> {
        let plugin = self.plugins.remove(plugin_id)
            .ok_or_else(|| PluginError::ProcessFailed(format!("插件未找到: {}", plugin_id)))?;
        self.chain.insert(index, plugin);
        Ok(())
    }

    /// 从信号链中移除指定位置的插件（移回插件池）
    pub fn remove_from_chain(&mut self, index: usize) -> Result<String, PluginError> {
        let plugin = self.chain.remove(index)
            .ok_or_else(|| PluginError::ProcessFailed(format!("链索引越界: {}", index)))?;
        let id = plugin.plugin_id().to_string();
        // 插件移回插件池
        self.plugins.insert(id.clone(), plugin);
        Ok(id)
    }

    /// 处理音频（opendaw-extension AudioBuffer）
    pub fn process(&mut self, input: &AudioBuffer, output: &mut AudioBuffer) {
        self.chain.process(input, output);
    }

    /// 处理音频（audio-engine AudioBuffer，自动桥接转换）
    pub fn process_engine(&mut self, input: &EngineAudioBuffer, output: &mut EngineAudioBuffer) {
        self.chain.process_engine(input, output);
    }

    /// 设置插件参数（兼容层，f64 值）
    pub fn set_plugin_param(
        &mut self,
        plugin_id: &str,
        param_id: &str,
        value: f64,
    ) -> Result<(), PluginError> {
        // 更新参数管理器
        if let Some(clamped) = self.param_manager.set_param(plugin_id, param_id, value) {
            // 同步到增强参数模型
            if let Some(params) = self.plugin_params.get_mut(plugin_id) {
                if let Some(param) = params.iter_mut().find(|p| p.id == param_id) {
                    param.set_from_f64(clamped);
                }
            }
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

    /// 获取插件的增强参数列表
    pub fn get_plugin_params(&self, plugin_id: &str) -> Option<&[PluginParameter]> {
        self.plugin_params.get(plugin_id).map(|v| v.as_slice())
    }

    /// 设置增强参数值
    pub fn set_enhanced_param(
        &mut self,
        plugin_id: &str,
        param_id: &str,
        value: &ParameterValue,
    ) -> Result<(), PluginError> {
        if let Some(params) = self.plugin_params.get_mut(plugin_id) {
            if let Some(param) = params.iter_mut().find(|p| p.id == param_id) {
                let f64_val = value.to_f64();
                param.set_from_f64(f64_val);
                // 同步到传统层和插件
                return self.set_plugin_param(plugin_id, param_id, f64_val);
            }
        }
        Err(PluginError::ParamNotFound(format!("{}:{}", plugin_id, param_id)))
    }

    /// 将参数设置为归一化值 [0.0, 1.0]
    pub fn set_param_normalized(
        &mut self,
        plugin_id: &str,
        param_id: &str,
        normalized: f64,
    ) -> Result<(), PluginError> {
        if let Some(params) = self.plugin_params.get(plugin_id) {
            if let Some(param) = params.iter().find(|p| p.id == param_id) {
                let value = param.min_f64 + normalized.clamp(0.0, 1.0) * (param.max_f64 - param.min_f64);
                return self.set_plugin_param(plugin_id, param_id, value);
            }
        }
        Err(PluginError::ParamNotFound(format!("{}:{}", plugin_id, param_id)))
    }

    /// 获取参数的归一化值 [0.0, 1.0]
    pub fn get_param_normalized(&self, plugin_id: &str, param_id: &str) -> Option<f64> {
        self.plugin_params.get(plugin_id).and_then(|params| {
            params.iter().find(|p| p.id == param_id).map(|p| p.normalized())
        })
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

    /// 获取插件加载器可变引用
    pub fn loader_mut(&mut self) -> &mut PluginLoader {
        &mut self.loader
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

    /// 列出所有增强参数
    pub fn list_all_params(&self) -> Vec<(String, String, ParameterType, f64)> {
        let mut result = Vec::new();
        for (plugin_id, params) in &self.plugin_params {
            for p in params {
                result.push((
                    plugin_id.clone(),
                    p.id.clone(),
                    p.param_type,
                    p.as_f64(),
                ));
            }
        }
        result
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

    /// 测试用增益插件（带参数）
    struct GainPlugin {
        gain: f64,
    }

    impl VcPlugin for GainPlugin {
        fn plugin_id(&self) -> &str { "test-gain" }
        fn plugin_name(&self) -> &str { "测试增益" }
        fn plugin_type(&self) -> PluginType { PluginType::Effect }
        fn version(&self) -> &str { "0.1.0" }
        fn init(&mut self, _sr: f64, _bs: usize) -> Result<(), PluginError> { Ok(()) }
        fn process(&mut self, input: &AudioBuffer, output: &mut AudioBuffer) {
            for (i, &s) in input.data.iter().enumerate() {
                if i < output.data.len() {
                    output.data[i] = s * self.gain;
                }
            }
        }
        fn get_params(&self) -> Vec<opendaw_extension::ParamInfo> {
            vec![opendaw_extension::ParamInfo::new("gain", "增益", 0.0, 2.0, 1.0, "x")]
        }
        fn set_param(&mut self, id: &str, v: f64) -> Result<(), PluginError> {
            if id == "gain" { self.gain = v; Ok(()) }
            else { Err(PluginError::ParamNotFound(id.to_string())) }
        }
        fn get_param(&self, id: &str) -> Option<f64> {
            if id == "gain" { Some(self.gain) } else { None }
        }
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

    #[test]
    fn test_add_to_chain() {
        let mut host = PluginHost::new(44100.0, 256, 2);
        host.load_plugin(Box::new(PassthroughPlugin)).unwrap();
        assert_eq!(host.plugin_count(), 1);
        assert_eq!(host.chain_length(), 0);

        // 添加到信号链
        host.add_to_chain("passthrough").unwrap();
        assert_eq!(host.plugin_count(), 0); // 从插件池移出
        assert_eq!(host.chain_length(), 1); // 添加到链中

        // 重复添加应失败（已不在插件池中）
        assert!(host.add_to_chain("passthrough").is_err());
    }

    #[test]
    fn test_chain_process_after_add() {
        let mut host = PluginHost::new(44100.0, 256, 2);
        host.load_plugin(Box::new(PassthroughPlugin)).unwrap();
        host.add_to_chain("passthrough").unwrap();

        let input = AudioBuffer::new(2, 256);
        let mut output = AudioBuffer::new(2, 256);
        // 在输入中写入一些数据
        output.data[0] = 0.0;
        host.process(&input, &mut output);
        // 直通插件应该复制input到output
        assert_eq!(output.data[0], input.data[0]);
    }

    #[test]
    fn test_enhanced_params() {
        let mut host = PluginHost::new(44100.0, 256, 2);
        host.load_plugin(Box::new(GainPlugin { gain: 1.0 })).unwrap();

        // 检查增强参数
        let params = host.get_plugin_params("test-gain").unwrap();
        assert_eq!(params.len(), 1);
        assert_eq!(params[0].id, "gain");

        // 设置参数
        host.set_plugin_param("test-gain", "gain", 1.5).unwrap();
        let params = host.get_plugin_params("test-gain").unwrap();
        assert!((params[0].as_f64() - 1.5).abs() < 1e-10);
    }

    #[test]
    fn test_normalized_param() {
        let mut host = PluginHost::new(44100.0, 256, 2);
        host.load_plugin(Box::new(GainPlugin { gain: 1.0 })).unwrap();

        // gain range: [0.0, 2.0], default 1.0 → normalized = 0.5
        let norm = host.get_param_normalized("test-gain", "gain").unwrap();
        assert!((norm - 0.5).abs() < 1e-10);

        // Set to normalized 0.0 → value should be 0.0
        host.set_param_normalized("test-gain", "gain", 0.0).unwrap();
        assert!((host.get_plugin_param("test-gain", "gain").unwrap() - 0.0).abs() < 1e-10);

        // Set to normalized 1.0 → value should be 2.0
        host.set_param_normalized("test-gain", "gain", 1.0).unwrap();
        assert!((host.get_plugin_param("test-gain", "gain").unwrap() - 2.0).abs() < 1e-10);
    }

    #[test]
    fn test_list_all_params() {
        let mut host = PluginHost::new(44100.0, 256, 2);
        host.load_plugin(Box::new(GainPlugin { gain: 1.0 })).unwrap();
        host.load_plugin(Box::new(PassthroughPlugin)).unwrap();

        let all_params = host.list_all_params();
        // GainPlugin has 1 param, PassthroughPlugin has 0
        assert_eq!(all_params.len(), 1);
        assert_eq!(all_params[0].1, "gain");
    }
}
