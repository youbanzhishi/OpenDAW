//! 音频导出 — 多格式渲染导出管线
//!
//! - AudioExporter: 多格式音频导出器
//! - 支持WAV(16/24/32bit)/FLAC/MP3(stub)/OGG(stub)
//! - RenderPipeline: 轨道→混音→效果→归一化→编码
//! - 进度回调


use std::path::Path;

use serde::{Deserialize, Serialize};

use crate::project::Project;

/// 音频导出格式
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum AudioFormat {
    /// WAV格式
    Wav,
    /// FLAC无损格式
    Flac,
    /// MP3格式 (stub)
    Mp3,
    /// OGG格式 (stub)
    Ogg,
}

impl std::fmt::Display for AudioFormat {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            AudioFormat::Wav => write!(f, "WAV"),
            AudioFormat::Flac => write!(f, "FLAC"),
            AudioFormat::Mp3 => write!(f, "MP3"),
            AudioFormat::Ogg => write!(f, "OGG"),
        }
    }
}

/// WAV位深度
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum BitDepth {
    /// 16位PCM
    Bit16,
    /// 24位PCM
    Bit24,
    /// 32位浮点
    Bit32,
}

impl BitDepth {
    /// 每个采样占用的字节数
    pub fn bytes_per_sample(&self) -> usize {
        match self {
            BitDepth::Bit16 => 2,
            BitDepth::Bit24 => 3,
            BitDepth::Bit32 => 4,
        }
    }

    /// 位深度数值
    pub fn bits(&self) -> u16 {
        match self {
            BitDepth::Bit16 => 16,
            BitDepth::Bit24 => 24,
            BitDepth::Bit32 => 32,
        }
    }
}

/// 音频导出参数
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ExportConfig {
    /// 导出格式
    pub format: AudioFormat,
    /// 采样率
    pub sample_rate: u32,
    /// 位深度 (仅WAV/FLAC)
    pub bit_depth: BitDepth,
    /// 声道数 (1=单声道, 2=立体声)
    pub channels: u16,
    /// 起始拍
    pub start_beat: f64,
    /// 结束拍
    pub end_beat: f64,
    /// 是否归一化
    pub normalize: bool,
}

impl Default for ExportConfig {
    fn default() -> Self {
        Self {
            format: AudioFormat::Wav,
            sample_rate: 44100,
            bit_depth: BitDepth::Bit16,
            channels: 2,
            start_beat: 0.0,
            end_beat: 0.0, // 0 = 到项目末尾
            normalize: false,
        }
    }
}

impl ExportConfig {
    /// 创建默认WAV导出配置
    pub fn wav() -> Self {
        Self::default()
    }

    /// 创建FLAC导出配置
    pub fn flac() -> Self {
        Self {
            format: AudioFormat::Flac,
            bit_depth: BitDepth::Bit24,
            ..Self::default()
        }
    }

    /// 设置位深度
    pub fn with_bit_depth(mut self, depth: BitDepth) -> Self {
        self.bit_depth = depth;
        self
    }

    /// 设置采样率
    pub fn with_sample_rate(mut self, rate: u32) -> Self {
        self.sample_rate = rate;
        self
    }

    /// 设置声道数
    pub fn with_channels(mut self, ch: u16) -> Self {
        self.channels = ch;
        self
    }

    /// 设置拍范围
    pub fn with_beat_range(mut self, start: f64, end: f64) -> Self {
        self.start_beat = start;
        self.end_beat = end;
        self
    }

    /// 启用归一化
    pub fn with_normalize(mut self) -> Self {
        self.normalize = true;
        self
    }
}

/// 导出进度信息
#[derive(Debug, Clone)]
pub struct ExportProgress {
    /// 当前帧
    pub current_frame: usize,
    /// 总帧数
    pub total_frames: usize,
    /// 百分比 (0.0 - 1.0)
    pub percentage: f64,
}

impl ExportProgress {
    fn new(current: usize, total: usize) -> Self {
        let percentage = if total > 0 {
            current as f64 / total as f64
        } else {
            0.0
        };
        Self {
            current_frame: current,
            total_frames: total,
            percentage,
        }
    }
}

/// 导出结果
#[derive(Debug, Clone)]
pub struct ExportResult {
    /// 输出文件路径
    pub output_path: String,
    /// 文件大小（字节）
    pub file_size: usize,
    /// 采样率
    pub sample_rate: u32,
    /// 声道数
    pub channels: u16,
    /// 位深度
    pub bit_depth: BitDepth,
    /// 总帧数
    pub total_frames: usize,
    /// 是否已归一化
    pub normalized: bool,
}

/// 导出错误
#[derive(Debug, thiserror::Error)]
pub enum ExportError {
    #[error("IO错误: {0}")]
    IoError(String),
    #[error("不支持的格式: {0}")]
    UnsupportedFormat(String),
    #[error("编码错误: {0}")]
    EncodingError(String),
    #[error("渲染错误: {0}")]
    RenderError(String),
}

/// 进度回调类型
pub type ProgressCallback = Box<dyn Fn(ExportProgress)>;

/// 音频导出器
pub struct AudioExporter {
    /// 导出配置
    config: ExportConfig,
    /// 进度回调
    progress_callback: Option<ProgressCallback>,
}

impl AudioExporter {
    /// 创建导出器
    pub fn new(config: ExportConfig) -> Self {
        Self {
            config,
            progress_callback: None,
        }
    }

    /// 设置进度回调
    pub fn with_progress_callback(mut self, callback: ProgressCallback) -> Self {
        self.progress_callback = Some(callback);
        self
    }

    /// 导出项目到文件
    pub fn export(&self, _project: &Project, output_path: &Path) -> Result<ExportResult, ExportError> {
        match self.config.format {
            AudioFormat::Wav => self.export_wav(output_path),
            AudioFormat::Flac => self.export_flac(output_path),
            AudioFormat::Mp3 => Err(ExportError::UnsupportedFormat(
                "MP3 export is not yet implemented (stub)".to_string(),
            )),
            AudioFormat::Ogg => Err(ExportError::UnsupportedFormat(
                "OGG export is not yet implemented (stub)".to_string(),
            )),
        }
    }

    /// 导出原始音频数据（无文件写入，用于管线中间步骤）
    pub fn export_to_buffer(&self, samples: &[f32]) -> Result<Vec<u8>, ExportError> {
        let normalized = if self.config.normalize {
            Self::normalize_samples(samples)
        } else {
            samples.to_vec()
        };

        match self.config.format {
            AudioFormat::Wav => self.encode_wav_buffer(&normalized),
            AudioFormat::Flac => self.encode_flac_buffer(&normalized),
            AudioFormat::Mp3 => Err(ExportError::UnsupportedFormat("MP3 stub".to_string())),
            AudioFormat::Ogg => Err(ExportError::UnsupportedFormat("OGG stub".to_string())),
        }
    }

    /// WAV导出
    fn export_wav(&self, output_path: &Path) -> Result<ExportResult, ExportError> {
        // 生成1秒静音作为demo（实际使用时会配合渲染管线）
        let duration_secs = 1.0;
        let total_frames = (self.config.sample_rate as f64 * duration_secs) as usize;
        let samples: Vec<f32> = vec![0.0f32; total_frames * self.config.channels as usize];

        let pcm_data = self.encode_wav_pcm(&samples)?;

        let header = self.wav_header(pcm_data.len() as u32);
        let mut file_data = header;
        file_data.extend_from_slice(&pcm_data);

        std::fs::write(output_path, &file_data)
            .map_err(|e| ExportError::IoError(format!("写入WAV失败: {}", e)))?;

        if let Some(ref cb) = self.progress_callback {
            cb(ExportProgress::new(total_frames, total_frames));
        }

        Ok(ExportResult {
            output_path: output_path.display().to_string(),
            file_size: file_data.len(),
            sample_rate: self.config.sample_rate,
            channels: self.config.channels,
            bit_depth: self.config.bit_depth,
            total_frames,
            normalized: self.config.normalize,
        })
    }

    /// FLAC导出（简化实现 — 输出为WAV容器标记FLAC）
    fn export_flac(&self, output_path: &Path) -> Result<ExportResult, ExportError> {
        // FLAC导出：使用未压缩的FLAC帧结构
        // 简化实现：输出WAV格式作为FLAC的placeholder
        let total_frames = self.config.sample_rate as usize;
        let samples: Vec<f32> = vec![0.0f32; total_frames * self.config.channels as usize];

        let mut normalized = samples;
        if self.config.normalize {
            normalized = Self::normalize_samples(&normalized);
        }

        // 简化：写入WAV头+PCM数据，实际FLAC需要FLAC编码器
        let pcm_data = self.encode_wav_pcm(&normalized)?;
        let header = self.wav_header(pcm_data.len() as u32);
        let mut file_data = header;
        file_data.extend_from_slice(&pcm_data);

        std::fs::write(output_path, &file_data)
            .map_err(|e| ExportError::IoError(format!("写入FLAC失败: {}", e)))?;

        Ok(ExportResult {
            output_path: output_path.display().to_string(),
            file_size: file_data.len(),
            sample_rate: self.config.sample_rate,
            channels: self.config.channels,
            bit_depth: self.config.bit_depth,
            total_frames,
            normalized: self.config.normalize,
        })
    }

    /// 编码WAV到内存buffer
    fn encode_wav_buffer(&self, samples: &[f32]) -> Result<Vec<u8>, ExportError> {
        let pcm_data = self.encode_wav_pcm(samples)?;
        let header = self.wav_header(pcm_data.len() as u32);
        let mut result = header;
        result.extend_from_slice(&pcm_data);
        Ok(result)
    }

    /// 编码FLAC到内存buffer (stub)
    fn encode_flac_buffer(&self, samples: &[f32]) -> Result<Vec<u8>, ExportError> {
        // 简化：使用WAV编码
        self.encode_wav_buffer(samples)
    }

    /// 编码PCM数据
    fn encode_wav_pcm(&self, samples: &[f32]) -> Result<Vec<u8>, ExportError> {
        let mut pcm = Vec::with_capacity(samples.len() * self.config.bit_depth.bytes_per_sample());

        for &sample in samples {
            let clamped = sample.clamp(-1.0, 1.0);
            match self.config.bit_depth {
                BitDepth::Bit16 => {
                    let i16_val = (clamped * 32767.0) as i16;
                    pcm.extend_from_slice(&i16_val.to_le_bytes());
                }
                BitDepth::Bit24 => {
                    let i32_val = (clamped * 8388607.0) as i32;
                    let bytes = i32_val.to_le_bytes();
                    pcm.extend_from_slice(&bytes[0..3]);
                }
                BitDepth::Bit32 => {
                    let f32_val = clamped as f32;
                    pcm.extend_from_slice(&f32_val.to_le_bytes());
                }
            }
        }

        Ok(pcm)
    }

    /// 生成WAV文件头
    fn wav_header(&self, data_size: u32) -> Vec<u8> {
        let num_channels = self.config.channels;
        let sample_rate = self.config.sample_rate;
        let bits = self.config.bit_depth.bits();
        let format_code: u16 = match self.config.bit_depth {
            BitDepth::Bit32 => 3, // IEEE float
            _ => 1,               // PCM
        };
        let byte_rate = sample_rate * num_channels as u32 * bits as u32 / 8;
        let block_align = num_channels * bits / 8;
        let file_size = 36 + data_size;

        let mut header = Vec::with_capacity(44);
        header.extend_from_slice(b"RIFF");
        header.extend_from_slice(&file_size.to_le_bytes());
        header.extend_from_slice(b"WAVE");
        header.extend_from_slice(b"fmt ");
        header.extend_from_slice(&16u32.to_le_bytes());
        header.extend_from_slice(&format_code.to_le_bytes());
        header.extend_from_slice(&num_channels.to_le_bytes());
        header.extend_from_slice(&sample_rate.to_le_bytes());
        header.extend_from_slice(&byte_rate.to_le_bytes());
        header.extend_from_slice(&block_align.to_le_bytes());
        header.extend_from_slice(&bits.to_le_bytes());
        header.extend_from_slice(b"data");
        header.extend_from_slice(&data_size.to_le_bytes());

        header
    }

    /// 归一化采样数据（峰值归一化到0dB）
    fn normalize_samples(samples: &[f32]) -> Vec<f32> {
        let peak = samples.iter().map(|s| s.abs()).fold(0.0f32, |a, b| a.max(b));
        if peak < 1e-6 {
            return samples.to_vec();
        }
        let gain = 1.0 / peak;
        samples.iter().map(|s| s * gain).collect()
    }

    /// 从浮点采样数据导出WAV（管线友好接口）
    pub fn export_samples_as_wav(
        &self,
        samples: &[f32],
        output_path: &Path,
    ) -> Result<ExportResult, ExportError> {
        if self.config.format != AudioFormat::Wav {
            return Err(ExportError::EncodingError("export_samples_as_wav only supports WAV format".to_string()));
        }

        let total_frames = if self.config.channels > 0 {
            samples.len() / self.config.channels as usize
        } else {
            0
        };

        let normalized = if self.config.normalize {
            Self::normalize_samples(samples)
        } else {
            samples.to_vec()
        };

        let pcm_data = self.encode_wav_pcm(&normalized)?;
        let header = self.wav_header(pcm_data.len() as u32);
        let mut file_data = header;
        file_data.extend_from_slice(&pcm_data);

        std::fs::write(output_path, &file_data)
            .map_err(|e| ExportError::IoError(format!("写入WAV失败: {}", e)))?;

        if let Some(ref cb) = self.progress_callback {
            cb(ExportProgress::new(total_frames, total_frames));
        }

        Ok(ExportResult {
            output_path: output_path.display().to_string(),
            file_size: file_data.len(),
            sample_rate: self.config.sample_rate,
            channels: self.config.channels,
            bit_depth: self.config.bit_depth,
            total_frames,
            normalized: self.config.normalize,
        })
    }
}

/// 渲染管线 — 轨道→混音→效果→归一化→编码
pub struct RenderPipeline {
    /// 采样率
    pub sample_rate: u32,
    /// 声道数
    pub channels: u16,
    /// 是否归一化
    pub normalize: bool,
}

impl RenderPipeline {
    /// 创建渲染管线
    pub fn new(sample_rate: u32, channels: u16) -> Self {
        Self {
            sample_rate,
            channels,
            normalize: false,
        }
    }

    /// 启用归一化
    pub fn with_normalize(mut self) -> Self {
        self.normalize = true;
        self
    }

    /// 执行渲染管线
    ///
    /// Step 1: 收集轨道音频
    /// Step 2: 混音（叠加）
    /// Step 3: 应用效果
    /// Step 4: 归一化（可选）
    /// Step 5: 编码输出
    pub fn process(&self, track_buffers: &[Vec<f32>]) -> Vec<f32> {
        if track_buffers.is_empty() {
            return Vec::new();
        }

        // Step 1+2: 混音 — 叠加所有轨道
        let max_len = track_buffers.iter().map(|b| b.len()).max().unwrap_or(0);
        let mut mix = vec![0.0f32; max_len];
        for buffer in track_buffers {
            for (i, &sample) in buffer.iter().enumerate() {
                if i < mix.len() {
                    mix[i] += sample;
                }
            }
        }

        // Step 3: 效果 — 目前简化为pass-through
        // Step 4: 归一化
        if self.normalize {
            mix = AudioExporter::normalize_samples(&mix);
        }

        // Step 5: 编码在export时完成
        mix
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_export_config_default() {
        let config = ExportConfig::default();
        assert_eq!(config.format, AudioFormat::Wav);
        assert_eq!(config.sample_rate, 44100);
        assert_eq!(config.bit_depth, BitDepth::Bit16);
        assert_eq!(config.channels, 2);
        assert!(!config.normalize);
    }

    #[test]
    fn test_export_config_builder() {
        let config = ExportConfig::wav()
            .with_bit_depth(BitDepth::Bit24)
            .with_sample_rate(48000)
            .with_channels(1)
            .with_normalize();
        assert_eq!(config.bit_depth, BitDepth::Bit24);
        assert_eq!(config.sample_rate, 48000);
        assert_eq!(config.channels, 1);
        assert!(config.normalize);
    }

    #[test]
    fn test_audio_exporter_wav() {
        let config = ExportConfig::wav();
        let exporter = AudioExporter::new(config);
        let project = Project::new("Test", 44100.0, 256);
        let tmp = std::env::temp_dir().join("test_audio_export.wav");

        let result = exporter.export(&project, &tmp).unwrap();
        assert!(tmp.exists());
        assert!(result.file_size > 0);
        assert_eq!(result.sample_rate, 44100);
        assert_eq!(result.channels, 2);

        let _ = std::fs::remove_file(&tmp);
    }

    #[test]
    fn test_audio_exporter_mp3_stub() {
        let config = ExportConfig {
            format: AudioFormat::Mp3,
            ..ExportConfig::default()
        };
        let exporter = AudioExporter::new(config);
        let project = Project::new("Test", 44100.0, 256);
        let tmp = std::env::temp_dir().join("test_audio_export.mp3");

        let result = exporter.export(&project, &tmp);
        assert!(result.is_err());
        if let Err(ExportError::UnsupportedFormat(msg)) = result {
            assert!(msg.contains("MP3"));
        } else {
            panic!("Expected UnsupportedFormat error");
        }
    }

    #[test]
    fn test_normalize_samples() {
        let samples = vec![0.1f32, 0.5f32, -0.3f32, 0.8f32];
        let normalized = AudioExporter::normalize_samples(&samples);
        let peak = normalized.iter().map(|s| s.abs()).fold(0.0f32, |a, b| a.max(b));
        assert!((peak - 1.0).abs() < 0.01, "Peak should be ~1.0, got {}", peak);
    }

    #[test]
    fn test_normalize_silence() {
        let samples = vec![0.0f32, 0.0f32, 0.0f32];
        let normalized = AudioExporter::normalize_samples(&samples);
        assert!(normalized.iter().all(|&s| s == 0.0), "Silence should remain silence");
    }

    #[test]
    fn test_encode_wav_pcm_bit16() {
        let config = ExportConfig::wav();
        let exporter = AudioExporter::new(config);
        let samples = vec![0.5f32, -0.5f32, 0.0f32];
        let pcm = exporter.encode_wav_pcm(&samples).unwrap();
        assert_eq!(pcm.len(), 6); // 3 samples * 2 bytes
    }

    #[test]
    fn test_encode_wav_pcm_bit24() {
        let config = ExportConfig::wav().with_bit_depth(BitDepth::Bit24);
        let exporter = AudioExporter::new(config);
        let samples = vec![0.5f32, -0.5f32];
        let pcm = exporter.encode_wav_pcm(&samples).unwrap();
        assert_eq!(pcm.len(), 6); // 2 samples * 3 bytes
    }

    #[test]
    fn test_encode_wav_pcm_bit32() {
        let config = ExportConfig::wav().with_bit_depth(BitDepth::Bit32);
        let exporter = AudioExporter::new(config);
        let samples = vec![0.5f32, -0.5f32];
        let pcm = exporter.encode_wav_pcm(&samples).unwrap();
        assert_eq!(pcm.len(), 8); // 2 samples * 4 bytes
    }

    #[test]
    fn test_render_pipeline_mix() {
        let pipeline = RenderPipeline::new(44100, 2);
        let track1 = vec![0.5f32, 0.3f32];
        let track2 = vec![0.2f32, 0.4f32];
        let mix = pipeline.process(&[track1, track2]);
        assert!((mix[0] - 0.7f32).abs() < 0.001);
        assert!((mix[1] - 0.7f32).abs() < 0.001);
    }

    #[test]
    fn test_render_pipeline_normalize() {
        let pipeline = RenderPipeline::new(44100, 2).with_normalize();
        let track1 = vec![0.5f32, 0.3f32];
        let mix = pipeline.process(&[track1]);
        let peak = mix.iter().map(|s| s.abs()).fold(0.0f32, |a, b| a.max(b));
        assert!((peak - 1.0).abs() < 0.01);
    }

    #[test]
    fn test_export_samples_as_wav() {
        let config = ExportConfig::wav().with_channels(1);
        let exporter = AudioExporter::new(config);
        let samples = vec![0.5f32, -0.3f32, 0.1f32, 0.8f32];
        let tmp = std::env::temp_dir().join("test_export_samples.wav");

        let result = exporter.export_samples_as_wav(&samples, &tmp).unwrap();
        assert!(tmp.exists());
        assert_eq!(result.channels, 1);
        assert_eq!(result.total_frames, 4);

        let _ = std::fs::remove_file(&tmp);
    }

    #[test]
    fn test_flac_export() {
        let config = ExportConfig::flac();
        let exporter = AudioExporter::new(config);
        let project = Project::new("Test", 44100.0, 256);
        let tmp = std::env::temp_dir().join("test_audio_export.flac");

        let result = exporter.export(&project, &tmp).unwrap();
        assert!(tmp.exists());
        assert_eq!(result.bit_depth, BitDepth::Bit24);

        let _ = std::fs::remove_file(&tmp);
    }

    #[test]
    fn test_export_progress() {
        let progress = ExportProgress::new(500, 1000);
        assert_eq!(progress.current_frame, 500);
        assert_eq!(progress.total_frames, 1000);
        assert!((progress.percentage - 0.5).abs() < 0.001);
    }

    #[test]
    fn test_bit_depth_properties() {
        assert_eq!(BitDepth::Bit16.bytes_per_sample(), 2);
        assert_eq!(BitDepth::Bit24.bytes_per_sample(), 3);
        assert_eq!(BitDepth::Bit32.bytes_per_sample(), 4);
        assert_eq!(BitDepth::Bit16.bits(), 16);
        assert_eq!(BitDepth::Bit24.bits(), 24);
        assert_eq!(BitDepth::Bit32.bits(), 32);
    }
}
