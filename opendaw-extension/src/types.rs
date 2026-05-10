//! 公共类型定义

use serde::{Deserialize, Serialize};

/// 音频缓冲区 — 零拷贝处理的核心数据结构
///
/// # 存储格式
///
/// 非交错（planar）存储：每个声道连续存放
/// ```text
/// data = [L0, L1, L2, ..., R0, R1, R2, ...]
/// ```
/// channels: 声道数（1=单声道, 2=立体声）
/// frames: 每声道的采样帧数
#[derive(Clone, Debug)]
pub struct AudioBuffer {
    pub channels: usize,
    pub frames: usize,
    pub data: Vec<f64>,
}

impl AudioBuffer {
    /// 创建静音缓冲区
    pub fn new(channels: usize, frames: usize) -> Self {
        Self {
            channels,
            frames,
            data: vec![0.0; channels * frames],
        }
    }

    /// 获取指定声道和帧位置的采样值
    pub fn sample(&self, channel: usize, frame: usize) -> f64 {
        debug_assert!(channel < self.channels, "声道索引越界");
        debug_assert!(frame < self.frames, "帧索引越界");
        self.data[channel * self.frames + frame]
    }

    /// 设置指定声道和帧位置的采样值
    pub fn set_sample(&mut self, channel: usize, frame: usize, value: f64) {
        debug_assert!(channel < self.channels, "声道索引越界");
        debug_assert!(frame < self.frames, "帧索引越界");
        self.data[channel * self.frames + frame] = value;
    }

    /// 获取指定声道的切片（零拷贝，借用视图）
    ///
    /// 返回该声道所有帧的连续切片，无需拷贝。
    /// 适用于 DSP 读取操作。
    pub fn channel_slice(&self, channel: usize) -> &[f64] {
        debug_assert!(channel < self.channels, "声道索引越界");
        let start = channel * self.frames;
        let end = start + self.frames;
        &self.data[start..end]
    }

    /// 获取指定声道的可变切片（零拷贝，可变借用视图）
    ///
    /// 返回该声道所有帧的连续可变切片，无需拷贝。
    /// 适用于 DSP 写入操作。
    pub fn channel_slice_mut(&mut self, channel: usize) -> &mut [f64] {
        debug_assert!(channel < self.channels, "声道索引越界");
        let start = channel * self.frames;
        let end = start + self.frames;
        &mut self.data[start..end]
    }

    /// 获取指定声道的拷贝数据（向后兼容）
    pub fn channel_data(&self, channel: usize) -> Vec<f64> {
        debug_assert!(channel < self.channels);
        self.data[channel * self.frames..(channel + 1) * self.frames].to_vec()
    }

    /// 填充静音
    pub fn clear(&mut self) {
        self.data.fill(0.0);
    }

    /// 从另一个 AudioBuffer 复制数据（相同尺寸时零分配）
    ///
    /// 如果 src 和 self 尺寸一致，则纯内存拷贝无分配。
    /// 如果尺寸不同，自动调整 self 并拷贝。
    pub fn copy_from(&mut self, src: &AudioBuffer) {
        self.channels = src.channels;
        self.frames = src.frames;
        if self.data.len() != src.data.len() {
            self.data.resize(src.data.len(), 0.0);
        }
        self.data.copy_from_slice(&src.data);
    }

    /// 缓冲区总采样数
    pub fn len(&self) -> usize {
        self.data.len()
    }

    pub fn is_empty(&self) -> bool {
        self.data.is_empty()
    }

    /// 从交错数据创建（用于 WAV 等外部数据源）
    ///
    /// interleaved: [L0, R0, L1, R1, ...] → planar [L0, L1, ..., R0, R1, ...]
    pub fn from_interleaved(interleaved: &[f64], channels: usize) -> Self {
        let frames = if channels > 0 {
            interleaved.len() / channels
        } else {
            0
        };
        let mut buf = Self::new(channels, frames);
        for (i, &sample) in interleaved.iter().enumerate() {
            let ch = i % channels;
            let frame = i / channels;
            buf.data[ch * frames + frame] = sample;
        }
        buf
    }

    /// 转换为交错数据（用于 WAV 输出等）
    ///
    /// planar [L0, L1, ..., R0, R1, ...] → interleaved [L0, R0, L1, R1, ...]
    pub fn to_interleaved(&self) -> Vec<f64> {
        let mut result = Vec::with_capacity(self.data.len());
        for frame in 0..self.frames {
            for ch in 0..self.channels {
                result.push(self.data[ch * self.frames + frame]);
            }
        }
        result
    }
}

/// 插件类型
#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub enum PluginType {
    /// 效果器（增益、EQ、压缩等）
    Effect,
    /// 虚拟乐器（合成器、采样器等）
    Instrument,
    /// 分析器（频谱、响度等）
    Analyzer,
    /// MIDI处理器
    MidiProcessor,
}

/// 参数信息
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct ParamInfo {
    pub id: String,
    pub name: String,
    pub min: f64,
    pub max: f64,
    pub default: f64,
    /// 参数步进值（UI步长），0.0表示连续参数
    #[serde(default)]
    pub step: f64,
    pub value: f64,
    pub unit: String,
}

impl ParamInfo {
    /// 创建新参数（step默认0.0，表示连续参数）
    pub fn new(id: &str, name: &str, min: f64, max: f64, default: f64, unit: &str) -> Self {
        Self {
            id: id.to_string(),
            name: name.to_string(),
            min,
            max,
            default,
            step: 0.0,
            value: default,
            unit: unit.to_string(),
        }
    }

    /// 创建带步进值的参数
    pub fn with_step(
        id: &str,
        name: &str,
        min: f64,
        max: f64,
        default: f64,
        step: f64,
        unit: &str,
    ) -> Self {
        Self {
            id: id.to_string(),
            name: name.to_string(),
            min,
            max,
            default,
            step,
            value: default,
            unit: unit.to_string(),
        }
    }

    /// 将值钳位到合法范围
    pub fn clamp_value(&self, v: f64) -> f64 {
        v.clamp(self.min, self.max)
    }
}

/// 模型输入
#[derive(Clone, Debug)]
pub struct ModelInput {
    /// 输入特征向量
    pub features: Vec<f64>,
    /// 可选的音频数据
    pub audio: Option<AudioBuffer>,
    /// 可选的文本提示
    pub prompt: Option<String>,
    /// 附加元数据
    pub metadata: std::collections::HashMap<String, String>,
}

impl ModelInput {
    pub fn from_features(features: Vec<f64>) -> Self {
        Self {
            features,
            audio: None,
            prompt: None,
            metadata: std::collections::HashMap::new(),
        }
    }

    pub fn with_prompt(mut self, prompt: &str) -> Self {
        self.prompt = Some(prompt.to_string());
        self
    }

    pub fn with_audio(mut self, audio: AudioBuffer) -> Self {
        self.audio = Some(audio);
        self
    }
}

/// 模型输出
#[derive(Clone, Debug)]
pub struct ModelOutput {
    /// 输出特征向量
    pub features: Vec<f64>,
    /// 可选的生成音频
    pub audio: Option<AudioBuffer>,
    /// 可选的文本结果
    pub text: Option<String>,
    /// 置信度（0.0~1.0）
    pub confidence: f64,
}

impl ModelOutput {
    pub fn from_features(features: Vec<f64>) -> Self {
        Self {
            features,
            audio: None,
            text: None,
            confidence: 1.0,
        }
    }

    pub fn from_text(text: &str) -> Self {
        Self {
            features: vec![],
            audio: None,
            text: Some(text.to_string()),
            confidence: 1.0,
        }
    }
}

/// 脚本值 — 脚本引擎与Rust之间的通用值类型
#[derive(Clone, Debug)]
pub enum ScriptValue {
    Null,
    Bool(bool),
    Int(i64),
    Float(f64),
    Str(String),
    Array(Vec<ScriptValue>),
    Map(Vec<(String, ScriptValue)>),
}

impl ScriptValue {
    pub fn as_float(&self) -> Option<f64> {
        match self {
            ScriptValue::Float(f) => Some(*f),
            ScriptValue::Int(i) => Some(*i as f64),
            _ => None,
        }
    }

    pub fn as_str(&self) -> Option<&str> {
        match self {
            ScriptValue::Str(s) => Some(s),
            _ => None,
        }
    }

    pub fn as_bool(&self) -> Option<bool> {
        match self {
            ScriptValue::Bool(b) => Some(*b),
            _ => None,
        }
    }
}

impl std::fmt::Display for ScriptValue {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            ScriptValue::Null => write!(f, "null"),
            ScriptValue::Bool(b) => write!(f, "{}", b),
            ScriptValue::Int(i) => write!(f, "{}", i),
            ScriptValue::Float(v) => write!(f, "{}", v),
            ScriptValue::Str(s) => write!(f, "{:?}", s),
            ScriptValue::Array(a) => {
                write!(f, "[")?;
                for (i, v) in a.iter().enumerate() {
                    if i > 0 {
                        write!(f, ", ")?;
                    }
                    write!(f, "{}", v)?;
                }
                write!(f, "]")
            }
            ScriptValue::Map(m) => {
                write!(f, "{{")?;
                for (i, (k, v)) in m.iter().enumerate() {
                    if i > 0 {
                        write!(f, ", ")?;
                    }
                    write!(f, "{:?}: {}", k, v)?;
                }
                write!(f, "}}")
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_audio_buffer_channel_slice() {
        let mut buf = AudioBuffer::new(2, 4);
        // 填充: channel 0 = [1,2,3,4], channel 1 = [5,6,7,8]
        buf.data = vec![1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0];

        // 零拷贝读取
        assert_eq!(buf.channel_slice(0), &[1.0, 2.0, 3.0, 4.0]);
        assert_eq!(buf.channel_slice(1), &[5.0, 6.0, 7.0, 8.0]);

        // 零拷贝写入
        buf.channel_slice_mut(0)[0] = 99.0;
        assert_eq!(buf.sample(0, 0), 99.0);
    }

    #[test]
    fn test_audio_buffer_copy_from() {
        let src = AudioBuffer::new(2, 4);
        let mut dst = AudioBuffer::new(2, 2);
        dst.copy_from(&src);
        assert_eq!(dst.channels, 2);
        assert_eq!(dst.frames, 4);
        assert_eq!(dst.data.len(), 8);
    }

    #[test]
    fn test_audio_buffer_interleaved() {
        // Planar: [1,2,3,4, 5,6,7,8] (ch0=1,2,3,4 ch1=5,6,7,8)
        let mut buf = AudioBuffer::new(2, 4);
        buf.data = vec![1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0];

        let interleaved = buf.to_interleaved();
        assert_eq!(interleaved, vec![1.0, 5.0, 2.0, 6.0, 3.0, 7.0, 4.0, 8.0]);

        let roundtrip = AudioBuffer::from_interleaved(&interleaved, 2);
        assert_eq!(roundtrip.data, buf.data);
    }

    #[test]
    fn test_plugin_type_variants() {
        assert_ne!(PluginType::Effect, PluginType::Instrument);
        assert_ne!(PluginType::Analyzer, PluginType::MidiProcessor);
    }
}
