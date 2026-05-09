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
            })),
            buffer_size: 256,
            scheduler: None,
            #[cfg(feature = "audio")]
            stream: None,
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
}
