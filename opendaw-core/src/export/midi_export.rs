//! MIDI导出 — Standard MIDI File (SMF) 导出
//!
//! - MidiExporter: SMF导出器
//! - Format 0（单轨）和 Format 1（多轨）
//! - 支持tempo map、time signature、track name等meta事件
//! - 从OpenDAW项目提取→MIDI文件

use std::collections::HashMap;
use std::io::Write;
use std::path::Path;

use serde::{Deserialize, Serialize};

use crate::pattern::{MidiNote, Pattern, PatternType};

// ── MIDI文件常量 ──────────────────────────────────────────

/// MIDI头部标签
const MIDI_HEADER_TAG: &[u8; 4] = b"MThd";
/// MIDI轨道标签
const MIDI_TRACK_TAG: &[u8; 4] = b"MTrk";

/// Meta事件类型
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum MetaType {
    /// 序号
    SequenceNumber = 0x00,
    /// 文本事件
    TextEvent = 0x01,
    /// 版权声明
    CopyrightNotice = 0x02,
    /// 轨道名称
    TrackName = 0x03,
    /// 乐器名称
    InstrumentName = 0x04,
    /// 歌词
    Lyric = 0x05,
    /// 标记
    Marker = 0x06,
    /// Cue点
    CuePoint = 0x07,
    /// 通道前缀
    ChannelPrefix = 0x20,
    /// 端口
    MidiPort = 0x21,
    /// 曲目结束
    EndOfTrack = 0x2F,
    /// 速度
    SetTempo = 0x51,
    /// SMPTE偏移
    SmpteOffset = 0x54,
    /// 拍号
    TimeSignature = 0x58,
    /// 调号
    KeySignature = 0x59,
    /// 音序器特定
    SequencerSpecific = 0x7F,
}

// ── MIDI事件 ──────────────────────────────────────────────

/// MIDI事件
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MidiEvent {
    /// 绝对tick位置
    pub tick: u32,
    /// 事件数据
    pub data: Vec<u8>,
}

impl MidiEvent {
    /// 创建音符开启事件
    pub fn note_on(channel: u8, note: u8, velocity: u8, tick: u32) -> Self {
        Self {
            tick,
            data: vec![0x90 | (channel & 0x0F), note & 0x7F, velocity & 0x7F],
        }
    }

    /// 创建音符关闭事件
    pub fn note_off(channel: u8, note: u8, tick: u32) -> Self {
        Self {
            tick,
            data: vec![0x80 | (channel & 0x0F), note & 0x7F, 0x00],
        }
    }

    /// 创建速度meta事件
    pub fn tempo(bpm: f64, tick: u32) -> Self {
        let microseconds_per_beat = (60_000_000.0 / bpm) as u32;
        Self {
            tick,
            data: vec![
                0xFF,
                MetaType::SetTempo as u8,
                0x03,
                ((microseconds_per_beat >> 16) & 0xFF) as u8,
                ((microseconds_per_beat >> 8) & 0xFF) as u8,
                (microseconds_per_beat & 0xFF) as u8,
            ],
        }
    }

    /// 创建拍号meta事件
    pub fn time_signature(num: u8, den: u8, tick: u32) -> Self {
        let den_power = (den as f64).log2() as u8; // 4→2, 8→3
        Self {
            tick,
            data: vec![
                0xFF,
                MetaType::TimeSignature as u8,
                0x04,
                num,
                den_power,
                24, // MIDI clocks per metronome tick
                8,  // 32nd notes per quarter note
            ],
        }
    }

    /// 创建轨道名称meta事件
    pub fn track_name(name: &str, tick: u32) -> Self {
        let name_bytes = name.as_bytes();
        let mut data = vec![0xFF, MetaType::TrackName as u8];
        data.extend_from_slice(&Self::encode_variable_length(name_bytes.len() as u32));
        data.extend_from_slice(name_bytes);
        Self { tick, data }
    }

    /// 创建曲目结束meta事件
    pub fn end_of_track(tick: u32) -> Self {
        Self {
            tick,
            data: vec![0xFF, MetaType::EndOfTrack as u8, 0x00],
        }
    }

    /// 编码变长数值
    fn encode_variable_length(value: u32) -> Vec<u8> {
        if value == 0 {
            return vec![0x00];
        }

        let mut result = Vec::new();
        let mut v = value;

        // 从低到高每7位一组
        let mut bytes = Vec::new();
        while v > 0 {
            bytes.push((v & 0x7F) as u8);
            v >>= 7;
        }

        // 反转，高位在前，设置最高位标志
        for (i, &byte) in bytes.iter().rev().enumerate() {
            if i < bytes.len() - 1 {
                result.push(byte | 0x80);
            } else {
                result.push(byte);
            }
        }

        result
    }
}

// ── MIDI轨道 ──────────────────────────────────────────────

/// MIDI轨道（用于导出）
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MidiTrack {
    /// 轨道名称
    pub name: String,
    /// MIDI通道
    pub channel: u8,
    /// 事件列表（已排序）
    pub events: Vec<MidiEvent>,
}

impl MidiTrack {
    /// 创建新的MIDI轨道
    pub fn new(name: &str, channel: u8) -> Self {
        Self {
            name: name.to_string(),
            channel,
            events: Vec::new(),
        }
    }

    /// 添加音符
    pub fn add_note(&mut self, note: &MidiNote, ppq: u32, bpm: f64) {
        let start_tick = (note.start_beat * ppq as f64).round() as u32;
        let duration_ticks = (note.duration_beats * ppq as f64).round() as u32;
        let end_tick = start_tick + duration_ticks.max(1);

        self.events.push(MidiEvent::note_on(
            self.channel,
            note.pitch,
            note.velocity,
            start_tick,
        ));
        self.events
            .push(MidiEvent::note_off(self.channel, note.pitch, end_tick));
    }

    /// 排序事件
    pub fn sort_events(&mut self) {
        self.events.sort_by_key(|e| e.tick);
    }

    /// 添加轨道名称事件
    pub fn add_track_name(&mut self, tick: u32) {
        self.events.push(MidiEvent::track_name(&self.name, tick));
    }

    /// 添加曲目结束事件
    pub fn add_end_of_track(&mut self) {
        if let Some(last) = self.events.last() {
            self.events.push(MidiEvent::end_of_track(last.tick));
        } else {
            self.events.push(MidiEvent::end_of_track(0));
        }
    }
}

// ── MIDI导出器 ────────────────────────────────────────────

/// MIDI导出配置
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MidiExportConfig {
    /// MIDI格式 (0或1)
    pub format: u16,
    /// 每四分音符的tick数 (PPQ)
    pub ppq: u16,
    /// 初始BPM
    pub initial_bpm: f64,
    /// 拍号
    pub time_signature_num: u8,
    /// 拍号分母
    pub time_signature_den: u8,
    /// 是否包含轨道名称
    pub include_track_names: bool,
    /// 是否包含速度map
    pub include_tempo_map: bool,
    /// 是否包含拍号
    pub include_time_signature: bool,
}

impl Default for MidiExportConfig {
    fn default() -> Self {
        Self {
            format: 1,
            ppq: 480,
            initial_bpm: 120.0,
            time_signature_num: 4,
            time_signature_den: 4,
            include_track_names: true,
            include_tempo_map: true,
            include_time_signature: true,
        }
    }
}

/// MIDI导出器
pub struct MidiExporter {
    config: MidiExportConfig,
}

impl MidiExporter {
    /// 创建新的MIDI导出器
    pub fn new(config: MidiExportConfig) -> Self {
        Self { config }
    }

    /// 使用默认配置
    pub fn default_exporter() -> Self {
        Self::new(MidiExportConfig::default())
    }

    /// 导出Format 0（单轨）
    pub fn export_format0(&self, patterns: &[Pattern]) -> Vec<u8> {
        let mut tempo_track = self.create_tempo_track();

        // 合并所有Pattern到一条轨道
        let mut merged_track = MidiTrack::new("All Tracks", 0);

        for pattern in patterns {
            for note in &pattern.midi_notes {
                merged_track.add_note(note, self.config.ppq as u32, self.config.initial_bpm);
            }
        }

        merged_track.sort_events();
        if self.config.include_track_names {
            merged_track.add_track_name(0);
        }
        merged_track.add_end_of_track();

        // Format 0: 只有一个轨道（tempo track包含音符数据）
        // 将tempo事件合并到音符轨道
        let mut combined_track = MidiTrack::new("All Tracks", 0);

        // 添加tempo事件
        if self.config.include_tempo_map {
            combined_track
                .events
                .push(MidiEvent::tempo(self.config.initial_bpm, 0));
        }
        if self.config.include_time_signature {
            combined_track.events.push(MidiEvent::time_signature(
                self.config.time_signature_num,
                self.config.time_signature_den,
                0,
            ));
        }

        // 添加音符事件
        combined_track.events.extend(merged_track.events);
        combined_track.sort_events();
        combined_track.add_end_of_track();

        self.encode_file(0, 1, &[combined_track])
    }

    /// 导出Format 1（多轨）
    pub fn export_format1(&self, patterns: &[Pattern]) -> Vec<u8> {
        let tempo_track = self.create_tempo_track();

        let mut tracks = vec![tempo_track];

        for (i, pattern) in patterns.iter().enumerate() {
            if pattern.midi_notes.is_empty() {
                continue;
            }

            let channel = (i % 16) as u8;
            let mut track = MidiTrack::new(&pattern.name, channel);

            for note in &pattern.midi_notes {
                track.add_note(note, self.config.ppq as u32, self.config.initial_bpm);
            }

            track.sort_events();
            if self.config.include_track_names {
                track.add_track_name(0);
            }
            track.add_end_of_track();

            tracks.push(track);
        }

        self.encode_file(1, tracks.len() as u16, &tracks)
    }

    /// 创建速度轨道
    fn create_tempo_track(&self) -> MidiTrack {
        let mut track = MidiTrack::new("Tempo", 0);

        if self.config.include_time_signature {
            track.events.push(MidiEvent::time_signature(
                self.config.time_signature_num,
                self.config.time_signature_den,
                0,
            ));
        }

        if self.config.include_tempo_map {
            track
                .events
                .push(MidiEvent::tempo(self.config.initial_bpm, 0));
        }

        if self.config.include_track_names {
            track.add_track_name(0);
        }

        track.add_end_of_track();
        track
    }

    /// 编码MIDI文件
    fn encode_file(&self, format: u16, num_tracks: u16, tracks: &[MidiTrack]) -> Vec<u8> {
        let mut output = Vec::new();

        // Header chunk
        output.extend_from_slice(MIDI_HEADER_TAG);
        output.extend_from_slice(&6u32.to_be_bytes()); // header length
        output.extend_from_slice(&format.to_be_bytes());
        output.extend_from_slice(&num_tracks.to_be_bytes());
        output.extend_from_slice(&self.config.ppq.to_be_bytes());

        // Track chunks
        for track in tracks {
            let track_data = self.encode_track(track);
            output.extend_from_slice(MIDI_TRACK_TAG);
            output.extend_from_slice(&(track_data.len() as u32).to_be_bytes());
            output.extend_from_slice(&track_data);
        }

        output
    }

    /// 编码单个轨道
    fn encode_track(&self, track: &MidiTrack) -> Vec<u8> {
        let mut output = Vec::new();

        // 确保事件按tick排序
        let mut events = track.events.clone();
        events.sort_by_key(|e| e.tick);

        let mut last_tick: u32 = 0;
        let mut last_status: u8 = 0;

        for event in events {
            // 计算delta time
            let delta = event.tick.saturating_sub(last_tick);
            output.extend_from_slice(&MidiEvent::encode_variable_length(delta));
            last_tick = event.tick;

            // 写入事件数据
            // 运行状态压缩
            if !event.data.is_empty() && event.data[0] == last_status && event.data[0] < 0xF0 {
                // 跳过状态字节（运行状态）
                output.extend_from_slice(&event.data[1..]);
            } else {
                output.extend_from_slice(&event.data);
                if !event.data.is_empty() && event.data[0] < 0xF0 {
                    last_status = event.data[0];
                } else {
                    last_status = 0; // Meta/SysEx重置运行状态
                }
            }
        }

        output
    }

    /// 导出到文件
    pub fn export_to_file(&self, patterns: &[Pattern], path: &Path) -> std::io::Result<()> {
        let data = if self.config.format == 0 {
            self.export_format0(patterns)
        } else {
            self.export_format1(patterns)
        };

        let mut file = std::fs::File::create(path)?;
        file.write_all(&data)?;
        Ok(())
    }

    /// 导出单个Pattern为MIDI文件
    pub fn export_pattern(&self, pattern: &Pattern, path: &Path) -> std::io::Result<()> {
        self.export_to_file(&[pattern.clone()], path)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_midi_event_note_on() {
        let event = MidiEvent::note_on(0, 60, 100, 0);
        assert_eq!(event.data[0], 0x90);
        assert_eq!(event.data[1], 60);
        assert_eq!(event.data[2], 100);
    }

    #[test]
    fn test_midi_event_note_off() {
        let event = MidiEvent::note_off(0, 60, 480);
        assert_eq!(event.data[0], 0x80);
        assert_eq!(event.data[1], 60);
        assert_eq!(event.tick, 480);
    }

    #[test]
    fn test_midi_event_tempo() {
        let event = MidiEvent::tempo(120.0, 0);
        assert_eq!(event.data[0], 0xFF);
        assert_eq!(event.data[1], 0x51);
        // 120 BPM = 500000 microseconds per beat
        assert_eq!(event.data[3], 0x07);
        assert_eq!(event.data[4], 0xA1);
        assert_eq!(event.data[5], 0x20);
    }

    #[test]
    fn test_midi_event_time_signature() {
        let event = MidiEvent::time_signature(4, 4, 0);
        assert_eq!(event.data[0], 0xFF);
        assert_eq!(event.data[1], 0x58);
        assert_eq!(event.data[3], 4); // numerator
        assert_eq!(event.data[4], 2); // denominator power (4 = 2^2)
    }

    #[test]
    fn test_variable_length_encoding() {
        assert_eq!(MidiEvent::encode_variable_length(0), vec![0x00]);
        assert_eq!(MidiEvent::encode_variable_length(127), vec![0x7F]);
        assert_eq!(MidiEvent::encode_variable_length(128), vec![0x81, 0x00]);
        assert_eq!(MidiEvent::encode_variable_length(255), vec![0x81, 0x7F]);
        assert_eq!(MidiEvent::encode_variable_length(256), vec![0x82, 0x00]);
        assert_eq!(MidiEvent::encode_variable_length(480), vec![0x83, 0x60]);
    }

    #[test]
    fn test_midi_track() {
        let mut track = MidiTrack::new("Test", 0);
        let note = MidiNote::new(60, 0.0, 1.0, 100);
        track.add_note(&note, 480, 120.0);
        track.sort_events();

        // note_on + note_off
        assert_eq!(track.events.len(), 2);
    }

    #[test]
    fn test_midi_track_end_of_track() {
        let mut track = MidiTrack::new("Test", 0);
        let note = MidiNote::new(60, 0.0, 1.0, 100);
        track.add_note(&note, 480, 120.0);
        track.add_end_of_track();

        assert!(track.events.len() >= 3); // note_on + note_off + end_of_track
    }

    #[test]
    fn test_midi_export_format1() {
        let exporter = MidiExporter::new(MidiExportConfig {
            format: 1,
            ppq: 480,
            ..MidiExportConfig::default()
        });

        let mut pattern = Pattern::midi("test", "Test Pattern", 4.0);
        pattern.add_note(MidiNote::new(60, 0.0, 1.0, 100));
        pattern.add_note(MidiNote::new(64, 1.0, 1.0, 80));
        pattern.add_note(MidiNote::new(67, 2.0, 2.0, 90));

        let data = exporter.export_format1(&[pattern]);

        // 检查MIDI文件头
        assert_eq!(&data[0..4], b"MThd");
        assert_eq!(u16::from_be_bytes([data[8], data[9]]), 1); // format 1
        assert!(u16::from_be_bytes([data[10], data[11]]) >= 2); // at least tempo + note track
        assert_eq!(u16::from_be_bytes([data[12], data[13]]), 480); // ppq
    }

    #[test]
    fn test_midi_export_format0() {
        let exporter = MidiExporter::new(MidiExportConfig {
            format: 0,
            ppq: 480,
            ..MidiExportConfig::default()
        });

        let mut pattern = Pattern::midi("test", "Test", 4.0);
        pattern.add_note(MidiNote::new(60, 0.0, 1.0, 100));

        let data = exporter.export_format0(&[pattern]);

        // 检查MIDI文件头
        assert_eq!(&data[0..4], b"MThd");
        assert_eq!(u16::from_be_bytes([data[8], data[9]]), 0); // format 0
        assert_eq!(u16::from_be_bytes([data[10], data[11]]), 1); // single track
    }

    #[test]
    fn test_midi_export_empty_pattern() {
        let exporter = MidiExporter::default_exporter();
        let pattern = Pattern::midi("empty", "Empty", 4.0);

        let data = exporter.export_format1(&[pattern]);
        assert_eq!(&data[0..4], b"MThd");
        // Should have at least the tempo track
        assert!(u16::from_be_bytes([data[10], data[11]]) >= 1);
    }

    #[test]
    fn test_midi_export_multiple_patterns() {
        let exporter = MidiExporter::default_exporter();

        let mut p1 = Pattern::midi("p1", "Piano", 4.0);
        p1.add_note(MidiNote::new(60, 0.0, 1.0, 100));

        let mut p2 = Pattern::midi("p2", "Bass", 4.0);
        p2.add_note(MidiNote::new(36, 0.0, 2.0, 90));

        let data = exporter.export_format1(&[p1, p2]);
        assert_eq!(&data[0..4], b"MThd");
        // tempo track + piano + bass = 3 tracks
        let num_tracks = u16::from_be_bytes([data[10], data[11]]);
        assert!(num_tracks >= 3);
    }

    #[test]
    fn test_export_config_default() {
        let config = MidiExportConfig::default();
        assert_eq!(config.format, 1);
        assert_eq!(config.ppq, 480);
        assert!((config.initial_bpm - 120.0).abs() < 1e-10);
        assert_eq!(config.time_signature_num, 4);
        assert_eq!(config.time_signature_den, 4);
    }
}
