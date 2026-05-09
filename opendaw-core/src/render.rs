//! 离线渲染 — 遍历timeline -> process -> 写文件
//!
//! 支持将项目渲染为WAV文件

use std::path::Path;

use audio_engine::EngineAudioBuffer;
use opendaw_extension::AudioBuffer;

/// WAV文件头（16位PCM）
struct WavHeader {
    num_channels: u16,
    sample_rate: u32,
    bits_per_sample: u16,
    data_size: u32,
}

impl WavHeader {
    fn as_bytes(&self) -> Vec<u8> {
        let byte_rate = self.sample_rate * self.num_channels as u32 * self.bits_per_sample as u32 / 8;
        let block_align = self.num_channels * self.bits_per_sample / 8;
        let file_size = 36 + self.data_size;

        let mut bytes = Vec::with_capacity(44);

        // RIFF header
        bytes.extend_from_slice(b"RIFF");
        bytes.extend_from_slice(&file_size.to_le_bytes());
        bytes.extend_from_slice(b"WAVE");

        // fmt chunk
        bytes.extend_from_slice(b"fmt ");
        bytes.extend_from_slice(&16u32.to_le_bytes()); // chunk size
        bytes.extend_from_slice(&1u16.to_le_bytes()); // PCM format
        bytes.extend_from_slice(&self.num_channels.to_le_bytes());
        bytes.extend_from_slice(&self.sample_rate.to_le_bytes());
        bytes.extend_from_slice(&byte_rate.to_le_bytes());
        bytes.extend_from_slice(&block_align.to_le_bytes());
        bytes.extend_from_slice(&self.bits_per_sample.to_le_bytes());

        // data chunk
        bytes.extend_from_slice(b"data");
        bytes.extend_from_slice(&self.data_size.to_le_bytes());

        bytes
    }
}

/// 离线渲染器
pub struct OfflineRenderer {
    /// 采样率
    sample_rate: f64,
    /// 缓冲区大小
    buffer_size: usize,
    /// 声道数
    channels: usize,
}

impl OfflineRenderer {
    /// 创建离线渲染器
    pub fn new(sample_rate: f64, buffer_size: usize, channels: usize) -> Self {
        Self {
            sample_rate,
            buffer_size,
            channels,
        }
    }

    /// 渲染指定时长的静音到WAV文件
    ///
    /// 这是一个基础实现，用于验证渲染管线
    /// 实际使用时会配合Project和Mixer进行完整渲染
    pub fn render_silence(&self, duration_secs: f64, output_path: &Path) -> Result<RenderStats, RenderError> {
        let total_frames = (self.sample_rate * duration_secs) as usize;
        let total_samples = total_frames * self.channels;
        let data_size = (total_samples * 2) as u32; // 16-bit

        // 写WAV头
        let header = WavHeader {
            num_channels: self.channels as u16,
            sample_rate: self.sample_rate as u32,
            bits_per_sample: 16,
            data_size,
        };

        let mut file_data = header.as_bytes();
        // 静音数据（全零16-bit PCM）
        file_data.extend(std::iter::repeat(0u8).take(data_size as usize));

        std::fs::write(output_path, &file_data)
            .map_err(|e| RenderError::IoError(format!("写入WAV失败: {}", e)))?;

        Ok(RenderStats {
            duration_secs,
            total_frames,
            sample_rate: self.sample_rate,
            channels: self.channels,
            file_size: file_data.len(),
        })
    }

    /// 渲染正弦波到WAV文件（测试用）
    pub fn render_sine(
        &self,
        freq: f64,
        duration_secs: f64,
        amplitude: f64,
        output_path: &Path,
    ) -> Result<RenderStats, RenderError> {
        let total_frames = (self.sample_rate * duration_secs) as usize;
        let total_samples = total_frames * self.channels;
        let data_size = (total_samples * 2) as u32;

        let header = WavHeader {
            num_channels: self.channels as u16,
            sample_rate: self.sample_rate as u32,
            bits_per_sample: 16,
            data_size,
        };

        let mut file_data = header.as_bytes();

        // 生成正弦波数据
        for frame in 0..total_frames {
            let sample = (2.0 * std::f64::consts::PI * freq * frame as f64 / self.sample_rate).sin()
                * amplitude;
            let i16_sample = (sample.clamp(-1.0, 1.0) * 32767.0) as i16;
            for _ in 0..self.channels {
                file_data.extend_from_slice(&i16_sample.to_le_bytes());
            }
        }

        std::fs::write(output_path, &file_data)
            .map_err(|e| RenderError::IoError(format!("写入WAV失败: {}", e)))?;

        Ok(RenderStats {
            duration_secs,
            total_frames,
            sample_rate: self.sample_rate,
            channels: self.channels,
            file_size: file_data.len(),
        })
    }

    /// 使用回调函数渲染
    ///
    /// 每个buffer调用一次callback，用于自定义渲染逻辑
    pub fn render_with_callback<F>(
        &self,
        duration_secs: f64,
        output_path: &Path,
        mut callback: F,
    ) -> Result<RenderStats, RenderError>
    where
        F: FnMut(&mut EngineAudioBuffer),
    {
        let total_frames = (self.sample_rate * duration_secs) as usize;
        let mut pcm_data = Vec::new();

        let mut buffer = EngineAudioBuffer::new(self.channels, self.buffer_size, self.sample_rate);
        let mut frames_rendered = 0;

        while frames_rendered < total_frames {
            let frames_this_cycle = self.buffer_size.min(total_frames - frames_rendered);

            buffer.clear();
            callback(&mut buffer);

            // 转换为16-bit PCM
            for frame in 0..frames_this_cycle {
                for ch in 0..self.channels {
                    let sample = buffer.sample(ch, frame).clamp(-1.0, 1.0);
                    let i16_sample = (sample * 32767.0) as i16;
                    pcm_data.extend_from_slice(&i16_sample.to_le_bytes());
                }
            }

            frames_rendered += frames_this_cycle;
        }

        let data_size = pcm_data.len() as u32;
        let header = WavHeader {
            num_channels: self.channels as u16,
            sample_rate: self.sample_rate as u32,
            bits_per_sample: 16,
            data_size,
        };

        let mut file_data = header.as_bytes();
        file_data.extend(pcm_data);

        std::fs::write(output_path, &file_data)
            .map_err(|e| RenderError::IoError(format!("写入WAV失败: {}", e)))?;

        Ok(RenderStats {
            duration_secs,
            total_frames,
            sample_rate: self.sample_rate,
            channels: self.channels,
            file_size: file_data.len(),
        })
    }
}

/// 渲染统计信息
#[derive(Clone, Debug)]
pub struct RenderStats {
    pub duration_secs: f64,
    pub total_frames: usize,
    pub sample_rate: f64,
    pub channels: usize,
    pub file_size: usize,
}

/// 渲染错误
#[derive(Debug, thiserror::Error)]
pub enum RenderError {
    #[error("IO错误: {0}")]
    IoError(String),
    #[error("渲染错误: {0}")]
    RenderFailed(String),
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_render_silence() {
        let renderer = OfflineRenderer::new(44100.0, 256, 2);
        let tmp = std::env::temp_dir().join("test_silence.wav");

        let stats = renderer.render_silence(1.0, &tmp).unwrap();
        assert_eq!(stats.total_frames, 44100);
        assert!(tmp.exists());

        // 验证文件大小（44字节头 + 44100*2*2字节 = 176844）
        assert_eq!(stats.file_size, 44 + 44100 * 2 * 2);

        let _ = std::fs::remove_file(&tmp);
    }

    #[test]
    fn test_render_sine() {
        let renderer = OfflineRenderer::new(44100.0, 256, 2);
        let tmp = std::env::temp_dir().join("test_sine.wav");

        let stats = renderer.render_sine(440.0, 1.0, 0.5, &tmp).unwrap();
        assert_eq!(stats.total_frames, 44100);
        assert!(tmp.exists());

        let _ = std::fs::remove_file(&tmp);
    }

    #[test]
    fn test_render_with_callback() {
        let renderer = OfflineRenderer::new(44100.0, 256, 2);
        let tmp = std::env::temp_dir().join("test_callback.wav");

        let stats = renderer.render_with_callback(0.5, &tmp, |buf| {
            // 生成440Hz正弦波
            for frame in 0..buf.frames {
                let value = ((2.0 * std::f64::consts::PI * 440.0 * frame as f64 / 44100.0).sin() * 0.3) as f32;
                buf.set_sample(0, frame, value);
                buf.set_sample(1, frame, value);
            }
        }).unwrap();

        assert!(stats.total_frames > 0);
        assert!(tmp.exists());

        let _ = std::fs::remove_file(&tmp);
    }

    #[test]
    fn test_render_multiple_tracks_mix() {
        use std::path::Path;
        
        let renderer = OfflineRenderer::new(44100.0, 256, 2);
        let tmp = std::env::temp_dir().join("test_mix.wav");

        // 创建测试缓冲区
        let track1_samples: Vec<f32> = (0..4410)
            .map(|i| (2.0 * std::f64::consts::PI * 440.0 * i as f64 / 44100.0).sin() as f32 * 0.5)
            .collect();
        let track2_samples: Vec<f32> = (0..4410)
            .map(|i| (2.0 * std::f64::consts::PI * 880.0 * i as f64 / 44100.0).sin() as f32 * 0.3)
            .collect();

        let stats = renderer.render_with_callback(0.1, &tmp, |buf| {
            for frame in 0..buf.frames {
                let t1_idx = frame;
                let t2_idx = frame;
                let mix = if t1_idx < track1_samples.len() { track1_samples[t1_idx] } else { 0.0 }
                        + if t2_idx < track2_samples.len() { track2_samples[t2_idx] } else { 0.0 };
                buf.set_sample(0, frame, mix.clamp(-1.0, 1.0));
                buf.set_sample(1, frame, mix.clamp(-1.0, 1.0));
            }
        }).unwrap();

        assert!(stats.total_frames > 0);
        assert!(tmp.exists());

        // 验证文件可以被读取
        let loaded = EngineAudioBuffer::from_wav_file(&tmp);
        assert!(loaded.is_ok(), "渲染的文件应能被加载: {:?}", loaded.err());

        let _ = std::fs::remove_file(&tmp);
    }

    #[test]
    fn test_render_with_volume_control() {
        let renderer = OfflineRenderer::new(44100.0, 256, 2);
        let tmp = std::env::temp_dir().join("test_volume.wav");

        let amplitude = 0.8;
        let stats = renderer.render_with_callback(0.1, &tmp, |buf| {
            for frame in 0..buf.frames {
                let value = ((2.0 * std::f64::consts::PI * 440.0 * frame as f64 / 44100.0).sin() * amplitude) as f32;
                buf.set_sample(0, frame, value);
                buf.set_sample(1, frame, value);
            }
        }).unwrap();

        assert!(stats.total_frames > 0);

        // 加载并验证峰值
        let loaded = EngineAudioBuffer::from_wav_file(&tmp).unwrap();
        let max_sample = loaded.as_slice().iter()
            .map(|s| s.abs())
            .fold(0.0f32, |a, b| a.max(b));
        
        // 峰值应接近设定的幅度
        assert!((max_sample - amplitude as f32).abs() < 0.1, 
            "峰值应接近{}，实际{}", amplitude, max_sample);

        let _ = std::fs::remove_file(&tmp);
    }

    #[test]
    fn test_render_mono_to_stereo() {
        let renderer = OfflineRenderer::new(44100.0, 256, 2);
        let tmp = std::env::temp_dir().join("test_mono_stereo.wav");

        // 渲染单声道信号
        let stats = renderer.render_with_callback(0.1, &tmp, |buf| {
            for frame in 0..buf.frames {
                let value = (2.0 * std::f64::consts::PI * 440.0 * frame as f64 / 44100.0).sin() as f32 * 0.5;
                // 只设置声道0，声道1保持0
                buf.set_sample(0, frame, value);
                buf.set_sample(1, frame, 0.0);
            }
        }).unwrap();

        assert!(stats.total_frames > 0);

        // 加载并验证
        let loaded = EngineAudioBuffer::from_wav_file(&tmp).unwrap();
        assert_eq!(loaded.channels, 2);

        let _ = std::fs::remove_file(&tmp);
    }
}
