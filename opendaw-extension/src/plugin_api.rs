//! Plugin API — 音频/DSP插件扩展接口
//!
//! 所有音频效果器、虚拟乐器、分析器都实现此trait
//! 生命周期：init -> process (循环) -> destroy

use crate::error::PluginError;
use crate::types::{AudioBuffer, ParamInfo, PluginType};

/// 插件元信息 — 插件的静态描述
///
/// 包含插件的身份、作者、版本等元数据，
/// 用于插件发现、展示和分类管理。
#[derive(Clone, Debug)]
pub struct PluginInfo {
    /// 插件唯一标识（如 "vc-eq", "my-compressor"）
    pub id: String,
    /// 插件人类可读名称
    pub name: String,
    /// 作者/厂商
    pub author: String,
    /// 语义化版本号
    pub version: String,
    /// 插件类型
    pub plugin_type: PluginType,
    /// 插件所有可自动化参数
    pub parameters: Vec<ParamInfo>,
}

impl PluginInfo {
    /// 创建新的插件信息
    pub fn new(id: &str, name: &str, plugin_type: PluginType) -> Self {
        Self {
            id: id.to_string(),
            name: name.to_string(),
            author: String::new(),
            version: "0.1.0".to_string(),
            plugin_type,
            parameters: Vec::new(),
        }
    }

    /// 设置作者
    pub fn with_author(mut self, author: &str) -> Self {
        self.author = author.to_string();
        self
    }

    /// 设置版本
    pub fn with_version(mut self, version: &str) -> Self {
        self.version = version.to_string();
        self
    }

    /// 设置参数列表
    pub fn with_parameters(mut self, params: Vec<ParamInfo>) -> Self {
        self.parameters = params;
        self
    }
}

/// 插件核心trait — 扩展体系第一根柱子
///
/// 实现此trait即可成为OpenDAW的合法插件，
/// 通过ExtensionRegistry注册后即可被调度使用。
///
/// # 生命周期
///
/// 1. `init()` — 初始化，传入采样率和缓冲区大小
/// 2. `process()` — 循环调用，处理音频数据
/// 3. `destroy()` — 销毁，释放资源
///
/// # 参数管理
///
/// - `get_params()` / `set_param()` / `get_param()` — 参数读写
/// - `get_info()` — 获取插件完整元信息
///
/// # 预设支持
///
/// - `preset_names()` — 列出内置预设名称
/// - `load_preset()` — 加载内置预设
pub trait VcPlugin: Send + Sync {
    /// 插件唯一标识（如 "vc-eq", "my-compressor"）
    fn plugin_id(&self) -> &str;

    /// 插件人类可读名称
    fn plugin_name(&self) -> &str;

    /// 插件类型
    fn plugin_type(&self) -> PluginType;

    /// 版本号（语义化版本）
    fn version(&self) -> &str;

    /// 获取插件完整元信息
    ///
    /// 默认实现基于各独立方法组合，可覆盖以提供更完整信息
    fn get_info(&self) -> PluginInfo {
        PluginInfo {
            id: self.plugin_id().to_string(),
            name: self.plugin_name().to_string(),
            author: String::new(),
            version: self.version().to_string(),
            plugin_type: self.plugin_type(),
            parameters: self.get_params(),
        }
    }

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

    /// 列出内置预设名称
    ///
    /// 默认返回空列表，表示无内置预设。
    /// 插件可覆盖此方法提供出厂预设列表。
    fn preset_names(&self) -> Vec<String> {
        Vec::new()
    }

    /// 加载内置预设
    ///
    /// 按名称加载预设，将所有参数设置为预设值。
    /// 返回 Err 表示预设不存在。
    fn load_preset(&mut self, _name: &str) -> Result<(), PluginError> {
        Err(PluginError::ProcessFailed(format!(
            "插件 {} 无内置预设 '{}'",
            self.plugin_id(),
            _name
        )))
    }

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
        fn plugin_id(&self) -> &str {
            "null-plugin"
        }
        fn plugin_name(&self) -> &str {
            "空插件"
        }
        fn plugin_type(&self) -> PluginType {
            PluginType::Effect
        }
        fn version(&self) -> &str {
            "0.1.0"
        }
        fn init(&mut self, _sample_rate: f64, _buffer_size: usize) -> Result<(), PluginError> {
            Ok(())
        }
        fn process(&mut self, input: &AudioBuffer, output: &mut AudioBuffer) {
            // 直通：将输入复制到输出
            output.data.copy_from_slice(&input.data);
        }
        fn get_params(&self) -> Vec<ParamInfo> {
            vec![]
        }
        fn set_param(&mut self, _id: &str, _value: f64) -> Result<(), PluginError> {
            Ok(())
        }
        fn get_param(&self, _id: &str) -> Option<f64> {
            None
        }
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

    #[test]
    fn test_plugin_info_default() {
        let plugin = NullPlugin;
        let info = plugin.get_info();
        assert_eq!(info.id, "null-plugin");
        assert_eq!(info.name, "空插件");
        assert_eq!(info.plugin_type, PluginType::Effect);
        assert_eq!(info.version, "0.1.0");
        assert!(info.author.is_empty());
        assert!(info.parameters.is_empty());
    }

    #[test]
    fn test_plugin_info_builder() {
        let info = PluginInfo::new("test", "Test Plugin", PluginType::Instrument)
            .with_author("OpenDAW")
            .with_version("1.0.0");
        assert_eq!(info.id, "test");
        assert_eq!(info.author, "OpenDAW");
        assert_eq!(info.version, "1.0.0");
        assert_eq!(info.plugin_type, PluginType::Instrument);
    }

    #[test]
    fn test_default_preset_empty() {
        let mut plugin = NullPlugin;
        assert!(plugin.preset_names().is_empty());
        assert!(plugin.load_preset("nonexistent").is_err());
    }
}
