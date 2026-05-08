//! 公共类型定义

use serde::{Deserialize, Serialize};

/// 音频缓冲区 — 零拷贝处理的核心数据结构
/// channels: 声道数（1=单声道, 2=立体声）
/// frames: 每声道的采样帧数
/// data: 交错存储的浮点采样 [L0,R0,L1,R1,...]
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

    /// 获取指定声道的切片（非交错视图，拷贝）
    pub fn channel_data(&self, channel: usize) -> Vec<f64> {
        debug_assert!(channel < self.channels);
        self.data[channel * self.frames..(channel + 1) * self.frames].to_vec()
    }

    /// 填充静音
    pub fn clear(&mut self) {
        self.data.fill(0.0);
    }

    /// 缓冲区总采样数
    pub fn len(&self) -> usize {
        self.data.len()
    }

    pub fn is_empty(&self) -> bool {
        self.data.is_empty()
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
    pub value: f64,
    pub unit: String,
}

impl ParamInfo {
    /// 创建新参数
    pub fn new(id: &str, name: &str, min: f64, max: f64, default: f64, unit: &str) -> Self {
        Self {
            id: id.to_string(),
            name: name.to_string(),
            min,
            max,
            default,
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
                    if i > 0 { write!(f, ", ")?; }
                    write!(f, "{}", v)?;
                }
                write!(f, "]")
            }
            ScriptValue::Map(m) => {
                write!(f, "{{")?;
                for (i, (k, v)) in m.iter().enumerate() {
                    if i > 0 { write!(f, ", ")?; }
                    write!(f, "{:?}: {}", k, v)?;
                }
                write!(f, "}}")
            }
        }
    }
}
