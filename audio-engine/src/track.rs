//! 音轨定义
//!
//! Track 是音频引擎的基本单元，每个音轨拥有独立的缓冲区、音量、声像等参数。

use crate::buffer::AudioBuffer;

/// 音轨 - 音频引擎的基本单元
#[derive(Clone, Debug)]
pub struct Track {
    /// 音轨唯一标识
    pub id: String,
    /// 音轨名称（可不同于id，用于显示）
    pub name: String,
    /// 音量（dB），0dB = 原始音量
    pub volume: f64,
    /// 声像（-1.0全左 ~ 0.0居中 ~ 1.0全右）
    pub pan: f64,
    /// 是否静音
    pub muted: bool,
    /// 是否独奏
    pub solo: bool,
    /// 声道数（1=单声道, 2=立体声）
    pub channels: usize,
    /// 音频缓冲区
    pub buffer: AudioBuffer,
}

impl Track {
    /// 创建新的音轨（默认立体声, 44100Hz）
    pub fn new(id: &str) -> Self {
        Self {
            id: id.to_string(),
            name: id.to_string(),
            volume: 0.0,
            pan: 0.0,
            muted: false,
            solo: false,
            channels: 2,
            buffer: AudioBuffer::zeros(2, 0, 44100.0),
        }
    }

    /// 创建指定声道数和采样率的音轨
    pub fn with_channels(id: &str, channels: usize, sample_rate: f64) -> Self {
        Self {
            id: id.to_string(),
            name: id.to_string(),
            volume: 0.0,
            pan: 0.0,
            muted: false,
            solo: false,
            channels,
            buffer: AudioBuffer::zeros(channels, 0, sample_rate),
        }
    }

    /// 获取音轨时长（秒）
    pub fn duration(&self) -> f64 {
        if self.sample_rate() > 0.0 {
            self.buffer.frames as f64 / self.sample_rate()
        } else {
            0.0
        }
    }

    /// 获取采样率
    pub fn sample_rate(&self) -> f64 {
        self.buffer.sample_rate
    }

    /// 设置音量（dB）
    pub fn set_volume(&mut self, volume_db: f64) {
        self.volume = volume_db;
    }

    /// 设置声像
    pub fn set_pan(&mut self, pan: f64) {
        self.pan = pan.clamp(-1.0, 1.0);
    }

    /// 切换静音
    pub fn toggle_mute(&mut self) {
        self.muted = !self.muted;
    }

    /// 切换独奏
    pub fn toggle_solo(&mut self) {
        self.solo = !self.solo;
    }
}
