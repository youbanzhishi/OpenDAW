//! Pattern库 — 可复用的MIDI/音频片段
//!
//! - Pattern: 可复用的片段
//! - PatternLibrary: Pattern的增删改查、分类、标签
//! - PatternInstance: Pattern在时间线上的实例引用

use std::collections::HashMap;

use serde::{Deserialize, Serialize};

/// Pattern类型
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum PatternType {
    /// MIDI片段
    Midi,
    /// 音频片段
    Audio,
    /// 混合片段（MIDI+音频）
    Hybrid,
}

/// MIDI音符
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MidiNote {
    /// 音高 (0-127)
    pub pitch: u8,
    /// 起始拍
    pub start_beat: f64,
    /// 持续拍数
    pub duration_beats: f64,
    /// 力度 (0-127)
    pub velocity: u8,
}

impl MidiNote {
    /// 创建新的MIDI音符
    pub fn new(pitch: u8, start_beat: f64, duration_beats: f64, velocity: u8) -> Self {
        Self {
            pitch: pitch.min(127),
            start_beat,
            duration_beats,
            velocity: velocity.min(127),
        }
    }

    /// 结束拍
    pub fn end_beat(&self) -> f64 {
        self.start_beat + self.duration_beats
    }
}

/// 音频区域
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AudioRegion {
    /// 音频文件路径
    pub file_path: String,
    /// 起始拍
    pub start_beat: f64,
    /// 持续拍数
    pub duration_beats: f64,
    /// 偏移量（从音频文件的哪个位置开始播放，秒）
    pub offset_secs: f64,
}

impl AudioRegion {
    /// 创建新的音频区域
    pub fn new(file_path: &str, start_beat: f64, duration_beats: f64) -> Self {
        Self {
            file_path: file_path.to_string(),
            start_beat,
            duration_beats,
            offset_secs: 0.0,
        }
    }

    /// 结束拍
    pub fn end_beat(&self) -> f64 {
        self.start_beat + self.duration_beats
    }
}

/// Pattern — 可复用的MIDI/音频片段
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Pattern {
    /// 唯一ID
    pub id: String,
    /// Pattern名称
    pub name: String,
    /// Pattern类型
    pub pattern_type: PatternType,
    /// 长度（拍）
    pub length_beats: f64,
    /// MIDI音符列表
    pub midi_notes: Vec<MidiNote>,
    /// 音频区域列表
    pub audio_regions: Vec<AudioRegion>,
    /// 标签
    pub tags: Vec<String>,
    /// 分类
    pub category: String,
    /// 颜色 (0xRRGGBB)
    pub color: u32,
}

impl Pattern {
    /// 创建新的Pattern
    pub fn new(id: &str, name: &str, pattern_type: PatternType, length_beats: f64) -> Self {
        Self {
            id: id.to_string(),
            name: name.to_string(),
            pattern_type,
            length_beats,
            midi_notes: Vec::new(),
            audio_regions: Vec::new(),
            tags: Vec::new(),
            category: "未分类".to_string(),
            color: 0x4488FF,
        }
    }

    /// 创建MIDI Pattern
    pub fn midi(id: &str, name: &str, length_beats: f64) -> Self {
        Self::new(id, name, PatternType::Midi, length_beats)
    }

    /// 创建音频Pattern
    pub fn audio(id: &str, name: &str, length_beats: f64) -> Self {
        Self::new(id, name, PatternType::Audio, length_beats)
    }

    /// 添加MIDI音符
    pub fn add_note(&mut self, note: MidiNote) {
        self.midi_notes.push(note);
        self.update_type();
    }

    /// 移除MIDI音符
    pub fn remove_note(&mut self, index: usize) -> Option<MidiNote> {
        if index < self.midi_notes.len() {
            let note = self.midi_notes.remove(index);
            self.update_type();
            Some(note)
        } else {
            None
        }
    }

    /// 添加音频区域
    pub fn add_audio_region(&mut self, region: AudioRegion) {
        self.audio_regions.push(region);
        self.update_type();
    }

    /// 移除音频区域
    pub fn remove_audio_region(&mut self, index: usize) -> Option<AudioRegion> {
        if index < self.audio_regions.len() {
            let region = self.audio_regions.remove(index);
            self.update_type();
            Some(region)
        } else {
            None
        }
    }

    /// 添加标签
    pub fn add_tag(&mut self, tag: &str) {
        if !self.tags.contains(&tag.to_string()) {
            self.tags.push(tag.to_string());
        }
    }

    /// 移除标签
    pub fn remove_tag(&mut self, tag: &str) {
        self.tags.retain(|t| t != tag);
    }

    /// 音符数量
    pub fn note_count(&self) -> usize {
        self.midi_notes.len()
    }

    /// 获取指定范围内的音符
    pub fn notes_in_range(&self, start_beat: f64, end_beat: f64) -> Vec<&MidiNote> {
        self.midi_notes
            .iter()
            .filter(|n| n.start_beat < end_beat && n.end_beat() >= start_beat)
            .collect()
    }

    /// 转置所有音符
    pub fn transpose(&mut self, semitones: i8) {
        for note in &mut self.midi_notes {
            let new_pitch = (note.pitch as i16 + semitones as i16).clamp(0, 127) as u8;
            note.pitch = new_pitch;
        }
    }

    /// 量化所有音符
    pub fn quantize(&mut self, grid: f64) {
        for note in &mut self.midi_notes {
            note.start_beat = (note.start_beat / grid).round() * grid;
        }
    }

    /// 根据内容自动更新类型
    fn update_type(&mut self) {
        let has_midi = !self.midi_notes.is_empty()
            || matches!(self.pattern_type, PatternType::Midi | PatternType::Hybrid);
        let has_audio = !self.audio_regions.is_empty();
        self.pattern_type = match (has_midi, has_audio) {
            (true, true) => PatternType::Hybrid,
            (true, false) => PatternType::Midi,
            (false, true) => PatternType::Audio,
            (false, false) => self.pattern_type, // 保持原类型
        };
    }

    /// 生成示例Pattern
    pub fn example_kick() -> Self {
        let mut pattern = Self::midi("kick_4onfloor", "Kick 4-on-floor", 4.0);
        for i in 0..4 {
            pattern.add_note(MidiNote::new(36, i as f64, 0.25, 100)); // C1 = 36
        }
        pattern.add_tag("drums");
        pattern.add_tag("kick");
        pattern.category = "鼓组".to_string();
        pattern.color = 0xFF4444;
        pattern
    }

    /// 生成示例贝斯Pattern
    pub fn example_bass() -> Self {
        let mut pattern = Self::midi("bass_basic", "Bass Basic", 4.0);
        pattern.add_note(MidiNote::new(36, 0.0, 1.0, 90));  // C1
        pattern.add_note(MidiNote::new(36, 1.0, 1.0, 90));
        pattern.add_note(MidiNote::new(43, 2.0, 1.0, 85));  // G1
        pattern.add_note(MidiNote::new(43, 3.0, 1.0, 85));
        pattern.add_tag("bass");
        pattern.category = "贝斯".to_string();
        pattern.color = 0x44AA44;
        pattern
    }
}

/// Pattern实例 — Pattern在时间线上的引用
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PatternInstance {
    /// 实例唯一ID
    pub id: String,
    /// 引用的Pattern ID
    pub pattern_id: String,
    /// 在时间线上的起始拍
    pub start_beat: f64,
    /// 是否启用
    pub enabled: bool,
    /// 实例专属的音量偏移
    pub volume_offset: f64,
}

impl PatternInstance {
    /// 创建新的Pattern实例
    pub fn new(id: &str, pattern_id: &str, start_beat: f64) -> Self {
        Self {
            id: id.to_string(),
            pattern_id: pattern_id.to_string(),
            start_beat,
            enabled: true,
            volume_offset: 0.0,
        }
    }

    /// 结束拍（需要从Pattern获取长度，这里简化为记录起始拍）
    pub fn end_beat(&self, pattern_length: f64) -> f64 {
        self.start_beat + pattern_length
    }
}

/// Pattern库 — 管理所有Pattern
pub struct PatternLibrary {
    /// Pattern集合
    patterns: HashMap<String, Pattern>,
    /// Pattern实例集合
    instances: HashMap<String, PatternInstance>,
    /// 分类列表
    categories: Vec<String>,
    /// 下一个实例ID计数器
    next_instance_id: usize,
}

impl PatternLibrary {
    /// 创建新的Pattern库
    pub fn new() -> Self {
        Self {
            patterns: HashMap::new(),
            instances: HashMap::new(),
            categories: vec!["未分类".to_string()],
            next_instance_id: 0,
        }
    }

    /// 添加Pattern
    pub fn add_pattern(&mut self, pattern: Pattern) {
        // 确保分类存在
        if !self.categories.contains(&pattern.category) {
            self.categories.push(pattern.category.clone());
        }
        self.patterns.insert(pattern.id.clone(), pattern);
    }

    /// 移除Pattern
    pub fn remove_pattern(&mut self, id: &str) -> Option<Pattern> {
        // 同时移除所有引用该Pattern的实例
        let instance_ids: Vec<String> = self.instances
            .iter()
            .filter(|(_, inst)| inst.pattern_id == id)
            .map(|(inst_id, _)| inst_id.clone())
            .collect();
        for inst_id in instance_ids {
            self.instances.remove(&inst_id);
        }
        self.patterns.remove(id)
    }

    /// 获取Pattern
    pub fn get_pattern(&self, id: &str) -> Option<&Pattern> {
        self.patterns.get(id)
    }

    /// 获取Pattern可变引用
    pub fn get_pattern_mut(&mut self, id: &str) -> Option<&mut Pattern> {
        self.patterns.get_mut(id)
    }

    /// 创建Pattern实例（在时间线上放置Pattern）
    pub fn create_instance(&mut self, pattern_id: &str, start_beat: f64) -> Option<String> {
        if !self.patterns.contains_key(pattern_id) {
            return None;
        }

        let instance_id = format!("inst_{}", self.next_instance_id);
        self.next_instance_id += 1;

        let instance = PatternInstance::new(&instance_id, pattern_id, start_beat);
        self.instances.insert(instance_id.clone(), instance);
        Some(instance_id)
    }

    /// 移除Pattern实例
    pub fn remove_instance(&mut self, id: &str) -> Option<PatternInstance> {
        self.instances.remove(id)
    }

    /// 获取Pattern实例
    pub fn get_instance(&self, id: &str) -> Option<&PatternInstance> {
        self.instances.get(id)
    }

    /// 获取指定Pattern的所有实例
    pub fn get_instances_for_pattern(&self, pattern_id: &str) -> Vec<&PatternInstance> {
        self.instances
            .values()
            .filter(|i| i.pattern_id == pattern_id)
            .collect()
    }

    /// 按分类查找Pattern
    pub fn find_by_category(&self, category: &str) -> Vec<&Pattern> {
        self.patterns
            .values()
            .filter(|p| p.category == category)
            .collect()
    }

    /// 按标签查找Pattern
    pub fn find_by_tag(&self, tag: &str) -> Vec<&Pattern> {
        self.patterns
            .values()
            .filter(|p| p.tags.contains(&tag.to_string()))
            .collect()
    }

    /// 按名称搜索Pattern
    pub fn search(&self, query: &str) -> Vec<&Pattern> {
        let query_lower = query.to_lowercase();
        self.patterns
            .values()
            .filter(|p| {
                p.name.to_lowercase().contains(&query_lower)
                    || p.tags.iter().any(|t| t.to_lowercase().contains(&query_lower))
            })
            .collect()
    }

    /// Pattern数量
    pub fn pattern_count(&self) -> usize {
        self.patterns.len()
    }

    /// 实例数量
    pub fn instance_count(&self) -> usize {
        self.instances.len()
    }

    /// 获取所有分类
    pub fn categories(&self) -> &[String] {
        &self.categories
    }

    /// 列出所有Pattern的摘要
    pub fn list_patterns(&self) -> Vec<String> {
        self.patterns
            .values()
            .map(|p| {
                format!(
                    "{} [{}] {} ({:.1}拍, {}音符, 标签: {})",
                    p.name,
                    match p.pattern_type {
                        PatternType::Midi => "MIDI",
                        PatternType::Audio => "Audio",
                        PatternType::Hybrid => "混合",
                    },
                    p.category,
                    p.length_beats,
                    p.note_count(),
                    p.tags.join(", ")
                )
            })
            .collect()
    }
}

impl Default for PatternLibrary {
    fn default() -> Self {
        Self::new()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_midi_note() {
        let note = MidiNote::new(60, 0.0, 1.0, 100);
        assert_eq!(note.pitch, 60);
        assert!((note.end_beat() - 1.0).abs() < 1e-10);
    }

    #[test]
    fn test_midi_note_clamp() {
        let note = MidiNote::new(200, 0.0, 1.0, 200);
        assert_eq!(note.pitch, 127);
        assert_eq!(note.velocity, 127);
    }

    #[test]
    fn test_audio_region() {
        let region = AudioRegion::new("kick.wav", 0.0, 2.0);
        assert_eq!(region.file_path, "kick.wav");
        assert!((region.end_beat() - 2.0).abs() < 1e-10);
    }

    #[test]
    fn test_pattern_basic() {
        let mut pattern = Pattern::midi("p1", "Test Pattern", 4.0);
        pattern.add_note(MidiNote::new(60, 0.0, 1.0, 100));
        pattern.add_note(MidiNote::new(64, 1.0, 1.0, 80));
        pattern.add_note(MidiNote::new(67, 2.0, 2.0, 90));

        assert_eq!(pattern.note_count(), 3);
        assert_eq!(pattern.pattern_type, PatternType::Midi);
    }

    #[test]
    fn test_pattern_transpose() {
        let mut pattern = Pattern::midi("p1", "Test", 4.0);
        pattern.add_note(MidiNote::new(60, 0.0, 1.0, 100));

        pattern.transpose(5);
        assert_eq!(pattern.midi_notes[0].pitch, 65);
    }

    #[test]
    fn test_pattern_transpose_clamp() {
        let mut pattern = Pattern::midi("p1", "Test", 4.0);
        pattern.add_note(MidiNote::new(125, 0.0, 1.0, 100));

        pattern.transpose(10);
        assert_eq!(pattern.midi_notes[0].pitch, 127);
    }

    #[test]
    fn test_pattern_quantize() {
        let mut pattern = Pattern::midi("p1", "Test", 4.0);
        pattern.add_note(MidiNote::new(60, 0.1, 1.0, 100));
        pattern.add_note(MidiNote::new(64, 1.15, 1.0, 80));

        pattern.quantize(0.25);
        assert!((pattern.midi_notes[0].start_beat - 0.0).abs() < 1e-10);
        assert!((pattern.midi_notes[1].start_beat - 1.25).abs() < 1e-10);
    }

    #[test]
    fn test_pattern_notes_in_range() {
        let mut pattern = Pattern::midi("p1", "Test", 8.0);
        pattern.add_note(MidiNote::new(60, 0.0, 1.0, 100));
        pattern.add_note(MidiNote::new(64, 2.0, 1.0, 80));
        pattern.add_note(MidiNote::new(67, 5.0, 2.0, 90));

        let notes = pattern.notes_in_range(1.0, 4.0);
        assert_eq!(notes.len(), 2); // note at 0 and note at 2
    }

    #[test]
    fn test_pattern_tags() {
        let mut pattern = Pattern::midi("p1", "Test", 4.0);
        pattern.add_tag("drums");
        pattern.add_tag("kick");
        pattern.add_tag("drums"); // 重复标签不应重复添加
        assert_eq!(pattern.tags.len(), 2);

        pattern.remove_tag("kick");
        assert_eq!(pattern.tags.len(), 1);
    }

    #[test]
    fn test_pattern_type_auto_update() {
        let mut pattern = Pattern::midi("p1", "Test", 4.0);
        assert_eq!(pattern.pattern_type, PatternType::Midi);

        pattern.add_audio_region(AudioRegion::new("test.wav", 0.0, 4.0));
        assert_eq!(pattern.pattern_type, PatternType::Hybrid);
    }

    #[test]
    fn test_example_patterns() {
        let kick = Pattern::example_kick();
        assert_eq!(kick.note_count(), 4);
        assert!(kick.tags.contains(&"drums".to_string()));

        let bass = Pattern::example_bass();
        assert_eq!(bass.note_count(), 4);
    }

    #[test]
    fn test_pattern_instance() {
        let inst = PatternInstance::new("inst_0", "kick_4onfloor", 4.0);
        assert_eq!(inst.pattern_id, "kick_4onfloor");
        assert!((inst.start_beat - 4.0).abs() < 1e-10);
        assert!((inst.end_beat(4.0) - 8.0).abs() < 1e-10);
    }

    #[test]
    fn test_pattern_library_basic() {
        let mut lib = PatternLibrary::new();
        lib.add_pattern(Pattern::example_kick());
        lib.add_pattern(Pattern::example_bass());

        assert_eq!(lib.pattern_count(), 2);
        assert!(lib.get_pattern("kick_4onfloor").is_some());
        assert!(lib.get_pattern("bass_basic").is_some());
    }

    #[test]
    fn test_pattern_library_instance() {
        let mut lib = PatternLibrary::new();
        lib.add_pattern(Pattern::example_kick());

        let inst_id = lib.create_instance("kick_4onfloor", 0.0).unwrap();
        assert_eq!(lib.instance_count(), 1);

        let inst = lib.get_instance(&inst_id).unwrap();
        assert_eq!(inst.pattern_id, "kick_4onfloor");
    }

    #[test]
    fn test_pattern_library_instance_nonexistent() {
        let mut lib = PatternLibrary::new();
        let result = lib.create_instance("nonexistent", 0.0);
        assert!(result.is_none());
    }

    #[test]
    fn test_pattern_library_remove_cascade() {
        let mut lib = PatternLibrary::new();
        lib.add_pattern(Pattern::example_kick());
        lib.create_instance("kick_4onfloor", 0.0);
        lib.create_instance("kick_4onfloor", 4.0);

        assert_eq!(lib.instance_count(), 2);
        lib.remove_pattern("kick_4onfloor");
        assert_eq!(lib.instance_count(), 0);
    }

    #[test]
    fn test_pattern_library_find_by_category() {
        let mut lib = PatternLibrary::new();
        lib.add_pattern(Pattern::example_kick());
        lib.add_pattern(Pattern::example_bass());

        let drums = lib.find_by_category("鼓组");
        assert_eq!(drums.len(), 1);

        let bass = lib.find_by_category("贝斯");
        assert_eq!(bass.len(), 1);
    }

    #[test]
    fn test_pattern_library_find_by_tag() {
        let mut lib = PatternLibrary::new();
        lib.add_pattern(Pattern::example_kick());

        let results = lib.find_by_tag("kick");
        assert_eq!(results.len(), 1);

        let no_results = lib.find_by_tag("nonexistent");
        assert!(no_results.is_empty());
    }

    #[test]
    fn test_pattern_library_search() {
        let mut lib = PatternLibrary::new();
        lib.add_pattern(Pattern::example_kick());
        lib.add_pattern(Pattern::example_bass());

        let results = lib.search("kick");
        assert_eq!(results.len(), 1);

        let results = lib.search("BASS");
        assert_eq!(results.len(), 1); // 大小写不敏感
    }

    #[test]
    fn test_pattern_library_list() {
        let mut lib = PatternLibrary::new();
        lib.add_pattern(Pattern::example_kick());
        let list = lib.list_patterns();
        assert_eq!(list.len(), 1);
        assert!(list[0].contains("Kick"));
    }

    #[test]
    fn test_instances_for_pattern() {
        let mut lib = PatternLibrary::new();
        lib.add_pattern(Pattern::example_kick());
        lib.create_instance("kick_4onfloor", 0.0);
        lib.create_instance("kick_4onfloor", 4.0);
        lib.create_instance("kick_4onfloor", 8.0);

        let instances = lib.get_instances_for_pattern("kick_4onfloor");
        assert_eq!(instances.len(), 3);
    }
}
