//! 音频处理调度器
//!
//! 管理音频处理回调链，按注册顺序依次执行。
//! 可用于构建效果器链、音频分析管线等。

use crate::buffer::AudioBuffer;

/// 音频处理回调类型
///
/// 参数：(输入缓冲区, 输出缓冲区)
/// 回调应从输入读取数据，将处理结果写入输出。
pub type ProcessCallback = Box<dyn FnMut(&AudioBuffer, &mut AudioBuffer) + Send>;

/// 音频处理调度器
///
/// 管理音频处理回调链，按注册顺序依次执行。
/// 可用于构建效果器链（EQ → 压缩 → 混响等）或音频分析管线。
pub struct Scheduler {
    /// 处理回调列表
    callbacks: Vec<ProcessCallback>,
    /// 采样率
    sample_rate: f64,
    /// 缓冲区大小（帧数）
    buffer_size: usize,
}

impl Scheduler {
    /// 创建新的调度器
    pub fn new(sample_rate: f64, buffer_size: usize) -> Self {
        Self {
            callbacks: Vec::new(),
            sample_rate,
            buffer_size,
        }
    }

    /// 添加处理回调到链尾
    pub fn add_callback(&mut self, cb: ProcessCallback) {
        self.callbacks.push(cb);
    }

    /// 执行一轮音频处理
    ///
    /// 依次调用所有回调，将前一个回调的输出作为下一个的输入。
    pub fn process(&mut self, input: &AudioBuffer, output: &mut AudioBuffer) {
        for cb in &mut self.callbacks {
            cb(input, output);
        }
    }

    /// 获取采样率
    pub fn sample_rate(&self) -> f64 {
        self.sample_rate
    }

    /// 获取缓冲区大小
    pub fn buffer_size(&self) -> usize {
        self.buffer_size
    }

    /// 获取回调数量
    pub fn callback_count(&self) -> usize {
        self.callbacks.len()
    }

    /// 清除所有回调
    pub fn clear(&mut self) {
        self.callbacks.clear();
    }
}
