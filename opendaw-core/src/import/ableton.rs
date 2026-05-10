//! Ableton ALS解析 — 解析Ableton Live项目文件
//!
//! - AbletonProjectParser: ALS XML解析
//! - 解析轨道、Clip、设备链
//! - AbletonToProject: ALS→OpenDAW项目转换

use std::collections::HashMap;
use std::path::Path;

use serde::{Deserialize, Serialize};

use crate::pattern::{MidiNote, Pattern, PatternType};
use crate::project::{ProjectConfig, TrackConfig};

// ── ALS数据结构 ───────────────────────────────────────────

/// Ableton轨道类型
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum AbletonTrackType {
    /// 音频轨道
    Audio,
    /// MIDI轨道
    Midi,
    /// 返回轨道
    Return,
    /// 主轨道
    Master,
    /// 分组轨道
    Group,
}

/// Ableton轨道信息
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AbletonTrack {
    /// 轨道名称
    pub name: String,
    /// 轨道类型
    pub track_type: AbletonTrackType,
    /// 音量 (0~1)
    pub volume: f64,
    /// 声像 (-1~1)
    pub pan: f64,
    /// 是否静音
    pub muted: bool,
    /// 是否独奏
    pub solo: bool,
    /// 颜色
    pub color: u32,
    /// 设备链
    pub devices: Vec<AbletonDevice>,
    /// Clip列表
    pub clips: Vec<AbletonClip>,
    /// 发送列表
    pub sends: Vec<AbletonSend>,
    /// 编组ID
    pub group_id: Option<String>,
}

impl Default for AbletonTrack {
    fn default() -> Self {
        Self {
            name: String::new(),
            track_type: AbletonTrackType::Midi,
            volume: 1.0,
            pan: 0.0,
            muted: false,
            solo: false,
            color: 0,
            devices: Vec::new(),
            clips: Vec::new(),
            sends: Vec::new(),
            group_id: None,
        }
    }
}

/// Ableton设备
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AbletonDevice {
    /// 设备名称
    pub name: String,
    /// 设备类型
    pub device_type: AbletonDeviceType,
    /// 参数列表
    pub parameters: Vec<AbletonParameter>,
    /// 是否启用
    pub enabled: bool,
    /// 宏映射
    pub macro_mappings: HashMap<String, u8>,
}

/// Ableton设备类型
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum AbletonDeviceType {
    /// 内置音频效果器
    AudioEffect,
    /// 内置MIDI效果器
    MidiEffect,
    /// 内置乐器
    Instrument,
    /// VST插件
    Vst,
    /// AU插件
    Au,
    /// Max for Live
    MaxForLive,
    /// 未知
    Unknown,
}

/// Ableton参数
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AbletonParameter {
    /// 参数ID
    pub id: String,
    /// 参数名称
    pub name: String,
    /// 当前值
    pub value: f64,
    /// 最小值
    pub min: f64,
    /// 最大值
    pub max: f64,
}

/// Ableton Clip
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AbletonClip {
    /// Clip名称
    pub name: String,
    /// 起始时间（拍）
    pub start: f64,
    /// 结束时间（拍）
    pub end: f64,
    /// 是否循环
    pub loop_enabled: bool,
    /// 循环起始（拍）
    pub loop_start: f64,
    /// 循环结束（拍）
    pub loop_end: f64,
    /// Clip内容
    pub content: AbletonClipContent,
    /// 颜色
    pub color: u32,
}

/// Clip内容类型
#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum AbletonClipContent {
    /// MIDI Clip
    Midi {
        /// MIDI音符
        notes: Vec<AbletonMidiNote>,
        /// 通道
        channel: u8,
    },
    /// 音频Clip
    Audio {
        /// 文件路径
        file_path: String,
        /// 播放速率
        play_rate: f64,
        /// 反转
        reverse: bool,
    },
}

/// Ableton MIDI音符
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AbletonMidiNote {
    /// 音高
    pub pitch: u8,
    /// 起始拍
    pub start_beat: f64,
    /// 持续拍数
    pub duration_beats: f64,
    /// 力度
    pub velocity: u8,
    /// 是否静音
    pub muted: bool,
    /// 概率（0~1，用于概率性MIDI）
    pub probability: f64,
}

/// Ableton发送
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AbletonSend {
    /// 目标返回轨道索引
    pub target_return: usize,
    /// 发送量
    pub amount: f64,
}

/// Ableton项目信息
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AbletonProject {
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
    pub tracks: Vec<AbletonTrack>,
    /// 返回轨道列表
    pub return_tracks: Vec<AbletonTrack>,
    /// 主轨道
    pub master_track: Option<AbletonTrack>,
    /// Cue/Glob设置
    pub global_volume: f64,
    /// 预备拍数
    pub pre_roll_bars: u32,
}

// ── ALS解析器 ──────────────────────────────────────────────

/// ALS解析错误
#[derive(Debug, thiserror::Error)]
pub enum AbletonParseError {
    #[error("IO错误: {0}")]
    Io(#[from] std::io::Error),
    #[error("XML解析错误: {0}")]
    Xml(String),
    #[error("格式错误: {0}")]
    Format(String),
    #[error("Gzip解压错误: {0}")]
    Gzip(String),
}

/// Ableton ALS解析器
pub struct AbletonProjectParser {
    /// 是否严格模式
    strict: bool,
}

impl AbletonProjectParser {
    /// 创建新的解析器
    pub fn new() -> Self {
        Self { strict: false }
    }

    /// 设置严格模式
    pub fn strict(mut self, strict: bool) -> Self {
        self.strict = strict;
        self
    }

    /// 从XML字符串解析ALS项目（已解压的XML）
    pub fn parse_xml(&self, xml_content: &str) -> Result<AbletonProject, AbletonParseError> {
        // 简化的XML解析：ALS XML结构复杂，这里实现关键元素的解析
        let mut project = AbletonProject {
            name: String::new(),
            sample_rate: 44100.0,
            bpm: 120.0,
            time_signature_num: 4,
            time_signature_den: 4,
            tracks: Vec::new(),
            return_tracks: Vec::new(),
            master_track: None,
            global_volume: 1.0,
            pre_roll_bars: 2,
        };

        // 解析BPM
        if let Some(bpm) = Self::extract_xml_float(xml_content, "Tempo") {
            project.bpm = bpm;
        }

        // 解析采样率
        if let Some(srate) = Self::extract_xml_float(xml_content, "SampleRate") {
            project.sample_rate = srate;
        }

        // 解析拍号
        if let Some(num) = Self::extract_xml_int(xml_content, "TimeSignatureNumerator") {
            project.time_signature_num = num as u8;
        }
        if let Some(den) = Self::extract_xml_int(xml_content, "TimeSignatureDenominator") {
            project.time_signature_den = den as u8;
        }

        // 解析轨道
        project.tracks = self.parse_tracks(xml_content);

        // 解析返回轨道
        project.return_tracks = self.parse_return_tracks(xml_content);

        // 解析主轨道
        project.master_track = self.parse_master_track(xml_content);

        Ok(project)
    }

    /// 从ALS文件解析（ALS是gzip压缩的XML）
    pub fn parse_file(&self, path: &Path) -> Result<AbletonProject, AbletonParseError> {
        // 读取文件
        let data = std::fs::read(path)?;

        // ALS文件是gzip压缩的XML
        // 尝试解压
        let xml_content = if data.starts_with(&[0x1f, 0x8b]) {
            // gzip压缩
            self.decompress_gzip(&data)?
        } else if data.starts_with(b"<?xml") || data.starts_with(b"<Ableton") {
            // 直接是XML
            String::from_utf8(data).map_err(|e| AbletonParseError::Gzip(e.to_string()))?
        } else {
            return Err(AbletonParseError::Format("无法识别的文件格式".to_string()));
        };

        self.parse_xml(&xml_content)
    }

    /// 解压gzip数据
    fn decompress_gzip(&self, data: &[u8]) -> Result<String, AbletonParseError> {
        // 简化实现：使用flate2（需要添加依赖）
        // 这里使用一个简单的回退方案
        use std::io::Read;
        let decoder = flate2::read::GzDecoder::new(data);
        let mut xml = String::new();
        decoder
            .take(10 * 1024 * 1024) // 最大10MB
            .read_to_string(&mut xml)
            .map_err(|e| AbletonParseError::Gzip(format!("解压失败: {}", e)))?;
        Ok(xml)
    }

    /// 从XML中提取浮点值
    fn extract_xml_float(xml: &str, tag: &str) -> Option<f64> {
        // 查找 <Tag Value="xxx" /> 或 <Tag Value="xxx">
        let pattern1 = format!("<{} Value=\"", tag);
        let pattern2 = format!("<{} Manual=\"", tag);

        for pattern in [&pattern1, &pattern2] {
            if let Some(start) = xml.find(pattern) {
                let value_start = start + pattern.len();
                if let Some(end) = xml[value_start..].find('"') {
                    let value_str = &xml[value_start..value_start + end];
                    return value_str.parse().ok();
                }
            }
        }

        None
    }

    /// 从XML中提取整数值
    fn extract_xml_int(xml: &str, tag: &str) -> Option<i64> {
        Self::extract_xml_float(xml, tag).map(|v| v as i64)
    }

    /// 解析轨道列表
    fn parse_tracks(&self, xml: &str) -> Vec<AbletonTrack> {
        let mut tracks = Vec::new();

        // 查找所有轨道块
        let track_types = [
            ("MidiTrack", AbletonTrackType::Midi),
            ("AudioTrack", AbletonTrackType::Audio),
        ];

        for (tag, track_type) in track_types {
            let mut search_start = 0;
            while let Some(pos) = xml[search_start..].find(&format!("<{}", tag)) {
                let block_start = search_start + pos;
                if let Some(block_end) = Self::find_closing_tag(xml, block_start, tag) {
                    let block = &xml[block_start..block_end];
                    let track = self.parse_single_track(block, track_type);
                    tracks.push(track);
                    search_start = block_end;
                } else {
                    break;
                }
            }
        }

        tracks
    }

    /// 解析返回轨道
    fn parse_return_tracks(&self, xml: &str) -> Vec<AbletonTrack> {
        let mut tracks = Vec::new();
        let tag = "ReturnTrack";
        let mut search_start = 0;

        while let Some(pos) = xml[search_start..].find(&format!("<{}", tag)) {
            let block_start = search_start + pos;
            if let Some(block_end) = Self::find_closing_tag(xml, block_start, tag) {
                let block = &xml[block_start..block_end];
                let track = self.parse_single_track(block, AbletonTrackType::Return);
                tracks.push(track);
                search_start = block_end;
            } else {
                break;
            }
        }

        tracks
    }

    /// 解析主轨道
    fn parse_master_track(&self, xml: &str) -> Option<AbletonTrack> {
        let tag = "MasterTrack";
        if let Some(pos) = xml.find(&format!("<{}", tag)) {
            if let Some(block_end) = Self::find_closing_tag(xml, pos, tag) {
                let block = &xml[pos..block_end];
                return Some(self.parse_single_track(block, AbletonTrackType::Master));
            }
        }
        None
    }

    /// 解析单个轨道块
    fn parse_single_track(&self, block: &str, track_type: AbletonTrackType) -> AbletonTrack {
        let mut track = AbletonTrack {
            track_type,
            ..AbletonTrack::default()
        };

        // 名称
        if let Some(name) = Self::extract_xml_attribute(block, "Name", "Value") {
            track.name = name;
        } else if let Some(name) = Self::extract_xml_attribute(block, "EffectiveName", "Value") {
            track.name = name;
        }

        // 音量
        if let Some(vol) = Self::extract_xml_float(block, "Volume") {
            track.volume = vol;
        } else if let Some(vol) = Self::extract_xml_float(block, "TargetVolume") {
            track.volume = vol;
        }

        // 声像
        if let Some(pan) = Self::extract_xml_float(block, "Pan") {
            track.pan = (pan - 0.5) * 2.0; // ALS: 0~1 → OpenDAW: -1~1
        }

        // 静音
        if let Some(muted) = Self::extract_xml_int(block, "Mute") {
            track.muted = muted != 0;
        } else if let Some(muted) = Self::extract_xml_int(block, "TrackMute") {
            track.muted = muted != 0;
        }

        // 独奏
        if let Some(solo) = Self::extract_xml_int(block, "Solo") {
            track.solo = solo != 0;
        } else if let Some(solo) = Self::extract_xml_int(block, "TrackSolo") {
            track.solo = solo != 0;
        }

        // 颜色
        if let Some(color) = Self::extract_xml_int(block, "Color") {
            track.color = color as u32;
        }

        // 设备
        track.devices = self.parse_devices(block);

        // Clips
        track.clips = self.parse_clips(block);

        track
    }

    /// 解析设备列表
    fn parse_devices(&self, block: &str) -> Vec<AbletonDevice> {
        let mut devices = Vec::new();

        // 查找 <DeviceChain> 中的设备
        let device_tags = [
            ("AudioEffectDevice", AbletonDeviceType::AudioEffect),
            ("MidiEffectDevice", AbletonDeviceType::MidiEffect),
            ("InstrumentGroupDevice", AbletonDeviceType::Instrument),
            ("PluginDevice", AbletonDeviceType::Vst),
            ("AuPluginDevice", AbletonDeviceType::Au),
        ];

        for (tag, dtype) in device_tags {
            let mut search_start = 0;
            while let Some(pos) = block[search_start..].find(&format!("<{}", tag)) {
                let block_start = search_start + pos;
                if let Some(block_end) = Self::find_closing_tag(block, block_start, tag) {
                    let dev_block = &block[block_start..block_end];

                    let name = Self::extract_xml_attribute(dev_block, "UserName", "Value")
                        .or_else(|| Self::extract_xml_attribute(dev_block, "Name", "Value"))
                        .unwrap_or_else(|| tag.to_string());

                    let enabled = Self::extract_xml_int_from_attr(dev_block, "Value")
                        .map(|v| v != 0)
                        .unwrap_or(true);

                    devices.push(AbletonDevice {
                        name,
                        device_type: dtype,
                        parameters: Vec::new(),
                        enabled,
                        macro_mappings: HashMap::new(),
                    });

                    search_start = block_end;
                } else {
                    break;
                }
            }
        }

        devices
    }

    /// 解析Clip列表
    fn parse_clips(&self, block: &str) -> Vec<AbletonClip> {
        let mut clips = Vec::new();
        let clip_tag = "MidiClip";
        let audio_clip_tag = "AudioClip";

        // MIDI Clips
        let mut search_start = 0;
        while let Some(pos) = block[search_start..].find(&format!("<{}", clip_tag)) {
            let block_start = search_start + pos;
            if let Some(block_end) = Self::find_closing_tag(block, block_start, clip_tag) {
                let clip_block = &block[block_start..block_end];

                let name = Self::extract_xml_attribute(clip_block, "Name", "Value")
                    .unwrap_or_default();

                let start = Self::extract_xml_float(clip_block, "CurrentStart").unwrap_or(0.0);
                let end = Self::extract_xml_float(clip_block, "CurrentEnd").unwrap_or(4.0);

                let notes = self.parse_midi_notes(clip_block);

                clips.push(AbletonClip {
                    name,
                    start,
                    end,
                    loop_enabled: Self::extract_xml_int_from_attr(clip_block, "Value")
                        .map(|v| v != 0)
                        .unwrap_or(true),
                    loop_start: Self::extract_xml_float(clip_block, "LoopStart").unwrap_or(0.0),
                    loop_end: Self::extract_xml_float(clip_block, "LoopEnd").unwrap_or(4.0),
                    content: AbletonClipContent::Midi {
                        notes,
                        channel: 0,
                    },
                    color: 0,
                });

                search_start = block_end;
            } else {
                break;
            }
        }

        // Audio Clips
        search_start = 0;
        while let Some(pos) = block[search_start..].find(&format!("<{}", audio_clip_tag)) {
            let block_start = search_start + pos;
            if let Some(block_end) = Self::find_closing_tag(block, block_start, audio_clip_tag) {
                let clip_block = &block[block_start..block_end];

                let name = Self::extract_xml_attribute(clip_block, "Name", "Value")
                    .unwrap_or_default();

                let file_ref = Self::extract_xml_attribute(clip_block, "FileRef", "Path")
                    .unwrap_or_default();

                clips.push(AbletonClip {
                    name,
                    start: Self::extract_xml_float(clip_block, "CurrentStart").unwrap_or(0.0),
                    end: Self::extract_xml_float(clip_block, "CurrentEnd").unwrap_or(4.0),
                    loop_enabled: true,
                    loop_start: 0.0,
                    loop_end: 4.0,
                    content: AbletonClipContent::Audio {
                        file_path: file_ref,
                        play_rate: 1.0,
                        reverse: false,
                    },
                    color: 0,
                });

                search_start = block_end;
            } else {
                break;
            }
        }

        clips
    }

    /// 解析MIDI音符
    fn parse_midi_notes(&self, clip_block: &str) -> Vec<AbletonMidiNote> {
        let mut notes = Vec::new();
        let note_tag = "NoteEvent";

        let mut search_start = 0;
        while let Some(pos) = clip_block[search_start..].find(&format!("<{}", note_tag)) {
            let note_start = search_start + pos;
            // NoteEvent是自闭合标签
            if let Some(end) = clip_block[note_start..].find("/>") {
                let note_block = &clip_block[note_start..note_start + end + 2];

                let pitch = Self::extract_xml_int_from_attr(note_block, "Note")
                    .unwrap_or(60) as u8;
                let start_beat = Self::extract_xml_float_from_attr(note_block, "Time")
                    .unwrap_or(0.0);
                let duration = Self::extract_xml_float_from_attr(note_block, "Duration")
                    .unwrap_or(1.0);
                let velocity = Self::extract_xml_int_from_attr(note_block, "Velocity")
                    .unwrap_or(100) as u8;

                notes.push(AbletonMidiNote {
                    pitch: pitch.min(127),
                    start_beat,
                    duration_beats: duration,
                    velocity: velocity.min(127),
                    muted: false,
                    probability: 1.0,
                });

                search_start = note_start + end + 2;
            } else {
                break;
            }
        }

        notes
    }

    /// 从XML标签提取属性值
    fn extract_xml_attribute(xml: &str, tag: &str, attr: &str) -> Option<String> {
        let pattern = format!("<{} {}=\"", tag, attr);
        if let Some(start) = xml.find(&pattern) {
            let value_start = start + pattern.len();
            if let Some(end) = xml[value_start..].find('"') {
                return Some(xml[value_start..value_start + end].to_string());
            }
        }
        None
    }

    /// 从XML属性提取浮点值（通用属性搜索）
    fn extract_xml_float_from_attr(xml: &str, attr: &str) -> Option<f64> {
        let pattern = format!("{}=\"", attr);
        if let Some(start) = xml.find(&pattern) {
            let value_start = start + pattern.len();
            if let Some(end) = xml[value_start..].find('"') {
                return xml[value_start..value_start + end].parse().ok();
            }
        }
        None
    }

    /// 从XML属性提取整数值
    fn extract_xml_int_from_attr(xml: &str, attr: &str) -> Option<i64> {
        Self::extract_xml_float_from_attr(xml, attr).map(|v| v as i64)
    }

    /// 查找XML闭合标签
    fn find_closing_tag(xml: &str, start: usize, tag: &str) -> Option<usize> {
        let close_tag = format!("</{}>", tag);
        let open_tag = format!("<{}", tag);

        let mut depth = 0;
        let mut pos = start;

        while pos < xml.len() {
            if let Some(next_open) = xml[pos..].find(&open_tag) {
                let open_pos = pos + next_open;
                // 确保是完整标签开始（不是属性中包含标签名的情况）
                let after_tag = &xml[open_pos + open_tag.len()..];
                if after_tag.starts_with(' ') || after_tag.starts_with('>') || after_tag.starts_with('/') {
                    depth += 1;
                    pos = open_pos + open_tag.len();
                    continue;
                }
            }

            if let Some(next_close) = xml[pos..].find(&close_tag) {
                let close_pos = pos + next_close;
                depth -= 1;
                if depth == 0 {
                    return Some(close_pos + close_tag.len());
                }
                pos = close_pos + close_tag.len();
                continue;
            }

            break;
        }

        None
    }
}

impl Default for AbletonProjectParser {
    fn default() -> Self {
        Self::new()
    }
}

// ── ALS → OpenDAW项目转换 ─────────────────────────────────

/// ALS → OpenDAW转换器
pub struct AbletonToProject;

impl AbletonToProject {
    /// 创建新的转换器
    pub fn new() -> Self {
        Self
    }

    /// 转换Ableton项目为OpenDAW项目配置
    pub fn convert(&self, ableton: &AbletonProject) -> ProjectConfig {
        let tracks: Vec<TrackConfig> = ableton
            .tracks
            .iter()
            .filter(|t| t.track_type != AbletonTrackType::Group)
            .map(|track| {
                let plugins: Vec<String> = track
                    .devices
                    .iter()
                    .map(|d| match d.device_type {
                        AbletonDeviceType::AudioEffect => format!("ableton/fx/{}", d.name),
                        AbletonDeviceType::MidiEffect => format!("ableton/mfx/{}", d.name),
                        AbletonDeviceType::Instrument => format!("ableton/inst/{}", d.name),
                        AbletonDeviceType::Vst => format!("vst:{}", d.name),
                        AbletonDeviceType::Au => format!("au:{}", d.name),
                        _ => format!("plugin:{}", d.name),
                    })
                    .collect();

                let channels = match track.track_type {
                    AbletonTrackType::Midi => 1,
                    _ => 2,
                };

                TrackConfig {
                    name: if track.name.is_empty() {
                        format!("{:?}", track.track_type)
                    } else {
                        track.name.clone()
                    },
                    channels,
                    volume: track.volume,
                    pan: track.pan,
                    muted: track.muted,
                    plugins,
                }
            })
            .collect();

        ProjectConfig {
            name: if ableton.name.is_empty() {
                "Imported from Ableton".to_string()
            } else {
                ableton.name.clone()
            },
            sample_rate: ableton.sample_rate,
            buffer_size: 512,
            tracks,
            master_volume: ableton.global_volume,
        }
    }

    /// 转换Ableton MIDI Clips为Patterns
    pub fn convert_clips_to_patterns(&self, ableton: &AbletonProject) -> Vec<Pattern> {
        let mut patterns = Vec::new();
        let mut pattern_counter = 0;

        for track in &ableton.tracks {
            for clip in &track.clips {
                let length_beats = clip.end - clip.start;

                let (midi_notes, pattern_type) = match &clip.content {
                    AbletonClipContent::Midi { notes, .. } => {
                        let midi_notes: Vec<MidiNote> = notes
                            .iter()
                            .map(|n| MidiNote::new(n.pitch, n.start_beat, n.duration_beats, n.velocity))
                            .collect();
                        (midi_notes, PatternType::Midi)
                    }
                    AbletonClipContent::Audio { .. } => (Vec::new(), PatternType::Audio),
                };

                let mut pattern = Pattern::new(
                    &format!("als_{}", pattern_counter),
                    &clip.name,
                    pattern_type,
                    length_beats.max(1.0),
                );

                for note in midi_notes {
                    pattern.add_note(note);
                }

                pattern.add_tag("ableton-import");
                patterns.push(pattern);
                pattern_counter += 1;
            }
        }

        patterns
    }

    /// 生成转换报告
    pub fn conversion_report(&self, ableton: &AbletonProject) -> String {
        let mut report = String::new();

        report.push_str("Ableton项目转换报告\n");
        report.push_str("==================\n");
        report.push_str(&format!("BPM: {:.1}\n", ableton.bpm));
        report.push_str(&format!("采样率: {:.0}\n", ableton.sample_rate));
        report.push_str(&format!("轨道数: {}\n", ableton.tracks.len()));
        report.push_str(&format!("返回轨道数: {}\n\n", ableton.return_tracks.len()));

        for track in &ableton.tracks {
            report.push_str(&format!("轨道: {} ({:?})\n", track.name, track.track_type));
            report.push_str(&format!("  音量: {:.2}, 声像: {:.2}\n", track.volume, track.pan));
            report.push_str(&format!("  设备: {}\n", track.devices.len()));
            for device in &track.devices {
                report.push_str(&format!(
                    "    {} ({:?}) {}\n",
                    device.name,
                    device.device_type,
                    if device.enabled { "" } else { "[禁用]" }
                ));
            }
            report.push_str(&format!("  Clips: {}\n\n", track.clips.len()));
        }

        report
    }
}

impl Default for AbletonToProject {
    fn default() -> Self {
        Self::new()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_parse_empty_project() {
        let parser = AbletonProjectParser::new();
        let result = parser.parse_xml("<Ableton></Ableton>").unwrap();
        assert_eq!(result.tracks.len(), 0);
        assert!((result.bpm - 120.0).abs() < 1e-10);
    }

    #[test]
    fn test_parse_bpm() {
        let xml = r#"<Ableton><Tempo Value="140.5"/></Ableton>"#;
        let parser = AbletonProjectParser::new();
        let result = parser.parse_xml(xml).unwrap();
        assert!((result.bpm - 140.5).abs() < 1e-10);
    }

    #[test]
    fn test_parse_sample_rate() {
        let xml = r#"<Ableton><SampleRate Value="48000"/></Ableton>"#;
        let parser = AbletonProjectParser::new();
        let result = parser.parse_xml(xml).unwrap();
        assert!((result.sample_rate - 48000.0).abs() < 1e-10);
    }

    #[test]
    fn test_parse_midi_track() {
        let xml = r#"<Ableton><MidiTrack><Name Value="Synth"/><Volume Value="0.8"/><Pan Value="0.7"/><Mute Value="0"/></MidiTrack></Ableton>"#;
        let parser = AbletonProjectParser::new();
        let result = parser.parse_xml(xml).unwrap();
        assert_eq!(result.tracks.len(), 1);
        assert_eq!(result.tracks[0].name, "Synth");
        assert_eq!(result.tracks[0].track_type, AbletonTrackType::Midi);
    }

    #[test]
    fn test_parse_audio_track() {
        let xml = r#"<Ableton><AudioTrack><Name Value="Vocals"/><Volume Value="1.0"/></AudioTrack></Ableton>"#;
        let parser = AbletonProjectParser::new();
        let result = parser.parse_xml(xml).unwrap();
        assert_eq!(result.tracks.len(), 1);
        assert_eq!(result.tracks[0].track_type, AbletonTrackType::Audio);
    }

    #[test]
    fn test_ableton_to_project_convert() {
        let ableton = AbletonProject {
            name: "Test ALS".to_string(),
            sample_rate: 44100.0,
            bpm: 128.0,
            time_signature_num: 4,
            time_signature_den: 4,
            tracks: vec![AbletonTrack {
                name: "Synth".to_string(),
                track_type: AbletonTrackType::Midi,
                volume: 0.8,
                pan: -0.3,
                muted: false,
                solo: false,
                color: 0,
                devices: Vec::new(),
                clips: Vec::new(),
                sends: Vec::new(),
                group_id: None,
            }],
            return_tracks: Vec::new(),
            master_track: None,
            global_volume: 1.0,
            pre_roll_bars: 2,
        };

        let converter = AbletonToProject::new();
        let config = converter.convert(&ableton);
        assert_eq!(config.name, "Test ALS");
        assert_eq!(config.tracks.len(), 1);
        assert_eq!(config.tracks[0].name, "Synth");
    }

    #[test]
    fn test_ableton_to_project_patterns() {
        let ableton = AbletonProject {
            name: "Test".to_string(),
            sample_rate: 44100.0,
            bpm: 120.0,
            time_signature_num: 4,
            time_signature_den: 4,
            tracks: vec![AbletonTrack {
                name: "Piano".to_string(),
                track_type: AbletonTrackType::Midi,
                clips: vec![AbletonClip {
                    name: "Chorus".to_string(),
                    start: 0.0,
                    end: 4.0,
                    loop_enabled: true,
                    loop_start: 0.0,
                    loop_end: 4.0,
                    content: AbletonClipContent::Midi {
                        notes: vec![AbletonMidiNote {
                            pitch: 60,
                            start_beat: 0.0,
                            duration_beats: 1.0,
                            velocity: 100,
                            muted: false,
                            probability: 1.0,
                        }],
                        channel: 0,
                    },
                    color: 0,
                }],
                ..AbletonTrack::default()
            }],
            return_tracks: Vec::new(),
            master_track: None,
            global_volume: 1.0,
            pre_roll_bars: 2,
        };

        let converter = AbletonToProject::new();
        let patterns = converter.convert_clips_to_patterns(&ableton);
        assert_eq!(patterns.len(), 1);
        assert!(patterns[0].tags.contains(&"ableton-import".to_string()));
    }

    #[test]
    fn test_conversion_report() {
        let ableton = AbletonProject {
            name: "Report Test".to_string(),
            sample_rate: 48000.0,
            bpm: 128.0,
            time_signature_num: 4,
            time_signature_den: 4,
            tracks: vec![AbletonTrack {
                name: "Bass".to_string(),
                track_type: AbletonTrackType::Midi,
                ..AbletonTrack::default()
            }],
            return_tracks: Vec::new(),
            master_track: None,
            global_volume: 1.0,
            pre_roll_bars: 2,
        };

        let converter = AbletonToProject::new();
        let report = converter.conversion_report(&ableton);
        assert!(report.contains("128.0"));
        assert!(report.contains("Bass"));
    }
}
