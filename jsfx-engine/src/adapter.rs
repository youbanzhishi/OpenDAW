//! JSFX插件适配器
//!
//! 将JSFX引擎适配为VcPlugin trait，使其可被OpenDAW扩展系统加载

use std::path::Path;

use crate::ast::*;
use crate::error::JsfxError;
use crate::parser::JsfxParser;
use crate::vm::{AudioBuffer, JsfxVm};

/// 插件类型（与opendaw-extension保持一致）
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum PluginType {
    Effect,
    Instrument,
    Analyzer,
    MidiProcessor,
}

/// 参数信息（与opendaw-extension保持一致）
#[derive(Clone, Debug)]
pub struct ParamInfo {
    pub id: String,
    pub name: String,
    pub min: f64,
    pub max: f64,
    pub default: f64,
    pub step: f64,
    pub value: f64,
    pub unit: String,
}

/// 插件错误（与opendaw-extension保持一致）
#[derive(Debug)]
pub enum PluginError {
    InitFailed(String),
    InvalidParam { id: String, value: f64 },
    ParamNotFound(String),
    ProcessFailed(String),
    Destroyed,
}

/// VcPlugin trait — 与opendaw-extension定义一致
pub trait VcPlugin: Send + Sync {
    fn plugin_id(&self) -> &str;
    fn plugin_name(&self) -> &str;
    fn plugin_type(&self) -> PluginType;
    fn version(&self) -> &str;
    fn init(&mut self, sample_rate: f64, buffer_size: usize) -> Result<(), PluginError>;
    fn process(&mut self, input: &AudioBuffer, output: &mut AudioBuffer);
    fn get_params(&self) -> Vec<ParamInfo>;
    fn set_param(&mut self, id: &str, value: f64) -> Result<(), PluginError>;
    fn get_param(&self, id: &str) -> Option<f64>;
    fn destroy(&mut self);
}

/// JSFX插件 — 适配VcPlugin trait
pub struct JsfxPlugin {
    /// 插件唯一ID
    plugin_id: String,
    /// 插件名称
    plugin_name: String,
    /// JSFX程序AST
    program: JsfxProgram,
    /// 虚拟机
    vm: JsfxVm,
    /// 采样率
    sample_rate: f64,
    /// 缓冲区大小
    buffer_size: usize,
    /// 是否已初始化
    initialized: bool,
    /// 是否已销毁
    destroyed: bool,
}

impl JsfxPlugin {
    /// 从JSFX文件加载
    pub fn from_file(path: &Path) -> Result<Self, JsfxError> {
        let source = std::fs::read_to_string(path)?;
        let name = path.file_stem()
            .and_then(|s| s.to_str())
            .unwrap_or("unknown")
            .to_string();
        Self::from_source(&source, &name)
    }

    /// 从JSFX源码加载
    pub fn from_source(source: &str, name: &str) -> Result<Self, JsfxError> {
        let program = JsfxParser::parse(source)?;

        let plugin_name = if program.desc.is_empty() {
            name.to_string()
        } else {
            program.desc.clone()
        };

        let plugin_id = format!("jsfx-{}", name.to_lowercase().replace(' ', "-"));

        // 初始化slider默认值
        let mut vm = JsfxVm::new();
        vm.load(&program)?;

        Ok(Self {
            plugin_id,
            plugin_name,
            program,
            vm,
            sample_rate: 44100.0,
            buffer_size: 256,
            initialized: false,
            destroyed: false,
        })
    }

    /// 扫描目录下所有.jsfx文件
    pub fn scan_directory(dir: &Path) -> Result<Vec<JsfxPlugin>, JsfxError> {
        let mut plugins = Vec::new();

        if !dir.exists() {
            return Ok(plugins);
        }

        let entries = std::fs::read_dir(dir)?;
        for entry in entries {
            let entry = entry?;
            let path = entry.path();
            if path.extension().and_then(|e| e.to_str()) == Some("jsfx") {
                match Self::from_file(&path) {
                    Ok(plugin) => plugins.push(plugin),
                    Err(e) => {
                        // 跳过无法加载的文件，但不中断扫描
                        eprintln!("警告: 无法加载JSFX文件 {:?}: {}", path, e);
                    }
                }
            }
        }

        Ok(plugins)
    }

    /// 获取slider定义列表
    pub fn get_slider_defs(&self) -> &[SliderDef] {
        &self.program.sliders
    }
}

impl VcPlugin for JsfxPlugin {
    fn plugin_id(&self) -> &str {
        &self.plugin_id
    }

    fn plugin_name(&self) -> &str {
        &self.plugin_name
    }

    fn plugin_type(&self) -> PluginType {
        PluginType::Effect
    }

    fn version(&self) -> &str {
        "1.0.0"
    }

    fn init(&mut self, sample_rate: f64, buffer_size: usize) -> Result<(), PluginError> {
        if self.destroyed {
            return Err(PluginError::Destroyed);
        }
        self.sample_rate = sample_rate;
        self.buffer_size = buffer_size;
        self.vm.init(sample_rate);

        // 执行@slider块（初始化slider关联变量）
        for slider in &self.program.sliders {
            self.vm.update_slider(slider.index, slider.default);
        }

        self.initialized = true;
        Ok(())
    }

    fn process(&mut self, input: &AudioBuffer, output: &mut AudioBuffer) {
        if !self.initialized || self.destroyed {
            // 未初始化或已销毁时直通
            output.data.copy_from_slice(&input.data);
            return;
        }
        self.vm.process_buffer(input, output);
    }

    fn get_params(&self) -> Vec<ParamInfo> {
        self.program.sliders.iter().map(|s| {
            ParamInfo {
                id: format!("slider{}", s.index),
                name: s.name.clone().unwrap_or_else(|| format!("Slider {}", s.index)),
                min: s.min,
                max: s.max,
                default: s.default,
                step: s.step,
                value: self.vm.runtime.get_slider(s.index),
                unit: String::new(),
            }
        }).collect()
    }

    fn set_param(&mut self, id: &str, value: f64) -> Result<(), PluginError> {
        if self.destroyed {
            return Err(PluginError::Destroyed);
        }

        // 解析 "sliderN" 格式
        if let Some(idx_str) = id.strip_prefix("slider") {
            if let Ok(idx) = idx_str.parse::<usize>() {
                // 验证slider存在
                if self.program.sliders.iter().any(|s| s.index == idx) {
                    let slider = self.program.sliders.iter().find(|s| s.index == idx).unwrap();
                    let clamped = value.clamp(slider.min, slider.max);
                    self.vm.update_slider(idx, clamped);
                    return Ok(());
                }
            }
        }

        Err(PluginError::ParamNotFound(id.to_string()))
    }

    fn get_param(&self, id: &str) -> Option<f64> {
        if let Some(idx_str) = id.strip_prefix("slider") {
            if let Ok(idx) = idx_str.parse::<usize>() {
                if self.program.sliders.iter().any(|s| s.index == idx) {
                    return Some(self.vm.runtime.get_slider(idx));
                }
            }
        }
        None
    }

    fn destroy(&mut self) {
        self.destroyed = true;
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_jsfx_plugin_from_source() {
        let source = r#"
desc:Test Gain
slider1:0<-150,150,0.1>Gain (dB)

@slider
gain = 2^(slider1/6);

@sample
spl0 *= gain;
spl1 *= gain;
"#;
        let mut plugin = JsfxPlugin::from_source(source, "test_gain").unwrap();
        assert_eq!(plugin.plugin_id(), "jsfx-test_gain");
        assert_eq!(plugin.plugin_name(), "Test Gain");

        plugin.init(44100.0, 256).unwrap();

        let params = plugin.get_params();
        assert_eq!(params.len(), 1);
        assert_eq!(params[0].id, "slider1");
    }

    #[test]
    fn test_jsfx_plugin_process() {
        let source = r#"
desc:Test Gain
slider1:0<-150,150,0.1>Gain (dB)

@slider
gain = 2^(slider1/6);

@sample
spl0 *= gain;
spl1 *= gain;
"#;
        let mut plugin = JsfxPlugin::from_source(source, "test_gain").unwrap();
        plugin.init(44100.0, 256).unwrap();

        // 0dB = gain of 1.0
        plugin.set_param("slider1", 0.0).unwrap();

        let input = AudioBuffer::new(2, 4);
        let mut output = AudioBuffer::new(2, 4);

        // 设置一些输入值
        for i in 0..4 {
            // 输入静音，所以输出也应该是静音
        }

        plugin.process(&input, &mut output);
    }

    #[test]
    fn test_scan_directory() {
        // 扫描tests目录
        let dir = Path::new("tests");
        if dir.exists() {
            let plugins = JsfxPlugin::scan_directory(dir).unwrap();
            // 不强制要求有文件
            println!("找到 {} 个JSFX插件", plugins.len());
        }
    }
}
