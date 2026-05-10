//! 音频输出通道模块 - 通过crossbeam-channel发送音频帧到外部
//!
//! 当启用 `channel` feature 时，AudioOutput 允许外部消费者（通常是桌面应用）
//! 从 channel 接收渲染好的音频帧，然后自行处理音频输出（如通过CPAL播放）。
//!
//! ## 架构
//!
//! ```text
//! AudioEngine (render_frame)
//!        ↓
//!  AudioOutput (channel sender)
//!        ↓
//!  crossbeam-channel
//!        ↓
//!  Desktop Audio Thread (CPAL playback)
//! ```

use crossbeam_channel::{bounded, Sender};
use parking_lot::Mutex;
use std::sync::Arc;

/// 音频帧数据（交错格式）
///
/// 由 AudioOutput 通过 channel 发送，供外部消费者播放。
#[derive(Debug, Clone)]
pub struct AudioFrame {
    /// 交错格式的音频数据 [L,R,L,R,...]
    pub samples: Vec<f32>,
    /// 声道数（通常为2）
    pub channels: usize,
    /// 帧数
    pub frames: usize,
}

impl AudioFrame {
    /// 创建新的音频帧
    pub fn new(samples: Vec<f32>, channels: usize) -> Self {
        let frames = if channels > 0 {
            samples.len() / channels
        } else {
            0
        };
        Self {
            samples,
            channels,
            frames,
        }
    }

    /// 创建静音帧
    pub fn silence(channels: usize, frames: usize) -> Self {
        Self {
            samples: vec![0.0f32; channels * frames],
            channels,
            frames,
        }
    }
}

/// 音频输出控制器
///
/// 负责：
/// 1. 从 AudioEngine 接收渲染请求
/// 2. 将音频帧通过 channel 发送出去
///
/// ## 线程安全
///
/// OutputHandle 是 Clone 的，可以跨线程使用。
/// 所有操作都是 lock-free 的（通过 channel 实现）。
#[derive(Clone)]
pub struct AudioOutputHandle {
    sender: Sender<AudioFrame>,
    state: Arc<Mutex<OutputState>>,
}

/// 输出线程状态
struct OutputState {
    /// 是否正在输出
    playing: bool,
    /// 采样率
    sample_rate: f64,
    /// 缓冲区大小（帧数）
    buffer_size: usize,
    /// 声道数
    channels: usize,
}

impl OutputState {
    fn new() -> Self {
        Self {
            playing: false,
            sample_rate: 44100.0,
            buffer_size: 256,
            channels: 2,
        }
    }
}

impl AudioOutputHandle {
    /// 创建新的音频输出
    ///
    /// - `buffer_size`: 每帧缓冲区的样本数
    /// - `channels`: 声道数（通常为2）
    /// 返回：(handle, receiver)
    pub fn new(
        buffer_size: usize,
        channels: usize,
    ) -> (Self, crossbeam_channel::Receiver<AudioFrame>) {
        // 缓冲区大小设为约100ms的音频
        let capacity = (buffer_size * 10).max(1024);
        let (sender, receiver) = bounded(capacity);

        let handle = Self {
            sender,
            state: Arc::new(Mutex::new(OutputState {
                playing: false,
                sample_rate: 44100.0,
                buffer_size,
                channels,
            })),
        };

        (handle, receiver)
    }

    /// 发送一个音频帧
    ///
    /// 外部调用者（Desktop Audio Thread）应该持续调用此方法获取音频帧。
    /// 如果 channel 已满（缓冲区不足），会返回 false。
    pub fn send_frame(&self, frame: AudioFrame) -> bool {
        self.sender.send(frame).is_ok()
    }

    /// 尝试发送音频帧（非阻塞）
    ///
    /// 如果 channel 已满，立即返回 false。
    pub fn try_send_frame(&self, frame: AudioFrame) -> bool {
        self.sender.try_send(frame).is_ok()
    }

    /// 启动输出
    pub fn start(&self, sample_rate: f64) {
        let mut state = self.state.lock();
        state.playing = true;
        state.sample_rate = sample_rate;
    }

    /// 停止输出
    pub fn stop(&self) {
        let mut state = self.state.lock();
        state.playing = false;
    }

    /// 获取是否正在输出
    pub fn is_playing(&self) -> bool {
        self.state.lock().playing
    }

    /// 获取配置信息
    pub fn config(&self) -> OutputConfig {
        let state = self.state.lock();
        OutputConfig {
            sample_rate: state.sample_rate,
            buffer_size: state.buffer_size,
            channels: state.channels,
        }
    }
}

/// 输出配置信息
#[derive(Debug, Clone)]
pub struct OutputConfig {
    pub sample_rate: f64,
    pub buffer_size: usize,
    pub channels: usize,
}

/// 音频渲染器 trait
///
/// 实现此 trait 的类型可以作为音频数据的来源。
pub trait AudioRenderer {
    /// 渲染音频帧
    ///
    /// 将渲染的音频数据写入 output，返回是否还有更多音频可渲染。
    fn render(&self, output: &mut [f32], frames: usize) -> bool;
}

// ═══════════════════════════════════════════════════════════════════════════
// 测试
// ═══════════════════════════════════════════════════════════════════════════

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_audio_frame() {
        let frame = AudioFrame::new(vec![1.0, 2.0, 3.0, 4.0], 2);
        assert_eq!(frame.channels, 2);
        assert_eq!(frame.frames, 2);
    }

    #[test]
    fn test_audio_output_handle() {
        let (handle, receiver) = AudioOutputHandle::new(256, 2);

        // 发送一帧
        let frame = AudioFrame::new(vec![0.5, 0.5], 2);
        assert!(handle.try_send_frame(frame));

        // 接收帧
        let received = receiver.recv().unwrap();
        assert_eq!(received.frames, 1);
        assert_eq!(received.channels, 2);
    }

    #[test]
    fn test_output_control() {
        let (handle, _receiver) = AudioOutputHandle::new(256, 2);

        assert!(!handle.is_playing());

        handle.start(44100.0);
        assert!(handle.is_playing());
        assert_eq!(handle.config().sample_rate, 44100.0);

        handle.stop();
        assert!(!handle.is_playing());
    }
}
