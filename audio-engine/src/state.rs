//! 引擎状态与错误定义

use thiserror::Error;

/// 引擎运行状态
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum EngineState {
    /// 已停止
    Stopped,
    /// 播放中
    Playing,
    /// 已暂停
    Paused,
    /// 录音中
    Recording,
}

impl Default for EngineState {
    fn default() -> Self {
        Self::Stopped
    }
}

/// 引擎错误类型
#[derive(Error, Debug)]
pub enum EngineError {
    #[error("引擎未启动")]
    NotStarted,
    #[error("引擎已在运行")]
    AlreadyRunning,
    #[error("音轨未找到: {0}")]
    TrackNotFound(String),
    #[error("音轨已存在: {0}")]
    TrackAlreadyExists(String),
    #[error("无效参数: {0}")]
    InvalidParameter(String),
    #[cfg(feature = "audio")]
    #[error("音频设备错误: {0}")]
    DeviceError(String),
    #[error("缓冲区错误: {0}")]
    BufferError(String),
    #[error("WAV格式错误: {0}")]
    WavFormatError(String),
}
