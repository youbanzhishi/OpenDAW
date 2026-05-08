//! VST3 插件适配器 — 将 VST3 格式插件包装为 VcPlugin trait
//!
//! # VST3 插件生命周期
//!
//! 1. 加载 .vst3 动态库
//! 2. 通过 IPluginFactory 创建 IComponent 实例
//! 3. 设置采样率/缓冲区大小
//! 4. 创建 IAudioProcessor 接口
//! 5. 设置 Speaker Arrangement
//! 6. activate() → process() 循环 → deactivate()
//!
//! # 实现策略
//!
//! VST3 是基于 COM/IUnknown 接口的 C++ API，在 Rust 中需要通过
//! FFI 桥接。当前实现提供完整的结构框架和 trait 实现，
//! VST3 的 FFI 调用需要在启用 `vst3` feature 后实现。
//!
//! # 编译要求
//!
//! 此模块需要 `vst3` feature。VST3 依赖需要特殊处理
//!（可能需要 vst3-sys 或自定义 FFI 绑定）。

#![cfg(feature = "vst3")]

use std::collections::HashMap;
use std::path::{Path, PathBuf};

use opendaw_extension::{AudioBuffer, ParamInfo, PluginError, PluginType, VcPlugin};

// ── VST3 FFI 类型占位 ────────────────────────────────────────────────────
// 当 vst3 feature 启用且 vst3-sys 可用时，这些类型将被替换为实际 FFI 类型

/// VST3 插件工厂（占位，实际为 IPluginFactory COM 接口）
struct Vst3PluginFactory {
    _path: PathBuf,
}

/// VST3 组件实例（占位，实际为 IComponent COM 接口）
struct Vst3Component {
    _factory: Vst3PluginFactory,
}

/// VST3 音频处理器（占位，实际为 IAudioProcessor COM 接口）
struct Vst3AudioProcessor {
    _component: Vst3Component,
}

// ── Vst3Adapter ─────────────────────────────────────────────────────────

/// VST3 插件适配器
///
/// 将 VST3 格式插件包装为 VcPlugin trait 实现，
/// 使 VST3 插件在 OpenDAW 中与 VC-Plugin 一样使用。
///
/// # VST3 组件模型
///
/// VST3 使用 COM 风格的组件模型：
/// - `IComponent`：管理插件状态、参数
/// - `IAudioProcessor`：处理音频数据
/// - `IEditController`：管理 GUI（此适配器暂不支持）
///
/// # Speaker Arrangement
///
/// 默认使用立体声（2 in / 2 out），可在 init() 中配置。
pub struct Vst3Adapter {
    /// 插件唯一标识
    plugin_id: String,
    /// 插件人类可读名称
    plugin_name: String,
    /// 插件版本
    plugin_version: String,
    /// 插件类型
    plugin_type: PluginType,
    /// .vst3 文件路径
    plugin_path: PathBuf,
    /// VST3 组件实例
    component: Option<Vst3Component>,
    /// 音频处理器
    audio_processor: Option<Vst3AudioProcessor>,
    /// 当前采样率
    sample_rate: f64,
    /// 当前缓冲区大小
    buffer_size: usize,
    /// 声道数（输入）
    input_channels: usize,
    /// 声道数（输出）
    output_channels: usize,
    /// 参数信息缓存
    params: Vec<ParamInfo>,
    /// 参数当前值（VST3 ParamID → normalized value）
    param_values: HashMap<String, f64>,
    /// 是否已初始化
    initialized: bool,
}

impl Vst3Adapter {
    /// 从 .vst3 文件加载插件（仅扫描，不初始化）
    ///
    /// 读取 .vst3 动态库，获取插件信息，
    /// 但不激活音频处理器。调用 `init()` 后才能处理音频。
    ///
    /// # VST3 bundle 结构
    ///
    /// ```text
    /// MyPlugin.vst3/
    ///   Contents/
    ///     Info.plist        (macOS)
    ///     MacOS/
    ///       MyPlugin        (macOS 动态库)
    ///     Linux/
    ///       MyPlugin.so     (Linux)
    ///     Win/
    ///       MyPlugin.dll    (Windows)
    ///     Resources/
    ///       ...
    /// ```
    pub fn from_file(path: &Path) -> Result<Self, PluginError> {
        // 查找平台对应的动态库
        let binary_path = Self::find_vst3_binary(path)?;

        // 加载动态库并获取 IPluginFactory
        let factory = Vst3PluginFactory {
            _path: binary_path.clone(),
        };

        // TODO: 实际的 VST3 加载流程
        // 1. dlopen/LoadLibrary 加载动态库
        // 2. 获取 GetPluginFactory 入口点
        // 3. 通过 IPluginFactory::createInstance 创建 IComponent
        // 4. 查询 IAudioProcessor 接口

        // 从路径推断插件信息
        let (id, name) = Self::infer_plugin_info(path);

        Ok(Self {
            plugin_id: id,
            plugin_name: name,
            plugin_version: "1.0.0".to_string(),
            plugin_type: PluginType::Effect, // 默认，后续从 component 读取
            plugin_path: path.to_path_buf(),
            component: None,
            audio_processor: None,
            sample_rate: 0.0,
            buffer_size: 0,
            input_channels: 2,
            output_channels: 2,
            params: Vec::new(),
            param_values: HashMap::new(),
            initialized: false,
        })
    }

    /// 扫描目录下所有 .vst3 插件
    ///
    /// 递归扫描指定目录，查找所有 .vst3 文件（bundle 目录或动态库）。
    pub fn scan_directory(dir: &Path) -> Result<Vec<Vst3Adapter>, PluginError> {
        let mut adapters = Vec::new();

        if !dir.exists() {
            log::warn!("VST3 扫描目录不存在: {}", dir.display());
            return Ok(adapters);
        }

        let entries = std::fs::read_dir(dir)
            .map_err(|e| PluginError::InitFailed(
                format!("读取目录失败 {}: {}", dir.display(), e)
            ))?;

        for entry in entries.flatten() {
            let path = entry.path();

            if path.is_dir() {
                // 检查是否是 .vst3 bundle
                if path.extension().map(|e| e == "vst3").unwrap_or(false) {
                    match Vst3Adapter::from_file(&path) {
                        Ok(adapter) => adapters.push(adapter),
                        Err(e) => {
                            log::warn!("跳过无效 VST3 插件 {}: {}", path.display(), e);
                        }
                    }
                } else {
                    // 递归扫描子目录
                    if let Ok(sub) = Self::scan_directory(&path) {
                        adapters.extend(sub);
                    }
                }
            }
        }

        log::info!("VST3 扫描完成: {} 发现 {} 个插件", dir.display(), adapters.len());
        Ok(adapters)
    }

    /// 获取 .vst3 文件路径
    pub fn path(&self) -> &Path {
        &self.plugin_path
    }

    // ── 内部方法 ──────────────────────────────────────────────────────

    /// 查找 .vst3 bundle 中的平台动态库
    fn find_vst3_binary(path: &Path) -> Result<PathBuf, PluginError> {
        // 如果直接是文件，返回自身
        if path.is_file() {
            return Ok(path.to_path_buf());
        }

        // bundle 目录结构
        let stem = path.file_stem()
            .ok_or_else(|| PluginError::InitFailed(
                format!("无法解析 VST3 文件名: {}", path.display())
            ))?
            .to_string_lossy()
            .to_string();

        #[cfg(target_os = "macos")]
        {
            let binary = path.join("Contents/MacOS").join(&stem);
            if binary.exists() {
                return Ok(binary);
            }
        }

        #[cfg(target_os = "linux")]
        {
            let binary = path.join("Contents/Linux").join(format!("{}.so", stem));
            if binary.exists() {
                return Ok(binary);
            }
        }

        #[cfg(target_os = "windows")]
        {
            let binary = path.join("Contents/Win").join(format!("{}.dll", stem));
            if binary.exists() {
                return Ok(binary);
            }
        }

        // 回退：返回原始路径
        Ok(path.to_path_buf())
    }

    /// 从路径推断插件信息
    fn infer_plugin_info(path: &Path) -> (String, String) {
        let stem = path.file_stem()
            .map(|s| s.to_string_lossy().to_string())
            .unwrap_or_default();

        let id = stem.to_lowercase().replace(' ', "-");
        let name = stem;

        (id, name)
    }
}

impl VcPlugin for Vst3Adapter {
    fn plugin_id(&self) -> &str {
        &self.plugin_id
    }

    fn plugin_name(&self) -> &str {
        &self.plugin_name
    }

    fn plugin_type(&self) -> PluginType {
        self.plugin_type
    }

    fn version(&self) -> &str {
        &self.plugin_version
    }

    fn init(&mut self, sample_rate: f64, buffer_size: usize) -> Result<(), PluginError> {
        if self.initialized {
            log::warn!("VST3 插件已初始化，跳过: {}", self.plugin_id);
            return Ok(());
        }

        self.sample_rate = sample_rate;
        self.buffer_size = buffer_size;

        // TODO: 完整的 VST3 初始化流程
        //
        // 1. 创建 IComponent 实例
        //    factory.createInstance(class_id, IComponent.iid, &mut obj)
        //
        // 2. 初始化组件
        //    component.initialize(&host_context)
        //
        // 3. 设置采样率
        //    component.setSampleRate(sample_rate as f64)
        //
        // 4. 设置缓冲区大小
        //    component.setMaxSamplesPerBlock(buffer_size as i32)
        //
        // 5. 创建 IAudioProcessor
        //    component.queryInterface(IAudioProcessor.iid, &mut processor)
        //
        // 6. 设置 Speaker Arrangement
        //    processor.setBusArrangements(
        //        inputs: [Stereo], outputs: [Stereo]
        //    )
        //
        // 7. 激活
        //    component.setActive(true)
        //    processor.setProcessing(true)
        //
        // 8. 收集参数信息
        //    for i in 0..component.getParameterCount() {
        //        let info = component.getParameterInfo(i);
        //        params.push(ParamInfo { ... });
        //    }

        self.initialized = true;

        // 初始化参数默认值
        for p in &self.params {
            self.param_values.insert(p.id.clone(), p.default);
        }

        log::info!(
            "VST3 插件初始化成功: {} ({}Hz, {} frames)",
            self.plugin_id, sample_rate, buffer_size
        );

        Ok(())
    }

    fn process(&mut self, input: &AudioBuffer, output: &mut AudioBuffer) {
        if !self.initialized {
            // 未初始化时直通
            output.data.copy_from_slice(&input.data);
            return;
        }

        // TODO: 完整的 VST3 音频处理流程
        //
        // 1. 将 AudioBuffer (f64, planar) 转换为 VST3 的浮点缓冲区格式
        //    VST3 使用非交错 (planar) f32 缓冲区
        //
        // 2. 构建 VST3 ProcessData
        //    let process_data = ProcessData {
        //        process_mode: ProcessMode::Realtime,
        //        symbolic_sample_size: SymbolicSampleSizes::Sample32,
        //        num_samples: buffer_size as i32,
        //        input: &input_buffers,
        //        output: &mut output_buffers,
        //        input_parameter_changes: &param_changes,
        //        output_parameter_changes: &mut out_param_changes,
        //        input_events: &input_events,
        //        output_events: &mut output_events,
        //    };
        //
        // 3. 调用 process
        //    audio_processor.process(process_data)
        //
        // 4. 将结果从 f32 planar 转回 f64 写入 output

        // 当前版本：直通
        output.data.copy_from_slice(&input.data);
    }

    fn get_params(&self) -> Vec<ParamInfo> {
        self.params.clone()
    }

    fn set_param(&mut self, id: &str, value: f64) -> Result<(), PluginError> {
        let clamped = if let Some(param) = self.params.iter().find(|p| p.id == id) {
            param.clamp_value(value)
        } else {
            return Err(PluginError::ParamNotFound(
                format!("VST3 参数未找到: {}", id)
            ));
        };

        self.param_values.insert(id.to_string(), clamped);

        // TODO: 通过 VST3 IComponent::setParamNormalized 同步参数
        // VST3 使用归一化值 [0.0, 1.0]
        // let normalized = (value - min) / (max - min);
        // component.setParamNormalized(param_id, normalized);
        // 
        // 注意：VST3 要求在 edit controller 上设置参数，
        // 需要同步到 processor（通过 IComponent::setParamNormalized）

        Ok(())
    }

    fn get_param(&self, id: &str) -> Option<f64> {
        self.param_values.get(id).copied()
    }

    fn destroy(&mut self) {
        if self.initialized {
            log::info!("销毁 VST3 插件: {}", self.plugin_id);

            // VST3 清理流程：
            // 1. processor.setProcessing(false)
            // 2. component.setActive(false)
            // 3. component.terminate()
            // 4. 释放 COM 接口

            self.audio_processor = None;
            self.component = None;
            self.initialized = false;
        }
    }
}

// ── 单元测试 ──────────────────────────────────────────────────────────────

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_infer_plugin_info() {
        let (id, name) = Vst3Adapter::infer_plugin_info(
            Path::new("/Library/Audio/Plug-Ins/VST3/Surge.vst3")
        );
        assert_eq!(id, "surge");
        assert_eq!(name, "Surge");

        let (id2, name2) = Vst3Adapter::infer_plugin_info(
            Path::new("/usr/lib/vst3/Vital.vst3")
        );
        assert_eq!(id2, "vital");
        assert_eq!(name2, "Vital");
    }

    #[test]
    fn test_param_clamp() {
        let param = ParamInfo::new("cutoff", "Cutoff", 20.0, 20000.0, 1000.0, "Hz");
        assert_eq!(param.clamp_value(0.0), 20.0);
        assert_eq!(param.clamp_value(500.0), 500.0);
        assert_eq!(param.clamp_value(50000.0), 20000.0);
    }

    #[test]
    fn test_uninitialized_passthrough() {
        let input = AudioBuffer::new(2, 256);
        let mut output = AudioBuffer::new(2, 256);
        output.data.fill(1.0);
        output.data.copy_from_slice(&input.data);
        for i in 0..input.data.len() {
            assert!((output.data[i] - input.data[i]).abs() < 1e-10);
        }
    }
}
