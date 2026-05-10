//! 音频缓冲区与环形缓冲区
//!
//! AudioBuffer: 平面格式存储的音频数据（每声道连续存储）
//! RingBuffer: 无锁SPSC环形缓冲区，用于实时音频线程间数据传输

use std::cell::UnsafeCell;
use std::path::Path;
use std::sync::atomic::{AtomicUsize, Ordering};

use crate::state::EngineError;

/// 音频缓冲区 - 平面格式存储
///
/// 内部布局：[ch0_s0, ch0_s1, ..., ch1_s0, ch1_s1, ...]
/// 每个声道占 `frames` 个连续样本，便于声道级别的批量操作。
#[derive(Clone, Debug)]
pub struct AudioBuffer {
    /// 声道数（1=单声道, 2=立体声）
    pub channels: usize,
    /// 每声道帧数
    pub frames: usize,
    /// 采样率
    pub sample_rate: f64,
    /// 音频数据（平面格式：声道0全部帧 → 声道1全部帧 → ...）
    data: Vec<f32>,
}

impl AudioBuffer {
    /// 创建新的音频缓冲区，数据初始化为零
    pub fn new(channels: usize, frames: usize, sample_rate: f64) -> Self {
        Self {
            channels,
            frames,
            sample_rate,
            data: vec![0.0f32; channels * frames],
        }
    }

    /// 创建全零缓冲区（与 new 相同，语义更明确）
    pub fn zeros(channels: usize, frames: usize, sample_rate: f64) -> Self {
        Self::new(channels, frames, sample_rate)
    }

    /// 获取指定声道和帧的样本值
    pub fn get_sample(&self, channel: usize, frame: usize) -> f32 {
        debug_assert!(channel < self.channels, "声道索引越界");
        debug_assert!(frame < self.frames, "帧索引越界");
        self.data[channel * self.frames + frame]
    }

    /// 设置指定声道和帧的样本值
    pub fn set_sample(&mut self, channel: usize, frame: usize, value: f32) {
        debug_assert!(channel < self.channels, "声道索引越界");
        debug_assert!(frame < self.frames, "帧索引越界");
        self.data[channel * self.frames + frame] = value;
    }

    /// 按线性索引获取样本值
    ///
    /// 索引按平面格式排列：先声道0的所有帧，再声道1的所有帧...
    pub fn get(&self, index: usize) -> Option<f32> {
        self.data.get(index).copied()
    }

    /// 按线性索引设置样本值
    ///
    /// 索引按平面格式排列：先声道0的所有帧，再声道1的所有帧...
    pub fn set(&mut self, index: usize, value: f32) {
        if index < self.data.len() {
            self.data[index] = value;
        }
    }
    /// 获取指定声道的数据切片（平面格式）
    pub fn channel(&self, channel: usize) -> &[f32] {
        debug_assert!(channel < self.channels, "声道索引越界");
        let start = channel * self.frames;
        &self.data[start..start + self.frames]
    }

    /// 获取指定声道的可变数据切片（平面格式）
    pub fn channel_mut(&mut self, channel: usize) -> &mut [f32] {
        debug_assert!(channel < self.channels, "声道索引越界");
        let start = channel * self.frames;
        &mut self.data[start..start + self.frames]
    }

    /// 从交错格式数据创建缓冲区
    ///
    /// 交错格式：[L0, R0, L1, R1, ...]（常见于WAV文件、音频API）
    pub fn from_interleaved(data: &[f32], channels: usize, sample_rate: f64) -> Self {
        if channels == 0 || data.is_empty() {
            return Self::new(channels, 0, sample_rate);
        }
        let frames = data.len() / channels;
        let mut buf = Self::new(channels, frames, sample_rate);
        for frame in 0..frames {
            for ch in 0..channels {
                buf.data[ch * frames + frame] = data[frame * channels + ch];
            }
        }
        buf
    }

    /// 转换为交错格式
    ///
    /// 输出：[L0, R0, L1, R1, ...]
    pub fn to_interleaved(&self) -> Vec<f32> {
        if self.frames == 0 || self.channels == 0 {
            return Vec::new();
        }
        let mut out = vec![0.0f32; self.channels * self.frames];
        for frame in 0..self.frames {
            for ch in 0..self.channels {
                out[frame * self.channels + ch] = self.data[ch * self.frames + frame];
            }
        }
        out
    }

    /// 编码为 WAV 字节数据（16bit PCM）
    ///
    /// 手写简单WAV编码器，无需外部依赖。
    /// 输出格式：RIFF/WAVE, PCM 16bit, 交错格式。
    pub fn to_wav_bytes(&self) -> Result<Vec<u8>, EngineError> {
        if self.channels == 0 || self.frames == 0 {
            return Err(EngineError::WavFormatError("空缓冲区，无法生成WAV".into()));
        }
        let interleaved = self.to_interleaved();
        let num_samples = interleaved.len();
        let data_size = num_samples * 2; // 16bit = 2字节/样本
        let file_size = 44 + data_size; // WAV头44字节 + 数据

        let mut wav = Vec::with_capacity(file_size);

        // --- RIFF 头 ---
        wav.extend_from_slice(b"RIFF");
        wav.extend_from_slice(&(file_size as u32 - 8).to_le_bytes()); // 文件大小 - 8
        wav.extend_from_slice(b"WAVE");

        // --- fmt 子块 ---
        wav.extend_from_slice(b"fmt ");
        wav.extend_from_slice(&16u32.to_le_bytes()); // 子块大小（PCM固定16）
        wav.extend_from_slice(&1u16.to_le_bytes()); // 音频格式（1=PCM）
        wav.extend_from_slice(&(self.channels as u16).to_le_bytes()); // 声道数
        wav.extend_from_slice(&(self.sample_rate as u32).to_le_bytes()); // 采样率
        let byte_rate = self.sample_rate as u32 * self.channels as u32 * 2; // 字节率
        wav.extend_from_slice(&byte_rate.to_le_bytes());
        let block_align = self.channels as u16 * 2; // 块对齐
        wav.extend_from_slice(&block_align.to_le_bytes());
        wav.extend_from_slice(&16u16.to_le_bytes()); // 位深度

        // --- data 子块 ---
        wav.extend_from_slice(b"data");
        wav.extend_from_slice(&(data_size as u32).to_le_bytes());

        // 16bit 有符号 PCM 数据
        for sample in &interleaved {
            let clamped = sample.clamp(-1.0, 1.0);
            let int_sample = (clamped * 32767.0) as i16;
            wav.extend_from_slice(&int_sample.to_le_bytes());
        }

        Ok(wav)
    }

    /// 从 WAV 字节数据解码（16bit PCM）
    ///
    /// 手写简单WAV解码器，仅支持PCM 16bit格式。
    pub fn from_wav_bytes(data: &[u8]) -> Result<Self, EngineError> {
        if data.len() < 44 {
            return Err(EngineError::WavFormatError(
                "数据太短，不是有效WAV文件".into(),
            ));
        }

        // 验证 RIFF 头
        if &data[0..4] != b"RIFF" || &data[8..12] != b"WAVE" {
            return Err(EngineError::WavFormatError("无效的WAV文件头".into()));
        }

        // 解析子块
        let mut offset = 12;
        let mut channels: u16 = 0;
        let mut sample_rate: u32 = 0;
        let mut bits_per_sample: u16 = 0;
        let mut audio_format: u16 = 0;
        let mut data_offset: usize = 0;
        let mut data_size: usize = 0;

        while offset + 8 <= data.len() {
            let chunk_id = &data[offset..offset + 4];
            let chunk_size = u32::from_le_bytes(
                data[offset + 4..offset + 8]
                    .try_into()
                    .map_err(|_| EngineError::WavFormatError("解析块大小失败".into()))?,
            ) as usize;

            if chunk_id == b"fmt " {
                if offset + 24 > data.len() {
                    return Err(EngineError::WavFormatError("fmt块数据不完整".into()));
                }
                audio_format =
                    u16::from_le_bytes(data[offset + 8..offset + 10].try_into().unwrap());
                channels = u16::from_le_bytes(data[offset + 10..offset + 12].try_into().unwrap());
                sample_rate =
                    u32::from_le_bytes(data[offset + 12..offset + 16].try_into().unwrap());
                bits_per_sample =
                    u16::from_le_bytes(data[offset + 22..offset + 24].try_into().unwrap());
            } else if chunk_id == b"data" {
                data_offset = offset + 8;
                data_size = chunk_size;
                break;
            }

            offset += 8 + chunk_size;
            // WAV块按2字节对齐
            if chunk_size % 2 != 0 {
                offset += 1;
            }
        }

        if audio_format != 1 {
            return Err(EngineError::WavFormatError(format!(
                "仅支持PCM格式(1)，当前格式: {}",
                audio_format
            )));
        }
        if bits_per_sample != 16 {
            return Err(EngineError::WavFormatError(format!(
                "仅支持16bit位深，当前位深: {}",
                bits_per_sample
            )));
        }
        if channels == 0 {
            return Err(EngineError::WavFormatError("声道数为0".into()));
        }

        let bytes_per_sample = (bits_per_sample / 8) as usize;
        let num_samples = data_size / bytes_per_sample;

        // 解码 16bit PCM 样本
        let mut samples = Vec::with_capacity(num_samples);
        for i in 0..num_samples {
            let byte_offset = data_offset + i * bytes_per_sample;
            if byte_offset + 2 > data.len() {
                break;
            }
            let int_sample =
                i16::from_le_bytes(data[byte_offset..byte_offset + 2].try_into().unwrap());
            samples.push(int_sample as f32 / 32767.0);
        }

        Ok(Self::from_interleaved(
            &samples,
            channels as usize,
            sample_rate as f64,
        ))
    }

    /// 从WAV文件加载（使用hound库，支持多种格式）
    ///
    /// 支持:
    /// - 8/16/24/32bit PCM
    /// - 32bit IEEE Float
    /// - 单声道和立体声
    pub fn from_wav_file(path: &Path) -> Result<Self, EngineError> {
        let reader = hound::WavReader::open(path)
            .map_err(|e| EngineError::WavFormatError(format!("无法打开WAV文件: {}", e)))?;

        let spec = reader.spec();

        // 检查声道数
        if spec.channels == 0 || spec.channels > 2 {
            return Err(EngineError::WavFormatError(format!(
                "不支持的声道数: {}（仅支持1或2）",
                spec.channels
            )));
        }

        let sample_rate = spec.sample_rate as f64;
        let channels = spec.channels as usize;

        // 根据位深读取样本
        let samples: Vec<f32> = match spec.sample_format {
            hound::SampleFormat::Int => {
                let reader: hound::WavReader<_> = reader.into();
                match spec.bits_per_sample {
                    8 => reader
                        .into_samples::<i8>()
                        .filter_map(|s| s.ok())
                        .map(|s| (s as f32) / 128.0)
                        .collect(),
                    16 => reader
                        .into_samples::<i16>()
                        .filter_map(|s| s.ok())
                        .map(|s| (s as f32) / 32768.0)
                        .collect(),
                    24 => reader
                        .into_samples::<i32>()
                        .filter_map(|s| s.ok())
                        .map(|s| (s as f32) / 8388608.0)
                        .collect(),
                    32 => reader
                        .into_samples::<i32>()
                        .filter_map(|s| s.ok())
                        .map(|s| (s as f32) / 2147483648.0)
                        .collect(),
                    b => {
                        return Err(EngineError::WavFormatError(format!(
                            "不支持的位深: {}bit（支持8/16/24/32bit）",
                            b
                        )));
                    }
                }
            }
            hound::SampleFormat::Float => {
                let reader: hound::WavReader<_> = reader.into();
                reader
                    .into_samples::<f32>()
                    .filter_map(|s| s.ok())
                    .collect()
            }
        };

        if samples.is_empty() {
            return Err(EngineError::WavFormatError("WAV文件无音频数据".into()));
        }

        let total_samples = samples.len();
        let frames = total_samples / channels;

        // 转换为平面格式
        let mut buf = Self::new(channels, frames, sample_rate);
        for (i, &sample) in samples.iter().enumerate() {
            let ch = i % channels;
            let frame = i / channels;
            buf.set_sample(ch, frame, sample);
        }

        Ok(buf)
    }

    /// 获取内部数据切片
    pub fn as_slice(&self) -> &[f32] {
        &self.data
    }

    /// 获取内部可变数据切片
    pub fn as_mut_slice(&mut self) -> &mut [f32] {
        &mut self.data
    }

    /// 获取总样本数（channels * frames）
    pub fn len(&self) -> usize {
        self.data.len()
    }

    /// 缓冲区是否为空
    pub fn is_empty(&self) -> bool {
        self.data.is_empty()
    }

    /// 清零所有样本
    pub fn clear(&mut self) {
        self.data.fill(0.0);
    }

    /// 用指定值填充所有样本
    pub fn fill(&mut self, value: f32) {
        self.data.fill(value);
    }

    /// 获取指定声道的数据切片（别名，兼容旧代码）
    pub fn channel_slice(&self, channel: usize) -> &[f32] {
        self.channel(channel)
    }

    /// 获取指定声道的可变数据切片（别名，兼容旧代码）
    pub fn channel_slice_mut(&mut self, channel: usize) -> &mut [f32] {
        self.channel_mut(channel)
    }

    /// 对所有样本施加增益
    pub fn apply_gain(&mut self, gain: f32) {
        for sample in &mut self.data {
            *sample *= gain;
        }
    }

    /// 获取指定位置的样本值（别名，兼容旧代码）
    pub fn sample(&self, channel: usize, frame: usize) -> f32 {
        self.get_sample(channel, frame)
    }
}

// ========================================================================

/// 无锁环形缓冲区 - 用于实时音频线程间数据传输
///
/// 单生产者单消费者（SPSC）模型。
/// 使用原子操作实现无锁读写，UnsafeCell 保证缓冲区的安全可变访问。
pub struct RingBuffer {
    /// 缓冲区数据（通过 UnsafeCell 实现内部可变）
    buffer: UnsafeCell<Vec<f32>>,
    /// 缓冲区容量（帧数，2的幂次以优化取模）
    capacity: usize,
    /// 读位置（原子操作）
    read_pos: AtomicUsize,
    /// 写位置（原子操作）
    write_pos: AtomicUsize,
    /// 声道数
    channels: usize,
}

// SAFETY: SPSC模型 — 只有一个写线程和一个读线程并发访问
// 写线程只修改 write_pos 和 buffer[read_pos..write_pos] 区域
// 读线程只修改 read_pos 并读取 buffer[read_pos..write_pos] 区域
// 两者通过 Acquire/Release 语义同步
unsafe impl Send for RingBuffer {}
unsafe impl Sync for RingBuffer {}

impl RingBuffer {
    /// 创建新的环形缓冲区
    ///
    /// `capacity` 为帧数，实际分配 `capacity * channels` 个 f32。
    /// 容量会向上取整到2的幂以优化取模运算。
    pub fn new(capacity: usize, channels: usize) -> Self {
        let capacity = capacity.max(1).next_power_of_two();
        Self {
            buffer: UnsafeCell::new(vec![0.0f32; capacity * channels]),
            capacity,
            read_pos: AtomicUsize::new(0),
            write_pos: AtomicUsize::new(0),
            channels: channels.max(1),
        }
    }

    /// 写入数据到环形缓冲区
    ///
    /// `data` 为交错格式音频数据，长度为 `frames * channels`。
    /// 返回成功写入的帧数。
    pub fn write(&self, data: &[f32]) -> usize {
        let write_pos = self.write_pos.load(Ordering::Relaxed);
        let read_pos = self.read_pos.load(Ordering::Acquire);
        let available = self.available_write_internal(write_pos, read_pos);

        let frames_to_write = data.len() / self.channels;
        let frames = frames_to_write.min(available);
        let samples = frames * self.channels;

        // SAFETY: 单生产者场景，只有写线程会修改 buffer 中 write_pos 之后的区域
        let buffer = unsafe { &mut *self.buffer.get() };
        let total_samples = self.capacity * self.channels;

        for i in 0..samples {
            let pos = (write_pos + i) % total_samples;
            buffer[pos] = data[i];
        }

        self.write_pos
            .store((write_pos + samples) % total_samples, Ordering::Release);

        frames
    }

    /// 从环形缓冲区读取数据
    ///
    /// `out` 为输出缓冲区，长度应为 `frames * channels`。
    /// 返回成功读取的帧数。
    pub fn read(&self, out: &mut [f32]) -> usize {
        let read_pos = self.read_pos.load(Ordering::Relaxed);
        let write_pos = self.write_pos.load(Ordering::Acquire);
        let available = self.available_read_internal(read_pos, write_pos);

        let frames_to_read = out.len() / self.channels;
        let frames = frames_to_read.min(available);
        let samples = frames * self.channels;

        // SAFETY: 读线程只读取 buffer 中 read_pos..write_pos 区域的数据
        let buffer = unsafe { &*self.buffer.get() };
        let total_samples = self.capacity * self.channels;

        for i in 0..samples {
            let pos = (read_pos + i) % total_samples;
            out[i] = buffer[pos];
        }

        self.read_pos
            .store((read_pos + samples) % total_samples, Ordering::Release);

        frames
    }

    /// 可读取的帧数
    pub fn available_read(&self) -> usize {
        let read_pos = self.read_pos.load(Ordering::Relaxed);
        let write_pos = self.write_pos.load(Ordering::Acquire);
        self.available_read_internal(read_pos, write_pos)
    }

    /// 可写入的帧数
    pub fn available_write(&self) -> usize {
        let write_pos = self.write_pos.load(Ordering::Relaxed);
        let read_pos = self.read_pos.load(Ordering::Acquire);
        self.available_write_internal(write_pos, read_pos)
    }

    /// 计算可读帧数（内部辅助）
    fn available_read_internal(&self, read_pos: usize, write_pos: usize) -> usize {
        let total = self.capacity * self.channels;
        let diff = if write_pos >= read_pos {
            write_pos - read_pos
        } else {
            total - read_pos + write_pos
        };
        diff / self.channels
    }

    /// 计算可写帧数（内部辅助，预留一个帧的空间避免读写重叠）
    fn available_write_internal(&self, write_pos: usize, read_pos: usize) -> usize {
        let total = self.capacity * self.channels;
        let used = if write_pos >= read_pos {
            write_pos - read_pos
        } else {
            total - read_pos + write_pos
        };
        // 预留一个帧的空间
        if total > used + self.channels {
            (total - used - self.channels) / self.channels
        } else {
            0
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_audio_buffer_read_write() {
        let mut buf = AudioBuffer::new(2, 4, 44100.0);
        // 写入立体声数据
        for f in 0..4 {
            buf.set_sample(0, f, f as f32 * 10.0); // L: 0, 10, 20, 30
            buf.set_sample(1, f, f as f32 * 10.0 + 1.0); // R: 1, 11, 21, 31
        }
        assert_eq!(buf.get_sample(0, 2), 20.0);
        assert_eq!(buf.get_sample(1, 2), 21.0);

        // 测试声道切片
        assert_eq!(buf.channel(0), &[0.0, 10.0, 20.0, 30.0]);
        assert_eq!(buf.channel(1), &[1.0, 11.0, 21.0, 31.0]);
    }

    #[test]
    fn test_audio_buffer_interleaved() {
        let interleaved = vec![1.0, 2.0, 3.0, 4.0, 5.0, 6.0]; // L0,R0,L1,R1,L2,R2
        let buf = AudioBuffer::from_interleaved(&interleaved, 2, 44100.0);
        assert_eq!(buf.frames, 3);
        assert_eq!(buf.channel(0), &[1.0, 3.0, 5.0]); // L
        assert_eq!(buf.channel(1), &[2.0, 4.0, 6.0]); // R

        let back = buf.to_interleaved();
        assert_eq!(back, interleaved);
    }

    #[test]
    fn test_wav_roundtrip() {
        let mut buf = AudioBuffer::new(2, 100, 44100.0);
        for f in 0..100 {
            let v = (f as f32 / 100.0) * 2.0 - 1.0;
            buf.set_sample(0, f, v);
            buf.set_sample(1, f, v * 0.5);
        }

        let wav_bytes = buf.to_wav_bytes().unwrap();
        assert!(wav_bytes.starts_with(b"RIFF"));

        let decoded = AudioBuffer::from_wav_bytes(&wav_bytes).unwrap();
        assert_eq!(decoded.channels, 2);
        assert_eq!(decoded.frames, 100);

        // 16bit量化有精度损失，允许小误差
        for f in 0..100 {
            let orig = buf.get_sample(0, f);
            let roundtrip = decoded.get_sample(0, f);
            assert!(
                (orig - roundtrip).abs() < 0.001,
                "帧{}: {} vs {}",
                f,
                orig,
                roundtrip
            );
        }
    }

    #[test]
    fn test_ring_buffer_basic() {
        let rb = RingBuffer::new(1024, 2);
        let data = vec![1.0f32, 2.0, 3.0, 4.0]; // 2帧 * 2声道
        let written = rb.write(&data);
        assert_eq!(written, 2);

        let mut out = vec![0.0f32; 4];
        let read = rb.read(&mut out);
        assert_eq!(read, 2);
        assert_eq!(out, vec![1.0, 2.0, 3.0, 4.0]);
    }

    #[test]
    fn test_hound_wav_file_roundtrip() {
        use std::path::PathBuf;

        let sample_rate = 44100u32;
        let frames = 100;
        let channels = 2;

        // 创建测试音频数据
        let mut buf = AudioBuffer::new(channels, frames, sample_rate as f64);
        for frame in 0..frames {
            for ch in 0..channels {
                let value = ((frame as f32) * 0.01 + ch as f32 * 0.1).sin();
                buf.set_sample(ch, frame, value);
            }
        }

        // 使用hound写入WAV文件
        let tmp_path = std::env::temp_dir().join("hound_test.wav");
        let spec = hound::WavSpec {
            channels: channels as u16,
            sample_rate: sample_rate as u32,
            bits_per_sample: 16,
            sample_format: hound::SampleFormat::Int,
        };
        {
            let mut writer = hound::WavWriter::create(&tmp_path, spec).unwrap();
            for frame in 0..frames {
                for ch in 0..channels {
                    let sample = buf.get_sample(ch, frame).clamp(-1.0, 1.0);
                    let int_sample = (sample * 32767.0) as i16;
                    writer.write_sample(int_sample).unwrap();
                }
            }
        }

        // 使用AudioBuffer::from_wav_file加载
        let loaded = AudioBuffer::from_wav_file(&tmp_path).unwrap();

        // 验证
        assert_eq!(loaded.channels, channels);
        assert_eq!(loaded.frames, frames);
        assert!((loaded.sample_rate - sample_rate as f64).abs() < 1.0);

        // 检查数据精度
        for frame in 0..frames.min(10) {
            for ch in 0..channels {
                let orig = buf.get_sample(ch, frame);
                let load = loaded.get_sample(ch, frame);
                // 由于16bit量化，有一定精度损失
                assert!(
                    (orig - load).abs() < 0.01,
                    "帧{}/声道{}: 原始={:.4}, 加载={:.4}",
                    frame,
                    ch,
                    orig,
                    load
                );
            }
        }

        // 清理
        let _ = std::fs::remove_file(&tmp_path);
    }

    #[test]
    fn test_hound_wav_file_mono() {
        let sample_rate = 48000u32;
        let frames = 50;

        // 创建单声道测试数据
        let mut buf = AudioBuffer::new(1, frames, sample_rate as f64);
        for frame in 0..frames {
            buf.set_sample(0, frame, (frame as f32) * 0.02);
        }

        // 写入单声道WAV
        let tmp_path = std::env::temp_dir().join("mono_test.wav");
        let spec = hound::WavSpec {
            channels: 1,
            sample_rate,
            bits_per_sample: 16,
            sample_format: hound::SampleFormat::Int,
        };
        {
            let mut writer = hound::WavWriter::create(&tmp_path, spec).unwrap();
            for frame in 0..frames {
                let sample = buf.get_sample(0, frame).clamp(-1.0, 1.0);
                let int_sample = (sample * 32767.0) as i16;
                writer.write_sample(int_sample).unwrap();
            }
        }

        // 加载
        let loaded = AudioBuffer::from_wav_file(&tmp_path).unwrap();
        assert_eq!(loaded.channels, 1);
        assert_eq!(loaded.frames, frames);

        // 清理
        let _ = std::fs::remove_file(&tmp_path);
    }
}
