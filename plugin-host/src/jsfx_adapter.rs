//! JSFX 适配器 — 将 jsfx-engine 的 JsfxPlugin 桥接到 plugin-host
//!
//! 本模块通过 jsfx-engine crate 加载 JSFX 脚本，
//! 并将其包装为 VcPlugin trait 实现。
//!
//! # 生命周期映射
//!
//! | JSFX 区段   | VcPlugin 方法    |
//! |-------------|-----------------|
//! | @init       | init()          |
//! | @slider     | set_param()     |
//! | @sample     | process()       |
//! | -           | destroy()       |
//!
//! # 使用
//!
//! ```ignore
//! use plugin_host::jsfx_adapter::JsfxAdapter;
//! use plugin_host::PluginHost;
//!
//! let plugin = JsfxAdapter::from_file("effects/gain.jsfx")?;
//! let mut host = PluginHost::new(44100.0, 256, 2);
//! host.load_plugin(Box::new(plugin))?;
//! ```

use std::path::Path;

#[cfg(feature = "jsfx")]
use opendaw_extension::{AudioBuffer, ParamInfo, PluginError, PluginInfo, PluginType, VcPlugin};

#[cfg(not(feature = "jsfx"))]
use opendaw_extension::PluginError;

#[cfg(feature = "jsfx")]
use jsfx_engine::JsfxParser;
#[cfg(feature = "jsfx")]
use jsfx_engine::JsfxPlugin as InnerJsfxPlugin;

/// JSFX 插件适配器
///
/// 包装 jsfx-engine 的 JsfxPlugin，提供 VcPlugin trait 实现。
/// 支持 feature flag `jsfx` 控制，未启用时提供占位实现。
#[cfg(feature = "jsfx")]
pub struct JsfxAdapter {
    inner: InnerJsfxPlugin,
}

#[cfg(feature = "jsfx")]
impl JsfxAdapter {
    /// 从 JSFX 文件加载插件
    pub fn from_file(path: &Path) -> Result<Self, PluginError> {
        let inner = InnerJsfxPlugin::from_file(path)
            .map_err(|e| PluginError::InitFailed(format!("JSFX 加载失败 {:?}: {}", path, e)))?;
        Ok(Self { inner })
    }

    /// 从 JSFX 源码加载插件
    pub fn from_source(source: &str, name: &str) -> Result<Self, PluginError> {
        let inner = InnerJsfxPlugin::from_source(source, name)
            .map_err(|e| PluginError::InitFailed(format!("JSFX 源码加载失败: {}", e)))?;
        Ok(Self { inner })
    }

    /// 扫描目录中的 JSFX 文件
    pub fn scan_directory(dir: &Path) -> Result<Vec<Self>, PluginError> {
        if !dir.exists() {
            return Ok(Vec::new());
        }

        let entries = std::fs::read_dir(dir).map_err(|e| {
            PluginError::ProcessFailed(format!("读取目录失败 {}: {}", dir.display(), e))
        })?;

        let mut adapters = Vec::new();
        for entry in entries.flatten() {
            let path = entry.path();
            if path.extension().and_then(|e| e.to_str()) == Some("jsfx") {
                match Self::from_file(&path) {
                    Ok(adapter) => {
                        log::info!(
                            "[JsfxAdapter] 发现插件: {} → {}",
                            adapter.inner.plugin_id(),
                            path.display()
                        );
                        adapters.push(adapter);
                    }
                    Err(e) => {
                        log::warn!("[JsfxAdapter] 跳过无效 JSFX {}: {}", path.display(), e);
                    }
                }
            }
        }

        Ok(adapters)
    }
}

#[cfg(feature = "jsfx")]
impl VcPlugin for JsfxAdapter {
    fn plugin_id(&self) -> &str {
        self.inner.plugin_id()
    }

    fn plugin_name(&self) -> &str {
        self.inner.plugin_name()
    }

    fn plugin_type(&self) -> PluginType {
        self.inner.plugin_type()
    }

    fn version(&self) -> &str {
        self.inner.version()
    }

    fn get_info(&self) -> PluginInfo {
        PluginInfo {
            id: self.inner.plugin_id().to_string(),
            name: self.inner.plugin_name().to_string(),
            author: "JSFX".to_string(),
            version: self.inner.version().to_string(),
            plugin_type: self.inner.plugin_type(),
            parameters: self.inner.get_params(),
        }
    }

    fn init(&mut self, sample_rate: f64, buffer_size: usize) -> Result<(), PluginError> {
        self.inner.init(sample_rate, buffer_size)
    }

    fn process(&mut self, input: &AudioBuffer, output: &mut AudioBuffer) {
        self.inner.process(input, output)
    }

    fn get_params(&self) -> Vec<ParamInfo> {
        self.inner.get_params()
    }

    fn set_param(&mut self, id: &str, value: f64) -> Result<(), PluginError> {
        self.inner.set_param(id, value)
    }

    fn get_param(&self, id: &str) -> Option<f64> {
        self.inner.get_param(id)
    }

    fn preset_names(&self) -> Vec<String> {
        Vec::new()
    }

    fn load_preset(&mut self, name: &str) -> Result<(), PluginError> {
        Err(PluginError::ProcessFailed(format!(
            "JSFX 插件 {} 不支持预设: {}",
            self.plugin_id(),
            name
        )))
    }

    fn destroy(&mut self) {
        self.inner.destroy();
    }
}

// ── 非 jsfx feature 时的占位实现 ──────────────────────────────────────────

/// JSFX 插件适配器（无 jsfx feature 时的占位）
///
/// 当 `jsfx` feature 未启用时，提供基本的错误提示。
#[cfg(not(feature = "jsfx"))]
pub struct JsfxAdapter;

#[cfg(not(feature = "jsfx"))]
impl JsfxAdapter {
    /// 尝试加载 JSFX 文件（需要 jsfx feature）
    pub fn from_file(_path: &Path) -> Result<Self, PluginError> {
        Err(PluginError::InitFailed(
            "JSFX 支持未启用，请在 Cargo.toml 中启用 'jsfx' feature".to_string(),
        ))
    }

    /// 尝试从源码加载（需要 jsfx feature）
    pub fn from_source(_source: &str, _name: &str) -> Result<Self, PluginError> {
        Err(PluginError::InitFailed(
            "JSFX 支持未启用，请在 Cargo.toml 中启用 'jsfx' feature".to_string(),
        ))
    }

    /// 扫描目录（需要 jsfx feature）
    pub fn scan_directory(_dir: &Path) -> Result<Vec<Self>, PluginError> {
        Err(PluginError::InitFailed(
            "JSFX 支持未启用，请在 Cargo.toml 中启用 'jsfx' feature".to_string(),
        ))
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[cfg(feature = "jsfx")]
    #[test]
    fn test_jsfx_adapter_from_source() {
        let source = r#"
desc:Test Gain
slider1:0<-150,150,0.1>Gain (dB)

@slider
gain = 2^(slider1/6);

@sample
spl0 *= gain;
spl1 *= gain;
"#;
        let mut adapter = JsfxAdapter::from_source(source, "test_gain").unwrap();
        assert_eq!(adapter.plugin_id(), "jsfx-test_gain");
        assert_eq!(adapter.plugin_name(), "Test Gain");

        adapter.init(44100.0, 256).unwrap();

        let params = adapter.get_params();
        assert_eq!(params.len(), 1);
        assert_eq!(params[0].id, "slider1");
    }

    #[cfg(feature = "jsfx")]
    #[test]
    fn test_jsfx_adapter_process() {
        let source = r#"
desc:Pass Through
@sample
// spl0 and spl1 are pass-through by default
"#;
        let mut adapter = JsfxAdapter::from_source(source, "passthrough").unwrap();
        adapter.init(44100.0, 256).unwrap();

        let mut input = AudioBuffer::new(2, 4);
        input.data[0] = 1.0;
        input.data[4] = 0.5;
        let mut output = AudioBuffer::new(2, 4);

        adapter.process(&input, &mut output);
        // 验证有输出
        assert!(output.data.iter().any(|&v| v != 0.0));
    }

    #[cfg(feature = "jsfx")]
    #[test]
    fn test_jsfx_adapter_get_info() {
        let source = r#"
desc:Info Test
slider1:50<0,100,1>Mix
@sample
"#;
        let adapter = JsfxAdapter::from_source(source, "info_test").unwrap();
        let info = adapter.get_info();
        assert_eq!(info.id, "jsfx-info_test");
        assert_eq!(info.author, "JSFX");
        assert_eq!(info.plugin_type, PluginType::Effect);
    }

    #[cfg(not(feature = "jsfx"))]
    #[test]
    fn test_jsfx_adapter_disabled() {
        let result = JsfxAdapter::from_file(Path::new("/tmp/test.jsfx"));
        assert!(result.is_err());
    }
}
