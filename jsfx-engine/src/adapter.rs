//! JSFX插件适配器
//!
//! 将JSFX引擎适配为VcPlugin trait，使其可被OpenDAW扩展系统加载
//! 支持完整的插件生命周期：创建→初始化→处理→参数更新→销毁

use std::path::Path;

use opendaw_extension::{VcPlugin, PluginType, ParamInfo, PluginError, AudioBuffer as ExtAudioBuffer};

use crate::ast::*;
use crate::error::JsfxError;
use crate::parser::JsfxParser;
use crate::vm::{AudioBuffer as VmAudioBuffer, JsfxVm};

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

/// 将VM内部AudioBuffer转换为扩展层AudioBuffer
fn vm_to_ext(buf: &VmAudioBuffer) -> ExtAudioBuffer {
    ExtAudioBuffer {
        channels: buf.channels,
        frames: buf.frames,
        data: buf.data.clone(),
    }
}

/// 将扩展层AudioBuffer转换为VM内部AudioBuffer
fn ext_to_vm(buf: &ExtAudioBuffer) -> VmAudioBuffer {
    VmAudioBuffer {
        channels: buf.channels,
        frames: buf.frames,
        data: buf.data.clone(),
    }
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

    /// 获取程序引用
    pub fn program(&self) -> &JsfxProgram {
        &self.program
    }

    /// 获取运行时引用
    pub fn runtime(&self) -> &crate::runtime::JsfxRuntime {
        &self.vm.runtime
    }

    /// 执行@gfx块（手动触发GUI绘制脚本）
    pub fn execute_gfx(&mut self) {
        if !self.initialized || self.destroyed { return; }
        self.vm.execute_gfx();
    }

    /// 执行@serialize块（用于预设保存/加载）
    pub fn execute_serialize(&mut self) {
        if !self.initialized || self.destroyed { return; }
        self.vm.execute_serialize();
    }

    /// 获取gfx变量值
    pub fn get_gfx_var(&self, name: &str) -> f64 {
        self.vm.runtime.get_var(name)
    }

    /// 设置gfx变量值（例如从GUI层更新窗口尺寸）
    pub fn set_gfx_var(&mut self, name: &str, value: f64) {
        self.vm.runtime.set_var(name, value);
    }

    /// 获取所有运行时变量（调试/序列化用）
    pub fn get_all_vars(&self) -> &std::collections::HashMap<String, f64> {
        &self.vm.runtime.vars
    }

    /// 获取内存区域引用（调试用）
    pub fn get_memory(&self) -> &[f64] {
        &self.vm.runtime.memory
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

    fn process(&mut self, input: &ExtAudioBuffer, output: &mut ExtAudioBuffer) {
        if !self.initialized || self.destroyed {
            // 未初始化或已销毁时直通
            let min_len = input.data.len().min(output.data.len());
            output.data[..min_len].copy_from_slice(&input.data[..min_len]);
            return;
        }

        // 将扩展层AudioBuffer转换为VM内部AudioBuffer
        let vm_input = ext_to_vm(input);
        let mut vm_output = VmAudioBuffer::new(output.channels, output.frames);

        self.vm.process_buffer(&vm_input, &mut vm_output);

        // 将VM输出写回扩展层AudioBuffer
        let min_len = vm_output.data.len().min(output.data.len());
        output.data[..min_len].copy_from_slice(&vm_output.data[..min_len]);
    }

    fn get_params(&self) -> Vec<ParamInfo> {
        self.program.sliders.iter().map(|s| {
            ParamInfo::with_step(
                &format!("slider{}", s.index),
                &s.name.clone().unwrap_or_else(|| format!("Slider {}", s.index)),
                s.min,
                s.max,
                s.default,
                s.step,
                "",
            )
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

        let input = ExtAudioBuffer::new(2, 4);
        let mut output = ExtAudioBuffer::new(2, 4);

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
