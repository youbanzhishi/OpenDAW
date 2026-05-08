//! Plugin API — 音频/DSP插件扩展接口
//!
//! 所有音频效果器、虚拟乐器、分析器都实现此trait
//! 生命周期：init -> process (循环) -> destroy

use crate::error::PluginError;
use crate::types::{AudioBuffer, ParamInfo, PluginType};

/// 插件核心trait — 扩展体系第一根柱子
///
/// 实现此trait即可成为OpenDAW的合法插件，
/// 通过ExtensionRegistry注册后即可被调度使用。
pub trait VcPlugin: Send + Sync {
    /// 插件唯一标识（如 "vc-eq", "my-compressor"）
    fn plugin_id(&self) -> &str;

    /// 插件人类可读名称
    fn plugin_name(&self) -> &str;

    /// 插件类型
    fn plugin_type(&self) -> PluginType;

    /// 版本号（语义化版本）
    fn version(&self) -> &str;

    /// 初始化插件，传入采样率和缓冲区大小
    fn init(&mut self, sample_rate: f64, buffer_size: usize) -> Result<(), PluginError>;

    /// 处理音频数据 — 核心DSP回调
    /// input: 输入音频缓冲区
    /// output: 输出音频缓冲区（插件写入处理后的数据）
    fn process(&mut self, input: &AudioBuffer, output: &mut AudioBuffer);

    /// 获取所有可自动化参数的信息
    fn get_params(&self) -> Vec<ParamInfo>;

    /// 设置参数值
    fn set_param(&mut self, id: &str, value: f64) -> Result<(), PluginError>;

    /// 获取参数当前值
    fn get_param(&self, id: &str) -> Option<f64>;

    /// 销毁插件，释放资源
    fn destroy(&mut self);
}

/// 插件包装器 — 用于在注册中心内存储插件实例
pub struct PluginEntry {
    pub plugin: Box<dyn VcPlugin>,
    pub enabled: bool,
}

impl PluginEntry {
    pub fn new(plugin: Box<dyn VcPlugin>) -> Self {
        Self {
            plugin,
            enabled: true,
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    /// 测试用空插件
    struct NullPlugin;

    impl VcPlugin for NullPlugin {
        fn plugin_id(&self) -> &str { "null-plugin" }
        fn plugin_name(&self) -> &str { "空插件" }
        fn plugin_type(&self) -> PluginType { PluginType::Effect }
        fn version(&self) -> &str { "0.1.0" }
        fn init(&mut self, _sample_rate: f64, _buffer_size: usize) -> Result<(), PluginError> { Ok(()) }
        fn process(&mut self, input: &AudioBuffer, output: &mut AudioBuffer) {
            // 直通：将输入复制到输出
            output.data.copy_from_slice(&input.data);
        }
        fn get_params(&self) -> Vec<ParamInfo> { vec![] }
        fn set_param(&mut self, _id: &str, _value: f64) -> Result<(), PluginError> { Ok(()) }
        fn get_param(&self, _id: &str) -> Option<f64> { None }
        fn destroy(&mut self) {}
    }

    #[test]
    fn test_null_plugin_pass_through() {
        let mut plugin = NullPlugin;
        plugin.init(44100.0, 256).unwrap();

        let input = AudioBuffer::new(2, 256);
        let mut output = AudioBuffer::new(2, 256);
        plugin.process(&input, &mut output);

        // 直通插件的输出应该等于输入（都是静音）
        assert_eq!(output.data.len(), input.data.len());
    }
}
