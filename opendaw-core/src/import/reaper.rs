//! Reaper RPP导入 — 解析Reaper项目文件
//!
//! - ReaperProjectParser: RPP文件解析器
//! - 解析轨道、音量/声像、FX链、MIDI item
//! - ReaperToProject: RPP→OpenDAW项目转换
//! - 常见FX映射到JSFX等效效果器

use std::collections::HashMap;
use std::path::Path;

use serde::{Deserialize, Serialize};

use crate::pattern::{MidiNote, Pattern, PatternType};
use crate::project::{ProjectConfig, TrackConfig};

// ── RPP数据结构 ───────────────────────────────────────────

/// Reaper轨道信息
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ReaperTrack {
    /// 轨道名称
    pub name: String,
    /// 轨道编号
    pub index: usize,
    /// 音量 (0~1线性)
    pub volume: f64,
    /// 声像 (-1~1)
    pub pan: f64,
    /// 是否静音
    pub muted: bool,
    /// 是否独奏
    pub solo: bool,
    /// FX链
    pub fx_chain: Vec<ReaperFx>,
    /// MIDI items
    pub midi_items: Vec<ReaperMidiItem>,
    /// 音频items
    pub audio_items: Vec<ReaperAudioItem>,
    /// 发送列表
    pub sends: Vec<ReaperSend>,
    /// 颜色
    pub color: u32,
    /// 录制输入
    pub record_input: i32,
    /// 通道数
    pub channels: usize,
}

impl Default for ReaperTrack {
    fn default() -> Self {
        Self {
            name: String::new(),
            index: 0,
            volume: 1.0,
            pan: 0.0,
            muted: false,
            solo: false,
            fx_chain: Vec::new(),
            midi_items: Vec::new(),
            audio_items: Vec::new(),
            sends: Vec::new(),
            color: 0,
            record_input: -1,
            channels: 2,
        }
    }
}

/// Reaper FX
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ReaperFx {
    /// FX名称
    pub name: String,
    /// FX类型
    pub fx_type: ReaperFxType,
    /// 参数列表
    pub parameters: Vec<f64>,
    /// 是否旁通
    pub bypassed: bool,
    /// 预设名称
    pub preset: Option<String>,
}

/// FX类型
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum ReaperFxType {
    /// VST插件
    Vst,
    /// VST3插件
    Vst3,
    /// AU插件
    Au,
    /// JSFX脚本
    Jsfx,
    /// ReaPlugs内置
    ReaPlug,
    /// 未知
    Unknown,
}

/// Reaper MIDI Item
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ReaperMidiItem {
    /// Item名称
    pub name: String,
    /// 起始位置（秒）
    pub position: f64,
    /// 长度（秒）
    pub length: f64,
    /// MIDI音符
    pub notes: Vec<MidiNote>,
    /// 通道
    pub channel: u8,
    /// 量化
    pub quantize: f64,
}

/// Reaper Audio Item
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ReaperAudioItem {
    /// 音频文件路径
    pub file_path: String,
    /// 起始位置（秒）
    pub position: f64,
    /// 长度（秒）
    pub length: f64,
    /// 偏移（秒）
    pub offset: f64,
    /// 播放速率
    pub play_rate: f64,
    /// 音量
    pub volume: f64,
    /// 是否反向
    pub reverse: bool,
}

/// Reaper发送
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ReaperSend {
    /// 目标轨道索引
    pub target_track: usize,
    /// 发送音量
    pub volume: f64,
    /// 发送声像
    pub pan: f64,
    /// 发送类型
    pub send_type: ReaperSendType,
}

/// 发送类型
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum ReaperSendType {
    /// 音频发送
    Audio,
    /// MIDI发送
    Midi,
}

/// Reaper项目信息
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ReaperProject {
    /// 项目名称
    pub name: String,
    /// 采样率
    pub sample_rate: f64,
    /// BPM
    pub bpm: f64,
    /// 拍号分子
    pub time_signature_num: u8,
    /// 拍号分母
    pub time_signature_den: u8,
    /// 轨道列表
    pub tracks: Vec<ReaperTrack>,
    /// 标记列表
    pub markers: Vec<ReaperMarker>,
}

/// Reaper标记
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ReaperMarker {
    /// 位置（秒）
    pub position: f64,
    /// 名称
    pub name: String,
    /// 颜色
    pub color: u32,
}

// ── RPP解析器 ──────────────────────────────────────────────

/// RPP解析错误
#[derive(Debug, thiserror::Error)]
pub enum ReaperParseError {
    #[error("IO错误: {0}")]
    Io(#[from] std::io::Error),
    #[error("格式错误: {0}")]
    Format(String),
    #[error("编码错误: {0}")]
    Encoding(String),
}

/// Reaper RPP解析器
pub struct ReaperProjectParser {
    /// 是否严格模式
    strict: bool,
}

impl ReaperProjectParser {
    /// 创建新的解析器
    pub fn new() -> Self {
        Self { strict: false }
    }

    /// 设置严格模式
    pub fn strict(mut self, strict: bool) -> Self {
        self.strict = strict;
        self
    }

    /// 从字符串解析RPP项目
    pub fn parse(&self, content: &str) -> Result<ReaperProject, ReaperParseError> {
        let lines: Vec<&str> = content.lines().collect();
        self.parse_lines(&lines)
    }

    /// 从文件解析RPP项目
    pub fn parse_file(&self, path: &Path) -> Result<ReaperProject, ReaperParseError> {
        let content = std::fs::read_to_string(path)?;
        self.parse(&content)
    }

    /// 解析行列表
    fn parse_lines(&self, lines: &[&str]) -> Result<ReaperProject, ReaperParseError> {
        let mut project = ReaperProject {
            name: String::new(),
            sample_rate: 44100.0,
            bpm: 120.0,
            time_signature_num: 4,
            time_signature_den: 4,
            tracks: Vec::new(),
            markers: Vec::new(),
        };

        let mut current_track: Option<ReaperTrack> = None;
        let mut in_fx_chain = false;
        let mut current_fx: Option<ReaperFx> = None;
        let mut in_midi_item = false;
        let mut current_midi_item: Option<ReaperMidiItem> = None;
        let mut in_source = false;
        let mut current_audio_item: Option<ReaperAudioItem> = None;

        for line in lines {
            let trimmed = line.trim();

            // 解析项目级参数
            if trimmed.starts_with("bpm") {
                if let Some(val) = self.parse_float_value(trimmed) {
                    project.bpm = val;
                }
            } else if trimmed.starts_with("srate") {
                if let Some(val) = self.parse_float_value(trimmed) {
                    project.sample_rate = val;
                }
            } else if trimmed.starts_with("timemode") {
                // 时间模式
            }
            // 解析轨道
            else if trimmed.starts_with("<TRACK") {
                current_track = Some(ReaperTrack {
                    index: project.tracks.len(),
                    ..ReaperTrack::default()
                });
            } else if trimmed == ">" && current_track.is_some() && !in_fx_chain && !in_midi_item && !in_source {
                if let Some(track) = current_track.take() {
                    project.tracks.push(track);
                }
            }
            // 解析轨道参数
            else if let Some(ref mut track) = current_track {
                if trimmed.starts_with("NAME") {
                    track.name = self.parse_string_value(trimmed).unwrap_or_default();
                } else if trimmed.starts_with("VOLPAN") {
                    let parts: Vec<&str> = trimmed.split_whitespace().collect();
                    if parts.len() >= 3 {
                        track.volume = parts[1].parse().unwrap_or(1.0);
                        track.pan = parts[2].parse().unwrap_or(0.0);
                    }
                } else if trimmed.starts_with("MUTE") {
                    let parts: Vec<&str> = trimmed.split_whitespace().collect();
                    if parts.len() >= 2 {
                        track.muted = parts[1] != "0";
                    }
                } else if trimmed.starts_with("SOLO") {
                    let parts: Vec<&str> = trimmed.split_whitespace().collect();
                    if parts.len() >= 2 {
                        track.solo = parts[1] != "0";
                    }
                } else if trimmed.starts_with("COLOR") {
                    if let Some(val) = self.parse_int_value(trimmed) {
                        track.color = val as u32;
                    }
                } else if trimmed.starts_with("NCHAN") {
                    if let Some(val) = self.parse_int_value(trimmed) {
                        track.channels = val as usize;
                    }
                } else if trimmed.starts_with("INQ") {
                    let parts: Vec<&str> = trimmed.split_whitespace().collect();
                    if parts.len() >= 2 {
                        track.record_input = parts[1].parse().unwrap_or(-1);
                    }
                }
                // FX链
                else if trimmed.starts_with("<FXCHAIN") {
                    in_fx_chain = true;
                } else if trimmed == ">" && in_fx_chain && current_fx.is_none() {
                    in_fx_chain = false;
                }
                // 单个FX
                else if in_fx_chain && trimmed.starts_with("<VST") {
                    current_fx = Some(ReaperFx {
                        name: self.extract_fx_name(trimmed),
                        fx_type: ReaperFxType::Vst,
                        parameters: Vec::new(),
                        bypassed: false,
                        preset: None,
                    });
                } else if in_fx_chain && trimmed.starts_with("<VST3") {
                    current_fx = Some(ReaperFx {
                        name: self.extract_fx_name(trimmed),
                        fx_type: ReaperFxType::Vst3,
                        parameters: Vec::new(),
                        bypassed: false,
                        preset: None,
                    });
                } else if in_fx_chain && trimmed.starts_with("<JS") {
                    current_fx = Some(ReaperFx {
                        name: self.extract_fx_name(trimmed),
                        fx_type: ReaperFxType::Jsfx,
                        parameters: Vec::new(),
                        bypassed: false,
                        preset: None,
                    });
                } else if in_fx_chain && trimmed.starts_with("<AU") {
                    current_fx = Some(ReaperFx {
                        name: self.extract_fx_name(trimmed),
                        fx_type: ReaperFxType::Au,
                        parameters: Vec::new(),
                        bypassed: false,
                        preset: None,
                    });
                } else if in_fx_chain && trimmed == ">" && current_fx.is_some() {
                    if let Some(fx) = current_fx.take() {
                        track.fx_chain.push(fx);
                    }
                } else if in_fx_chain && current_fx.is_some() {
                    // 解析FX参数
                    if trimmed.starts_with("BYPASS") {
                        let parts: Vec<&str> = trimmed.split_whitespace().collect();
                        if parts.len() >= 2 {
                            if let Some(ref mut fx) = current_fx {
                                fx.bypassed = parts[1] != "0";
                            }
                        }
                    } else if trimmed.starts_with("PRESET") {
                        if let Some(ref mut fx) = current_fx {
                            fx.preset = self.parse_string_value(trimmed);
                        }
                    } else if !trimmed.is_empty() && !trimmed.starts_with('<') && !trimmed.starts_with("FLOATPOS") && !trimmed.starts_with("FXID") && !trimmed.starts_with("WAK") {
                        // 尝试解析为参数
                        if let Some(ref mut fx) = current_fx {
                            for part in trimmed.split_whitespace() {
                                if let Ok(val) = part.parse::<f64>() {
                                    fx.parameters.push(val);
                                }
                            }
                        }
                    }
                }
                // MIDI item
                else if trimmed.starts_with("<ITEM") {
                    in_midi_item = true;
                    current_midi_item = Some(ReaperMidiItem {
                        name: String::new(),
                        position: 0.0,
                        length: 0.0,
                        notes: Vec::new(),
                        channel: 0,
                        quantize: 0.0,
                    });
                    current_audio_item = None;
                } else if trimmed == ">" && in_midi_item && !in_source {
                    in_midi_item = false;
                    if let Some(midi_item) = current_midi_item.take() {
                        track.midi_items.push(midi_item);
                    }
                } else if in_midi_item {
                    if let Some(ref mut midi) = current_midi_item {
                        if trimmed.starts_with("POSITION") {
                            midi.position = self.parse_float_value(trimmed).unwrap_or(0.0);
                        } else if trimmed.starts_with("LENGTH") {
                            midi.length = self.parse_float_value(trimmed).unwrap_or(0.0);
                        } else if trimmed.starts_with("NAME") {
                            midi.name = self.parse_string_value(trimmed).unwrap_or_default();
                        } else if trimmed.starts_with("CHANNEL") {
                            midi.channel = self.parse_int_value(trimmed).unwrap_or(0) as u8;
                        } else if trimmed.starts_with("QN") {
                            midi.quantize = self.parse_float_value(trimmed).unwrap_or(0.0);
                        } else if trimmed.starts_with("<SOURCE MIDI") {
                            in_source = true;
                        } else if trimmed == ">" && in_source {
                            in_source = false;
                        } else if in_source && trimmed.starts_with("E") {
                            // MIDI event: E pp pp vv (position, pitch, velocity simplified)
                            let parts: Vec<&str> = trimmed.split_whitespace().collect();
                            if parts.len() >= 4 {
                                if let (Ok(start), Ok(pitch), Ok(velocity)) =
                                    (parts[1].parse::<f64>(), parts[2].parse::<u8>(), parts[3].parse::<u8>())
                                {
                                    let bps = project.bpm / 60.0;
                                    let start_beat = start / 960.0; // 简化：假定960ppq
                                    midi.notes.push(MidiNote::new(
                                        pitch.min(127),
                                        start_beat,
                                        1.0, // 默认1拍
                                        velocity.min(127),
                                    ));
                                }
                            }
                        } else if in_source && trimmed.starts_with("HASDATA") {
                            // MIDI数据头
                        }
                    }
                }
                // Audio item (在<ITEM中但source是文件)
                else if in_midi_item || current_audio_item.is_some() {
                    // 已在MIDI分支处理
                } else if trimmed.starts_with("FILE") {
                    // 简化：处理音频item
                    if let Some(ref mut midi) = current_midi_item {
                        // 如果MIDI item里有FILE，说明是音频item
                        in_midi_item = false;
                        current_midi_item = None;
                        current_audio_item = Some(ReaperAudioItem {
                            file_path: self.parse_string_value(trimmed).unwrap_or_default(),
                            position: 0.0,
                            length: 0.0,
                            offset: 0.0,
                            play_rate: 1.0,
                            volume: 1.0,
                            reverse: false,
                        });
                    }
                }
                // Sends
                else if trimmed.starts_with("AUXSEND") {
                    let parts: Vec<&str> = trimmed.split_whitespace().collect();
                    if parts.len() >= 4 {
                        track.sends.push(ReaperSend {
                            target_track: parts[1].parse().unwrap_or(0),
                            volume: parts[2].parse().unwrap_or(1.0),
                            pan: parts[3].parse().unwrap_or(0.0),
                            send_type: ReaperSendType::Audio,
                        });
                    }
                }
            }
        }

        Ok(project)
    }

    /// 解析浮点值
    fn parse_float_value(&self, line: &str) -> Option<f64> {
        let parts: Vec<&str> = line.split_whitespace().collect();
        if parts.len() >= 2 {
            parts[1].parse().ok()
        } else {
            None
        }
    }

    /// 解析整数值
    fn parse_int_value(&self, line: &str) -> Option<i64> {
        let parts: Vec<&str> = line.split_whitespace().collect();
        if parts.len() >= 2 {
            parts[1].parse().ok()
        } else {
            None
        }
    }

    /// 解析字符串值
    fn parse_string_value(&self, line: &str) -> Option<String> {
        let parts: Vec<&str> = line.splitn(2, whitespace_or_tab).collect();
        if parts.len() >= 2 {
            Some(parts[1].trim().to_string())
        } else {
            None
        }
    }

    /// 提取FX名称
    fn extract_fx_name(&self, line: &str) -> String {
        // 格式: <VST: VST3 Plugin Name (vendor) or <JS: script_name
        let line = line.trim_start_matches('<');
        let line = line.trim_start_matches("VST:");
        let line = line.trim_start_matches("VST3:");
        let line = line.trim_start_matches("JS:");
        let line = line.trim_start_matches("AU:");

        let name = line.split_whitespace().next().unwrap_or("Unknown");
        name.to_string()
    }
}

fn whitespace_or_tab(c: char) -> bool {
    c == ' ' || c == '\t'
}

impl Default for ReaperProjectParser {
    fn default() -> Self {
        Self::new()
    }
}

// ── FX映射 ────────────────────────────────────────────────

/// FX映射表
pub struct FxMapper {
    /// Reaper FX名 → JSFX等效
    mappings: HashMap<String, String>,
}

impl FxMapper {
    /// 创建默认FX映射
    pub fn new() -> Self {
        let mut mappings = HashMap::new();

        // ReaPlugs → JSFX等效
        mappings.insert("ReaComp".to_string(), "jsfx/compressor".to_string());
        mappings.insert("ReaEQ".to_string(), "jsfx/eq".to_string());
        mappings.insert("ReaDelay".to_string(), "jsfx/delay".to_string());
        mappings.insert("ReaVerb".to_string(), "jsfx/reverb".to_string());
        mappings.insert("ReaGate".to_string(), "jsfx/gate".to_string());
        mappings.insert("ReaLimit".to_string(), "jsfx/limiter".to_string());
        mappings.insert("ReaPitch".to_string(), "jsfx/pitchshift".to_string());
        mappings.insert("ReaStream".to_string(), "jsfx/stream".to_string());
        mappings.insert("ReaTune".to_string(), "jsfx/autotune".to_string());
        mappings.insert("ReaXcomp".to_string(), "jsfx/compressor".to_string());

        // 通用VST映射
        mappings.insert("EQ".to_string(), "jsfx/eq".to_string());
        mappings.insert("Compressor".to_string(), "jsfx/compressor".to_string());
        mappings.insert("Limiter".to_string(), "jsfx/limiter".to_string());
        mappings.insert("Reverb".to_string(), "jsfx/reverb".to_string());
        mappings.insert("Delay".to_string(), "jsfx/delay".to_string());
        mappings.insert("Chorus".to_string(), "jsfx/chorus".to_string());
        mappings.insert("Phaser".to_string(), "jsfx/phaser".to_string());
        mappings.insert("Distortion".to_string(), "jsfx/distortion".to_string());
        mappings.insert("Flanger".to_string(), "jsfx/flanger".to_string());

        Self { mappings }
    }

    /// 映射FX名称
    pub fn map(&self, fx_name: &str) -> Option<&str> {
        // 精确匹配
        if let Some(mapped) = self.mappings.get(fx_name) {
            return Some(mapped);
        }

        // 模糊匹配
        let lower = fx_name.to_lowercase();
        for (key, value) in &self.mappings {
            if lower.contains(&key.to_lowercase()) {
                return Some(value);
            }
        }

        None
    }

    /// 注册自定义映射
    pub fn register(&mut self, from: &str, to: &str) {
        self.mappings.insert(from.to_string(), to.to_string());
    }

    /// 获取所有映射
    pub fn list_mappings(&self) -> &HashMap<String, String> {
        &self.mappings
    }
}

impl Default for FxMapper {
    fn default() -> Self {
        Self::new()
    }
}

// ── RPP → OpenDAW项目转换 ─────────────────────────────────

/// RPP → OpenDAW转换器
pub struct ReaperToProject {
    /// FX映射器
    fx_mapper: FxMapper,
}

impl ReaperToProject {
    /// 创建新的转换器
    pub fn new() -> Self {
        Self {
            fx_mapper: FxMapper::new(),
        }
    }

    /// 使用自定义FX映射器
    pub fn with_fx_mapper(mut self, mapper: FxMapper) -> Self {
        self.fx_mapper = mapper;
        self
    }

    /// 转换Reaper项目为OpenDAW项目配置
    pub fn convert(&self, reaper: &ReaperProject) -> ProjectConfig {
        let tracks: Vec<TrackConfig> = reaper
            .tracks
            .iter()
            .map(|track| {
                let plugins: Vec<String> = track
                    .fx_chain
                    .iter()
                    .filter_map(|fx| {
                        self.fx_mapper
                            .map(&fx.name)
                            .map(|s| s.to_string())
                            .or_else(|| Some(format!("vst:{}", fx.name)))
                    })
                    .collect();

                TrackConfig {
                    name: if track.name.is_empty() {
                        format!("Track {}", track.index + 1)
                    } else {
                        track.name.clone()
                    },
                    channels: track.channels,
                    volume: track.volume,
                    pan: track.pan,
                    muted: track.muted,
                    plugins,
                }
            })
            .collect();

        ProjectConfig {
            name: if reaper.name.is_empty() {
                "Imported from Reaper".to_string()
            } else {
                reaper.name.clone()
            },
            sample_rate: reaper.sample_rate,
            buffer_size: 512,
            tracks,
            master_volume: 1.0,
        }
    }

    /// 转换Reaper MIDI items为Patterns
    pub fn convert_midi_to_patterns(&self, reaper: &ReaperProject) -> Vec<Pattern> {
        let mut patterns = Vec::new();
        let bps = reaper.bpm / 60.0;

        for track in &reaper.tracks {
            for (i, midi_item) in track.midi_items.iter().enumerate() {
                let length_beats = if bps > 0.0 {
                    midi_item.length * bps
                } else {
                    4.0
                };

                let pattern_name = if midi_item.name.is_empty() {
                        format!("{} - MIDI {}", track.name, i + 1)
                    } else {
                        midi_item.name.clone()
                    };
                let mut pattern = Pattern::new(
                    &format!("rpp_{}_{}", track.index, i),
                    &pattern_name,
                    PatternType::Midi,
                    length_beats,
                );

                for note in &midi_item.notes {
                    pattern.add_note(note.clone());
                }

                pattern.add_tag("reaper-import");
                patterns.push(pattern);
            }
        }

        patterns
    }

    /// 生成转换报告
    pub fn conversion_report(&self, reaper: &ReaperProject) -> String {
        let mut report = String::new();

        report.push_str(&format!("Reaper项目转换报告\n"));
        report.push_str(&format!("==================\n"));
        report.push_str(&format!("BPM: {:.1}\n", reaper.bpm));
        report.push_str(&format!("采样率: {:.0}\n", reaper.sample_rate));
        report.push_str(&format!("轨道数: {}\n", reaper.tracks.len()));
        report.push_str(&format!("标记数: {}\n\n", reaper.markers.len()));

        for track in &reaper.tracks {
            report.push_str(&format!("轨道: {} (#{})\n", track.name, track.index));
            report.push_str(&format!("  音量: {:.2}, 声像: {:.2}\n", track.volume, track.pan));
            report.push_str(&format!("  FX: {}\n", track.fx_chain.len()));
            for fx in &track.fx_chain {
                let mapped = self.fx_mapper.map(&fx.name);
                report.push_str(&format!(
                    "    {} → {}\n",
                    fx.name,
                    mapped.unwrap_or("未映射")
                ));
            }
            report.push_str(&format!(
                "  MIDI Items: {}, Audio Items: {}\n\n",
                track.midi_items.len(),
                track.audio_items.len()
            ));
        }

        report
    }
}

impl Default for ReaperToProject {
    fn default() -> Self {
        Self::new()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_parse_empty_project() {
        let parser = ReaperProjectParser::new();
        let result = parser.parse("").unwrap();
        assert_eq!(result.tracks.len(), 0);
        assert!((result.bpm - 120.0).abs() < 1e-10);
    }

    #[test]
    fn test_parse_bpm() {
        let rpp = "bpm 140.5\n";
        let parser = ReaperProjectParser::new();
        let result = parser.parse(rpp).unwrap();
        assert!((result.bpm - 140.5).abs() < 1e-10);
    }

    #[test]
    fn test_parse_sample_rate() {
        let rpp = "srate 48000\n";
        let parser = ReaperProjectParser::new();
        let result = parser.parse(rpp).unwrap();
        assert!((result.sample_rate - 48000.0).abs() < 1e-10);
    }

    #[test]
    fn test_parse_track() {
        let rpp = r#"<TRACK
NAME Test Track
VOLPAN 0.8 -0.5
MUTE 0
SOLO 0
COLOR 255
NCHAN 2
>"#;
        let parser = ReaperProjectParser::new();
        let result = parser.parse(rpp).unwrap();
        assert_eq!(result.tracks.len(), 1);
        assert_eq!(result.tracks[0].name, "Test Track");
        assert!((result.tracks[0].volume - 0.8).abs() < 1e-10);
        assert!((result.tracks[0].pan - (-0.5)).abs() < 1e-10);
    }

    #[test]
    fn test_parse_track_mute() {
        let rpp = "<TRACK\nMUTE 1\n>";
        let parser = ReaperProjectParser::new();
        let result = parser.parse(rpp).unwrap();
        assert!(result.tracks[0].muted);
    }

    #[test]
    fn test_parse_fx_chain() {
        let rpp = "<TRACK\n<FXCHAIN\n<VST: ReaComp\nBYPASS 0\n1.0 0.5 0.3\n>\n>\n>";
        let parser = ReaperProjectParser::new();
        let result = parser.parse(rpp).unwrap();
        assert_eq!(result.tracks[0].fx_chain.len(), 1);
        assert!(!result.tracks[0].fx_chain[0].bypassed);
    }

    #[test]
    fn test_parse_jsfx() {
        let rpp = "<TRACK\n<FXCHAIN\n<JS: delay_sim\nBYPASS 0\n0.5 0.3\n>\n>\n>";
        let parser = ReaperProjectParser::new();
        let result = parser.parse(rpp).unwrap();
        assert_eq!(result.tracks[0].fx_chain.len(), 1);
        assert_eq!(result.tracks[0].fx_chain[0].fx_type, ReaperFxType::Jsfx);
    }

    #[test]
    fn test_parse_midi_item() {
        let rpp = "<TRACK\n<ITEM\nPOSITION 0.0\nLENGTH 2.0\n<SOURCE MIDI\nHASDATA 1 960 QN\nE 0 60 100\nE 480 64 80\n>\n>\n>";
        let parser = ReaperProjectParser::new();
        let result = parser.parse(rpp).unwrap();
        assert_eq!(result.tracks[0].midi_items.len(), 1);
        assert_eq!(result.tracks[0].midi_items[0].notes.len(), 2);
        assert_eq!(result.tracks[0].midi_items[0].notes[0].pitch, 60);
    }

    #[test]
    fn test_fx_mapper() {
        let mapper = FxMapper::new();
        assert_eq!(mapper.map("ReaComp"), Some("jsfx/compressor"));
        assert_eq!(mapper.map("ReaEQ"), Some("jsfx/eq"));
        assert_eq!(mapper.map("Unknown"), None);
    }

    #[test]
    fn test_fx_mapper_fuzzy() {
        let mapper = FxMapper::new();
        assert!(mapper.map("My Compressor Pro").is_some());
    }

    #[test]
    fn test_fx_mapper_register() {
        let mut mapper = FxMapper::new();
        mapper.register("CustomEQ", "jsfx/custom_eq");
        assert_eq!(mapper.map("CustomEQ"), Some("jsfx/custom_eq"));
    }

    #[test]
    fn test_reaper_to_project_convert() {
        let reaper = ReaperProject {
            name: "Test Project".to_string(),
            sample_rate: 44100.0,
            bpm: 130.0,
            time_signature_num: 4,
            time_signature_den: 4,
            tracks: vec![ReaperTrack {
                name: "Drums".to_string(),
                volume: 0.8,
                pan: 0.0,
                channels: 2,
                ..ReaperTrack::default()
            }],
            markers: Vec::new(),
        };

        let converter = ReaperToProject::new();
        let config = converter.convert(&reaper);
        assert_eq!(config.name, "Test Project");
        assert_eq!(config.tracks.len(), 1);
        assert_eq!(config.tracks[0].name, "Drums");
    }

    #[test]
    fn test_reaper_to_project_patterns() {
        let reaper = ReaperProject {
            name: "Test".to_string(),
            sample_rate: 44100.0,
            bpm: 120.0,
            time_signature_num: 4,
            time_signature_den: 4,
            tracks: vec![ReaperTrack {
                name: "Keys".to_string(),
                midi_items: vec![ReaperMidiItem {
                    name: "Piano".to_string(),
                    position: 0.0,
                    length: 2.0,
                    notes: vec![MidiNote::new(60, 0.0, 1.0, 100)],
                    channel: 0,
                    quantize: 0.0,
                }],
                ..ReaperTrack::default()
            }],
            markers: Vec::new(),
        };

        let converter = ReaperToProject::new();
        let patterns = converter.convert_midi_to_patterns(&reaper);
        assert_eq!(patterns.len(), 1);
        assert!(patterns[0].tags.contains(&"reaper-import".to_string()));
    }

    #[test]
    fn test_conversion_report() {
        let reaper = ReaperProject {
            name: "Report Test".to_string(),
            sample_rate: 48000.0,
            bpm: 140.0,
            time_signature_num: 4,
            time_signature_den: 4,
            tracks: vec![ReaperTrack {
                name: "Bass".to_string(),
                fx_chain: vec![ReaperFx {
                    name: "ReaComp".to_string(),
                    fx_type: ReaperFxType::ReaPlug,
                    parameters: vec![0.5],
                    bypassed: false,
                    preset: None,
                }],
                ..ReaperTrack::default()
            }],
            markers: Vec::new(),
        };

        let converter = ReaperToProject::new();
        let report = converter.conversion_report(&reaper);
        assert!(report.contains("140.0"));
        assert!(report.contains("ReaComp"));
        assert!(report.contains("jsfx/compressor"));
    }
}
