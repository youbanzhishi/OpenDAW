//! 智能混音v2 — AI辅助混音
//!
//! - SmartMixEngine: AI辅助混音引擎
//! - FrequencyAnalyzer: 频谱分析（FFT + 倍频程分析）
//! - MixSuggestion: 混音建议（EQ/压缩/声像/音量）
//! - AutoMixProfile: 自动混音配置（按风格）
//! - LoudnessNormalizer: 响度标准化（LUFS目标）


use serde::{Deserialize, Serialize};

// ── 频谱分析 ──────────────────────────────────────────────

/// 倍频程分析结果
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct OctaveAnalysis {
    /// 倍频程中心频率 (Hz)
    pub center_frequency: f64,
    /// 该频段能量（dB）
    pub energy_db: f64,
    /// 该频段峰值（dB）
    pub peak_db: f64,
    /// 频段标签
    pub label: String,
}

/// 频谱分析结果
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SpectrumAnalysis {
    /// FFT bin数
    pub fft_size: usize,
    /// 采样率
    pub sample_rate: f64,
    /// 频率分辨率
    pub frequency_resolution: f64,
    /// 幅度谱 (dB)
    pub magnitude_db: Vec<f64>,
    /// 倍频程分析结果
    pub octave_bands: Vec<OctaveAnalysis>,
    /// 总RMS能量 (dB)
    pub total_rms_db: f64,
    /// 峰值 (dB)
    pub peak_db: f64,
    /// 动态范围 (dB)
    pub dynamic_range_db: f64,
}

/// 频谱分析器
pub struct FrequencyAnalyzer {
    /// 采样率
    sample_rate: f64,
    /// FFT大小
    fft_size: usize,
}

impl FrequencyAnalyzer {
    /// 创建新的频谱分析器
    pub fn new(sample_rate: f64, fft_size: usize) -> Self {
        // 确保fft_size是2的幂
        let fft_size = fft_size.next_power_of_two();
        Self {
            sample_rate,
            fft_size,
        }
    }

    /// 分析音频频谱
    pub fn analyze(&self, audio: &[f64]) -> SpectrumAnalysis {
        let frequency_resolution = self.sample_rate / self.fft_size as f64;

        // 应用Hann窗
        let windowed: Vec<f64> = audio
            .iter()
            .take(self.fft_size)
            .enumerate()
            .map(|(i, &s)| {
                let w = 0.5 * (1.0 - (2.0 * std::f64::consts::PI * i as f64
                    / (self.fft_size - 1) as f64).cos());
                s * w
            })
            .collect();

        // 计算DFT幅度谱
        let n = windowed.len();
        let half = n / 2;
        let mut magnitude_db = Vec::with_capacity(half);

        for k in 0..half {
            let mut re = 0.0;
            let mut im = 0.0;
            for j in 0..n {
                let angle = -2.0 * std::f64::consts::PI * k as f64 * j as f64 / n as f64;
                re += windowed[j] * angle.cos();
                im += windowed[j] * angle.sin();
            }
            let magnitude = (re * re + im * im).sqrt() / n as f64;
            let db = if magnitude > 1e-10 {
                20.0 * magnitude.log10()
            } else {
                -120.0
            };
            magnitude_db.push(db);
        }

        // 计算RMS和峰值
        let rms: f64 = (audio.iter().map(|&s| s * s).sum::<f64>() / audio.len() as f64).sqrt();
        let total_rms_db = if rms > 1e-10 { 20.0 * rms.log10() } else { -120.0 };
        let peak = audio.iter().cloned().fold(0.0f64, |a, b| a.abs().max(b.abs()));
        let peak_db = if peak > 1e-10 { 20.0 * peak.log10() } else { -120.0 };
        let dynamic_range_db = total_rms_db - peak_db;

        // 倍频程分析
        let octave_bands = self.compute_octave_bands(&magnitude_db, frequency_resolution);

        SpectrumAnalysis {
            fft_size: self.fft_size,
            sample_rate: self.sample_rate,
            frequency_resolution,
            magnitude_db,
            octave_bands,
            total_rms_db,
            peak_db,
            dynamic_range_db,
        }
    }

    /// 计算标准倍频程分析
    fn compute_octave_bands(&self, magnitude_db: &[f64], freq_res: f64) -> Vec<OctaveAnalysis> {
        // 标准倍频程中心频率
        let bands = [
            (31.5, "Sub Bass"),
            (63.0, "Bass"),
            (125.0, "Low Mid"),
            (250.0, "Mid"),
            (500.0, "Upper Mid"),
            (1000.0, "Presence"),
            (2000.0, "High Mid"),
            (4000.0, "Presence High"),
            (8000.0, "Brilliance"),
            (16000.0, "Air"),
        ];

        bands
            .iter()
            .map(|&(center, label)| {
                // 1/3倍频程带宽
                let low = center / 1.26; // 2^(1/3) ≈ 1.26
                let high = center * 1.26;

                let low_bin = (low / freq_res) as usize;
                let high_bin = (high / freq_res).min(magnitude_db.len() as f64) as usize;

                let mut energy_sum = 0.0;
                let mut peak: f64 = -120.0;
                let count = if high_bin > low_bin { high_bin - low_bin } else { 1 };

                for bin in low_bin..high_bin.min(magnitude_db.len()) {
                    energy_sum += 10.0_f64.powf(magnitude_db[bin] / 10.0);
                    peak = peak.max(magnitude_db[bin]);
                }

                let energy_db = if count > 0 && energy_sum > 0.0 {
                    10.0 * (energy_sum / count as f64).log10()
                } else {
                    -120.0
                };

                OctaveAnalysis {
                    center_frequency: center,
                    energy_db,
                    peak_db: peak,
                    label: label.to_string(),
                }
            })
            .collect()
    }

    /// 多帧平均频谱分析
    pub fn analyze_average(&self, audio: &[f64], hop_size: usize) -> SpectrumAnalysis {
        let num_frames = if audio.len() > self.fft_size {
            (audio.len() - self.fft_size) / hop_size + 1
        } else {
            1
        };

        if num_frames <= 1 {
            return self.analyze(audio);
        }

        // 简化：分析第一帧
        // 完整实现应对所有帧取平均
        let first_frame = &audio[..self.fft_size.min(audio.len())];
        self.analyze(first_frame)
    }
}

// ── 混音建议 ──────────────────────────────────────────────

/// EQ建议
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct EqSuggestion {
    /// 频段标签
    pub band_label: String,
    /// 中心频率 (Hz)
    pub frequency: f64,
    /// 增益 (dB)
    pub gain_db: f64,
    /// Q值
    pub q: f64,
    /// 原因说明
    pub reason: String,
}

/// 压缩建议
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CompressionSuggestion {
    /// 阈值 (dB)
    pub threshold_db: f64,
    /// 压缩比
    pub ratio: f64,
    /// 启动时间 (ms)
    pub attack_ms: f64,
    /// 释放时间 (ms)
    pub release_ms: f64,
    /// 原因说明
    pub reason: String,
}

/// 混音建议
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MixSuggestion {
    /// 轨道名称
    pub track_name: String,
    /// 建议音量 (dB)
    pub volume_db: f64,
    /// 建议声像 [-1.0, 1.0]
    pub pan: f64,
    /// EQ建议列表
    pub eq_suggestions: Vec<EqSuggestion>,
    /// 压缩建议
    pub compression: Option<CompressionSuggestion>,
    /// 总体建议说明
    pub notes: Vec<String>,
    /// 置信度
    pub confidence: f64,
}

impl MixSuggestion {
    /// 创建空建议
    pub fn new(track_name: &str) -> Self {
        Self {
            track_name: track_name.to_string(),
            volume_db: 0.0,
            pan: 0.0,
            eq_suggestions: Vec::new(),
            compression: None,
            notes: Vec::new(),
            confidence: 0.5,
        }
    }
}

// ── 自动混音配置 ──────────────────────────────────────────

/// 音乐风格
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum MixStyle {
    Pop,
    Rock,
    EDM,
    Classical,
    Jazz,
    HipHop,
    LoFi,
    Metal,
}

/// 自动混音配置
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AutoMixProfile {
    /// 风格名称
    pub style: MixStyle,
    /// 目标LUFS
    pub target_lufs: f64,
    /// 鼓组音量偏移 (dB)
    pub drums_volume_offset: f64,
    /// 贝斯音量偏移 (dB)
    pub bass_volume_offset: f64,
    /// 人声音量偏移 (dB)
    pub vocal_volume_offset: f64,
    /// 乐器音量偏移 (dB)
    pub instruments_volume_offset: f64,
    /// 鼓组声像策略
    pub drums_pan_strategy: PanStrategy,
    /// 贝斯声像策略
    pub bass_pan_strategy: PanStrategy,
    /// 人声声像策略
    pub vocal_pan_strategy: PanStrategy,
    /// 压缩配置
    pub compression_preset: CompressionPreset,
    /// EQ特征
    pub eq_character: EqCharacter,
}

/// 声像策略
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum PanStrategy {
    /// 居中
    Center,
    /// 轻微偏移
    Slight,
    /// 宽声场
    Wide,
    /// 窄声场
    Narrow,
}

/// 压缩预设
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum CompressionPreset {
    /// 轻度
    Light,
    /// 中度
    Medium,
    /// 重度
    Heavy,
    /// 极限（限幅）
    Brick,
    /// 无
    None,
}

/// EQ特征
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum EqCharacter {
    /// 平坦
    Flat,
    /// 温暖（提升低频）
    Warm,
    /// 明亮（提升高频）
    Bright,
    /// V形（提升低高频，衰减中频）
    VShape,
    /// 中频突出
    MidScoop,
}

impl AutoMixProfile {
    /// Pop风格配置
    pub fn pop() -> Self {
        Self {
            style: MixStyle::Pop,
            target_lufs: -14.0,
            drums_volume_offset: -1.0,
            bass_volume_offset: -2.0,
            vocal_volume_offset: 2.0,
            instruments_volume_offset: 0.0,
            drums_pan_strategy: PanStrategy::Wide,
            bass_pan_strategy: PanStrategy::Center,
            vocal_pan_strategy: PanStrategy::Center,
            compression_preset: CompressionPreset::Medium,
            eq_character: EqCharacter::Bright,
        }
    }

    /// Rock风格配置
    pub fn rock() -> Self {
        Self {
            style: MixStyle::Rock,
            target_lufs: -12.0,
            drums_volume_offset: 1.0,
            bass_volume_offset: -1.0,
            vocal_volume_offset: 1.0,
            instruments_volume_offset: 1.0,
            drums_pan_strategy: PanStrategy::Wide,
            bass_pan_strategy: PanStrategy::Center,
            vocal_pan_strategy: PanStrategy::Center,
            compression_preset: CompressionPreset::Medium,
            eq_character: EqCharacter::VShape,
        }
    }

    /// EDM风格配置
    pub fn edm() -> Self {
        Self {
            style: MixStyle::EDM,
            target_lufs: -10.0,
            drums_volume_offset: 2.0,
            bass_volume_offset: 1.0,
            vocal_volume_offset: 0.0,
            instruments_volume_offset: -1.0,
            drums_pan_strategy: PanStrategy::Wide,
            bass_pan_strategy: PanStrategy::Center,
            vocal_pan_strategy: PanStrategy::Center,
            compression_preset: CompressionPreset::Heavy,
            eq_character: EqCharacter::VShape,
        }
    }

    /// Classical风格配置
    pub fn classical() -> Self {
        Self {
            style: MixStyle::Classical,
            target_lufs: -18.0,
            drums_volume_offset: -3.0,
            bass_volume_offset: 0.0,
            vocal_volume_offset: 0.0,
            instruments_volume_offset: 0.0,
            drums_pan_strategy: PanStrategy::Slight,
            bass_pan_strategy: PanStrategy::Slight,
            vocal_pan_strategy: PanStrategy::Center,
            compression_preset: CompressionPreset::Light,
            eq_character: EqCharacter::Flat,
        }
    }

    /// Jazz风格配置
    pub fn jazz() -> Self {
        Self {
            style: MixStyle::Jazz,
            target_lufs: -16.0,
            drums_volume_offset: -1.0,
            bass_volume_offset: 1.0,
            vocal_volume_offset: 1.0,
            instruments_volume_offset: 0.0,
            drums_pan_strategy: PanStrategy::Slight,
            bass_pan_strategy: PanStrategy::Center,
            vocal_pan_strategy: PanStrategy::Center,
            compression_preset: CompressionPreset::Light,
            eq_character: EqCharacter::Warm,
        }
    }

    /// Lo-Fi风格配置
    pub fn lofi() -> Self {
        Self {
            style: MixStyle::LoFi,
            target_lufs: -16.0,
            drums_volume_offset: 0.0,
            bass_volume_offset: 2.0,
            vocal_volume_offset: -1.0,
            instruments_volume_offset: -1.0,
            drums_pan_strategy: PanStrategy::Slight,
            bass_pan_strategy: PanStrategy::Center,
            vocal_pan_strategy: PanStrategy::Center,
            compression_preset: CompressionPreset::Medium,
            eq_character: EqCharacter::Warm,
        }
    }

    /// 根据风格获取配置
    pub fn for_style(style: MixStyle) -> Self {
        match style {
            MixStyle::Pop => Self::pop(),
            MixStyle::Rock => Self::rock(),
            MixStyle::EDM => Self::edm(),
            MixStyle::Classical => Self::classical(),
            MixStyle::Jazz => Self::jazz(),
            MixStyle::HipHop => Self {
                style: MixStyle::HipHop,
                target_lufs: -12.0,
                drums_volume_offset: 2.0,
                bass_volume_offset: 2.0,
                vocal_volume_offset: 1.0,
                instruments_volume_offset: -2.0,
                drums_pan_strategy: PanStrategy::Slight,
                bass_pan_strategy: PanStrategy::Center,
                vocal_pan_strategy: PanStrategy::Center,
                compression_preset: CompressionPreset::Medium,
                eq_character: EqCharacter::Warm,
            },
            MixStyle::LoFi => Self::lofi(),
            MixStyle::Metal => Self {
                style: MixStyle::Metal,
                target_lufs: -10.0,
                drums_volume_offset: 2.0,
                bass_volume_offset: 0.0,
                vocal_volume_offset: 1.0,
                instruments_volume_offset: 2.0,
                drums_pan_strategy: PanStrategy::Wide,
                bass_pan_strategy: PanStrategy::Center,
                vocal_pan_strategy: PanStrategy::Center,
                compression_preset: CompressionPreset::Heavy,
                eq_character: EqCharacter::VShape,
            },
        }
    }

    /// 将声像策略转为具体声像值
    pub fn pan_value(&self, strategy: PanStrategy) -> f64 {
        match strategy {
            PanStrategy::Center => 0.0,
            PanStrategy::Slight => 0.2,
            PanStrategy::Wide => 0.7,
            PanStrategy::Narrow => 0.1,
        }
    }

    /// 将压缩预设转为具体参数
    pub fn compression_params(&self) -> (f64, f64, f64, f64) {
        // (threshold_db, ratio, attack_ms, release_ms)
        match self.compression_preset {
            CompressionPreset::Light => (-18.0, 2.0, 30.0, 200.0),
            CompressionPreset::Medium => (-14.0, 4.0, 15.0, 150.0),
            CompressionPreset::Heavy => (-10.0, 8.0, 5.0, 100.0),
            CompressionPreset::Brick => (-6.0, 20.0, 1.0, 50.0),
            CompressionPreset::None => (-0.0, 1.0, 0.0, 0.0),
        }
    }
}

// ── 响度标准化 ────────────────────────────────────────────

/// 响度标准化结果
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct LoudnessResult {
    /// 当前LUFS
    pub current_lufs: f64,
    /// 目标LUFS
    pub target_lufs: f64,
    /// 需要的增益 (dB)
    pub gain_db: f64,
    /// 峰值 (dBTP)
    pub true_peak_db: f64,
    /// 是否需要限幅
    pub needs_limiting: bool,
}

/// 响度标准化器
pub struct LoudnessNormalizer {
    /// 目标LUFS
    target_lufs: f64,
    /// 最大真峰值 (dBTP)
    max_true_peak: f64,
}

impl LoudnessNormalizer {
    /// 创建新的响度标准化器
    pub fn new(target_lufs: f64) -> Self {
        Self {
            target_lufs,
            max_true_peak: -1.0,
        }
    }

    /// 设置最大真峰值
    pub fn with_max_true_peak(mut self, peak: f64) -> Self {
        self.max_true_peak = peak;
        self
    }

    /// 测量LUFS（简化版，使用RMS近似）
    pub fn measure_lufs(&self, audio: &[f64], sample_rate: f64) -> f64 {
        // 简化LUFS计算：使用K加权滤波器的RMS
        // 完整实现需要ITU-R BS.1770-4标准

        // Step 1: 简单的高频预加重（近似K加权）
        let mut weighted = vec![0.0f64; audio.len()];
        if audio.len() > 1 {
            weighted[0] = audio[0];
            for i in 1..audio.len() {
                // 简单一阶高通
                weighted[i] = audio[i] - 0.95 * audio[i - 1];
            }
        }

        // Step 2: 计算RMS
        let rms: f64 = if weighted.is_empty() {
            0.0
        } else {
            (weighted.iter().map(|&s| s * s).sum::<f64>() / weighted.len() as f64).sqrt()
        };

        // Step 3: 转为LUFS（近似）
        // 完整的LUFS计算更复杂，这里用简单近似
        if rms > 1e-10 {
            -0.691 + 10.0 * rms.log10()
        } else {
            -120.0
        }
    }

    /// 计算响度标准化所需增益
    pub fn analyze(&self, audio: &[f64], sample_rate: f64) -> LoudnessResult {
        let current_lufs = self.measure_lufs(audio, sample_rate);
        let gain_db = self.target_lufs - current_lufs;

        // 计算真峰值
        let true_peak = audio.iter().cloned().fold(0.0f64, |a, b| a.abs().max(b.abs()));
        let true_peak_db = if true_peak > 1e-10 {
            20.0 * true_peak.log10()
        } else {
            -120.0
        };

        // 应用增益后的峰值
        let new_peak_db = true_peak_db + gain_db;
        let needs_limiting = new_peak_db > self.max_true_peak;

        LoudnessResult {
            current_lufs,
            target_lufs: self.target_lufs,
            gain_db,
            true_peak_db: true_peak_db,
            needs_limiting,
        }
    }

    /// 应用响度标准化
    pub fn normalize(&self, audio: &[f64], sample_rate: f64) -> Vec<f64> {
        let result = self.analyze(audio, sample_rate);
        let gain = 10.0_f64.powf(result.gain_db / 20.0);

        let mut output = audio.to_vec();

        for sample in &mut output {
            *sample *= gain;

            // 简单软限幅
            if result.needs_limiting {
                let threshold = 10.0_f64.powf(self.max_true_peak / 20.0);
                if sample.abs() > threshold {
                    *sample = threshold * sample.signum() * (1.0 - (-(sample.abs() - threshold) * 10.0).exp());
                }
            }
        }

        output
    }
}

// ── 智能混音引擎 ──────────────────────────────────────────

/// 轨道分析数据
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TrackAnalysis {
    /// 轨道名称
    pub name: String,
    /// 轨道类型
    pub track_role: TrackRole,
    /// 频谱分析
    pub spectrum: SpectrumAnalysis,
    /// 响度 (LUFS)
    pub loudness_lufs: f64,
    /// 峰值 (dB)
    pub peak_db: f64,
    /// 动态范围 (dB)
    pub dynamic_range_db: f64,
}

/// 轨道角色
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum TrackRole {
    /// 鼓组
    Drums,
    /// 贝斯
    Bass,
    /// 人声
    Vocal,
    /// 旋律乐器
    MelodicInstrument,
    /// 和声乐器
    HarmonicInstrument,
    /// 效果/氛围
    Effects,
    /// 主输出
    Master,
    /// 未识别
    Unknown,
}

impl TrackRole {
    /// 从轨道名称推断角色
    pub fn from_name(name: &str) -> Self {
        let lower = name.to_lowercase();
        if lower.contains("kick") || lower.contains("snare") || lower.contains("hi")
            || lower.contains("drum") || lower.contains("perc")
        {
            Self::Drums
        } else if lower.contains("bass") || lower.contains("sub") {
            Self::Bass
        } else if lower.contains("vocal") || lower.contains("voice") || lower.contains("sing") {
            Self::Vocal
        } else if lower.contains("lead") || lower.contains("solo") {
            Self::MelodicInstrument
        } else if lower.contains("pad") || lower.contains("chord") || lower.contains("keys")
            || lower.contains("guitar") || lower.contains("piano") || lower.contains("synth")
        {
            Self::HarmonicInstrument
        } else if lower.contains("fx") || lower.contains("ambient") || lower.contains("effect") {
            Self::Effects
        } else if lower.contains("master") || lower.contains("mix") || lower.contains("main") {
            Self::Master
        } else {
            Self::Unknown
        }
    }
}

/// 智能混音引擎
pub struct SmartMixEngine {
    /// 频谱分析器
    analyzer: FrequencyAnalyzer,
    /// 响度标准化器
    normalizer: LoudnessNormalizer,
    /// 自动混音配置
    profile: AutoMixProfile,
}

impl SmartMixEngine {
    /// 创建新的智能混音引擎
    pub fn new(sample_rate: f64, style: MixStyle) -> Self {
        Self {
            analyzer: FrequencyAnalyzer::new(sample_rate, 4096),
            normalizer: LoudnessNormalizer::new(-14.0),
            profile: AutoMixProfile::for_style(style),
        }
    }

    /// 分析轨道
    pub fn analyze_track(&self, name: &str, audio: &[f64]) -> TrackAnalysis {
        let spectrum = self.analyzer.analyze(audio);
        let loudness_lufs = self.normalizer.measure_lufs(audio, self.analyzer.sample_rate);

        TrackAnalysis {
            name: name.to_string(),
            track_role: TrackRole::from_name(name),
            spectrum,
            loudness_lufs,
            peak_db: audio.iter().cloned().fold(0.0f64, |a, b| a.abs().max(b.abs())),
            dynamic_range_db: 0.0, // 简化
        }
    }

    /// 生成混音建议
    pub fn suggest(&self, analyses: &[TrackAnalysis]) -> Vec<MixSuggestion> {
        let mut suggestions = Vec::new();

        for analysis in analyses {
            let mut suggestion = MixSuggestion::new(&analysis.name);

            // 根据轨道角色和风格配置生成建议
            let volume_offset = match analysis.track_role {
                TrackRole::Drums => self.profile.drums_volume_offset,
                TrackRole::Bass => self.profile.bass_volume_offset,
                TrackRole::Vocal => self.profile.vocal_volume_offset,
                TrackRole::MelodicInstrument | TrackRole::HarmonicInstrument => {
                    self.profile.instruments_volume_offset
                }
                TrackRole::Master => 0.0,
                _ => 0.0,
            };

            suggestion.volume_db = volume_offset;

            // 声像建议
            suggestion.pan = match analysis.track_role {
                TrackRole::Drums => self.profile.pan_value(self.profile.drums_pan_strategy),
                TrackRole::Bass => self.profile.pan_value(self.profile.bass_pan_strategy),
                TrackRole::Vocal => self.profile.pan_value(self.profile.vocal_pan_strategy),
                TrackRole::MelodicInstrument => self.profile.pan_value(PanStrategy::Slight),
                TrackRole::HarmonicInstrument => self.profile.pan_value(PanStrategy::Wide),
                _ => 0.0,
            };

            // EQ建议：基于频谱分析
            suggestion.eq_suggestions = self.suggest_eq(analysis);

            // 压缩建议
            suggestion.compression = self.suggest_compression(analysis);

            // 说明
            suggestion.notes.push(format!(
                "轨道角色: {:?}",
                analysis.track_role
            ));
            suggestion.notes.push(format!(
                "响度: {:.1} LUFS",
                analysis.loudness_lufs
            ));
            suggestion.confidence = 0.7;

            suggestions.push(suggestion);
        }

        // 频率冲突检测
        self.detect_frequency_conflicts(analyses, &mut suggestions);

        suggestions
    }

    /// 生成EQ建议
    fn suggest_eq(&self, analysis: &TrackAnalysis) -> Vec<EqSuggestion> {
        let mut suggestions = Vec::new();

        // 检查低频过多
        let sub_bass_energy = analysis.spectrum.octave_bands
            .iter()
            .find(|b| b.center_frequency < 50.0)
            .map(|b| b.energy_db)
            .unwrap_or(-60.0);

        let bass_energy = analysis.spectrum.octave_bands
            .iter()
            .find(|b| (b.center_frequency - 63.0).abs() < 10.0)
            .map(|b| b.energy_db)
            .unwrap_or(-60.0);

        let mid_energy = analysis.spectrum.octave_bands
            .iter()
            .find(|b| (b.center_frequency - 500.0).abs() < 50.0)
            .map(|b| b.energy_db)
            .unwrap_or(-60.0);

        let high_energy = analysis.spectrum.octave_bands
            .iter()
            .find(|b| (b.center_frequency - 8000.0).abs() < 500.0)
            .map(|b| b.energy_db)
            .unwrap_or(-60.0);

        // 根据轨道角色给出EQ建议
        match analysis.track_role {
            TrackRole::Vocal => {
                suggestions.push(EqSuggestion {
                    band_label: "High-pass".to_string(),
                    frequency: 80.0,
                    gain_db: -12.0,
                    q: 0.7,
                    reason: "人声低频切除，去除隆隆声".to_string(),
                });
                if high_energy < mid_energy - 6.0 {
                    suggestions.push(EqSuggestion {
                        band_label: "Presence boost".to_string(),
                        frequency: 3000.0,
                        gain_db: 2.0,
                        q: 1.5,
                        reason: "提升人声清晰度".to_string(),
                    });
                }
            }
            TrackRole::Bass => {
                if sub_bass_energy > bass_energy + 3.0 {
                    suggestions.push(EqSuggestion {
                        band_label: "Sub cut".to_string(),
                        frequency: 40.0,
                        gain_db: -3.0,
                        q: 1.0,
                        reason: "削减次低频，避免混浊".to_string(),
                    });
                }
            }
            TrackRole::Drums => {
                suggestions.push(EqSuggestion {
                    band_label: "Low cut".to_string(),
                    frequency: 30.0,
                    gain_db: -6.0,
                    q: 0.7,
                    reason: "鼓组低频切除".to_string(),
                });
            }
            _ => {}
        }

        // 风格相关EQ
        match self.profile.eq_character {
            EqCharacter::Warm => {
                suggestions.push(EqSuggestion {
                    band_label: "Warmth".to_string(),
                    frequency: 200.0,
                    gain_db: 1.5,
                    q: 0.8,
                    reason: "温暖感提升".to_string(),
                });
            }
            EqCharacter::Bright => {
                suggestions.push(EqSuggestion {
                    band_label: "Air".to_string(),
                    frequency: 12000.0,
                    gain_db: 1.5,
                    q: 0.7,
                    reason: "明亮感提升".to_string(),
                });
            }
            EqCharacter::VShape => {
                suggestions.push(EqSuggestion {
                    band_label: "Low boost".to_string(),
                    frequency: 80.0,
                    gain_db: 2.0,
                    q: 0.8,
                    reason: "V形EQ低频提升".to_string(),
                });
                suggestions.push(EqSuggestion {
                    band_label: "High boost".to_string(),
                    frequency: 8000.0,
                    gain_db: 2.0,
                    q: 0.8,
                    reason: "V形EQ高频提升".to_string(),
                });
            }
            _ => {}
        }

        suggestions
    }

    /// 生成压缩建议
    fn suggest_compression(&self, analysis: &TrackAnalysis) -> Option<CompressionSuggestion> {
        let (threshold, ratio, attack, release) = self.profile.compression_params();

        if ratio <= 1.0 {
            return None;
        }

        let reason = match analysis.track_role {
            TrackRole::Vocal => "人声动态控制".to_string(),
            TrackRole::Bass => "贝斯动态一致性".to_string(),
            TrackRole::Drums => "鼓组力度控制".to_string(),
            TrackRole::Master => "总线压缩".to_string(),
            _ => "动态范围控制".to_string(),
        };

        Some(CompressionSuggestion {
            threshold_db: threshold,
            ratio,
            attack_ms: attack,
            release_ms: release,
            reason,
        })
    }

    /// 检测频率冲突
    fn detect_frequency_conflicts(
        &self,
        analyses: &[TrackAnalysis],
        suggestions: &mut [MixSuggestion],
    ) {
        // 检查低频冲突（贝斯vs鼓组）
        let bass_tracks: Vec<&TrackAnalysis> = analyses
            .iter()
            .filter(|a| a.track_role == TrackRole::Bass)
            .collect();
        let drum_tracks: Vec<&TrackAnalysis> = analyses
            .iter()
            .filter(|a| a.track_role == TrackRole::Drums)
            .collect();

        if !bass_tracks.is_empty() && !drum_tracks.is_empty() {
            // 建议侧链压缩
            for suggestion in suggestions.iter_mut() {
                if suggestion.compression.is_none() {
                    match analyses.iter().find(|a| a.name == suggestion.track_name) {
                        Some(a) if a.track_role == TrackRole::Bass => {
                            suggestion.compression = Some(CompressionSuggestion {
                                threshold_db: -12.0,
                                ratio: 4.0,
                                attack_ms: 5.0,
                                release_ms: 100.0,
                                reason: "侧链压缩：贝斯为鼓组让出空间".to_string(),
                            });
                            suggestion.notes.push("检测到低频冲突：建议使用侧链压缩".to_string());
                        }
                        _ => {}
                    }
                }
            }
        }
    }

    /// 应用混音建议到音频
    pub fn apply_suggestion(&self, audio: &[f64], suggestion: &MixSuggestion) -> Vec<f64> {
        let mut output = audio.to_vec();

        // 应用音量
        let gain = 10.0_f64.powf(suggestion.volume_db / 20.0);
        for sample in &mut output {
            *sample *= gain;
        }

        // 简化：不实现EQ和压缩的实际DSP处理
        // 完整实现应使用biquad滤波器和压缩器

        output
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_frequency_analyzer() {
        let analyzer = FrequencyAnalyzer::new(44100.0, 1024);
        let signal = vec![0.5f64; 1024];
        let result = analyzer.analyze(&signal);
        assert_eq!(result.fft_size, 1024);
        assert!(!result.magnitude_db.is_empty());
        assert!(!result.octave_bands.is_empty());
    }

    #[test]
    fn test_octave_bands_count() {
        let analyzer = FrequencyAnalyzer::new(44100.0, 1024);
        let signal = vec![0.0f64; 1024];
        let result = analyzer.analyze(&signal);
        assert_eq!(result.octave_bands.len(), 10);
    }

    #[test]
    fn test_auto_mix_profile_pop() {
        let profile = AutoMixProfile::pop();
        assert_eq!(profile.style, MixStyle::Pop);
        assert!((profile.target_lufs - (-14.0)).abs() < 1e-10);
    }

    #[test]
    fn test_auto_mix_profile_for_style() {
        for style in [MixStyle::Pop, MixStyle::Rock, MixStyle::EDM, MixStyle::Classical, MixStyle::Jazz] {
            let profile = AutoMixProfile::for_style(style);
            assert_eq!(profile.style, style);
        }
    }

    #[test]
    fn test_compression_params() {
        let profile = AutoMixProfile::pop();
        let (threshold, ratio, _, _) = profile.compression_params();
        assert!(threshold < 0.0);
        assert!(ratio > 1.0);
    }

    #[test]
    fn test_pan_strategy() {
        let profile = AutoMixProfile::pop();
        assert!((profile.pan_value(PanStrategy::Center) - 0.0).abs() < 1e-10);
        assert!(profile.pan_value(PanStrategy::Wide) > 0.0);
    }

    #[test]
    fn test_loudness_normalizer() {
        let normalizer = LoudnessNormalizer::new(-14.0);
        let signal = vec![0.1f64; 44100];
        let lufs = normalizer.measure_lufs(&signal, 44100.0);
        assert!(lufs > -120.0);
    }

    #[test]
    fn test_loudness_normalize() {
        let normalizer = LoudnessNormalizer::new(-14.0);
        let signal = vec![0.1f64; 44100];
        let result = normalizer.analyze(&signal, 44100.0);
        assert!((result.target_lufs - (-14.0)).abs() < 1e-10);
    }

    #[test]
    fn test_track_role_from_name() {
        assert_eq!(TrackRole::from_name("Kick Drum"), TrackRole::Drums);
        assert_eq!(TrackRole::from_name("Bass"), TrackRole::Bass);
        assert_eq!(TrackRole::from_name("Lead Vocal"), TrackRole::Vocal);
        assert_eq!(TrackRole::from_name("Piano"), TrackRole::HarmonicInstrument);
    }

    #[test]
    fn test_smart_mix_engine() {
        let engine = SmartMixEngine::new(44100.0, MixStyle::Pop);
        let audio = vec![0.5f64; 4096];
        let analysis = engine.analyze_track("Test", &audio);
        assert_eq!(analysis.name, "Test");
    }

    #[test]
    fn test_smart_mix_suggest() {
        let engine = SmartMixEngine::new(44100.0, MixStyle::Pop);
        let audio = vec![0.5f64; 4096];
        let analyses = vec![
            engine.analyze_track("Kick Drum", &audio),
            engine.analyze_track("Bass", &audio),
            engine.analyze_track("Lead Vocal", &audio),
        ];
        let suggestions = engine.suggest(&analyses);
        assert_eq!(suggestions.len(), 3);
    }

    #[test]
    fn test_mix_suggestion_new() {
        let suggestion = MixSuggestion::new("Test");
        assert_eq!(suggestion.track_name, "Test");
        assert!(suggestion.eq_suggestions.is_empty());
    }
}
