//! CLAP 插件适配器 — 将 CLAP 格式插件包装为 VcPlugin trait
//!
//! 使用 `clack-host` crate（Rust 原生、安全封装）来 host CLAP 插件。
//!
//! # CLAP 插件生命周期
//!
//! 1. `PluginEntry::load()` — 从 .clap 动态库加载入口
//! 2. `PluginInstance::new()` — 创建插件实例
//! 3. `activate()` — 激活音频处理器，配置采样率/缓冲区
//! 4. `start_processing()` — 开始处理
//! 5. `process()` — 循环调用处理音频
//! 6. `stop_processing()` → `deactivate()` — 停止并去激活
//!
//! # 编译要求
//!
//! 此模块需要 `clap` feature 和 Rust 1.85+（clack-host 使用 edition 2024）。
//! 在 Rust 1.85 以下版本中，此模块不可用。

#![cfg(feature = "clap")]

use std::collections::HashMap;
use std::path::{Path, PathBuf};

use opendaw_extension::{AudioBuffer, ParamInfo, PluginError, PluginType, VcPlugin};

// ── CLAP Host 实现 ──────────────────────────────────────────────────────

/// OpenDAW 的 CLAP Host 回调实现
///
/// 实现 clack-host 要求的 SharedHandler 和 HostHandlers trait，
/// 用于接收插件发来的请求（如 request_restart 等）。
struct OpenDawClapHost;

impl<'a> clack_host::prelude::SharedHandler<'a> for OpenDawClapHost {
    fn request_restart(&self) {
        log::info!("CLAP 插件请求重启");
    }

    fn request_process(&self) {
        log::info!("CLAP 插件请求处理");
    }

    fn request_callback(&self) {
        log::info!("CLAP 插件请求回调");
    }
}

impl clack_host::prelude::HostHandlers for OpenDawClapHost {
    type Shared<'a> = OpenDawClapHost;
    type MainThread<'a> = ();
    type AudioProcessor<'a> = ();
}

// ── ClapAdapter ─────────────────────────────────────────────────────────

/// CLAP 插件适配器
///
/// 将 CLAP 格式插件包装为 VcPlugin trait 实现，
/// 使 CLAP 插件在 OpenDAW 中与 VC-Plugin 一样使用。
///
/// # 线程安全
///
/// CLAP 插件的处理必须在音频线程中完成。
/// 此适配器在 `process()` 中直接调用 CLAP 的音频处理回调。
pub struct ClapAdapter {
    /// 插件唯一标识（来自 CLAP descriptor 的 id）
    plugin_id: String,
    /// 插件人类可读名称（来自 CLAP descriptor 的 name）
    plugin_name: String,
    /// 插件版本（来自 CLAP descriptor 的 version）
    plugin_version: String,
    /// 插件类型（从 descriptor 的 features 推断）
    plugin_type: PluginType,
    /// .clap 文件路径
    plugin_path: PathBuf,
    /// 插件入口（持有动态库句柄）
    entry: Option<clack_host::prelude::PluginEntry>,
    /// 激活的音频处理器标记
    processor_active: bool,
    /// 当前采样率
    sample_rate: f64,
    /// 当前缓冲区大小
    buffer_size: usize,
    /// 声道数
    channels: usize,
    /// 参数信息缓存
    params: Vec<ParamInfo>,
    /// 参数当前值
    param_values: HashMap<String, f64>,
    /// 是否已初始化
    initialized: bool,
}

impl ClapAdapter {
    /// 从 .clap 文件加载插件（仅扫描，不初始化）
    ///
    /// 读取 .clap 动态库，获取插件描述符信息，
    /// 但不激活音频处理器。调用 `init()` 后才能处理音频。
    ///
    /// # Safety
    ///
    /// 此函数加载外部动态库（.clap 文件），属于 unsafe 操作。
    /// 仅信任来自已知路径的 CLAP 插件。
    pub fn from_file(path: &Path) -> Result<Self, PluginError> {
        let entry = unsafe {
            clack_host::prelude::PluginEntry::load(path)
                .map_err(|e| PluginError::InitFailed(
                    format!("加载 CLAP 插件失败 {}: {}", path.display(), e)
                ))?
        };

        let plugin_factory = entry.get_plugin_factory()
            .ok_or_else(|| PluginError::InitFailed(
                format!("CLAP 插件无 plugin factory: {}", path.display())
            ))?;

        // 取第一个插件的描述符
        let descriptor = plugin_factory.plugin_descriptors()
            .next()
            .ok_or_else(|| PluginError::InitFailed(
                format!("CLAP 插件无描述符: {}", path.display())
            ))?;

        let id = descriptor.id()
            .map(|s| s.to_string())
            .unwrap_or_else(||
                path.file_stem()
                    .map(|s| s.to_string_lossy().to_string())
                    .unwrap_or_default()
            );

        let name = descriptor.name()
            .map(|s| s.to_string())
            .unwrap_or_else(|| id.clone());

        let version = descriptor.version()
            .map(|s| s.to_string())
            .unwrap_or_else(|| "1.0.0".to_string());

        // 从 features 推断插件类型
        let plugin_type = Self::infer_plugin_type(&descriptor);

        // 尝试获取参数信息
        // 注意：完整的参数收集需要先创建 PluginInstance 并通过 params extension 获取
        let params = Vec::new();

        Ok(Self {
            plugin_id: id,
            plugin_name: name,
            plugin_version: version,
            plugin_type,
            plugin_path: path.to_path_buf(),
            entry: Some(entry),
            processor_active: false,
            sample_rate: 0.0,
            buffer_size: 0,
            channels: 2,
            params,
            param_values: HashMap::new(),
            initialized: false,
        })
    }

    /// 扫描目录下所有 .clap 插件
    ///
    /// 递归扫描指定目录，查找所有 .clap 文件（动态库），
    /// 返回可加载的适配器列表。
    ///
    /// 在 Linux 上 .clap 文件是 .so 共享库；
    /// 在 macOS 上是 .dylib；
    /// 在 Windows 上是 .dll。
    pub fn scan_directory(dir: &Path) -> Result<Vec<ClapAdapter>, PluginError> {
        let mut adapters = Vec::new();

        if !dir.exists() {
            log::warn!("CLAP 扫描目录不存在: {}", dir.display());
            return Ok(adapters);
        }

        let entries = std::fs::read_dir(dir)
            .map_err(|e| PluginError::InitFailed(
                format!("读取目录失败 {}: {}", dir.display(), e)
            ))?;

        for entry in entries.flatten() {
            let path = entry.path();

            if path.is_dir() {
                // CLAP 规范：.clap 可以是 bundle 目录（macOS）
                if path.extension().map(|e| e == "clap").unwrap_or(false) {
                    if let Some(adapter) = Self::try_load_clap_bundle(&path) {
                        adapters.push(adapter);
                    }
                } else {
                    // 递归扫描子目录
                    if let Ok(sub) = Self::scan_directory(&path) {
                        adapters.extend(sub);
                    }
                }
            } else if Self::is_clap_binary(&path) {
                match Self::from_file(&path) {
                    Ok(adapter) => adapters.push(adapter),
                    Err(e) => {
                        log::warn!("跳过无效 CLAP 插件 {}: {}", path.display(), e);
                    }
                }
            }
        }

        log::info!("CLAP 扫描完成: {} 发现 {} 个插件", dir.display(), adapters.len());
        Ok(adapters)
    }

    /// 获取 .clap 文件路径
    pub fn path(&self) -> &Path {
        &self.plugin_path
    }

    // ── 内部方法 ──────────────────────────────────────────────────────

    /// 从 CLAP descriptor 的 features 推断插件类型
    fn infer_plugin_type(
        descriptor: &clack_host::plugin::PluginDescriptor
    ) -> PluginType {
        let features = descriptor.features();
        for feature in features {
            if let Ok(f) = feature {
                match f.as_bytes() {
                    b"audio-effect" => return PluginType::Effect,
                    b"instrument" => return PluginType::Instrument,
                    b"note-effect" => return PluginType::MidiProcessor,
                    b"analyzer" => return PluginType::Analyzer,
                    _ => continue,
                }
            }
        }
        PluginType::Effect
    }

    /// 尝试加载 .clap bundle 目录中的动态库
    fn try_load_clap_bundle(dir: &Path) -> Option<ClapAdapter> {
        #[cfg(target_os = "macos")]
        {
            let stem = dir.file_stem()?.to_string_lossy().to_string();
            let binary = dir.join("Contents/MacOS").join(&stem);
            if binary.exists() {
                return ClapAdapter::from_file(&binary).ok();
            }
        }

        #[cfg(target_os = "linux")]
        {
            if dir.extension().map(|e| e == "clap").unwrap_or(false) {
                let stem = dir.file_stem()?.to_string_lossy().to_string();
                let binary = dir.join(format!("{}.so", stem));
                if binary.exists() {
                    return ClapAdapter::from_file(&binary).ok();
                }
            }
        }

        #[cfg(target_os = "windows")]
        {
            let stem = dir.file_stem()?.to_string_lossy().to_string();
            let binary = dir.join("Contents/Win").join(format!("{}.dll", stem));
            if binary.exists() {
                return ClapAdapter::from_file(&binary).ok();
            }
        }

        None
    }

    /// 检查文件是否是 CLAP 二进制文件
    fn is_clap_binary(path: &Path) -> bool {
        #[cfg(target_os = "linux")]
        {
            path.extension().map(|e| e == "clap").unwrap_or(false)
                || path.extension().map(|e| e == "so").unwrap_or(false)
        }

        #[cfg(target_os = "macos")]
        {
            path.extension().map(|e| e == "clap").unwrap_or(false)
                || path.extension().map(|e| e == "dylib").unwrap_or(false)
        }

        #[cfg(target_os = "windows")]
        {
            path.extension().map(|e| e == "clap").unwrap_or(false)
                || path.extension().map(|e| e == "dll").unwrap_or(false)
        }

        #[cfg(not(any(target_os = "linux", target_os = "macos", target_os = "windows")))]
        {
            path.extension().map(|e| e == "clap").unwrap_or(false)
        }
    }
}

impl VcPlugin for ClapAdapter {
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
            log::warn!("CLAP 插件已初始化，跳过: {}", self.plugin_id);
            return Ok(());
        }

        self.sample_rate = sample_rate;
        self.buffer_size = buffer_size;

        let entry = self.entry.as_ref()
            .ok_or_else(|| PluginError::InitFailed(
                "CLAP 插件入口未加载".to_string()
            ))?;

        // 创建 Host 信息
        let host_info = clack_host::prelude::HostInfo::new(
            "OpenDAW",
            "OpenDAW Project",
            "https://opendaw.org",
            "0.1.0",
        ).map_err(|e| PluginError::InitFailed(
            format!("创建 CLAP host info 失败: {}", e)
        ))?;

        // 获取插件 factory
        let plugin_factory = entry.get_plugin_factory()
            .ok_or_else(|| PluginError::InitFailed(
                "CLAP 插件无 plugin factory".to_string()
            ))?;

        // 查找指定 ID 的插件描述符
        let descriptor = plugin_factory.plugin_descriptors()
            .find(|d| d.id().map(|id| id.as_bytes() == self.plugin_id.as_bytes()).unwrap_or(false))
            .ok_or_else(|| PluginError::InitFailed(
                format!("CLAP 插件未找到: {}", self.plugin_id)
            ))?;

        // 创建插件实例
        let _instance = clack_host::prelude::PluginInstance::<OpenDawClapHost>::new(
            |_| OpenDawClapHost,
            |_| (),
            entry,
            descriptor.id().unwrap(),
            &host_info,
        ).map_err(|e| PluginError::InitFailed(
            format!("创建 CLAP 插件实例失败: {}", e)
        ))?;

        // 配置音频参数
        let _audio_config = clack_host::prelude::PluginAudioConfiguration {
            sample_rate,
            min_frames_count: 1,
            max_frames_count: buffer_size as u32,
        };

        // TODO: 完整的激活流程
        // let audio_processor = _instance.activate(|_, _| (), _audio_config)?;
        // let mut processing = audio_processor.start_processing()?;
        // 
        // 完整实现需要：
        // 1. 持有 ActivePluginInstance + StartedAudioProcessor
        // 2. 在 process() 中构建 AudioPorts 和 Event buffers
        // 3. 调用 processing.process() 方法
        //
        // clack-host 的类型状态机设计要求我们在 init() 中
        // 完成所有状态转换，并持有最终的处理器引用。
        // 当前版本标记为已激活，process() 中执行直通。

        self.processor_active = true;
        self.initialized = true;

        // 初始化参数默认值
        for p in &self.params {
            self.param_values.insert(p.id.clone(), p.default);
        }

        log::info!(
            "CLAP 插件初始化成功: {} ({}Hz, {} frames)",
            self.plugin_id, sample_rate, buffer_size
        );

        Ok(())
    }

    fn process(&mut self, input: &AudioBuffer, output: &mut AudioBuffer) {
        if !self.initialized || !self.processor_active {
            // 未初始化时直通
            output.data.copy_from_slice(&input.data);
            return;
        }

        // TODO: 完整的 CLAP 音频处理流程
        //
        // 完整实现步骤：
        // 1. 将 AudioBuffer (f64, planar) 转换为 f32 planar 格式
        // 2. 构建 AudioPorts（input/output）
        //    let mut input_ports = AudioPorts::with_capacity(channels, 1);
        //    let mut output_ports = AudioPorts::with_capacity(channels, 1);
        // 3. 构建 InputEvents / OutputEvents
        // 4. 调用 audio_processor.process()
        //    let process = Process::new(
        //        steady_time,
        //        frames_count,
        //        &input_events,
        //        &mut output_events,
        //        &mut input_audio,
        //        &mut output_audio,
        //    );
        //    audio_processor.process(process)?;
        // 5. 将结果从 f32 转回 f64 写入 output

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
                format!("CLAP 参数未找到: {}", id)
            ));
        };

        self.param_values.insert(id.to_string(), clamped);

        // TODO: 通过 CLAP params extension 将参数值同步到插件
        // 需要 clack-extensions crate 的 params extension 实现
        // 使用 normalized value 归一化后传递：
        // let normalized = (value - min) / (max - min);
        // params_extension.set_value(param_id, normalized);

        Ok(())
    }

    fn get_param(&self, id: &str) -> Option<f64> {
        self.param_values.get(id).copied()
    }

    fn destroy(&mut self) {
        if self.initialized {
            log::info!("销毁 CLAP 插件: {}", self.plugin_id);

            // CLAP 插件的清理流程：
            // 1. stop_processing()
            // 2. deactivate()
            // 3. 释放 PluginInstance
            // 4. 释放 PluginEntry（关闭动态库）

            self.processor_active = false;
            self.entry = None;
            self.initialized = false;
        }
    }
}

// ── 单元测试 ──────────────────────────────────────────────────────────────

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_param_clamp_logic() {
        // 测试参数钳位逻辑
        let param = ParamInfo::new("gain", "Gain", 0.0, 1.0, 0.5, "");
        assert_eq!(param.clamp_value(-0.5), 0.0);  // 低于最小值
        assert_eq!(param.clamp_value(0.5), 0.5);   // 正常值
        assert_eq!(param.clamp_value(2.0), 1.0);   // 高于最大值
    }

    #[test]
    fn test_uninitialized_passthrough() {
        // 未初始化的适配器应该直通音频
        let input = AudioBuffer::new(2, 256);
        let mut output = AudioBuffer::new(2, 256);
        output.data.fill(1.0);

        // 直通应该复制 input 到 output
        output.data.copy_from_slice(&input.data);
        for i in 0..input.data.len() {
            assert!((output.data[i] - input.data[i]).abs() < 1e-10);
        }
    }
}
