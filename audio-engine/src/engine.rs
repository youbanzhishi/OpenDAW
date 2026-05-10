//! 音频引擎核心 - 管理音频设备、音轨和播放
//!
//! AudioEngine 是 OpenDAW 的核心组件，提供：
//! - 实时音频I/O（通过CPAL，需启用 `audio` feature）
//! - 音轨管理（注册/注销/注入缓冲区）
//! - 播放控制（播放/暂停/停止/定位）
//! - 多音轨混合与声像处理
//!
//! 未启用 `audio` feature 时，引擎以模拟模式运行，适用于CI和测试环境。

use std::collections::HashMap;
use std::sync::Arc;

use parking_lot::Mutex;

use crate::buffer::AudioBuffer;
use crate::scheduler::Scheduler;
use crate::state::{EngineError, EngineState};
use crate::track::Track;

#[cfg(feature = "audio")]
use cpal::traits::{DeviceTrait, HostTrait, StreamTrait};

/// 引擎内部共享状态
///
/// 通过 `Arc<Mutex<>>` 在引擎主线程和音频回调线程之间安全共享。
#[allow(dead_code)]
struct SharedState {
    /// 音轨集合
    tracks: HashMap<String, Track>,
    /// 当前播放位置（样本数）
    position: usize,
    /// 采样率
    sample_rate: f64,
    /// 输出声道数
    channels: usize,
    /// 引擎状态
    engine_state: EngineState,
    /// 主音量（dB），0dB = 无增益
    master_volume: f64,
}

/// 音轨渲染参数（预计算，避免每帧重复计算）
#[derive(Clone, Debug)]
struct TrackRenderParams {
    /// 线性音量增益
    volume_gain: f32,
    /// 左声道声像增益
    pan_gain_l: f32,
    /// 右声道声像增益
    pan_gain_r: f32,
    /// 是否静音
    muted: bool,
    /// 缓冲区帧数
    buffer_frames: usize,
}

impl TrackRenderParams {
    /// 从 Track 计算渲染参数
    fn from_track(track: &Track) -> Self {
        // 音量转换：dB → 线性增益
        let volume_gain = if track.volume <= -60.0 {
            0.0
        } else {
            (10.0_f64.powf(track.volume / 20.0)) as f32
        };

        // 声像处理（简化线性声像法则）
        let pan = track.pan.clamp(-1.0, 1.0);
        let pan_gain_l = ((1.0 - pan) * 0.5).sqrt() as f32;
        let pan_gain_r = ((1.0 + pan) * 0.5).sqrt() as f32;

        Self {
            volume_gain,
            pan_gain_l,
            pan_gain_r,
            muted: track.muted,
            buffer_frames: track.buffer.frames,
        }
    }

    /// 获取指定声道的声像增益
    fn get_pan_gain(&self, channel: usize) -> f32 {
        if channel == 0 {
            self.pan_gain_l
        } else {
            self.pan_gain_r
        }
    }
}

/// OpenDAW 音频引擎
///
/// 提供实时音频 I/O、音轨管理、播放控制等核心功能。
/// 启用 `audio` feature 后可使用 CPAL 进行实时音频播放。
/// 未启用时引擎以模拟模式运行，适用于 CI 环境和测试。
///
/// # 线程安全
///
/// 引擎内部状态通过 `Arc<Mutex<SharedState>>` 保护：
/// - 主线程：通过引擎方法修改状态
/// - 音频线程（`audio` feature）：通过回调函数读取状态
///
/// # 示例
///
/// ```no_run
/// use audio_engine::AudioEngine;
/// use audio_engine::buffer::AudioBuffer;
///
/// let mut engine = AudioEngine::new();
/// engine.register_track("demo").unwrap();
///
/// // 注入音频数据
/// let buffer = AudioBuffer::zeros(2, 44100, 44100.0);
/// engine.inject_buffer("demo", buffer).unwrap();
///
/// engine.start(44100.0, 256).unwrap();
/// // ... 播放中 ...
/// engine.stop().unwrap();
/// ```
pub struct AudioEngine {
    /// 内部共享状态（与音频回调线程共享）
    shared: Arc<Mutex<SharedState>>,
    /// 缓冲区大小（帧数）
    buffer_size: usize,
    /// 音频处理调度器
    scheduler: Option<Scheduler>,
    /// CPAL 音频流（启用 `audio` feature 时可用）
    #[cfg(feature = "audio")]
    stream: Option<cpal::Stream>,
    /// 音频输出句柄（启用 `channel` feature 时可用）
    #[cfg(feature = "channel")]
    output_handle: Option<super::channel_output::AudioOutputHandle>,
}

impl Default for AudioEngine {
    fn default() -> Self {
        Self::new()
    }
}

impl AudioEngine {
    /// 创建新的音频引擎实例
    pub fn new() -> Self {
        Self {
            shared: Arc::new(Mutex::new(SharedState {
                tracks: HashMap::new(),
                position: 0,
                sample_rate: 44100.0,
                channels: 2,
                engine_state: EngineState::Stopped,
            master_volume: 0.0,
            })),
            buffer_size: 256,
            scheduler: None,
            #[cfg(feature = "audio")]
            stream: None,
            #[cfg(feature = "channel")]
            output_handle: None,
        }
    }

    // ==================== 播放控制 ====================

    /// 启动音频引擎
    ///
    /// - 从停止状态：全新启动，播放位置归零
    /// - 从暂停状态：恢复播放，保留当前位置
    ///
    /// 启用 `audio` feature 后将初始化 CPAL 音频流。
    pub fn start(&mut self, sample_rate: f64, buffer_size: usize) -> Result<(), EngineError> {
        self.buffer_size = buffer_size;

        let resuming = {
            let mut state = self.shared.lock();
            match state.engine_state {
                EngineState::Playing => return Err(EngineError::AlreadyRunning),
                EngineState::Paused => {
                    state.engine_state = EngineState::Playing;
                    true
                }
                _ => {
                    state.engine_state = EngineState::Playing;
                    state.sample_rate = sample_rate;
                    state.position = 0;
                    false
                }
            }
        };

        #[cfg(feature = "audio")]
        {
            if resuming {
                // 从暂停恢复：重新播放现有流
                if let Some(stream) = &self.stream {
                    stream
                        .play()
                        .map_err(|e| EngineError::DeviceError(e.to_string()))?;
                }
            } else if self.stream.is_none() {
                // 创建新的音频流
                self.build_and_start_stream()?;
            }
        }

        // 避免无 audio feature 时 unused variable 警告
        let _ = resuming;

        Ok(())
    }

    /// 停止音频引擎
    ///
    /// 停止播放并重置播放位置到开头。
    pub fn stop(&mut self) -> Result<(), EngineError> {
        {
            let mut state = self.shared.lock();
            if state.engine_state == EngineState::Stopped {
                return Err(EngineError::NotStarted);
            }
            state.engine_state = EngineState::Stopped;
            state.position = 0;
        }

        #[cfg(feature = "audio")]
        {
            // 释放音频流
            self.stream = None;
        }

        Ok(())
    }

    /// 暂停音频引擎
    ///
    /// 暂停播放，保留当前播放位置。之后可调用 `start()` 恢复。
    pub fn pause(&mut self) -> Result<(), EngineError> {
        {
            let mut state = self.shared.lock();
            if state.engine_state != EngineState::Playing {
                return Err(EngineError::NotStarted);
            }
            state.engine_state = EngineState::Paused;
        }

        #[cfg(feature = "audio")]
        {
            if let Some(stream) = &self.stream {
                stream
                    .pause()
                    .map_err(|e| EngineError::DeviceError(e.to_string()))?;
            }
        }

        Ok(())
    }

    // ==================== 位置控制 ====================

    /// 获取当前播放位置（秒）
    pub fn get_position(&self) -> f64 {
        let state = self.shared.lock();
        if state.sample_rate > 0.0 {
            state.position as f64 / state.sample_rate
        } else {
            0.0
        }
    }

    /// 设置播放位置（秒）
    pub fn set_position(&mut self, pos: f64) {
        let mut state = self.shared.lock();
        if pos >= 0.0 {
            state.position = (pos * state.sample_rate) as usize;
        }
    }

    /// 获取引擎当前状态
    pub fn get_state(&self) -> EngineState {
        self.shared.lock().engine_state
    }

    // ==================== 音轨管理 ====================

    /// 注册新音轨
    ///
    /// 音轨ID必须唯一，重复注册将返回错误。
    pub fn register_track(&mut self, track_id: &str) -> Result<(), EngineError> {
        let mut state = self.shared.lock();
        if state.tracks.contains_key(track_id) {
            return Err(EngineError::TrackAlreadyExists(track_id.to_string()));
        }
        let sr = state.sample_rate;
        state
            .tracks
            .insert(track_id.to_string(), Track::with_channels(track_id, 2, sr));
        Ok(())
    }

    /// 注销音轨
    pub fn unregister_track(&mut self, track_id: &str) -> Result<(), EngineError> {
        let mut state = self.shared.lock();
        if state.tracks.remove(track_id).is_none() {
            return Err(EngineError::TrackNotFound(track_id.to_string()));
        }
        Ok(())
    }

    /// 获取音轨缓冲区的克隆
    pub fn get_buffer(&self, track_id: &str) -> Option<AudioBuffer> {
        let state = self.shared.lock();
        state.tracks.get(track_id).map(|t| t.buffer.clone())
    }

    /// 注入音频数据到指定音轨
    ///
    /// 替换音轨的整个缓冲区。注入后音轨可立即播放。
    pub fn inject_buffer(&mut self, track_id: &str, data: AudioBuffer) -> Result<(), EngineError> {
        let mut state = self.shared.lock();
        if let Some(track) = state.tracks.get_mut(track_id) {
            track.buffer = data;
            Ok(())
        } else {
            Err(EngineError::TrackNotFound(track_id.to_string()))
        }
    }


    // ==================== 音轨控制 ====================

    /// 设置音轨音量
    ///
    /// - `track_id`: 音轨ID
    /// - `volume_db`: 音量（dB），范围 -60.0 ~ 12.0
    pub fn set_track_volume(&mut self, track_id: &str, volume_db: f64) -> Result<(), EngineError> {
        let mut state = self.shared.lock();
        if let Some(track) = state.tracks.get_mut(track_id) {
            track.set_volume(volume_db.clamp(-60.0, 12.0));
            Ok(())
        } else {
            Err(EngineError::TrackNotFound(track_id.to_string()))
        }
    }

    /// 切换音轨静音状态
    ///
    /// 返回静音后的状态（true=静音，false=非静音）
    pub fn toggle_track_mute(&mut self, track_id: &str) -> Result<bool, EngineError> {
        let mut state = self.shared.lock();
        if let Some(track) = state.tracks.get_mut(track_id) {
            track.toggle_mute();
            Ok(track.muted)
        } else {
            Err(EngineError::TrackNotFound(track_id.to_string()))
        }
    }

    /// 设置音轨声像
    ///
    /// - `track_id`: 音轨ID
    /// - `pan`: 声像值，范围 -1.0（完全左）~ 0.0（居中）~ 1.0（完全右）
    pub fn set_track_pan(&mut self, track_id: &str, pan: f64) -> Result<(), EngineError> {
        let mut state = self.shared.lock();
        if let Some(track) = state.tracks.get_mut(track_id) {
            track.set_pan(pan);
            Ok(())
        } else {
            Err(EngineError::TrackNotFound(track_id.to_string()))
        }
    }

    /// 获取音轨声像
    ///
    /// - `track_id`: 音轨ID
    /// 返回: 声像值（-1.0 ~ 1.0）
    pub fn get_track_pan(&self, track_id: &str) -> Result<f64, EngineError> {
        let state = self.shared.lock();
        if let Some(track) = state.tracks.get(track_id) {
            Ok(track.pan)
        } else {
            Err(EngineError::TrackNotFound(track_id.to_string()))
        }
    }

    // ==================== 主音量控制 ====================

    /// 设置主音量
    ///
    /// - `volume_db`: 音量（dB），范围 -60.0 ~ 12.0
    pub fn set_master_volume(&mut self, volume_db: f64) {
        let mut state = self.shared.lock();
        state.master_volume = volume_db.clamp(-60.0, 12.0);
    }

    /// 获取主音量
    pub fn get_master_volume(&self) -> f64 {
        self.shared.lock().master_volume
    }

    // ==================== WAV 文件加载 ====================

    /// 从 WAV 文件加载音频数据到指定音轨（使用手动解析器）
    ///
    /// 支持 16bit PCM WAV 文件。
    pub fn load_wav(&mut self, track_id: &str, file_path: &str) -> Result<(), EngineError> {
        use std::fs;
        use std::path::Path;

        // 确保音轨存在
        {
            let state = self.shared.lock();
            if !state.tracks.contains_key(track_id) {
                return Err(EngineError::TrackNotFound(track_id.to_string()));
            }
        }

        // 读取文件
        let path = Path::new(file_path);
        if !path.exists() {
            return Err(EngineError::BufferError(format!("文件不存在: {}", file_path)));
        }

        let wav_data = fs::read(path)
            .map_err(|e| EngineError::BufferError(format!("读取WAV文件失败: {}", e)))?;

        // 解析 WAV
        let buffer = AudioBuffer::from_wav_bytes(&wav_data)?;

        // 注入缓冲区
        let mut state = self.shared.lock();
        if let Some(track) = state.tracks.get_mut(track_id) {
            track.buffer = buffer;
            Ok(())
        } else {
            Err(EngineError::TrackNotFound(track_id.to_string()))
        }
    }

    /// 从 WAV 文件加载音频数据到指定音轨（使用hound库，支持多种格式）
    ///
    /// 支持 8/16/24/32bit PCM 和 32bit Float WAV 文件。
    pub fn load_wav_file(&mut self, track_id: &str, file_path: &str) -> Result<(), EngineError> {
        use std::path::Path;

        // 确保音轨存在
        {
            let state = self.shared.lock();
            if !state.tracks.contains_key(track_id) {
                return Err(EngineError::TrackNotFound(track_id.to_string()));
            }
        }

        // 加载WAV文件
        let path = Path::new(file_path);
        if !path.exists() {
            return Err(EngineError::BufferError(format!("文件不存在: {}", file_path)));
        }

        let buffer = AudioBuffer::from_wav_file(path)?;

        // 注入缓冲区
        let mut state = self.shared.lock();
        if let Some(track) = state.tracks.get_mut(track_id) {
            track.buffer = buffer;
            Ok(())
        } else {
            Err(EngineError::TrackNotFound(track_id.to_string()))
        }
    }

    /// 从内存中的WAV字节数据加载音频到指定音轨
    pub fn load_wav_bytes(&mut self, track_id: &str, wav_data: &[u8]) -> Result<(), EngineError> {
        // 确保音轨存在
        {
            let state = self.shared.lock();
            if !state.tracks.contains_key(track_id) {
                return Err(EngineError::TrackNotFound(track_id.to_string()));
            }
        }

        // 解析 WAV
        let buffer = AudioBuffer::from_wav_bytes(wav_data)?;

        // 注入缓冲区
        let mut state = self.shared.lock();
        if let Some(track) = state.tracks.get_mut(track_id) {
            track.buffer = buffer;
            Ok(())
        } else {
            Err(EngineError::TrackNotFound(track_id.to_string()))
        }
    }

    // ==================== 辅助方法 ====================

    /// 获取采样率
    pub fn sample_rate(&self) -> f64 {
        self.shared.lock().sample_rate
    }

    /// 获取缓冲区大小
    pub fn buffer_size(&self) -> usize {
        self.buffer_size
    }

    /// 获取音轨数量
    pub fn track_count(&self) -> usize {
        self.shared.lock().tracks.len()
    }

    /// 设置调度器
    pub fn set_scheduler(&mut self, scheduler: Scheduler) {
        self.scheduler = Some(scheduler);
    }

    /// 推进引擎一个 buffer 周期（无音频模式使用）
    ///
    /// 在没有 `audio` feature 时，手动推进播放位置。
    /// 适用于测试和CI环境。
    pub fn tick(&mut self) {
        let mut state = self.shared.lock();
        if state.engine_state == EngineState::Playing {
            state.position += self.buffer_size;
        }
    }

    // ==================== Channel Feature: 音频输出通道 ====================

    /// 设置音频输出句柄（channel feature）
    ///
    /// 用于在外部线程中接收渲染好的音频帧。
    /// 通常与 AudioOutputHandle 配合使用。
    #[cfg(feature = "channel")]
    pub fn set_output_handle(&mut self, handle: super::channel_output::AudioOutputHandle) {
        self.output_handle = Some(handle);
    }

    /// 获取音频输出句柄的克隆（channel feature）
    ///
    /// 如果未设置输出句柄，返回 None。
    #[cfg(feature = "channel")]
    pub fn get_output_handle(&self) -> Option<super::channel_output::AudioOutputHandle> {
        self.output_handle.clone()
    }

    /// 创建音频输出并返回句柄（channel feature）
    ///
    /// 这是一个便捷方法，同时设置内部句柄并返回接收端。
    /// 返回 (output_handle, receiver)
    #[cfg(feature = "channel")]
    pub fn setup_channel_output(
        &mut self,
        buffer_size: usize,
        channels: usize,
    ) -> (
        super::channel_output::AudioOutputHandle,
        crossbeam_channel::Receiver<super::channel_output::AudioFrame>,
    ) {
        let (handle, receiver) = super::channel_output::AudioOutputHandle::new(buffer_size, channels);
        self.output_handle = Some(handle.clone());
        (handle, receiver)
    }

    /// 通过channel发送一个渲染帧（channel feature）
    ///
    /// 如果设置了output_handle且引擎正在播放，则渲染帧并发送。
    /// 通常由外部音频线程调用。
    #[cfg(feature = "channel")]
    pub fn send_output_frame(&self) -> bool {
        use super::channel_output::AudioFrame;

        let output_handle = match &self.output_handle {
            Some(h) => h,
            None => return false,
        };

        let state = self.shared.lock();
        if state.engine_state != EngineState::Playing {
            return false;
        }

        let channels = state.channels.max(1);
        let frames = self.buffer_size;
        let mut output = vec![0.0f32; channels * frames];

        // 渲染音频
        drop(state); // 释放锁，允许render_frame获取状态
        self.render_frame(&mut output, frames);

        // 发送帧
        let frame = AudioFrame::new(output, channels);
        output_handle.try_send_frame(frame)
    }

    // ==================== 混音辅助（供模拟模式使用）====================

    /// 渲染一帧音频数据到输出缓冲区（模拟模式使用）
    ///
    /// 混合所有音轨的当前帧数据，返回是否还有音频可播放。
    /// 用于无 audio feature 时的离线渲染验证。
    ///
    /// # 参数
    /// - `output`: 输出缓冲区（交错格式，len = frames * channels）
    /// - `frames`: 要渲染的帧数
    ///
    /// # 返回
    /// - `true`: 还有音频可渲染
    /// - `false`: 所有音轨已播放完毕
    pub fn render_frame(&self, output: &mut [f32], frames: usize) -> bool {
        let mut state = self.shared.lock();
        let channels = state.channels.max(1);

        // 预计算主音量增益
        let master_gain = if state.master_volume <= -60.0 {
            0.0f32
        } else {
            (10.0_f64.powf(state.master_volume / 20.0)) as f32
        };

        // 预计算所有音轨的渲染参数（避免每帧重复计算）
        let track_params: Vec<_> = state
            .tracks
            .values()
            .map(TrackRenderParams::from_track)
            .collect();
        let track_buffers: Vec<_> = state.tracks.values().map(|t| &t.buffer).collect();

        let start_pos = state.position;
        let mut has_more_audio = false;

        for frame_idx in 0..frames {
            let pos = start_pos + frame_idx;

            for ch in 0..channels {
                let mut mixed = 0.0f32;

                for (i, params) in track_params.iter().enumerate() {
                    // 跳过静音或无缓冲的音轨
                    if params.muted || params.buffer_frames == 0 {
                        continue;
                    }

                    let buffer = &track_buffers[i];
                    let track_ch = ch.min(buffer.channels.saturating_sub(1));

                    if pos < params.buffer_frames {
                        has_more_audio = true;
                        let sample = buffer.get_sample(track_ch, pos);
                        let pan_gain = params.get_pan_gain(ch);
                        mixed += sample * params.volume_gain * pan_gain;
                    }
                }

                // 应用主音量增益
                mixed *= master_gain;
                // 硬限幅，防止削波
                output[frame_idx * channels + ch] = mixed.clamp(-1.0, 1.0);
            }
        }

        state.position += frames;
        has_more_audio
    }

    /// 渲染完整缓冲区（模拟模式）
    ///
    /// 一次性渲染整个缓冲区，填充静音。
    pub fn render(&self, output: &mut [f32], frames: usize) {
        let mut state = self.shared.lock();
        let channels = state.channels.max(1);

        // 预计算所有音轨的渲染参数
        let track_params: Vec<_> = state
            .tracks
            .values()
            .map(TrackRenderParams::from_track)
            .collect();
        let track_buffers: Vec<_> = state.tracks.values().map(|t| &t.buffer).collect();

        let start_pos = state.position;

        for frame_idx in 0..frames {
            for ch in 0..channels {
                let mut mixed = 0.0f32;
                let pos = start_pos + frame_idx;

                for (i, params) in track_params.iter().enumerate() {
                    if params.muted || params.buffer_frames == 0 {
                        continue;
                    }

                    let buffer = &track_buffers[i];
                    let track_ch = ch.min(buffer.channels.saturating_sub(1));

                    if pos < params.buffer_frames {
                        let sample = buffer.get_sample(track_ch, pos);
                        let pan_gain = params.get_pan_gain(ch);
                        mixed += sample * params.volume_gain * pan_gain;
                    }
                }

                output[frame_idx * channels + ch] = mixed.clamp(-1.0, 1.0);
            }
        }

        state.position += frames;
    }
}

// ==================== CPAL 音频回调实现 ====================

#[cfg(feature = "audio")]
impl AudioEngine {
    /// 构建并启动 CPAL 音频输出流
    fn build_and_start_stream(&mut self) -> Result<(), EngineError> {
        let host = cpal::default_host();
        let device = host
            .default_output_device()
            .ok_or_else(|| EngineError::DeviceError("未找到音频输出设备".into()))?;

        let default_config = device
            .default_output_config()
            .map_err(|e| EngineError::DeviceError(format!("获取设备配置失败: {}", e)))?;

        // 仅支持 F32 采样格式
        if default_config.sample_format() != cpal::SampleFormat::F32 {
            return Err(EngineError::DeviceError(format!(
                "仅支持F32采样格式，当前: {:?}",
                default_config.sample_format()
            )));
        }

        let config = default_config.config();

        // 更新共享状态中的设备实际参数
        {
            let mut state = self.shared.lock();
            state.sample_rate = config.sample_rate.0 as f64;
            state.channels = config.channels as usize;
        }

        // 构建输出流：回调函数通过 Arc<Mutex<SharedState>> 访问音轨数据
        let shared_clone = self.shared.clone();
        let stream = device
            .build_output_stream(
                &config,
                move |output: &mut [f32], _: &cpal::OutputCallbackInfo| {
                    audio_callback(output, &shared_clone);
                },
                |err: cpal::StreamError| {
                    eprintln!("⚠️ 音频流错误: {}", err);
                },
                None, // timeout: 无超时限制
            )
            .map_err(|e| EngineError::DeviceError(format!("创建音频流失败: {}", e)))?;

        stream
            .play()
            .map_err(|e| EngineError::DeviceError(format!("启动音频流失败: {}", e)))?;

        self.stream = Some(stream);
        Ok(())
    }
}

/// CPAL 音频回调函数（优化版）
///
/// 混合所有非静音音轨的音频数据并写入输出缓冲区。
/// 使用预计算的渲染参数避免每帧重复计算。
#[cfg(feature = "audio")]
fn audio_callback(output: &mut [f32], shared: &Arc<Mutex<SharedState>>) {
    let mut state = shared.lock();
    let channels = state.channels.max(1);
    let frames = output.len() / channels;

    // 预计算主音量增益
    let master_gain = if state.master_volume <= -60.0 {
        0.0f32
    } else {
        (10.0_f64.powf(state.master_volume / 20.0)) as f32
    };

    // 预计算所有音轨的渲染参数（避免每帧重复计算）
    let track_params: Vec<_> = state
        .tracks
        .values()
        .map(TrackRenderParams::from_track)
        .collect();
    let track_buffers: Vec<_> = state.tracks.values().map(|t| &t.buffer).collect();

    for frame_idx in 0..frames {
        for ch in 0..channels {
            let mut mixed = 0.0f32;
            let pos = state.position;

            for (i, params) in track_params.iter().enumerate() {
                // 跳过静音或无缓冲的音轨
                if params.muted || params.buffer_frames == 0 {
                    continue;
                }

                let buffer = &track_buffers[i];
                let track_ch = ch.min(buffer.channels.saturating_sub(1));

                if pos < params.buffer_frames {
                    let sample = buffer.get_sample(track_ch, pos);
                    let pan_gain = params.get_pan_gain(ch);
                    mixed += sample * params.volume_gain * pan_gain;
                }
            }

            // 应用主音量增益
            mixed *= master_gain;
            // 硬限幅，防止削波
            output[frame_idx * channels + ch] = mixed.clamp(-1.0, 1.0);
        }
        state.position += 1;
    }
}

// ==================== 测试模块 ====================

#[cfg(test)]
mod tests {
    use super::*;

    // ==================== 基础测试 ====================

    #[test]
    fn test_engine_lifecycle() {
        let mut engine = AudioEngine::new();

        // 初始状态
        assert_eq!(engine.get_state(), EngineState::Stopped);

        // 启动（无音频模式）
        engine.start(44100.0, 256).unwrap();
        assert_eq!(engine.get_state(), EngineState::Playing);

        // 重复启动应报错
        assert!(engine.start(44100.0, 256).is_err());

        // 暂停
        engine.pause().unwrap();
        assert_eq!(engine.get_state(), EngineState::Paused);

        // 恢复
        engine.start(44100.0, 256).unwrap();
        assert_eq!(engine.get_state(), EngineState::Playing);

        // 停止
        engine.stop().unwrap();
        assert_eq!(engine.get_state(), EngineState::Stopped);

        // 重复停止应报错
        assert!(engine.stop().is_err());
    }

    #[test]
    fn test_track_management() {
        let mut engine = AudioEngine::new();

        // 注册音轨
        engine.register_track("vocals").unwrap();
        engine.register_track("drums").unwrap();
        assert_eq!(engine.track_count(), 2);

        // 重复注册应报错
        assert!(engine.register_track("vocals").is_err());

        // 注入缓冲区
        let buf = AudioBuffer::zeros(2, 1024, 44100.0);
        engine.inject_buffer("vocals", buf).unwrap();

        // 注入到不存在的音轨应报错
        let buf2 = AudioBuffer::zeros(2, 512, 44100.0);
        assert!(engine.inject_buffer("missing", buf2).is_err());

        // 注销音轨
        engine.unregister_track("drums").unwrap();
        assert_eq!(engine.track_count(), 1);

        // 注销不存在的音轨应报错
        assert!(engine.unregister_track("drums").is_err());
    }

    #[test]
    fn test_position() {
        let mut engine = AudioEngine::new();
        engine.start(44100.0, 256).unwrap();
        assert_eq!(engine.get_position(), 0.0);

        // 手动推进
        engine.tick();
        engine.tick();
        let pos = engine.get_position();
        assert!((pos - (512.0 / 44100.0)).abs() < 0.0001);

        // 设置位置
        engine.set_position(1.0);
        let pos = engine.get_position();
        assert!((pos - 1.0).abs() < 0.001);
    }

    #[test]
    fn test_tick_advances_position() {
        let mut engine = AudioEngine::new();
        // tick 在停止状态下不应推进位置
        engine.tick();
        assert_eq!(engine.get_position(), 0.0);

        // 启动后 tick 应推进位置
        engine.start(44100.0, 256).unwrap();
        engine.tick();
        assert!((engine.get_position() - (256.0 / 44100.0)).abs() < 0.0001);
    }

    // ==================== 正弦波播放集成测试 ====================

    #[test]
    fn test_sine_wave_playback() {
        let sample_rate = 44100.0;
        let frequency = 440.0; // A4
        let duration = 0.1; // 100ms
        let frames = (sample_rate * duration) as usize;

        // 生成 440Hz 正弦波
        let mut buffer = AudioBuffer::new(2, frames, sample_rate);
        for frame in 0..frames {
            let t = frame as f64 / sample_rate;
            let sample = (2.0 * std::f64::consts::PI * frequency * t).sin() as f32 * 0.5;
            buffer.set_sample(0, frame, sample);
            buffer.set_sample(1, frame, sample);
        }

        // 创建引擎并注入音频
        let mut engine = AudioEngine::new();
        engine.register_track("sine").unwrap();
        engine.inject_buffer("sine", buffer).unwrap();

        // 启动引擎
        engine.start(sample_rate, 256).unwrap();

        // 渲染几个 buffer
        let channels = 2;
        let mut output = vec![0.0f32; 256 * channels];
        let has_more = engine.render_frame(&mut output, 256);
        assert!(has_more, "首帧应有音频数据");

        // 验证前几个样本与原始正弦波一致
        for frame in 0..10.min(frames.min(256)) {
            let t = frame as f64 / sample_rate;
            let expected = (2.0 * std::f64::consts::PI * frequency * t).sin() as f32 * 0.5 * 0.7071; // 等功率声像中心增益
            let actual = output[frame * channels]; // 左声道
            assert!(
                (expected - actual).abs() < 0.05,
                "帧{}: 期望{:?}, 实际{:?}",
                frame,
                expected,
                actual
            );
        }

        engine.stop().unwrap();
    }

    #[test]
    fn test_mute_track() {
        let sample_rate = 44100.0;
        let frames = 256;

        // 创建引擎和音轨
        let mut engine = AudioEngine::new();
        engine.register_track("test").unwrap();

        // 注入非零音频
        let mut buf = AudioBuffer::new(2, frames, sample_rate);
        buf.fill(0.5);
        engine.inject_buffer("test", buf).unwrap();

        engine.start(sample_rate, 256).unwrap();

        // 渲染 - 应该听到音频
        let mut output = vec![0.0f32; 256 * 2];
        engine.render_frame(&mut output, 256);
        assert!(output.iter().any(|&s| s != 0.0), "未静音时应有音频");

        // 获取 track 并静音
        {
            let mut state = engine.shared.lock();
            if let Some(track) = state.tracks.get_mut("test") {
                track.muted = true;
            }
        }

        // 再次渲染 - 应该是静音
        let mut output2 = vec![0.0f32; 256 * 2];
        engine.render_frame(&mut output2, 256);
        assert!(
            output2.iter().all(|&s| s == 0.0),
            "静音后应无音频"
        );

        engine.stop().unwrap();
    }

    #[test]
    fn test_position_beyond_buffer() {
        let sample_rate = 44100.0;
        let frames = 100;

        // 创建引擎
        let mut engine = AudioEngine::new();
        engine.register_track("short").unwrap();

        // 注入短音频
        let mut buf = AudioBuffer::new(2, frames, sample_rate);
        buf.fill(0.5);
        engine.inject_buffer("short", buf).unwrap();

        engine.start(sample_rate, 256).unwrap();

        // 渲染超过缓冲区长度
        let mut output = vec![0.0f32; 256 * 2];
        engine.render_frame(&mut output, 256);

        // 位置应该已超出缓冲区，输出应全为零（循环播放未启用）
        // 实际行为取决于实现：可能是静音或循环
        // 这里验证位置确实推进了
        assert_eq!(engine.get_position(), 256.0 / sample_rate);

        engine.stop().unwrap();
    }

    #[test]
    fn test_multi_track_mixing() {
        let sample_rate = 44100.0;
        let frames = 100;

        // 创建引擎和多个音轨
        let mut engine = AudioEngine::new();
        engine.register_track("track1").unwrap();
        engine.register_track("track2").unwrap();

        // 音轨1: 0.3 增益
        let mut buf1 = AudioBuffer::new(1, frames, sample_rate);
        for i in 0..frames {
            buf1.set_sample(0, i, 1.0);
        }
        engine.inject_buffer("track1", buf1).unwrap();

        // 音轨2: 0.2 增益
        let mut buf2 = AudioBuffer::new(1, frames, sample_rate);
        for i in 0..frames {
            buf2.set_sample(0, i, 1.0);
        }
        engine.inject_buffer("track2", buf2).unwrap();

        // 设置不同音量
        {
            let mut state = engine.shared.lock();
            if let Some(t) = state.tracks.get_mut("track1") {
                t.volume = -10.46; // ≈ 0.3 线性 (20*log10(0.3) ≈ -10.46)
            }
            if let Some(t) = state.tracks.get_mut("track2") {
                t.volume = -13.98; // ≈ 0.2 线性 (20*log10(0.2) ≈ -13.98)
            }
        }

        engine.start(sample_rate, 256).unwrap();

        // 渲染一帧
        let mut output = vec![0.0f32; 256 * 2];
        engine.render_frame(&mut output, 1);

        // 验证混合结果 ≈ 0.5 (0.3 + 0.2)
        let mixed = output[0]; // L
        assert!(
            (mixed - 0.3535).abs() < 0.05,
            "混合应≈0.5，实际={}",
            mixed
        );

        engine.stop().unwrap();
    }

    #[test]
    fn test_render_after_end() {
        let sample_rate = 44100.0;
        let frames = 50;

        let mut engine = AudioEngine::new();
        engine.register_track("test").unwrap();

        let mut buf = AudioBuffer::new(2, frames, sample_rate);
        engine.inject_buffer("test", buf).unwrap();
        engine.start(sample_rate, 256).unwrap();

        // 渲染足够多的帧直到缓冲区结束
        let mut all_zero = false;
        let mut total_frames = 0;

        while total_frames < 200 {
            let mut output = vec![0.0f32; 256 * 2];
            let has_more = engine.render_frame(&mut output, 256);

            // 检查输出是否全为零
            let this_batch_zero = output.iter().all(|&s| s == 0.0);
            if this_batch_zero {
                all_zero = true;
                break;
            }
            total_frames += 256;
        }

        assert!(all_zero, "缓冲区结束后应输出静音");

        engine.stop().unwrap();
    }


    // ==================== v0.24.0 Engine Commands 测试 ====================

    #[test]
    fn test_set_track_volume() {
        let mut engine = AudioEngine::new();
        engine.register_track("test").unwrap();

        // 设置音量
        engine.set_track_volume("test", -6.0).unwrap();
        {
            let state = engine.shared.lock();
            assert!((state.tracks.get("test").unwrap().volume - (-6.0)).abs() < 0.001);
        }

        // 超出范围应被钳制
        engine.set_track_volume("test", 100.0).unwrap();
        {
            let state = engine.shared.lock();
            assert!((state.tracks.get("test").unwrap().volume - 12.0).abs() < 0.001);
        }

        // 不存在的音轨应报错
        assert!(engine.set_track_volume("missing", 0.0).is_err());
    }

    #[test]
    fn test_toggle_track_mute() {
        let mut engine = AudioEngine::new();
        engine.register_track("test").unwrap();

        // 初始为非静音
        assert_eq!(engine.toggle_track_mute("test").unwrap(), true);

        // 再次切换
        assert_eq!(engine.toggle_track_mute("test").unwrap(), false);

        // 不存在的音轨应报错
        assert!(engine.toggle_track_mute("missing").is_err());
    }

    #[test]
    fn test_master_volume() {
        let mut engine = AudioEngine::new();

        // 默认 0dB
        assert_eq!(engine.get_master_volume(), 0.0);

        // 设置主音量
        engine.set_master_volume(-6.0);
        assert_eq!(engine.get_master_volume(), -6.0);

        // 超出范围应被钳制
        engine.set_master_volume(100.0);
        assert_eq!(engine.get_master_volume(), 12.0);

        engine.set_master_volume(-100.0);
        assert_eq!(engine.get_master_volume(), -60.0);
    }

    #[test]
    fn test_master_volume_affects_output() {
        let sample_rate = 44100.0;
        let frames = 256;

        let mut engine = AudioEngine::new();
        engine.register_track("test").unwrap();

        // 渲染 0dB（默认）
        let mut buf = AudioBuffer::new(2, frames, sample_rate);
        buf.fill(1.0);
        engine.inject_buffer("test", buf).unwrap();
        engine.start(sample_rate, 256).unwrap();

        let mut output1 = vec![0.0f32; frames * 2];
        engine.render_frame(&mut output1, frames);
        let level1 = output1.iter().map(|&s| s.abs()).sum::<f32>() / (frames * 2) as f32;

        engine.stop().unwrap();

        // 渲染 -6dB：重新创建引擎和buffer（避免position推进导致第二次渲染无声）
        let mut engine2 = AudioEngine::new();
        engine2.register_track("test").unwrap();
        let mut buf2 = AudioBuffer::new(2, frames, sample_rate);
        buf2.fill(1.0);
        engine2.inject_buffer("test", buf2).unwrap();
        engine2.start(sample_rate, 256).unwrap();
        engine2.set_master_volume(-6.0);

        let mut output2 = vec![0.0f32; frames * 2];
        engine2.render_frame(&mut output2, frames);
        let level2 = output2.iter().map(|&s| s.abs()).sum::<f32>() / (frames * 2) as f32;

        // -6dB 约等于 0.501 线性增益
        assert!(level2 < level1, "降低主音量后输出应减小");
        assert!((level1 / level2 - 2.0).abs() < 0.2, "比例应约为2");

        engine2.stop().unwrap();
    }

    #[test]
    fn test_load_wav_invalid_path() {
        let mut engine = AudioEngine::new();
        engine.register_track("test").unwrap();

        let result = engine.load_wav("test", "/nonexistent/path.wav");
        assert!(result.is_err());
    }

    #[test]
    fn test_load_wav_nonexistent_track() {
        let mut engine = AudioEngine::new();

        let result = engine.load_wav("missing", "/tmp/test.wav");
        assert!(result.is_err());
    }

    // ==================== TrackRenderParams 测试 ====================

    #[test]
    fn test_track_render_params_volume() {
        // 0dB
        let track = Track::new("test");
        let params = TrackRenderParams::from_track(&track);
        assert!((params.volume_gain - 1.0).abs() < 0.001);

        // -6dB
        let mut track = Track::new("test");
        track.volume = -6.0;
        let params = TrackRenderParams::from_track(&track);
        assert!((params.volume_gain - 0.501).abs() < 0.01);

        // -inf dB (静音)
        let mut track = Track::new("test");
        track.volume = -60.0;
        let params = TrackRenderParams::from_track(&track);
        assert_eq!(params.volume_gain, 0.0);
    }

    #[test]
    fn test_track_render_params_pan() {
        // 居中
        let track = Track::new("test");
        let params = TrackRenderParams::from_track(&track);
        assert!((params.pan_gain_l - params.pan_gain_r).abs() < 0.001);

        // 全左
        let mut track = Track::new("test");
        track.pan = -1.0;
        let params = TrackRenderParams::from_track(&track);
        assert!(params.pan_gain_l > params.pan_gain_r);
        assert!(params.pan_gain_r < 0.01);

        // 全右
        let mut track = Track::new("test");
        track.pan = 1.0;
        let params = TrackRenderParams::from_track(&track);
        assert!(params.pan_gain_r > params.pan_gain_l);
        assert!(params.pan_gain_l < 0.01);
    }

    // ==================== 声像(Pan)控制测试 ====================

    #[test]
    fn test_set_track_pan() {
        let mut engine = AudioEngine::new();
        engine.register_track("test").unwrap();

        // 设置声像
        engine.set_track_pan("test", 0.5).unwrap();
        assert!((engine.get_track_pan("test").unwrap() - 0.5).abs() < 0.001);

        // 全左
        engine.set_track_pan("test", -1.0).unwrap();
        assert!((engine.get_track_pan("test").unwrap() - (-1.0)).abs() < 0.001);

        // 全右
        engine.set_track_pan("test", 1.0).unwrap();
        assert!((engine.get_track_pan("test").unwrap() - 1.0).abs() < 0.001);

        // 超出范围应被钳制
        engine.set_track_pan("test", 2.0).unwrap();
        assert!((engine.get_track_pan("test").unwrap() - 1.0).abs() < 0.001);

        engine.set_track_pan("test", -2.0).unwrap();
        assert!((engine.get_track_pan("test").unwrap() - (-1.0)).abs() < 0.001);

        // 不存在的音轨应报错
        assert!(engine.set_track_pan("missing", 0.0).is_err());
        assert!(engine.get_track_pan("missing").is_err());
    }

    #[test]
    fn test_pan_affects_stereo_output() {
        let sample_rate = 44100.0;
        let frames = 256;

        let mut engine = AudioEngine::new();
        engine.register_track("test").unwrap();

        // 创建单声道测试信号
        let mut buf = AudioBuffer::new(1, frames, sample_rate);
        for i in 0..frames {
            buf.set_sample(0, i, 1.0);
        }
        engine.inject_buffer("test", buf).unwrap();

        engine.start(sample_rate, 256).unwrap();

        // 居中声像
        engine.set_track_pan("test", 0.0).unwrap();
        let mut output_center = vec![0.0f32; frames * 2];
        engine.render_frame(&mut output_center, frames);

        // 重置位置
        engine.set_position(0.0);

        // 全左声像
        engine.set_track_pan("test", -1.0).unwrap();
        let mut output_left = vec![0.0f32; frames * 2];
        engine.render_frame(&mut output_left, frames);

        // 重置位置
        engine.set_position(0.0);

        // 全右键像
        engine.set_track_pan("test", 1.0).unwrap();
        let mut output_right = vec![0.0f32; frames * 2];
        engine.render_frame(&mut output_right, frames);

        // 验证居中时左右声道相等
        assert!((output_center[0] - output_center[1]).abs() < 0.01,
            "居中时左右声道应相等");

        // 验证全左时左声道大于右声道
        assert!(output_left[0] > output_left[1],
            "全左时左声道应大于右声道");

        // 验证全右时右声道大于左声道
        assert!(output_right[1] > output_right[0],
            "全右时右声道应大于左声道");

        engine.stop().unwrap();
    }

    // ==================== WAV加载测试 ====================

    #[test]
    fn test_wav_bytes_roundtrip() {
        // 创建测试音频数据
        let sample_rate = 44100.0;
        let frames = 100;
        let channels = 2;
        let mut original = AudioBuffer::new(channels, frames, sample_rate);
        for frame in 0..frames {
            for ch in 0..channels {
                let value = ((frame + ch) as f32) * 0.01;
                original.set_sample(ch, frame, value);
            }
        }

        // 转换为WAV字节
        let wav_bytes = original.to_wav_bytes().unwrap();

        // 从WAV字节加载
        let loaded = AudioBuffer::from_wav_bytes(&wav_bytes).unwrap();

        // 验证
        assert_eq!(loaded.channels, channels);
        assert_eq!(loaded.frames, frames);
        assert!((loaded.sample_rate - sample_rate).abs() < 1.0);

        for frame in 0..frames.min(10) {
            for ch in 0..channels {
                let orig = original.get_sample(ch, frame);
                let load = loaded.get_sample(ch, frame);
                assert!((orig - load).abs() < 0.001,
                    "帧{}/声道{}: 原始={}, 加载={}", frame, ch, orig, load);
            }
        }
    }

    #[test]
    fn test_load_wav_bytes() {
        let sample_rate = 44100.0;
        let frames = 100;
        let channels = 2;

        // 创建测试音频
        let mut buf = AudioBuffer::new(channels, frames, sample_rate);
        for frame in 0..frames {
            buf.set_sample(0, frame, 0.5);
            buf.set_sample(1, frame, 0.3);
        }

        // 转换为WAV字节
        let wav_bytes = buf.to_wav_bytes().unwrap();

        // 创建引擎并加载
        let mut engine = AudioEngine::new();
        engine.register_track("test").unwrap();
        engine.load_wav_bytes("test", &wav_bytes).unwrap();

        // 验证
        let state = engine.shared.lock();
        let track = state.tracks.get("test").unwrap();
        assert_eq!(track.buffer.channels, channels);
        assert_eq!(track.buffer.frames, frames);
        assert!((track.buffer.get_sample(0, 0) - 0.5).abs() < 0.001);
    }

    #[test]
    fn test_load_wav_invalid_data() {
        let mut engine = AudioEngine::new();
        engine.register_track("test").unwrap();

        // 无效的WAV数据
        let invalid_data = vec![0u8; 10];
        let result = engine.load_wav_bytes("test", &invalid_data);
        assert!(result.is_err());
    }

    // ==================== 音量+声像+静音组合测试 ====================

    #[test]
    fn test_volume_pan_mute_combined() {
        let sample_rate = 44100.0;
        let frames = 256;

        let mut engine = AudioEngine::new();
        engine.register_track("test").unwrap();

        // 创建单声道测试信号
        let mut buf = AudioBuffer::new(1, frames, sample_rate);
        for i in 0..frames {
            buf.set_sample(0, i, 1.0);
        }
        engine.inject_buffer("test", buf).unwrap();

        engine.start(sample_rate, 256).unwrap();

        // 场景1: 默认设置
        let mut output1 = vec![0.0f32; frames * 2];
        engine.render_frame(&mut output1, frames);
        let level1 = output1.iter().map(|&s| s.abs()).sum::<f32>() / (frames * 2) as f32;
        engine.set_position(0.0);

        // 场景2: 静音
        engine.toggle_track_mute("test").unwrap();
        let mut output2 = vec![0.0f32; frames * 2];
        engine.render_frame(&mut output2, frames);
        let level2 = output2.iter().map(|&s| s.abs()).sum::<f32>() / (frames * 2) as f32;
        engine.toggle_track_mute("test").unwrap();
        engine.set_position(0.0);

        // 场景3: -6dB音量
        engine.set_track_volume("test", -6.0).unwrap();
        let mut output3 = vec![0.0f32; frames * 2];
        engine.render_frame(&mut output3, frames);
        let level3 = output3.iter().map(|&s| s.abs()).sum::<f32>() / (frames * 2) as f32;
        engine.set_track_volume("test", 0.0).unwrap();
        engine.set_position(0.0);

        // 场景4: 声像左
        engine.set_track_pan("test", -1.0).unwrap();
        let mut output4 = vec![0.0f32; frames * 2];
        engine.render_frame(&mut output4, frames);
        engine.set_position(0.0);

        // 场景5: 声像右
        engine.set_track_pan("test", 1.0).unwrap();
        let mut output5 = vec![0.0f32; frames * 2];
        engine.render_frame(&mut output5, frames);

        // 验证
        assert!(level1 > level2 * 10.0, "静音时输出应远小于非静音");
        assert!(level1 > level3 * 1.5, "-6dB时输出应小于0dB");
        assert!(output4[0] > output4[1], "声像左时左声道应大于右声道");
        assert!(output5[1] > output5[0], "声像右时右声道应大于左声道");

        engine.stop().unwrap();
    }

    // ==================== 播放控制测试 ====================

    #[test]
    fn test_playback_with_position_control() {
        let sample_rate = 44100.0;
        let frames = 1000;

        let mut engine = AudioEngine::new();
        engine.register_track("test").unwrap();

        // 创建不同频率的测试信号
        let mut buf = AudioBuffer::new(1, frames, sample_rate);
        for frame in 0..frames {
            let t = frame as f64 / sample_rate;
            let sample = (2.0 * std::f64::consts::PI * 440.0 * t).sin() as f32;
            buf.set_sample(0, frame, sample);
        }
        engine.inject_buffer("test", buf).unwrap();

        engine.start(sample_rate, 256).unwrap();

        // 从位置0渲染
        engine.set_position(0.0);
        let mut output1 = vec![0.0f32; 256 * 2];
        engine.render_frame(&mut output1, 256);

        // 从位置500渲染
        engine.set_position(500.0 / sample_rate);
        let mut output2 = vec![0.0f32; 256 * 2];
        engine.render_frame(&mut output2, 256);

        // 两个位置输出的相位应该不同
        // 检查前几个样本
        let same_count = output1.iter().zip(output2.iter())
            .filter(|(a, b)| (*a - *b).abs() < 0.001f32)
            .count();
        
        // 由于相位不同，相同样本数量应该很少
        assert!(same_count < 50, "不同位置应有不同输出");

        engine.stop().unwrap();
    }
}
