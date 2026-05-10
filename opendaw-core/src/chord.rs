//! 和弦进行生成器 — 和弦识别、进行模板、自动生成
//!
//! - Chord: 根音+和弦类型
//! - ChordProgression: 和弦进行模板
//! - ChordGenerator: 基于调式/风格自动生成进行
//! - VoicingStrategy: 转位/密集/开放排列

use std::fmt;

use serde::{Deserialize, Serialize};

/// 和弦类型
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum ChordType {
    /// 大三和弦
    Major,
    /// 小三和弦
    Minor,
    /// 增三和弦
    Augmented,
    /// 减三和弦
    Diminished,
    /// 大七和弦
    Major7,
    /// 小七和弦
    Minor7,
    /// 属七和弦
    Dominant7,
    /// 减七和弦
    Diminished7,
    /// 半减七和弦
    HalfDiminished7,
    /// 大九和弦
    Major9,
    /// 小九和弦
    Minor9,
    /// 属九和弦
    Dominant9,
    /// 挂四和弦
    Sus4,
    /// 挂二和弦
    Sus2,
    /// 加六和弦
    Add9,
}

impl ChordType {
    /// 获取和弦的音程结构（半音数）
    pub fn intervals(&self) -> Vec<i8> {
        match self {
            ChordType::Major => vec![0, 4, 7],
            ChordType::Minor => vec![0, 3, 7],
            ChordType::Augmented => vec![0, 4, 8],
            ChordType::Diminished => vec![0, 3, 6],
            ChordType::Major7 => vec![0, 4, 7, 11],
            ChordType::Minor7 => vec![0, 3, 7, 10],
            ChordType::Dominant7 => vec![0, 4, 7, 10],
            ChordType::Diminished7 => vec![0, 3, 6, 9],
            ChordType::HalfDiminished7 => vec![0, 3, 6, 10],
            ChordType::Major9 => vec![0, 4, 7, 11, 14],
            ChordType::Minor9 => vec![0, 3, 7, 10, 14],
            ChordType::Dominant9 => vec![0, 4, 7, 10, 14],
            ChordType::Sus4 => vec![0, 5, 7],
            ChordType::Sus2 => vec![0, 2, 7],
            ChordType::Add9 => vec![0, 4, 7, 14],
        }
    }

    /// 和弦名称缩写
    pub fn symbol(&self) -> &'static str {
        match self {
            ChordType::Major => "",
            ChordType::Minor => "m",
            ChordType::Augmented => "aug",
            ChordType::Diminished => "dim",
            ChordType::Major7 => "maj7",
            ChordType::Minor7 => "m7",
            ChordType::Dominant7 => "7",
            ChordType::Diminished7 => "dim7",
            ChordType::HalfDiminished7 => "m7b5",
            ChordType::Major9 => "maj9",
            ChordType::Minor9 => "m9",
            ChordType::Dominant9 => "9",
            ChordType::Sus4 => "sus4",
            ChordType::Sus2 => "sus2",
            ChordType::Add9 => "add9",
        }
    }

    /// 和弦完整名称
    pub fn full_name(&self) -> &'static str {
        match self {
            ChordType::Major => "大三和弦",
            ChordType::Minor => "小三和弦",
            ChordType::Augmented => "增三和弦",
            ChordType::Diminished => "减三和弦",
            ChordType::Major7 => "大七和弦",
            ChordType::Minor7 => "小七和弦",
            ChordType::Dominant7 => "属七和弦",
            ChordType::Diminished7 => "减七和弦",
            ChordType::HalfDiminished7 => "半减七和弦",
            ChordType::Major9 => "大九和弦",
            ChordType::Minor9 => "小九和弦",
            ChordType::Dominant9 => "属九和弦",
            ChordType::Sus4 => "挂四和弦",
            ChordType::Sus2 => "挂二和弦",
            ChordType::Add9 => "加九和弦",
        }
    }
}

/// 音名
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum NoteName {
    C,
    Db,
    D,
    Eb,
    E,
    F,
    Gb,
    G,
    Ab,
    A,
    Bb,
    B,
}

impl NoteName {
    /// MIDI音高编号 (C4 = 60)
    pub fn midi_offset(&self) -> u8 {
        match self {
            NoteName::C => 0,
            NoteName::Db => 1,
            NoteName::D => 2,
            NoteName::Eb => 3,
            NoteName::E => 4,
            NoteName::F => 5,
            NoteName::Gb => 6,
            NoteName::G => 7,
            NoteName::Ab => 8,
            NoteName::A => 9,
            NoteName::Bb => 10,
            NoteName::B => 11,
        }
    }

    /// 从MIDI音高获取音名
    pub fn from_midi(pitch: u8) -> Self {
        match pitch % 12 {
            0 => NoteName::C,
            1 => NoteName::Db,
            2 => NoteName::D,
            3 => NoteName::Eb,
            4 => NoteName::E,
            5 => NoteName::F,
            6 => NoteName::Gb,
            7 => NoteName::G,
            8 => NoteName::Ab,
            9 => NoteName::A,
            10 => NoteName::Bb,
            11 => NoteName::B,
            _ => NoteName::C, // unreachable
        }
    }

    /// 音名文本
    pub fn name(&self) -> &'static str {
        match self {
            NoteName::C => "C",
            NoteName::Db => "Db",
            NoteName::D => "D",
            NoteName::Eb => "Eb",
            NoteName::E => "E",
            NoteName::F => "F",
            NoteName::Gb => "Gb",
            NoteName::G => "G",
            NoteName::Ab => "Ab",
            NoteName::A => "A",
            NoteName::Bb => "Bb",
            NoteName::B => "B",
        }
    }
}

/// 和弦
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Chord {
    /// 根音
    pub root: NoteName,
    /// 和弦类型
    pub chord_type: ChordType,
    /// 低音（转位用，None表示根音在低音）
    pub bass: Option<NoteName>,
}

impl Chord {
    /// 创建新的和弦
    pub fn new(root: NoteName, chord_type: ChordType) -> Self {
        Self {
            root,
            chord_type,
            bass: None,
        }
    }

    /// 创建转位和弦
    pub fn inversion(root: NoteName, chord_type: ChordType, bass: NoteName) -> Self {
        Self {
            root,
            chord_type,
            bass: Some(bass),
        }
    }

    /// 获取和弦的所有音高（MIDI编号，第4八度为基础）
    pub fn pitches(&self, octave: u8) -> Vec<u8> {
        let base = (octave as u32 + 1) * 12 + self.root.midi_offset() as u32;
        let base = base as u8;
        self.chord_type
            .intervals()
            .iter()
            .map(|&interval| base + interval as u8)
            .collect()
    }

    /// 和弦符号（如 Cmaj7, Am7, G7/B）
    pub fn symbol(&self) -> String {
        let base = format!("{}{}", self.root.name(), self.chord_type.symbol());
        match self.bass {
            Some(bass) => format!("{}/{}", base, bass.name()),
            None => base,
        }
    }
}

impl fmt::Display for Chord {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "{}", self.symbol())
    }
}

/// 调式
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum Mode {
    /// 自然大调
    Major,
    /// 自然小调
    Minor,
    /// 多利亚调式
    Dorian,
    /// 弗里几亚调式
    Phrygian,
    /// 利底亚调式
    Lydian,
    /// 混合利底亚调式
    Mixolydian,
}

impl Mode {
    /// 调式的音程结构（半音数）
    pub fn intervals(&self) -> Vec<i8> {
        match self {
            Mode::Major => vec![0, 2, 4, 5, 7, 9, 11],
            Mode::Minor => vec![0, 2, 3, 5, 7, 8, 10],
            Mode::Dorian => vec![0, 2, 3, 5, 7, 9, 10],
            Mode::Phrygian => vec![0, 1, 3, 5, 7, 8, 10],
            Mode::Lydian => vec![0, 2, 4, 6, 7, 9, 11],
            Mode::Mixolydian => vec![0, 2, 4, 5, 7, 9, 10],
        }
    }

    /// 根据调式生成各级和弦
    pub fn scale_chords(&self) -> Vec<ChordType> {
        match self {
            Mode::Major => vec![
                ChordType::Major,
                ChordType::Minor,
                ChordType::Minor,
                ChordType::Major,
                ChordType::Major,
                ChordType::Minor,
                ChordType::Diminished,
            ],
            Mode::Minor => vec![
                ChordType::Minor,
                ChordType::Diminished,
                ChordType::Major,
                ChordType::Minor,
                ChordType::Minor,
                ChordType::Major,
                ChordType::Major,
            ],
            Mode::Dorian => vec![
                ChordType::Minor,
                ChordType::Minor,
                ChordType::Major,
                ChordType::Major,
                ChordType::Minor,
                ChordType::Diminished,
                ChordType::Major,
            ],
            Mode::Phrygian => vec![
                ChordType::Minor,
                ChordType::Major,
                ChordType::Major,
                ChordType::Minor,
                ChordType::Diminished,
                ChordType::Major,
                ChordType::Minor,
            ],
            Mode::Lydian => vec![
                ChordType::Major,
                ChordType::Major,
                ChordType::Minor,
                ChordType::Diminished,
                ChordType::Major,
                ChordType::Minor,
                ChordType::Minor,
            ],
            Mode::Mixolydian => vec![
                ChordType::Major,
                ChordType::Minor,
                ChordType::Diminished,
                ChordType::Major,
                ChordType::Minor,
                ChordType::Minor,
                ChordType::Major,
            ],
        }
    }

    /// 获取调式的各级音名
    pub fn scale_notes(&self, root: NoteName) -> Vec<NoteName> {
        let root_offset = root.midi_offset() as i8;
        self.intervals()
            .iter()
            .map(|&interval| NoteName::from_midi(((root_offset + interval) % 12) as u8))
            .collect()
    }

    /// 获取调式的各级和弦
    pub fn scale_chords_for_key(&self, root: NoteName) -> Vec<Chord> {
        let notes = self.scale_notes(root);
        let chord_types = self.scale_chords();
        notes
            .into_iter()
            .zip(chord_types.into_iter())
            .map(|(root, ct)| Chord::new(root, ct))
            .collect()
    }
}

/// 和弦进行
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ChordProgression {
    /// 进行名称
    pub name: String,
    /// 和弦序列
    pub chords: Vec<Chord>,
    /// 每个和弦的拍数
    pub beats_per_chord: f64,
    /// 调式
    pub mode: Mode,
    /// 调性根音
    pub key: NoteName,
}

impl ChordProgression {
    /// 创建新的和弦进行
    pub fn new(name: &str, key: NoteName, mode: Mode) -> Self {
        Self {
            name: name.to_string(),
            chords: Vec::new(),
            beats_per_chord: 4.0,
            mode,
            key,
        }
    }

    /// 添加和弦
    pub fn add_chord(&mut self, chord: Chord) {
        self.chords.push(chord);
    }

    /// 总拍数
    pub fn total_beats(&self) -> f64 {
        self.chords.len() as f64 * self.beats_per_chord
    }

    /// 获取指定拍处的和弦
    pub fn chord_at_beat(&self, beat: f64) -> Option<&Chord> {
        if self.chords.is_empty() {
            return None;
        }
        let index = (beat / self.beats_per_chord) as usize % self.chords.len();
        Some(&self.chords[index])
    }

    /// 和弦数量
    pub fn chord_count(&self) -> usize {
        self.chords.len()
    }

    /// 获取进行符号（如 I-V-vi-IV）
    pub fn roman_numerals(&self) -> Vec<String> {
        let scale_chords = self.mode.scale_chords_for_key(self.key);
        self.chords
            .iter()
            .map(|chord| {
                let pos = scale_chords
                    .iter()
                    .position(|sc| sc.root == chord.root && sc.chord_type == chord.chord_type);
                match pos {
                    Some(i) => {
                        let numerals = ["I", "II", "III", "IV", "V", "VI", "VII"];
                        let numeral = numerals[i];
                        match chord.chord_type {
                            ChordType::Minor | ChordType::Minor7 | ChordType::Minor9 => {
                                numeral.to_lowercase()
                            }
                            ChordType::Diminished
                            | ChordType::Diminished7
                            | ChordType::HalfDiminished7 => {
                                format!("{}°", numeral.to_lowercase())
                            }
                            _ => numeral.to_string(),
                        }
                    }
                    None => chord.symbol(),
                }
            })
            .collect()
    }

    // ========================================================================
    // 预置模板
    // ========================================================================

    /// I-V-vi-IV (流行音乐最常用)
    pub fn pop_progression(key: NoteName) -> Self {
        let scale = Mode::Major.scale_notes(key);
        let chord_types = Mode::Major.scale_chords();
        let mut prog = Self::new("I-V-vi-IV (Pop)", key, Mode::Major);
        // I, V, vi, IV
        prog.add_chord(Chord::new(scale[0], chord_types[0])); // I
        prog.add_chord(Chord::new(scale[4], chord_types[4])); // V
        prog.add_chord(Chord::new(scale[5], chord_types[5])); // vi
        prog.add_chord(Chord::new(scale[3], chord_types[3])); // IV
        prog
    }

    /// ii-V-I (爵士标准)
    pub fn jazz_251(key: NoteName) -> Self {
        let scale = Mode::Major.scale_notes(key);
        let mut prog = Self::new("ii-V-I (Jazz)", key, Mode::Major);
        prog.add_chord(Chord::new(scale[1], ChordType::Minor7)); // ii7
        prog.add_chord(Chord::new(scale[4], ChordType::Dominant7)); // V7
        prog.add_chord(Chord::new(scale[0], ChordType::Major7)); // Imaj7
        prog
    }

    /// I-IV-V-I (布鲁斯基础)
    pub fn blues_145(key: NoteName) -> Self {
        let scale = Mode::Major.scale_notes(key);
        let chord_types = Mode::Major.scale_chords();
        let mut prog = Self::new("I-IV-V (Blues)", key, Mode::Major);
        prog.add_chord(Chord::new(scale[0], ChordType::Dominant7)); // I7
        prog.add_chord(Chord::new(scale[3], ChordType::Dominant7)); // IV7
        prog.add_chord(Chord::new(scale[4], ChordType::Dominant7)); // V7
        prog.add_chord(Chord::new(scale[0], ChordType::Dominant7)); // I7
        prog
    }

    /// i-VI-III-VII (小调流行)
    pub fn minor_pop(key: NoteName) -> Self {
        let scale = Mode::Minor.scale_notes(key);
        let chord_types = Mode::Minor.scale_chords();
        let mut prog = Self::new("i-VI-III-VII (Minor Pop)", key, Mode::Minor);
        prog.add_chord(Chord::new(scale[0], chord_types[0])); // i
        prog.add_chord(Chord::new(scale[5], chord_types[5])); // VI
        prog.add_chord(Chord::new(scale[2], chord_types[2])); // III
        prog.add_chord(Chord::new(scale[6], chord_types[6])); // VII
        prog
    }

    /// I-vi-IV-V (50s进行)
    pub fn fifties(key: NoteName) -> Self {
        let scale = Mode::Major.scale_notes(key);
        let chord_types = Mode::Major.scale_chords();
        let mut prog = Self::new("I-vi-IV-V (50s)", key, Mode::Major);
        prog.add_chord(Chord::new(scale[0], chord_types[0])); // I
        prog.add_chord(Chord::new(scale[5], chord_types[5])); // vi
        prog.add_chord(Chord::new(scale[3], chord_types[3])); // IV
        prog.add_chord(Chord::new(scale[4], chord_types[4])); // V
        prog
    }
}

/// 排列策略 — 和弦音符的排列方式
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum VoicingStrategy {
    /// 根音位置（无转位）
    RootPosition,
    /// 第一转位（三音在低音）
    FirstInversion,
    /// 第二转位（五音在低音）
    SecondInversion,
    /// 密集排列（音符尽量靠近）
    Close,
    /// 开放排列（音符间距较大）
    Open,
    /// Drop2（第二个音降低八度）
    Drop2,
}

impl VoicingStrategy {
    /// 应用排列策略，返回排列后的MIDI音高列表
    pub fn apply(&self, chord: &Chord, octave: u8) -> Vec<u8> {
        let base_pitches = chord.pitches(octave);
        match self {
            VoicingStrategy::RootPosition => base_pitches,
            VoicingStrategy::FirstInversion => {
                // 三音移到最低
                if base_pitches.len() >= 2 {
                    let mut result = base_pitches.clone();
                    let third = result.remove(1);
                    result.insert(0, third - 12);
                    result
                } else {
                    base_pitches
                }
            }
            VoicingStrategy::SecondInversion => {
                // 五音移到最低
                if base_pitches.len() >= 3 {
                    let mut result = base_pitches.clone();
                    let fifth = result.remove(2);
                    result.insert(0, fifth - 12);
                    result
                } else {
                    base_pitches
                }
            }
            VoicingStrategy::Close => {
                // 密集排列：所有音在同一个八度内
                let mut result = Vec::new();
                let mut last = base_pitches[0];
                for &pitch in &base_pitches {
                    let note = if pitch < last { pitch + 12 } else { pitch };
                    result.push(note);
                    last = note;
                }
                result
            }
            VoicingStrategy::Open => {
                // 开放排列：间隔放置音符
                let mut result = Vec::new();
                let mut last = base_pitches[0];
                for (i, &pitch) in base_pitches.iter().enumerate() {
                    let note = if i % 2 == 1 && pitch < last + 7 {
                        pitch + 12
                    } else if pitch < last {
                        pitch + 12
                    } else {
                        pitch
                    };
                    result.push(note);
                    last = note;
                }
                result
            }
            VoicingStrategy::Drop2 => {
                // Drop2：从高到低第二个音降低八度
                if base_pitches.len() >= 4 {
                    let mut result = base_pitches.clone();
                    let drop_idx = result.len() - 2;
                    result[drop_idx] -= 12;
                    result.sort();
                    result
                } else {
                    base_pitches
                }
            }
        }
    }
}

/// 和弦生成器 — 基于调式/风格自动生成进行
pub struct ChordGenerator;

impl ChordGenerator {
    /// 根据调式和级数生成和弦
    pub fn generate_from_degree(key: NoteName, mode: Mode, degrees: &[usize]) -> ChordProgression {
        let scale = mode.scale_notes(key);
        let chord_types = mode.scale_chords();
        let mut prog = ChordProgression::new("Generated", key, mode);

        for &degree in degrees {
            let idx = (degree - 1) % scale.len();
            prog.add_chord(Chord::new(scale[idx], chord_types[idx]));
        }

        prog
    }

    /// 生成随机和弦进行（基于调式）
    pub fn generate_random(key: NoteName, mode: Mode, length: usize) -> ChordProgression {
        let scale = mode.scale_notes(key);
        let chord_types = mode.scale_chords();

        // 常用进行模式（权重）
        let patterns: &[Vec<usize>] = match mode {
            Mode::Major => &[
                vec![0, 4, 5, 3], // I-V-vi-IV
                vec![0, 3, 4, 0], // I-IV-V-I
                vec![0, 5, 3, 4], // I-vi-IV-V
            ],
            Mode::Minor => &[
                vec![0, 5, 2, 6], // i-VI-III-VII
                vec![0, 3, 6, 5], // i-iv-VII-VI
                vec![0, 6, 5, 3], // i-VII-VI-iv
            ],
            _ => &[vec![0, 3, 4, 0]],
        };

        let mut prog = ChordProgression::new("Random", key, mode);

        // 用4小节模式循环填充
        let pattern = &patterns[0]; // 简化：使用第一个模式
        for i in 0..length {
            let idx = pattern[i % pattern.len()] % scale.len();
            prog.add_chord(Chord::new(scale[idx], chord_types[idx]));
        }

        prog
    }

    /// 为旋律配和声（简化版：基于旋律音匹配和弦）
    pub fn harmonize_melody(key: NoteName, mode: Mode, melody_pitches: &[u8]) -> ChordProgression {
        let scale_chords = mode.scale_chords_for_key(key);
        let mut prog = ChordProgression::new("Harmonized", key, mode);

        for &pitch in melody_pitches {
            // 找到包含该音的和弦
            let pitch_class = pitch % 12;
            let best_chord = scale_chords
                .iter()
                .find(|chord| chord.pitches(4).iter().any(|&p| p % 12 == pitch_class))
                .cloned();

            match best_chord {
                Some(chord) => prog.add_chord(chord),
                None => prog.add_chord(Chord::new(key, ChordType::Major)),
            }
        }

        prog
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_chord_type_intervals() {
        assert_eq!(ChordType::Major.intervals(), vec![0, 4, 7]);
        assert_eq!(ChordType::Minor.intervals(), vec![0, 3, 7]);
        assert_eq!(ChordType::Major7.intervals(), vec![0, 4, 7, 11]);
        assert_eq!(ChordType::Dominant7.intervals(), vec![0, 4, 7, 10]);
    }

    #[test]
    fn test_note_name_midi() {
        assert_eq!(NoteName::C.midi_offset(), 0);
        assert_eq!(NoteName::A.midi_offset(), 9);
        assert_eq!(NoteName::B.midi_offset(), 11);
    }

    #[test]
    fn test_note_name_from_midi() {
        assert_eq!(NoteName::from_midi(0), NoteName::C);
        assert_eq!(NoteName::from_midi(60), NoteName::C);
        assert_eq!(NoteName::from_midi(69), NoteName::A);
    }

    #[test]
    fn test_chord_pitches() {
        let chord = Chord::new(NoteName::C, ChordType::Major);
        let pitches = chord.pitches(4);
        assert_eq!(pitches, vec![60, 64, 67]); // C4, E4, G4
    }

    #[test]
    fn test_chord_minor_pitches() {
        let chord = Chord::new(NoteName::A, ChordType::Minor);
        let pitches = chord.pitches(4);
        assert_eq!(pitches, vec![69, 72, 76]); // A4, C5, E5
    }

    #[test]
    fn test_chord_symbol() {
        let chord = Chord::new(NoteName::C, ChordType::Major7);
        assert_eq!(chord.symbol(), "Cmaj7");

        let chord = Chord::new(NoteName::A, ChordType::Minor7);
        assert_eq!(chord.symbol(), "Am7");

        let chord = Chord::inversion(NoteName::G, ChordType::Major, NoteName::B);
        assert_eq!(chord.symbol(), "G/B");
    }

    #[test]
    fn test_chord_display() {
        let chord = Chord::new(NoteName::C, ChordType::Dominant7);
        assert_eq!(format!("{}", chord), "C7");
    }

    #[test]
    fn test_mode_intervals() {
        assert_eq!(Mode::Major.intervals(), vec![0, 2, 4, 5, 7, 9, 11]);
        assert_eq!(Mode::Minor.intervals(), vec![0, 2, 3, 5, 7, 8, 10]);
    }

    #[test]
    fn test_mode_scale_notes() {
        let c_major = Mode::Major.scale_notes(NoteName::C);
        assert_eq!(c_major[0], NoteName::C);
        assert_eq!(c_major[2], NoteName::E);
        assert_eq!(c_major[4], NoteName::G);
    }

    #[test]
    fn test_mode_scale_chords() {
        let chords = Mode::Major.scale_chords_for_key(NoteName::C);
        assert_eq!(chords.len(), 7);
        assert_eq!(chords[0].root, NoteName::C);
        assert_eq!(chords[0].chord_type, ChordType::Major);
        assert_eq!(chords[1].root, NoteName::D);
        assert_eq!(chords[1].chord_type, ChordType::Minor);
    }

    #[test]
    fn test_pop_progression() {
        let prog = ChordProgression::pop_progression(NoteName::C);
        assert_eq!(prog.chord_count(), 4);
        assert_eq!(prog.chords[0].root, NoteName::C); // I
        assert_eq!(prog.chords[1].root, NoteName::G); // V
        assert_eq!(prog.chords[2].chord_type, ChordType::Minor); // vi
    }

    #[test]
    fn test_jazz_251() {
        let prog = ChordProgression::jazz_251(NoteName::C);
        assert_eq!(prog.chord_count(), 3);
        assert_eq!(prog.chords[0].chord_type, ChordType::Minor7); // ii7
        assert_eq!(prog.chords[1].chord_type, ChordType::Dominant7); // V7
        assert_eq!(prog.chords[2].chord_type, ChordType::Major7); // Imaj7
    }

    #[test]
    fn test_blues_145() {
        let prog = ChordProgression::blues_145(NoteName::C);
        assert_eq!(prog.chord_count(), 4);
        // All dominant 7th
        for chord in &prog.chords {
            assert_eq!(chord.chord_type, ChordType::Dominant7);
        }
    }

    #[test]
    fn test_progression_chord_at_beat() {
        let prog = ChordProgression::pop_progression(NoteName::C);
        assert_eq!(prog.chord_at_beat(0.0).unwrap().root, NoteName::C);
        assert_eq!(prog.chord_at_beat(4.0).unwrap().root, NoteName::G);
        assert_eq!(
            prog.chord_at_beat(8.0).unwrap().chord_type,
            ChordType::Minor
        );
    }

    #[test]
    fn test_progression_total_beats() {
        let prog = ChordProgression::pop_progression(NoteName::C);
        assert!((prog.total_beats() - 16.0).abs() < 1e-10);
    }

    #[test]
    fn test_voicing_root_position() {
        let chord = Chord::new(NoteName::C, ChordType::Major);
        let voicing = VoicingStrategy::RootPosition.apply(&chord, 4);
        assert_eq!(voicing, vec![60, 64, 67]);
    }

    #[test]
    fn test_voicing_first_inversion() {
        let chord = Chord::new(NoteName::C, ChordType::Major);
        let voicing = VoicingStrategy::FirstInversion.apply(&chord, 4);
        // 三音在低音
        assert_eq!(voicing[0] % 12, 4 % 12); // E在最低
    }

    #[test]
    fn test_voicing_close() {
        let chord = Chord::new(NoteName::C, ChordType::Major7);
        let voicing = VoicingStrategy::Close.apply(&chord, 4);
        // 所有音应该在相近的范围内
        let max_diff = voicing.iter().max().unwrap() - voicing.iter().min().unwrap();
        assert!(
            max_diff <= 12,
            "Close voicing should span at most one octave"
        );
    }

    #[test]
    fn test_generator_from_degree() {
        let prog = ChordGenerator::generate_from_degree(NoteName::C, Mode::Major, &[1, 5, 6, 4]);
        assert_eq!(prog.chord_count(), 4);
        assert_eq!(prog.chords[0].root, NoteName::C);
    }

    #[test]
    fn test_generator_random() {
        let prog = ChordGenerator::generate_random(NoteName::C, Mode::Major, 8);
        assert_eq!(prog.chord_count(), 8);
    }

    #[test]
    fn test_generator_harmonize() {
        let melody = [60u8, 64, 67]; // C, E, G
        let prog = ChordGenerator::harmonize_melody(NoteName::C, Mode::Major, &melody);
        assert_eq!(prog.chord_count(), 3);
    }

    #[test]
    fn test_minor_pop_progression() {
        let prog = ChordProgression::minor_pop(NoteName::A);
        assert_eq!(prog.chord_count(), 4);
        assert_eq!(prog.chords[0].chord_type, ChordType::Minor);
    }

    #[test]
    fn test_fifties_progression() {
        let prog = ChordProgression::fifties(NoteName::C);
        assert_eq!(prog.chord_count(), 4);
    }

    #[test]
    fn test_chord_type_symbol() {
        assert_eq!(ChordType::Major.symbol(), "");
        assert_eq!(ChordType::Minor.symbol(), "m");
        assert_eq!(ChordType::Sus4.symbol(), "sus4");
        assert_eq!(ChordType::Dominant7.symbol(), "7");
    }
}
