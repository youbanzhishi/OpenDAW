//! 扒带引擎 — 音频→MIDI扒带闭环
//!
//! - TranscriptionEngine: 音频→MIDI扒带主引擎
//! - PitchDetector: 基音检测（YIN算法简化版）
//! - BeatDetector: 节拍检测（onset detection + tempo estimation）
//! - TranscriptionResult: 扒带结果（MIDI音符 + 节拍标记 + 调式推断）
//! - TranscriptionToProject: 扒带结果→项目转换（自动创建轨道+分配乐器）


use serde::{Deserialize, Serialize};

use crate::pattern::{MidiNote, Pattern, PatternType};
use crate::chord::{NoteName, Mode};

// ── 基音检测器 ──────────────────────────────────────────────

/// 基音检测结果
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PitchDetection {
    /// 检测到的频率 (Hz)，None表示未检测到基音
    pub frequency: Option<f64>,
    /// 置信度 [0.0, 1.0]
    pub confidence: f64,
    /// 对应MIDI音高（如有）
    pub midi_pitch: Option<u8>,
    /// 对应音分偏差 (-50.0, +50.0)
    pub cents_deviation: Option<f64>,
}

/// YIN算法简化版 — 基音检测器
pub struct PitchDetector {
    /// 采样率
    sample_rate: f64,
    /// YIN阈值（0.0~1.0，越低越严格）
    threshold: f64,
    /// 最低检测频率 (Hz)
    min_frequency: f64,
    /// 最高检测频率 (Hz)
    max_frequency: f64,
    /// 最小帧长度
    frame_size: usize,
}

impl PitchDetector {
    /// 创建新的基音检测器
    pub fn new(sample_rate: f64) -> Self {
        Self {
            sample_rate,
            threshold: 0.15,
            min_frequency: 50.0,
            max_frequency: 4000.0,
            frame_size: 2048,
        }
    }

    /// 设置检测阈值
    pub fn with_threshold(mut self, threshold: f64) -> Self {
        self.threshold = threshold.clamp(0.01, 1.0);
        self
    }

    /// 设置频率检测范围
    pub fn with_frequency_range(mut self, min: f64, max: f64) -> Self {
        self.min_frequency = min;
        self.max_frequency = max;
        self
    }

    /// 设置帧长度
    pub fn with_frame_size(mut self, size: usize) -> Self {
        self.frame_size = size;
        self
    }

    /// 检测单帧基音
    pub fn detect(&self, frame: &[f64]) -> PitchDetection {
        if frame.len() < self.frame_size / 2 {
            return PitchDetection {
                frequency: None,
                confidence: 0.0,
                midi_pitch: None,
                cents_deviation: None,
            };
        }

        // 检测静音：如果信号能量极低，直接返回无音高
        let rms = (frame.iter().map(|&s| s * s).sum::<f64>() / frame.len() as f64).sqrt();
        if rms < 1e-6 {
            return PitchDetection {
                frequency: None,
                confidence: 0.0,
                midi_pitch: None,
                cents_deviation: None,
            };
        }

        // YIN差分函数
        let half = self.frame_size / 2;
        let mut diff = vec![0.0f64; half];

        for tau in 1..half {
            let mut sum = 0.0;
            for j in 0..half {
                if j + tau < frame.len() {
                    let d = frame[j] - frame[j + tau];
                    sum += d * d;
                }
            }
            diff[tau] = sum;
        }

        // 累积均值归一化差分函数 (CMNDF)
        let mut cmndf = vec![1.0f64; half];
        cmndf[0] = 1.0;
        let mut running_sum = 0.0;

        for tau in 1..half {
            running_sum += diff[tau];
            cmndf[tau] = if running_sum > 0.0 {
                diff[tau] * tau as f64 / running_sum
            } else {
                1.0
            };
        }

        // 绝对阈值法：找到第一个低于阈值的tau
        let min_tau = (self.sample_rate / self.max_frequency) as usize;
        let max_tau = ((self.sample_rate / self.min_frequency) as usize).min(half - 1);

        if min_tau >= max_tau {
            return PitchDetection {
                frequency: None,
                confidence: 0.0,
                midi_pitch: None,
                cents_deviation: None,
            };
        }

        let mut best_tau = 0usize;
        let mut found = false;

        for tau in min_tau..=max_tau {
            if cmndf[tau] < self.threshold {
                // 找到局部最小值
                let mut local_min_tau = tau;
                let mut local_min_val = cmndf[tau];
                let mut t = tau + 1;
                while t < max_tau && cmndf[t] < self.threshold {
                    if cmndf[t] < local_min_val {
                        local_min_val = cmndf[t];
                        local_min_tau = t;
                    }
                    t += 1;
                }
                best_tau = local_min_tau;
                found = true;
                break;
            }
        }

        if !found {
            // 回退：选择全局最小值
            let mut min_val = f64::MAX;
            for tau in min_tau..=max_tau {
                if cmndf[tau] < min_val {
                    min_val = cmndf[tau];
                    best_tau = tau;
                }
            }
        }

        if best_tau == 0 {
            return PitchDetection {
                frequency: None,
                confidence: 0.0,
                midi_pitch: None,
                cents_deviation: None,
            };
        }

        // 抛物线插值提高精度
        let (refined_tau, confidence) = if best_tau > 0 && best_tau < half - 1 {
            let s0 = cmndf[best_tau - 1];
            let s1 = cmndf[best_tau];
            let s2 = cmndf[best_tau + 1];
            let shift = if (2.0 * s1 - s0 - s2).abs() > 1e-10 {
                (s0 - s2) / (2.0 * (2.0 * s1 - s0 - s2))
            } else {
                0.0
            };
            (best_tau as f64 + shift, 1.0 - s1)
        } else {
            (best_tau as f64, 1.0 - cmndf[best_tau])
        };

        if refined_tau <= 0.0 {
            return PitchDetection {
                frequency: None,
                confidence: 0.0,
                midi_pitch: None,
                cents_deviation: None,
            };
        }

        let frequency = self.sample_rate / refined_tau;

        // 频率→MIDI音高
        if frequency <= 0.0 {
            return PitchDetection {
                frequency: Some(frequency),
                confidence: confidence.clamp(0.0, 1.0),
                midi_pitch: None,
                cents_deviation: None,
            };
        }

        let midi_float = 69.0 + 12.0 * (frequency / 440.0).log2();
        let midi_pitch = midi_float.round().clamp(0.0, 127.0) as u8;
        let cents_deviation = (midi_float - midi_pitch as f64) * 100.0;

        PitchDetection {
            frequency: Some(frequency),
            confidence: confidence.clamp(0.0, 1.0),
            midi_pitch: Some(midi_pitch),
            cents_deviation: Some(cents_deviation),
        }
    }

    /// 对整段音频进行逐帧检测
    pub fn detect_all(&self, audio: &[f64], hop_size: usize) -> Vec<PitchDetection> {
        let mut results = Vec::new();
        let mut pos = 0;
        while pos + self.frame_size <= audio.len() {
            let frame = &audio[pos..pos + self.frame_size];
            results.push(self.detect(frame));
            pos += hop_size;
        }
        results
    }
}

// ── 节拍检测器 ──────────────────────────────────────────────

/// 节拍检测结果
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct BeatDetection {
    /// 检测到的BPM
    pub bpm: f64,
    /// BPM置信度
    pub bpm_confidence: f64,
    /// onset位置（秒）
    pub onsets: Vec<f64>,
    /// 节拍位置（秒）
    pub beats: Vec<f64>,
    /// 小节位置（秒）
    pub bar_positions: Vec<f64>,
    /// 拍号分子
    pub time_signature_num: u8,
    /// 拍号分母
    pub time_signature_den: u8,
}

/// onset检测方法
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum OnsetMethod {
    /// 频谱通量法
    SpectralFlux,
    /// 高频内容法
    HighFrequencyContent,
    /// 复合相位法
    PhaseDeviation,
}

/// 节拍检测器
pub struct BeatDetector {
    /// 采样率
    sample_rate: f64,
    /// onset检测方法
    onset_method: OnsetMethod,
    /// onset检测阈值
    onset_threshold: f64,
    /// 最小BPM
    min_bpm: f64,
    /// 最大BPM
    max_bpm: f64,
    /// 分析帧长度
    frame_size: usize,
    /// 帧移
    hop_size: usize,
}

impl BeatDetector {
    /// 创建新的节拍检测器
    pub fn new(sample_rate: f64) -> Self {
        Self {
            sample_rate,
            onset_method: OnsetMethod::SpectralFlux,
            onset_threshold: 0.5,
            min_bpm: 60.0,
            max_bpm: 200.0,
            frame_size: 1024,
            hop_size: 512,
        }
    }

    /// 设置onset检测方法
    pub fn with_onset_method(mut self, method: OnsetMethod) -> Self {
        self.onset_method = method;
        self
    }

    /// 设置onset阈值
    pub fn with_onset_threshold(mut self, threshold: f64) -> Self {
        self.onset_threshold = threshold.clamp(0.1, 1.0);
        self
    }

    /// 设置BPM范围
    pub fn with_bpm_range(mut self, min: f64, max: f64) -> Self {
        self.min_bpm = min;
        self.max_bpm = max;
        self
    }

    /// 检测节拍
    pub fn detect(&self, audio: &[f64]) -> BeatDetection {
        // Step 1: 计算onset强度函数
        let onset_curve = self.compute_onset_curve(audio);

        // Step 2: 峰值拾取得到onset
        let onsets = self.pick_onsets(&onset_curve);

        // Step 3: 自相关法估计BPM
        let (bpm, confidence) = self.estimate_bpm(&onset_curve);

        // Step 4: 从BPM推导节拍位置
        let beats = self.generate_beats(&onsets, bpm);

        // Step 5: 推断拍号
        let (ts_num, ts_den) = self.infer_time_signature(&beats, &onsets);

        // Step 6: 生成小节位置
        let beat_interval = 60.0 / bpm;
        let bar_interval = beat_interval * ts_num as f64;
        let bar_positions = if !beats.is_empty() {
            let start = beats[0];
            let end = audio.len() as f64 / self.sample_rate;
            let mut bars = Vec::new();
            let mut t = start;
            while t <= end {
                bars.push(t);
                t += bar_interval;
            }
            bars
        } else {
            Vec::new()
        };

        BeatDetection {
            bpm,
            bpm_confidence: confidence,
            onsets,
            beats,
            bar_positions,
            time_signature_num: ts_num,
            time_signature_den: ts_den,
        }
    }

    /// 计算onset强度函数
    fn compute_onset_curve(&self, audio: &[f64]) -> Vec<f64> {
        let num_frames = if audio.len() > self.frame_size {
            (audio.len() - self.frame_size) / self.hop_size + 1
        } else {
            return Vec::new();
        };

        // 简化FFT：使用幅度谱差分（spectral flux）
        let half = self.frame_size / 2;
        let mut prev_magnitude = vec![0.0f64; half];
        let mut onset_curve = Vec::with_capacity(num_frames);

        for i in 0..num_frames {
            let start = i * self.hop_size;
            let end = (start + self.frame_size).min(audio.len());

            if end - start < self.frame_size {
                break;
            }

            // 窗函数（Hann窗）
            let windowed: Vec<f64> = audio[start..end]
                .iter()
                .enumerate()
                .map(|(j, &s)| {
                    let w = 0.5 * (1.0 - (2.0 * std::f64::consts::PI * j as f64
                        / (self.frame_size - 1) as f64).cos());
                    s * w
                })
                .collect();

            // DFT幅度谱（简化版）
            let n = windowed.len();
            let mut magnitude = vec![0.0f64; half];

            for k in 0..half {
                let mut re = 0.0;
                let mut im = 0.0;
                for j in 0..n {
                    let angle = -2.0 * std::f64::consts::PI * k as f64 * j as f64 / n as f64;
                    re += windowed[j] * angle.cos();
                    im += windowed[j] * angle.sin();
                }
                magnitude[k] = (re * re + im * im).sqrt();
            }

            // Spectral flux: 正差分之和
            let mut flux = 0.0;
            for k in 0..half {
                let diff = magnitude[k] - prev_magnitude[k];
                if diff > 0.0 {
                    flux += diff;
                }
            }

            onset_curve.push(flux);
            prev_magnitude = magnitude;
        }

        onset_curve
    }

    /// 从onset曲线拾取峰值
    fn pick_onsets(&self, curve: &[f64]) -> Vec<f64> {
        if curve.is_empty() {
            return Vec::new();
        }

        let max_val = curve.iter().cloned().fold(0.0f64, f64::max);
        let threshold = max_val * self.onset_threshold;

        let min_gap_frames = (0.05 * self.sample_rate / self.hop_size as f64) as usize;

        let mut onsets = Vec::new();
        let mut last_onset_frame = 0usize;

        for i in 1..curve.len().saturating_sub(1) {
            if curve[i] > threshold
                && curve[i] > curve[i - 1]
                && curve[i] > curve[i + 1]
                && i - last_onset_frame >= min_gap_frames
            {
                let time = i as f64 * self.hop_size as f64 / self.sample_rate;
                onsets.push(time);
                last_onset_frame = i;
            }
        }

        onsets
    }

    /// 自相关法估计BPM
    fn estimate_bpm(&self, curve: &[f64]) -> (f64, f64) {
        if curve.is_empty() {
            return (120.0, 0.0);
        }

        let min_lag = (60.0 / self.max_bpm * self.sample_rate / self.hop_size as f64) as usize;
        let max_lag = (60.0 / self.min_bpm * self.sample_rate / self.hop_size as f64) as usize;

        let max_lag = max_lag.min(curve.len() / 2);
        if min_lag >= max_lag {
            return (120.0, 0.0);
        }

        let mean: f64 = curve.iter().sum::<f64>() / curve.len() as f64;
        let centered: Vec<f64> = curve.iter().map(|&x| x - mean).collect();

        let norm = centered.iter().map(|x| x * x).sum::<f64>();
        if norm < 1e-10 {
            return (120.0, 0.0);
        }

        let mut autocorr = vec![0.0f64; max_lag + 1];

        for lag in min_lag..=max_lag {
            let mut sum = 0.0;
            for i in 0..centered.len() - lag {
                sum += centered[i] * centered[i + lag];
            }
            autocorr[lag] = sum / norm;
        }

        let mut best_lag = min_lag;
        let mut best_val = autocorr[min_lag];

        for lag in min_lag..=max_lag {
            if autocorr[lag] > best_val {
                best_val = autocorr[lag];
                best_lag = lag;
            }
        }

        if best_lag == 0 {
            return (120.0, 0.0);
        }

        let bpm = 60.0 * self.sample_rate / self.hop_size as f64 / best_lag as f64;
        let confidence = best_val.clamp(0.0, 1.0);

        (bpm, confidence)
    }

    /// 从BPM和onsets生成节拍位置
    fn generate_beats(&self, onsets: &[f64], bpm: f64) -> Vec<f64> {
        if onsets.is_empty() || bpm <= 0.0 {
            return Vec::new();
        }

        let beat_interval = 60.0 / bpm;
        let start = onsets[0];

        let mut beats = Vec::new();
        let mut t = start;
        while t >= 0.0 {
            beats.push(t);
            t -= beat_interval;
        }
        beats.sort_by(|a, b| a.partial_cmp(b).unwrap());

        t = start + beat_interval;
        while t < 300.0 {
            beats.push(t);
            t += beat_interval;
        }

        beats
    }

    /// 推断拍号
    fn infer_time_signature(&self, _beats: &[f64], onsets: &[f64]) -> (u8, u8) {
        if onsets.len() < 4 {
            return (4, 4);
        }

        let intervals: Vec<f64> = onsets.windows(2).map(|w| w[1] - w[0]).collect();
        if intervals.is_empty() {
            return (4, 4);
        }

        let mut count_3 = 0usize;
        let mut count_4 = 0usize;

        for chunk in intervals.chunks(3) {
            if chunk.len() == 3 {
                count_3 += 1;
            }
        }
        for chunk in intervals.chunks(4) {
            if chunk.len() == 4 {
                count_4 += 1;
            }
        }

        if count_3 > count_4 * 2 {
            (3, 4)
        } else {
            (4, 4)
        }
    }
}

// ── 扒带结果 ──────────────────────────────────────────────

/// 单个扒带音符
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TranscribedNote {
    /// MIDI音高
    pub pitch: u8,
    /// 起始时间（秒）
    pub start_time: f64,
    /// 持续时间（秒）
    pub duration: f64,
    /// 力度
    pub velocity: u8,
    /// 基音置信度
    pub confidence: f64,
    /// 音分偏差
    pub cents_deviation: f64,
}

/// 调式推断结果
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct KeyEstimate {
    /// 推断的主音
    pub tonic: NoteName,
    /// 推断的调式
    pub mode: Mode,
    /// 置信度
    pub confidence: f64,
}

/// 扒带结果
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TranscriptionResult {
    /// 检测到的MIDI音符
    pub notes: Vec<TranscribedNote>,
    /// 节拍检测结果
    pub beat_detection: BeatDetection,
    /// 调式推断
    pub key_estimate: Option<KeyEstimate>,
    /// 音频总时长（秒）
    pub duration_secs: f64,
    /// 源音频采样率
    pub sample_rate: f64,
    /// 检测质量评分 [0, 100]
    pub quality_score: f64,
}

impl TranscriptionResult {
    /// 计算检测质量评分
    pub fn compute_quality_score(&mut self) -> f64 {
        let mut score = 100.0;

        if !self.notes.is_empty() {
            let avg_confidence: f64 =
                self.notes.iter().map(|n| n.confidence).sum::<f64>() / self.notes.len() as f64;
            score *= avg_confidence;
        }

        score *= self.beat_detection.bpm_confidence.max(0.3);

        if self.notes.is_empty() {
            score *= 0.1;
        }

        self.quality_score = score.clamp(0.0, 100.0);
        self.quality_score
    }

    /// 转换为MidiNote列表
    pub fn to_midi_notes(&self) -> Vec<MidiNote> {
        let beat_duration = 60.0 / self.beat_detection.bpm;
        self.notes
            .iter()
            .map(|n| {
                let start_beat = n.start_time / beat_duration;
                let duration_beats = n.duration / beat_duration;
                MidiNote::new(n.pitch, start_beat, duration_beats, n.velocity)
            })
            .collect()
    }
}

// ── 扒带引擎 ──────────────────────────────────────────────

/// 扒带引擎配置
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TranscriptionConfig {
    /// 采样率
    pub sample_rate: f64,
    /// 基音检测阈值
    pub pitch_threshold: f64,
    /// onset检测阈值
    pub onset_threshold: f64,
    /// BPM范围
    pub min_bpm: f64,
    pub max_bpm: f64,
    /// 最小音符持续时间（秒）
    pub min_note_duration: f64,
    /// 是否推断调式
    pub estimate_key: bool,
}

impl Default for TranscriptionConfig {
    fn default() -> Self {
        Self {
            sample_rate: 44100.0,
            pitch_threshold: 0.15,
            onset_threshold: 0.5,
            min_bpm: 60.0,
            max_bpm: 200.0,
            min_note_duration: 0.05,
            estimate_key: true,
        }
    }
}

/// 扒带引擎 — 音频→MIDI转换
pub struct TranscriptionEngine {
    config: TranscriptionConfig,
    pitch_detector: PitchDetector,
    beat_detector: BeatDetector,
}

impl TranscriptionEngine {
    /// 创建新的扒带引擎
    pub fn new(config: TranscriptionConfig) -> Self {
        let pitch_detector = PitchDetector::new(config.sample_rate)
            .with_threshold(config.pitch_threshold);

        let beat_detector = BeatDetector::new(config.sample_rate)
            .with_onset_threshold(config.onset_threshold)
            .with_bpm_range(config.min_bpm, config.max_bpm);

        Self {
            config,
            pitch_detector,
            beat_detector,
        }
    }

    /// 使用默认配置
    pub fn with_sample_rate(sample_rate: f64) -> Self {
        let mut config = TranscriptionConfig::default();
        config.sample_rate = sample_rate;
        Self::new(config)
    }

    /// 执行扒带
    pub fn transcribe(&self, audio: &[f64]) -> TranscriptionResult {
        let duration_secs = audio.len() as f64 / self.config.sample_rate;

        // Step 1: 节拍检测
        let beat_detection = self.beat_detector.detect(audio);

        // Step 2: 逐帧基音检测
        let hop_size = self.pitch_detector.frame_size / 4;
        let pitch_detections = self.pitch_detector.detect_all(audio, hop_size);

        // Step 3: 基音轨迹→音符
        let notes = self.pitches_to_notes(&pitch_detections, hop_size);

        // Step 4: 调式推断
        let key_estimate = if self.config.estimate_key && !notes.is_empty() {
            Some(self.estimate_key(&notes))
        } else {
            None
        };

        let mut result = TranscriptionResult {
            notes,
            beat_detection,
            key_estimate,
            duration_secs,
            sample_rate: self.config.sample_rate,
            quality_score: 0.0,
        };

        result.compute_quality_score();
        result
    }

    /// 将逐帧基音检测结果转换为音符
    fn pitches_to_notes(
        &self,
        detections: &[PitchDetection],
        hop_size: usize,
    ) -> Vec<TranscribedNote> {
        if detections.is_empty() {
            return Vec::new();
        }

        let frame_duration = hop_size as f64 / self.config.sample_rate;
        let mut notes = Vec::new();

        let mut current_pitch: Option<u8> = None;
        let mut start_time = 0.0;
        let mut total_confidence = 0.0;
        let mut frame_count = 0usize;
        let mut total_cents = 0.0;

        for (i, det) in detections.iter().enumerate() {
            let time = i as f64 * frame_duration;

            match (current_pitch, det.midi_pitch) {
                (None, Some(pitch)) => {
                    current_pitch = Some(pitch);
                    start_time = time;
                    total_confidence = det.confidence;
                    frame_count = 1;
                    total_cents = det.cents_deviation.unwrap_or(0.0);
                }
                (Some(_), Some(pitch)) if Some(pitch) == current_pitch => {
                    total_confidence += det.confidence;
                    frame_count += 1;
                    total_cents += det.cents_deviation.unwrap_or(0.0);
                }
                (Some(prev_pitch), Some(pitch)) => {
                    let duration = time - start_time;
                    if duration >= self.config.min_note_duration {
                        notes.push(TranscribedNote {
                            pitch: prev_pitch,
                            start_time,
                            duration,
                            velocity: 80,
                            confidence: total_confidence / frame_count as f64,
                            cents_deviation: total_cents / frame_count as f64,
                        });
                    }
                    current_pitch = Some(pitch);
                    start_time = time;
                    total_confidence = det.confidence;
                    frame_count = 1;
                    total_cents = det.cents_deviation.unwrap_or(0.0);
                }
                (Some(prev_pitch), None) => {
                    let duration = time - start_time;
                    if duration >= self.config.min_note_duration {
                        notes.push(TranscribedNote {
                            pitch: prev_pitch,
                            start_time,
                            duration,
                            velocity: 80,
                            confidence: total_confidence / frame_count as f64,
                            cents_deviation: total_cents / frame_count as f64,
                        });
                    }
                    current_pitch = None;
                }
                (None, None) => {}
            }
        }

        // 处理最后一个音符
        if let Some(pitch) = current_pitch {
            let duration = detections.len() as f64 * frame_duration - start_time;
            if duration >= self.config.min_note_duration {
                notes.push(TranscribedNote {
                    pitch,
                    start_time,
                    duration,
                    velocity: 80,
                    confidence: total_confidence / frame_count as f64,
                    cents_deviation: total_cents / frame_count as f64,
                });
            }
        }

        notes
    }

    /// Krumhansl-Schmuckler 调式推断（简化版）
    fn estimate_key(&self, notes: &[TranscribedNote]) -> KeyEstimate {
        let mut pitch_classes = [0.0f64; 12];
        for note in notes {
            pitch_classes[note.pitch as usize % 12] += note.duration * note.velocity as f64;
        }

        let total: f64 = pitch_classes.iter().sum();
        if total > 0.0 {
            for pc in &mut pitch_classes {
                *pc /= total;
            }
        }

        let major_profile = [6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88];
        let minor_profile = [6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17];

        let note_names = [
            NoteName::C, NoteName::D, NoteName::E, NoteName::F,
            NoteName::G, NoteName::A, NoteName::B,
        ];

        let mut best_key = KeyEstimate {
            tonic: NoteName::C,
            mode: Mode::Major,
            confidence: 0.0,
        };

        for shift in 0..12 {
            let mut rotated_major = [0.0f64; 12];
            let mut rotated_minor = [0.0f64; 12];
            for i in 0..12 {
                rotated_major[i] = major_profile[(i + shift) % 12];
                rotated_minor[i] = minor_profile[(i + shift) % 12];
            }

            let major_corr = Self::correlation(&pitch_classes, &rotated_major);
            let minor_corr = Self::correlation(&pitch_classes, &rotated_minor);

            if major_corr > best_key.confidence {
                best_key = KeyEstimate {
                    tonic: note_names[shift % 7],
                    mode: Mode::Major,
                    confidence: major_corr,
                };
            }
            if minor_corr > best_key.confidence {
                best_key = KeyEstimate {
                    tonic: note_names[shift % 7],
                    mode: Mode::Minor,
                    confidence: minor_corr,
                };
            }
        }

        best_key.confidence = best_key.confidence.clamp(0.0, 1.0);
        best_key
    }

    /// 计算Pearson相关系数
    fn correlation(x: &[f64], y: &[f64]) -> f64 {
        let n = x.len().min(y.len()) as f64;
        if n < 2.0 {
            return 0.0;
        }

        let mean_x: f64 = x.iter().sum::<f64>() / n;
        let mean_y: f64 = y.iter().sum::<f64>() / n;

        let mut cov = 0.0;
        let mut var_x = 0.0;
        let mut var_y = 0.0;

        for i in 0..n as usize {
            let dx = x[i] - mean_x;
            let dy = y[i] - mean_y;
            cov += dx * dy;
            var_x += dx * dx;
            var_y += dy * dy;
        }

        if var_x < 1e-10 || var_y < 1e-10 {
            return 0.0;
        }

        cov / (var_x * var_y).sqrt()
    }
}

// ── 扒带→项目转换 ──────────────────────────────────────────

/// 轨道分配策略
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum TrackAllocationStrategy {
    /// 所有音符放一个轨道
    SingleTrack,
    /// 按音高范围分配（低/中/高）
    ByPitchRange,
    /// 按音色/力度分组
    ByVelocity,
}

/// 扒带→项目转换器
pub struct TranscriptionToProject {
    /// 轨道分配策略
    strategy: TrackAllocationStrategy,
}

impl TranscriptionToProject {
    /// 创建新的转换器
    pub fn new(strategy: TrackAllocationStrategy) -> Self {
        Self { strategy }
    }

    /// 将扒带结果转换为Pattern
    pub fn to_pattern(&self, result: &TranscriptionResult, name: &str) -> Pattern {
        let beat_duration = 60.0 / result.beat_detection.bpm;
        let length_beats = result.duration_secs / beat_duration;

        let mut pattern = Pattern::new(
            &format!("transcription_{}", name),
            name,
            PatternType::Midi,
            length_beats,
        );

        let midi_notes = result.to_midi_notes();
        for note in midi_notes {
            pattern.add_note(note);
        }

        pattern.add_tag("transcription");
        pattern.category = "扒带".to_string();

        pattern
    }

    /// 将扒带结果转换为多个Pattern（按轨道分配策略）
    pub fn to_patterns(&self, result: &TranscriptionResult, name: &str) -> Vec<Pattern> {
        match self.strategy {
            TrackAllocationStrategy::SingleTrack => {
                vec![self.to_pattern(result, name)]
            }
            TrackAllocationStrategy::ByPitchRange => {
                self.split_by_pitch_range(result, name)
            }
            TrackAllocationStrategy::ByVelocity => {
                self.split_by_velocity(result, name)
            }
        }
    }

    /// 按音高范围拆分
    fn split_by_pitch_range(&self, result: &TranscriptionResult, name: &str) -> Vec<Pattern> {
        let beat_duration = 60.0 / result.beat_detection.bpm;
        let length_beats = result.duration_secs / beat_duration;

        let ranges: [(u8, u8, &str); 3] = [
            (0, 47, "低音"),
            (48, 71, "中音"),
            (72, 127, "高音"),
        ];

        let mut patterns = Vec::new();

        for (lo, hi, label) in ranges {
            let notes: Vec<MidiNote> = result
                .notes
                .iter()
                .filter(|n| n.pitch >= lo && n.pitch <= hi)
                .map(|n| {
                    let start_beat = n.start_time / beat_duration;
                    let duration_beats = n.duration / beat_duration;
                    MidiNote::new(n.pitch, start_beat, duration_beats, n.velocity)
                })
                .collect();

            if !notes.is_empty() {
                let mut pattern = Pattern::new(
                    &format!("transcription_{}_{}", name, label),
                    &format!("{} - {}", name, label),
                    PatternType::Midi,
                    length_beats,
                );
                for note in notes {
                    pattern.add_note(note);
                }
                pattern.add_tag("transcription");
                pattern.add_tag(label);
                pattern.category = "扒带".to_string();
                patterns.push(pattern);
            }
        }

        patterns
    }

    /// 按力度拆分
    fn split_by_velocity(&self, result: &TranscriptionResult, name: &str) -> Vec<Pattern> {
        let beat_duration = 60.0 / result.beat_detection.bpm;
        let length_beats = result.duration_secs / beat_duration;

        let ranges: [(u8, u8, &str); 3] = [
            (0, 63, "弱"),
            (64, 95, "中"),
            (96, 127, "强"),
        ];

        let mut patterns = Vec::new();

        for (lo, hi, label) in ranges {
            let notes: Vec<MidiNote> = result
                .notes
                .iter()
                .filter(|n| n.velocity >= lo && n.velocity <= hi)
                .map(|n| {
                    let start_beat = n.start_time / beat_duration;
                    let duration_beats = n.duration / beat_duration;
                    MidiNote::new(n.pitch, start_beat, duration_beats, n.velocity)
                })
                .collect();

            if !notes.is_empty() {
                let mut pattern = Pattern::new(
                    &format!("transcription_{}_{}", name, label),
                    &format!("{} - {}", name, label),
                    PatternType::Midi,
                    length_beats,
                );
                for note in notes {
                    pattern.add_note(note);
                }
                pattern.add_tag("transcription");
                pattern.add_tag(label);
                pattern.category = "扒带".to_string();
                patterns.push(pattern);
            }
        }

        patterns
    }

    /// 生成项目轨道配置建议
    pub fn suggest_track_config(&self, result: &TranscriptionResult) -> Vec<TrackSuggestion> {
        let mut suggestions = Vec::new();

        match self.strategy {
            TrackAllocationStrategy::SingleTrack => {
                suggestions.push(TrackSuggestion {
                    name: "扒带音轨".to_string(),
                    suggested_instrument: "Piano".to_string(),
                    note_count: result.notes.len(),
                    pitch_range: Self::compute_pitch_range(&result.notes),
                });
            }
            TrackAllocationStrategy::ByPitchRange => {
                let ranges = [(0u8, 47u8, "Bass", "低音贝斯"), (48, 71, "Keys", "键盘"), (72, 127, "Lead", "主音")];
                for (lo, hi, inst, label) in ranges {
                    let range_notes: Vec<&TranscribedNote> =
                        result.notes.iter().filter(|n| n.pitch >= lo && n.pitch <= hi).collect();
                    if !range_notes.is_empty() {
                        suggestions.push(TrackSuggestion {
                            name: format!("扒带-{}", label),
                            suggested_instrument: inst.to_string(),
                            note_count: range_notes.len(),
                            pitch_range: Self::compute_pitch_range_from_ref(&range_notes),
                        });
                    }
                }
            }
            TrackAllocationStrategy::ByVelocity => {
                suggestions.push(TrackSuggestion {
                    name: "扒带音轨".to_string(),
                    suggested_instrument: "Piano".to_string(),
                    note_count: result.notes.len(),
                    pitch_range: Self::compute_pitch_range(&result.notes),
                });
            }
        }

        suggestions
    }

    fn compute_pitch_range(notes: &[TranscribedNote]) -> (u8, u8) {
        if notes.is_empty() {
            return (60, 60);
        }
        let min = notes.iter().map(|n| n.pitch).min().unwrap();
        let max = notes.iter().map(|n| n.pitch).max().unwrap();
        (min, max)
    }

    fn compute_pitch_range_from_ref(notes: &[&TranscribedNote]) -> (u8, u8) {
        if notes.is_empty() {
            return (60, 60);
        }
        let min = notes.iter().map(|n| n.pitch).min().unwrap();
        let max = notes.iter().map(|n| n.pitch).max().unwrap();
        (min, max)
    }
}

/// 轨道配置建议
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TrackSuggestion {
    /// 轨道名称
    pub name: String,
    /// 建议乐器
    pub suggested_instrument: String,
    /// 音符数量
    pub note_count: usize,
    /// 音高范围
    pub pitch_range: (u8, u8),
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_pitch_detector_silence() {
        let detector = PitchDetector::new(44100.0);
        let silence = vec![0.0f64; 2048];
        let result = detector.detect(&silence);
        assert!(result.frequency.is_none());
    }

    #[test]
    fn test_pitch_detector_sine() {
        let detector = PitchDetector::new(44100.0);
        let frame_size = 2048;
        let mut signal = vec![0.0f64; frame_size * 2];
        for i in 0..signal.len() {
            signal[i] = 0.5 * (2.0 * std::f64::consts::PI * 440.0 * i as f64 / 44100.0).sin();
        }
        let result = detector.detect(&signal);
        assert!(result.frequency.is_some());
        let freq = result.frequency.unwrap();
        assert!((freq - 440.0).abs() < 10.0, "Expected ~440Hz, got {}", freq);
    }

    #[test]
    fn test_beat_detector_silence() {
        let detector = BeatDetector::new(44100.0);
        let silence = vec![0.0f64; 44100];
        let result = detector.detect(&silence);
        assert!(result.onsets.is_empty() || result.bpm_confidence < 0.5);
    }

    #[test]
    fn test_transcription_config_default() {
        let config = TranscriptionConfig::default();
        assert!((config.sample_rate - 44100.0).abs() < 1e-10);
        assert!((config.pitch_threshold - 0.15).abs() < 1e-10);
    }

    #[test]
    fn test_transcription_result_to_midi() {
        let result = TranscriptionResult {
            notes: vec![TranscribedNote {
                pitch: 60,
                start_time: 0.0,
                duration: 0.5,
                velocity: 100,
                confidence: 0.9,
                cents_deviation: 0.0,
            }],
            beat_detection: BeatDetection {
                bpm: 120.0,
                bpm_confidence: 0.8,
                onsets: vec![0.0],
                beats: vec![0.0],
                bar_positions: vec![0.0],
                time_signature_num: 4,
                time_signature_den: 4,
            },
            key_estimate: None,
            duration_secs: 10.0,
            sample_rate: 44100.0,
            quality_score: 80.0,
        };

        let midi_notes = result.to_midi_notes();
        assert_eq!(midi_notes.len(), 1);
        assert_eq!(midi_notes[0].pitch, 60);
    }

    #[test]
    fn test_transcription_to_project_by_pitch() {
        let result = TranscriptionResult {
            notes: vec![
                TranscribedNote {
                    pitch: 36,
                    start_time: 0.0,
                    duration: 0.5,
                    velocity: 100,
                    confidence: 0.9,
                    cents_deviation: 0.0,
                },
                TranscribedNote {
                    pitch: 60,
                    start_time: 0.5,
                    duration: 0.5,
                    velocity: 80,
                    confidence: 0.8,
                    cents_deviation: 5.0,
                },
            ],
            beat_detection: BeatDetection {
                bpm: 120.0,
                bpm_confidence: 0.8,
                onsets: vec![0.0, 0.5],
                beats: vec![0.0, 0.5],
                bar_positions: vec![0.0],
                time_signature_num: 4,
                time_signature_den: 4,
            },
            key_estimate: None,
            duration_secs: 10.0,
            sample_rate: 44100.0,
            quality_score: 80.0,
        };

        let converter = TranscriptionToProject::new(TrackAllocationStrategy::ByPitchRange);
        let patterns = converter.to_patterns(&result, "test");
        assert!(patterns.len() >= 2);
    }

    #[test]
    fn test_track_suggestion() {
        let result = TranscriptionResult {
            notes: vec![TranscribedNote {
                pitch: 36,
                start_time: 0.0,
                duration: 0.5,
                velocity: 100,
                confidence: 0.9,
                cents_deviation: 0.0,
            }],
            beat_detection: BeatDetection {
                bpm: 120.0,
                bpm_confidence: 0.8,
                onsets: vec![0.0],
                beats: vec![0.0],
                bar_positions: vec![0.0],
                time_signature_num: 4,
                time_signature_den: 4,
            },
            key_estimate: None,
            duration_secs: 10.0,
            sample_rate: 44100.0,
            quality_score: 80.0,
        };

        let converter = TranscriptionToProject::new(TrackAllocationStrategy::SingleTrack);
        let suggestions = converter.suggest_track_config(&result);
        assert_eq!(suggestions.len(), 1);
        assert_eq!(suggestions[0].note_count, 1);
    }
}
