//! Desktop音频输出模块 - 通过CPAL实现实时音频播放
//!
//! ## 架构
//!
//! ```text
//! AudioEngine (render_frame)
//!        ↓
//!  AudioOutput (crossbeam channel receiver)
//!        ↓
//!  CPAL Output Stream (speaker playback)
//! ```
//!
//! ## 设计决策
//!
//! - CPAL Stream 在 Linux 上不是 Send，所以我们需要在独立线程中运行它
//! - AudioEngine 渲染音频帧，通过 channel 发送给 DesktopAudioOutput
//! - DesktopAudioOutput 在独立线程中运行 CPAL，接收音频帧并播放

use audio_engine::channel_output::AudioFrame;
use cpal::traits::{DeviceTrait, HostTrait, StreamTrait};
use crossbeam_channel::{bounded, Receiver, Sender};
use parking_lot::Mutex;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Arc;
use std::thread;
use std::time::Duration;

// ═══════════════════════════════════════════════════════════════════════════
// Types
// ═══════════════════════════════════════════════════════════════════════════

/// 音频输出状态
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum OutputState {
    /// 空闲（未启动）
    Idle,
    /// 正在播放
    Playing,
    /// 已暂停
    Paused,
    /// 错误状态
    Error,
}

impl Default for OutputState {
    fn default() -> Self {
        Self::Idle
    }
}

/// 音频输出错误
#[derive(Debug, Clone)]
pub enum OutputError {
    /// 未找到音频设备
    NoDevice,
    /// 设备配置失败
    ConfigError(String),
    /// 流创建失败
    StreamError(String),
    /// 通道接收错误
    ChannelError(String),
    /// 线程错误
    ThreadError(String),
}

impl std::fmt::Display for OutputError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::NoDevice => write!(f, "未找到音频输出设备"),
            Self::ConfigError(msg) => write!(f, "设备配置失败: {}", msg),
            Self::StreamError(msg) => write!(f, "流创建失败: {}", msg),
            Self::ChannelError(msg) => write!(f, "通道错误: {}", msg),
            Self::ThreadError(msg) => write!(f, "线程错误: {}", msg),
        }
    }
}

impl std::error::Error for OutputError {}

/// 音频输出配置
#[derive(Debug, Clone)]
pub struct OutputConfig {
    /// 采样率
    pub sample_rate: u32,
    /// 缓冲区大小（帧数）
    pub buffer_size: usize,
    /// 声道数
    pub channels: u16,
}

impl Default for OutputConfig {
    fn default() -> Self {
        Self {
            sample_rate: 44100,
            buffer_size: 256,
            channels: 2,
        }
    }
}

// ═══════════════════════════════════════════════════════════════════════════
// DesktopAudioOutput
// ═══════════════════════════════════════════════════════════════════════════

/// Desktop 音频输出
///
/// 在独立线程中运行 CPAL，从 channel 接收音频帧并播放。
///
/// ## 使用方式
///
/// ```no_run
/// use audio_engine::{AudioEngine, AudioFrame};
/// use vcmix_desktop_lib::audio_output::DesktopAudioOutput;
///
/// // 创建输出设备
/// let mut output = DesktopAudioOutput::new().unwrap();
///
/// // 设置配置
/// output.configure(44100, 256, 2).unwrap();
///
/// // 启动播放
/// output.start().unwrap();
///
/// // 在播放循环中发送音频帧
/// loop {
///     // 从 AudioEngine 获取渲染帧
///     let frame = AudioFrame::new(samples, 2);
///     output.send_frame(frame);
/// }
///
/// // 停止播放
/// output.stop();
/// ```
pub struct DesktopAudioOutput {
    /// 当前状态
    state: Arc<Mutex<OutputState>>,
    /// 运行标志
    running: Arc<AtomicBool>,
    /// 暂停标志
    paused: Arc<AtomicBool>,
    /// 配置
    config: Arc<Mutex<OutputConfig>>,
    /// 音频帧发送器（用于手动注入帧）
    sender: Arc<Mutex<Option<Sender<AudioFrame>>>>,
    /// 音频帧接收器（由外部填充）
    receiver: Arc<Mutex<Option<Receiver<AudioFrame>>>>,
    /// 音频线程句柄
    thread_handle: Arc<Mutex<Option<thread::JoinHandle<()>>>>,
    /// 采样率
    actual_sample_rate: Arc<Mutex<f64>>,
}

impl DesktopAudioOutput {
    /// 创建新的音频输出设备
    pub fn new() -> Result<Self, OutputError> {
        // 检查音频设备
        let host = cpal::default_host();
        let _device = host
            .default_output_device()
            .ok_or(OutputError::NoDevice)?;

        Ok(Self {
            state: Arc::new(Mutex::new(OutputState::Idle)),
            running: Arc::new(AtomicBool::new(false)),
            paused: Arc::new(AtomicBool::new(false)),
            config: Arc::new(Mutex::new(OutputConfig::default())),
            sender: Arc::new(Mutex::new(None)),
            receiver: Arc::new(Mutex::new(None)),
            thread_handle: Arc::new(Mutex::new(None)),
            actual_sample_rate: Arc::new(Mutex::new(44100.0)),
        })
    }

    /// 获取可用设备信息
    pub fn device_info() -> Result<Vec<String>, OutputError> {
        let host = cpal::default_host();
        let mut devices = Vec::new();

        if let Ok(enumerated) = host.output_devices() {
            for (idx, device) in enumerated.enumerate() {
                let name = device
                    .name()
                    .unwrap_or_else(|_| format!("Device {}", idx));
                devices.push(name);
            }
        }

        if devices.is_empty() {
            return Err(OutputError::NoDevice);
        }

        Ok(devices)
    }

    /// 配置音频输出
    pub fn configure(&mut self, sample_rate: u32, buffer_size: usize, channels: u16) -> Result<(), OutputError> {
        let mut config = self.config.lock();
        config.sample_rate = sample_rate;
        config.buffer_size = buffer_size;
        config.channels = channels;
        Ok(())
    }

    /// 设置音频帧通道（发送器和接收器）
    ///
    /// 通常与 AudioEngine.setup_channel_output() 配合使用。
    pub fn set_channel(&self, sender: Sender<AudioFrame>, receiver: Receiver<AudioFrame>) {
        *self.sender.lock() = Some(sender);
        *self.receiver.lock() = Some(receiver);
    }

    /// 获取当前状态
    pub fn state(&self) -> OutputState {
        *self.state.lock()
    }

    /// 是否正在运行
    pub fn is_running(&self) -> bool {
        self.running.load(Ordering::SeqCst)
    }

    /// 是否暂停
    pub fn is_paused(&self) -> bool {
        self.paused.load(Ordering::SeqCst)
    }

    /// 获取实际采样率
    pub fn sample_rate(&self) -> f64 {
        *self.actual_sample_rate.lock()
    }

    /// 启动音频播放
    ///
    /// 启动独立线程运行 CPAL 音频流。
    /// 如果已经启动，则忽略。
    pub fn start(&mut self) -> Result<(), OutputError> {
        // 如果已经在运行，忽略
        if self.running.load(Ordering::SeqCst) {
            return Ok(());
        }

        // 获取配置
        let config = self.config.lock().clone();
        let receiver = {
            let guard = self.receiver.lock();
            guard.clone()
                .ok_or_else(|| OutputError::ChannelError("未设置音频帧接收器".into()))?
        };

        // 设置状态
        *self.state.lock() = OutputState::Playing;
        self.running.store(true, Ordering::SeqCst);
        self.paused.store(false, Ordering::SeqCst);

        // 克隆需要在线程中使用的状态
        let state_clone = self.state.clone();
        let running_clone = self.running.clone();
        let paused_clone = self.paused.clone();
        let actual_sr_clone = self.actual_sample_rate.clone();

        // 启动音频线程
        let handle = thread::Builder::new()
            .name("audio-output".into())
            .spawn(move || {
                Self::audio_thread_fn(
                    config,
                    receiver,
                    state_clone,
                    running_clone,
                    paused_clone,
                    actual_sr_clone,
                );
            })
            .map_err(|e| OutputError::ThreadError(e.to_string()))?;

        *self.thread_handle.lock() = Some(handle);
        Ok(())
    }

    /// 音频线程函数
    fn audio_thread_fn(
        config: OutputConfig,
        receiver: Receiver<AudioFrame>,
        state: Arc<Mutex<OutputState>>,
        running: Arc<AtomicBool>,
        paused: Arc<AtomicBool>,
        actual_sample_rate: Arc<Mutex<f64>>,
    ) {
        // 获取默认音频设备
        let host = cpal::default_host();
        let device = match host.default_output_device() {
            Some(d) => d,
            None => {
                *state.lock() = OutputState::Error;
                running.store(false, Ordering::SeqCst);
                eprintln!("[AudioOutput] 错误: 未找到音频输出设备");
                return;
            }
        };

        // 获取设备配置
        let default_config = match device.default_output_config() {
            Ok(c) => c,
            Err(e) => {
                *state.lock() = OutputState::Error;
                running.store(false, Ordering::SeqCst);
                eprintln!("[AudioOutput] 错误: 获取设备配置失败: {}", e);
                return;
            }
        };

        // 设置实际采样率
        *actual_sample_rate.lock() = default_config.sample_rate().0 as f64;

        let channels = default_config.channels();
        let sample_rate = default_config.sample_rate().0;
        let frames_per_buffer = default_config.buffer_size();
        let buffer_size_display = match frames_per_buffer {
            cpal::SupportedBufferSize::Range { min, max } => format!("{}-{}", min, max),
            cpal::SupportedBufferSize::Unknown => "unknown".to_string(),
        };

        // 构建音频流
        let stream = match device.build_output_stream(
            &default_config.into(),
            move |output: &mut [f32], _: &cpal::OutputCallbackInfo| {
                if paused.load(Ordering::SeqCst) {
                    // 暂停时输出静音
                    for sample in output.iter_mut() {
                        *sample = 0.0;
                    }
                    return;
                }

                // 尝试接收音频帧
                match receiver.recv_timeout(Duration::from_millis(10)) {
                    Ok(frame) => {
                        // 帧数据复制到输出
                        let samples_to_copy = frame.samples.len().min(output.len());
                        output[..samples_to_copy].copy_from_slice(&frame.samples[..samples_to_copy]);

                        // 如果帧比缓冲区小，填充静音
                        if frame.samples.len() < output.len() {
                            for sample in output[frame.samples.len()..].iter_mut() {
                                *sample = 0.0;
                            }
                        }
                    }
                    Err(_) => {
                        // 没有收到帧，输出静音
                        for sample in output.iter_mut() {
                            *sample = 0.0;
                        }
                    }
                }
            },
            |err| {
                eprintln!("[AudioOutput] 流错误: {}", err);
            },
            None,
        ) {
            Ok(s) => s,
            Err(e) => {
                *state.lock() = OutputState::Error;
                running.store(false, Ordering::SeqCst);
                eprintln!("[AudioOutput] 错误: 创建音频流失败: {}", e);
                return;
            }
        };

        // 启动流
        if let Err(e) = stream.play() {
            *state.lock() = OutputState::Error;
            running.store(false, Ordering::SeqCst);
            eprintln!("[AudioOutput] 错误: 启动音频流失败: {}", e);
            return;
        }

        println!(
            "[AudioOutput] 播放中 - 采样率: {} Hz, 声道: {}, 缓冲区: {}",
            sample_rate, channels, buffer_size_display
        );

        // 等待停止信号
        while running.load(Ordering::SeqCst) {
            thread::sleep(Duration::from_millis(50));
        }

        // 停止时输出静音
        for _ in 0..10 {
            thread::sleep(Duration::from_millis(20));
        }

        *state.lock() = OutputState::Idle;
        println!("[AudioOutput] 已停止");
    }

    /// 发送音频帧
    ///
    /// 非阻塞发送，如果 channel 已满则丢弃帧。
    pub fn send_frame(&self, frame: AudioFrame) -> bool {
        let guard = self.sender.lock();
        if let Some(ref tx) = *guard {
            tx.try_send(frame).is_ok()
        } else {
            false
        }
    }

    /// 暂停播放
    pub fn pause(&self) {
        self.paused.store(true, Ordering::SeqCst);
        *self.state.lock() = OutputState::Paused;
    }

    /// 恢复播放
    pub fn resume(&self) {
        self.paused.store(false, Ordering::SeqCst);
        *self.state.lock() = OutputState::Playing;
    }

    /// 停止播放
    pub fn stop(&self) {
        self.running.store(false, Ordering::SeqCst);
        self.paused.store(false, Ordering::SeqCst);

        // 等待线程结束
        if let Some(handle) = self.thread_handle.lock().take() {
            let _ = handle.join();
        }
    }
}

impl Drop for DesktopAudioOutput {
    fn drop(&mut self) {
        self.stop();
    }
}

// ═══════════════════════════════════════════════════════════════════════════
// Thread-safe wrapper for Tauri state
// ═══════════════════════════════════════════════════════════════════════════

/// 线程安全的音频输出封装（用于 Tauri State）
pub struct AudioOutputState {
    output: Arc<Mutex<Option<DesktopAudioOutput>>>,
    engine: Arc<Mutex<audio_engine::AudioEngine>>,
    receiver: Arc<Mutex<Option<Receiver<AudioFrame>>>>,
}

impl AudioOutputState {
    /// 创建新的音频输出状态
    pub fn new() -> Self {
        Self {
            output: Arc::new(Mutex::new(None)),
            engine: Arc::new(Mutex::new(audio_engine::AudioEngine::new())),
            receiver: Arc::new(Mutex::new(None)),
        }
    }

    /// 初始化音频输出
    pub fn init(&self, sample_rate: f64, buffer_size: usize) -> Result<(), OutputError> {
        let mut engine = self.engine.lock();

        // 注册默认音轨
        if engine.track_count() == 0 {
            let _ = engine.register_track("main");
        }

        // 设置采样率
        engine.sample_rate();

        // 创建独立的 channel 用于手动帧注入
        let (sender, receiver) = crossbeam_channel::bounded(4096);
        *self.receiver.lock() = Some(receiver.clone());

        // 创建音频输出
        let mut output = DesktopAudioOutput::new()?;
        output.configure(sample_rate as u32, buffer_size, 2)?;
        output.set_channel(sender, receiver);

        *self.output.lock() = Some(output);
        Ok(())
    }

    /// 启动播放
    pub fn start(&self) -> Result<(), OutputError> {
        let mut engine = self.engine.lock();
        engine.start(44100.0, 256).map_err(|e| OutputError::StreamError(e.to_string()))?;

        let mut output_guard = self.output.lock();
        if let Some(ref mut output) = *output_guard {
            output.start()?;
        }
        Ok(())
    }

    /// 停止播放
    pub fn stop(&self) {
        let mut engine = self.engine.lock();
        let _ = engine.stop();

        let output_guard = self.output.lock();
        if let Some(ref output) = *output_guard {
            output.stop();
        }
    }

    /// 加载 WAV 文件到音轨
    pub fn load_wav(&self, track_id: &str, file_path: &str) -> Result<(), String> {
        let mut engine = self.engine.lock();
        // 确保音轨存在
        if engine.track_count() == 0 {
            engine.register_track(track_id)
                .map_err(|e| e.to_string())?;
        }
        engine.load_wav(track_id, file_path).map_err(|e| e.to_string())
    }

    /// 获取引擎状态
    pub fn engine_state(&self) -> String {
        let engine = self.engine.lock();
        format!("{:?}", engine.get_state())
    }

    /// 获取输出状态
    pub fn output_state(&self) -> OutputState {
        let guard = self.output.lock();
        guard.as_ref().map(|o| o.state()).unwrap_or(OutputState::Idle)
    }

    /// 获取音轨数量
    pub fn track_count(&self) -> usize {
        self.engine.lock().track_count()
    }

    /// 注册音轨
    pub fn register_track(&self, track_id: &str) -> Result<(), String> {
        let mut engine = self.engine.lock();
        engine.register_track(track_id).map_err(|e| e.to_string())
    }

    /// 设置音轨音量
    pub fn set_track_volume(&self, track_id: &str, volume_db: f64) -> Result<(), String> {
        let mut engine = self.engine.lock();
        engine.set_track_volume(track_id, volume_db).map_err(|e| e.to_string())
    }

    /// 设置主音量
    pub fn set_master_volume(&self, volume_db: f64) {
        let mut engine = self.engine.lock();
        engine.set_master_volume(volume_db);
    }

    /// 切换音轨静音
    pub fn toggle_track_mute(&self, track_id: &str) -> Result<bool, String> {
        let mut engine = self.engine.lock();
        engine.toggle_track_mute(track_id).map_err(|e| e.to_string())
    }

    /// 暂停音频播放
    pub fn pause(&self) {
        let output_guard = self.output.lock();
        if let Some(ref output) = *output_guard {
            output.pause();
        }
    }

    /// 恢复音频播放
    pub fn resume(&self) {
        let output_guard = self.output.lock();
        if let Some(ref output) = *output_guard {
            output.resume();
        }
    }
}

impl Default for AudioOutputState {
    fn default() -> Self {
        Self::new()
    }
}

// ═══════════════════════════════════════════════════════════════════════════
// Tests
// ═══════════════════════════════════════════════════════════════════════════

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_output_state() {
        assert_eq!(OutputState::Idle, OutputState::Idle);
        assert_ne!(OutputState::Idle, OutputState::Playing);
    }

    #[test]
    fn test_audio_output_state_creation() {
        let state = AudioOutputState::new();
        assert_eq!(state.track_count(), 0);
    }

    #[test]
    fn test_device_info() {
        // 这个测试可能失败如果没有音频设备
        match DesktopAudioOutput::device_info() {
            Ok(devices) => println!("可用设备: {:?}", devices),
            Err(e) => println!("获取设备信息失败: {}", e),
        }
    }
}
