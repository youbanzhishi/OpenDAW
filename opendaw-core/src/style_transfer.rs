//! 风格迁移v2 — 风格特征提取、渐变与预置
//!
//! - StyleTransferEngine: 风格迁移引擎
//! - StyleProfile: 风格特征提取（节奏/和声/音色特征向量）
//! - StyleMorpher: 风格渐变（从风格A到风格B的连续过渡）
//! - 预置风格：Classical→EDM, Jazz→Pop, Rock→Lo-Fi

use std::collections::HashMap;

use serde::{Deserialize, Serialize};

use crate::chord::{Mode, NoteName};
use crate::pattern::{MidiNote, Pattern, PatternType};

// ── 风格特征向量 ──────────────────────────────────────────

/// 节奏特征
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RhythmFeatures {
    /// 平均BPM
    pub tempo: f64,
    /// 节奏密度（每拍onset数量）
    pub density: f64,
    /// 切分音比例 [0, 1]
    pub syncopation: f64,
    /// 律动模式强度 [0, 1]
    pub groove_strength: f64,
    /// 节奏规律性 [0, 1]
    pub regularity: f64,
    /// 典型节奏模式（16步序列，1=onset, 0=rest）
    pub pattern: [u8; 16],
}

impl Default for RhythmFeatures {
    fn default() -> Self {
        Self {
            tempo: 120.0,
            density: 0.5,
            syncopation: 0.3,
            groove_strength: 0.5,
            regularity: 0.8,
            pattern: [0; 16],
        }
    }
}

/// 和声特征
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct HarmonyFeatures {
    /// 常用和弦类型分布
    pub chord_type_distribution: HashMap<String, f64>,
    /// 平均和弦密度（每小节和弦数）
    pub chord_density: f64,
    /// 调式偏好
    pub preferred_modes: HashMap<String, f64>,
    /// 和声复杂度 [0, 1]
    pub complexity: f64,
    /// 调性模糊度 [0, 1]
    pub tonal_ambiguity: f64,
}

impl Default for HarmonyFeatures {
    fn default() -> Self {
        let mut chord_dist = HashMap::new();
        chord_dist.insert("Major".to_string(), 0.5);
        chord_dist.insert("Minor".to_string(), 0.3);
        chord_dist.insert("7th".to_string(), 0.2);

        let mut modes = HashMap::new();
        modes.insert("Major".to_string(), 0.6);
        modes.insert("Minor".to_string(), 0.4);

        Self {
            chord_type_distribution: chord_dist,
            chord_density: 2.0,
            preferred_modes: modes,
            complexity: 0.3,
            tonal_ambiguity: 0.2,
        }
    }
}

/// 音色特征
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TimbreFeatures {
    /// 亮度 [0, 1]（高频能量比例）
    pub brightness: f64,
    /// 温暖度 [0, 1]（低频能量比例）
    pub warmth: f64,
    /// 谐波丰富度 [0, 1]
    pub harmonic_richness: f64,
    /// 噪声成分 [0, 1]
    pub noise_component: f64,
    /// 动态范围 [0, 1]
    pub dynamic_range: f64,
    /// 音色特征向量（128维简化）
    pub feature_vector: Vec<f64>,
}

impl Default for TimbreFeatures {
    fn default() -> Self {
        Self {
            brightness: 0.5,
            warmth: 0.5,
            harmonic_richness: 0.5,
            noise_component: 0.0,
            dynamic_range: 0.5,
            feature_vector: vec![0.0; 128],
        }
    }
}

/// 风格特征组合
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct StyleFeatures {
    /// 节奏特征
    pub rhythm: RhythmFeatures,
    /// 和声特征
    pub harmony: HarmonyFeatures,
    /// 音色特征
    pub timbre: TimbreFeatures,
}

impl Default for StyleFeatures {
    fn default() -> Self {
        Self {
            rhythm: RhythmFeatures::default(),
            harmony: HarmonyFeatures::default(),
            timbre: TimbreFeatures::default(),
        }
    }
}

// ── 风格档案 ──────────────────────────────────────────────

/// 风格档案
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct StyleProfile {
    /// 风格名称
    pub name: String,
    /// 风格特征
    pub features: StyleFeatures,
    /// 典型MIDI音符范围
    pub typical_pitch_range: (u8, u8),
    /// 典型力度范围
    pub typical_velocity_range: (u8, u8),
    /// 典型轨道配置
    pub typical_tracks: Vec<String>,
    /// 描述
    pub description: String,
}

impl StyleProfile {
    /// 创建Classical风格
    pub fn classical() -> Self {
        let mut chord_dist = HashMap::new();
        chord_dist.insert("Major".to_string(), 0.4);
        chord_dist.insert("Minor".to_string(), 0.3);
        chord_dist.insert("7th".to_string(), 0.15);
        chord_dist.insert("Dim".to_string(), 0.1);
        chord_dist.insert("Aug".to_string(), 0.05);

        let mut modes = HashMap::new();
        modes.insert("Major".to_string(), 0.5);
        modes.insert("Minor".to_string(), 0.4);
        modes.insert("Modal".to_string(), 0.1);

        Self {
            name: "Classical".to_string(),
            features: StyleFeatures {
                rhythm: RhythmFeatures {
                    tempo: 90.0,
                    density: 0.4,
                    syncopation: 0.1,
                    groove_strength: 0.2,
                    regularity: 0.9,
                    pattern: [1, 0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 0],
                },
                harmony: HarmonyFeatures {
                    chord_type_distribution: chord_dist,
                    chord_density: 1.5,
                    preferred_modes: modes,
                    complexity: 0.6,
                    tonal_ambiguity: 0.3,
                },
                timbre: TimbreFeatures {
                    brightness: 0.4,
                    warmth: 0.7,
                    harmonic_richness: 0.8,
                    noise_component: 0.05,
                    dynamic_range: 0.8,
                    feature_vector: vec![0.0; 128],
                },
            },
            typical_pitch_range: (36, 96),
            typical_velocity_range: (30, 110),
            typical_tracks: vec![
                "Strings".to_string(),
                "Woodwinds".to_string(),
                "Brass".to_string(),
                "Piano".to_string(),
                "Timpani".to_string(),
            ],
            description: "古典音乐风格：丰富的和声进行，宽广的动态范围，管弦乐编制".to_string(),
        }
    }

    /// 创建EDM风格
    pub fn edm() -> Self {
        let mut chord_dist = HashMap::new();
        chord_dist.insert("Major".to_string(), 0.5);
        chord_dist.insert("Minor".to_string(), 0.3);
        chord_dist.insert("Sus2".to_string(), 0.15);
        chord_dist.insert("Sus4".to_string(), 0.05);

        let mut modes = HashMap::new();
        modes.insert("Major".to_string(), 0.4);
        modes.insert("Minor".to_string(), 0.5);
        modes.insert("Dorian".to_string(), 0.1);

        Self {
            name: "EDM".to_string(),
            features: StyleFeatures {
                rhythm: RhythmFeatures {
                    tempo: 128.0,
                    density: 0.8,
                    syncopation: 0.4,
                    groove_strength: 0.9,
                    regularity: 0.7,
                    pattern: [1, 0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 0],
                },
                harmony: HarmonyFeatures {
                    chord_type_distribution: chord_dist,
                    chord_density: 1.0,
                    preferred_modes: modes,
                    complexity: 0.2,
                    tonal_ambiguity: 0.1,
                },
                timbre: TimbreFeatures {
                    brightness: 0.8,
                    warmth: 0.4,
                    harmonic_richness: 0.6,
                    noise_component: 0.3,
                    dynamic_range: 0.3,
                    feature_vector: vec![0.0; 128],
                },
            },
            typical_pitch_range: (24, 108),
            typical_velocity_range: (80, 127),
            typical_tracks: vec![
                "Kick".to_string(),
                "Snare".to_string(),
                "Hi-Hat".to_string(),
                "Bass".to_string(),
                "Lead Synth".to_string(),
                "Pad".to_string(),
            ],
            description: "电子舞曲风格：强烈节拍驱动，合成器音色，四四拍鼓组".to_string(),
        }
    }

    /// 创建Jazz风格
    pub fn jazz() -> Self {
        let mut chord_dist = HashMap::new();
        chord_dist.insert("Major7".to_string(), 0.25);
        chord_dist.insert("Minor7".to_string(), 0.25);
        chord_dist.insert("Dom7".to_string(), 0.25);
        chord_dist.insert("Half-Dim".to_string(), 0.1);
        chord_dist.insert("Dim7".to_string(), 0.05);
        chord_dist.insert("Alt".to_string(), 0.1);

        let mut modes = HashMap::new();
        modes.insert("Major".to_string(), 0.3);
        modes.insert("Minor".to_string(), 0.3);
        modes.insert("Dorian".to_string(), 0.2);
        modes.insert("Mixolydian".to_string(), 0.2);

        Self {
            name: "Jazz".to_string(),
            features: StyleFeatures {
                rhythm: RhythmFeatures {
                    tempo: 130.0,
                    density: 0.6,
                    syncopation: 0.7,
                    groove_strength: 0.8,
                    regularity: 0.3,
                    pattern: [1, 0, 1, 0, 0, 1, 0, 1, 1, 0, 1, 0, 0, 1, 0, 1],
                },
                harmony: HarmonyFeatures {
                    chord_type_distribution: chord_dist,
                    chord_density: 2.0,
                    preferred_modes: modes,
                    complexity: 0.8,
                    tonal_ambiguity: 0.5,
                },
                timbre: TimbreFeatures {
                    brightness: 0.5,
                    warmth: 0.6,
                    harmonic_richness: 0.7,
                    noise_component: 0.1,
                    dynamic_range: 0.6,
                    feature_vector: vec![0.0; 128],
                },
            },
            typical_pitch_range: (28, 108),
            typical_velocity_range: (40, 120),
            typical_tracks: vec![
                "Piano".to_string(),
                "Upright Bass".to_string(),
                "Drums".to_string(),
                "Saxophone".to_string(),
                "Trumpet".to_string(),
            ],
            description: "爵士风格：复杂和声进行，大量即兴切分，蓝调音阶".to_string(),
        }
    }

    /// 创建Pop风格
    pub fn pop() -> Self {
        let mut chord_dist = HashMap::new();
        chord_dist.insert("Major".to_string(), 0.5);
        chord_dist.insert("Minor".to_string(), 0.25);
        chord_dist.insert("7th".to_string(), 0.15);
        chord_dist.insert("Sus".to_string(), 0.1);

        let mut modes = HashMap::new();
        modes.insert("Major".to_string(), 0.7);
        modes.insert("Minor".to_string(), 0.3);

        Self {
            name: "Pop".to_string(),
            features: StyleFeatures {
                rhythm: RhythmFeatures {
                    tempo: 120.0,
                    density: 0.5,
                    syncopation: 0.2,
                    groove_strength: 0.6,
                    regularity: 0.8,
                    pattern: [1, 0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 0],
                },
                harmony: HarmonyFeatures {
                    chord_type_distribution: chord_dist,
                    chord_density: 1.0,
                    preferred_modes: modes,
                    complexity: 0.2,
                    tonal_ambiguity: 0.1,
                },
                timbre: TimbreFeatures {
                    brightness: 0.6,
                    warmth: 0.5,
                    harmonic_richness: 0.4,
                    noise_component: 0.1,
                    dynamic_range: 0.4,
                    feature_vector: vec![0.0; 128],
                },
            },
            typical_pitch_range: (36, 96),
            typical_velocity_range: (60, 120),
            typical_tracks: vec![
                "Drums".to_string(),
                "Bass".to_string(),
                "Keys".to_string(),
                "Vocal".to_string(),
                "Guitar".to_string(),
            ],
            description: "流行音乐风格：简洁和声进行，突出人声，清晰节拍".to_string(),
        }
    }

    /// 创建Rock风格
    pub fn rock() -> Self {
        let mut chord_dist = HashMap::new();
        chord_dist.insert("Major".to_string(), 0.35);
        chord_dist.insert("Minor".to_string(), 0.35);
        chord_dist.insert("Power".to_string(), 0.2);
        chord_dist.insert("Dom7".to_string(), 0.1);

        let mut modes = HashMap::new();
        modes.insert("Major".to_string(), 0.4);
        modes.insert("Minor".to_string(), 0.4);
        modes.insert("Pentatonic".to_string(), 0.2);

        Self {
            name: "Rock".to_string(),
            features: StyleFeatures {
                rhythm: RhythmFeatures {
                    tempo: 130.0,
                    density: 0.7,
                    syncopation: 0.3,
                    groove_strength: 0.7,
                    regularity: 0.6,
                    pattern: [1, 0, 1, 0, 1, 0, 0, 1, 1, 0, 1, 0, 1, 0, 0, 0],
                },
                harmony: HarmonyFeatures {
                    chord_type_distribution: chord_dist,
                    chord_density: 1.0,
                    preferred_modes: modes,
                    complexity: 0.3,
                    tonal_ambiguity: 0.2,
                },
                timbre: TimbreFeatures {
                    brightness: 0.7,
                    warmth: 0.4,
                    harmonic_richness: 0.7,
                    noise_component: 0.3,
                    dynamic_range: 0.5,
                    feature_vector: vec![0.0; 128],
                },
            },
            typical_pitch_range: (28, 96),
            typical_velocity_range: (70, 127),
            typical_tracks: vec![
                "Drums".to_string(),
                "Bass".to_string(),
                "Rhythm Guitar".to_string(),
                "Lead Guitar".to_string(),
                "Vocal".to_string(),
            ],
            description: "摇滚风格：强力和弦，失真吉他，驱动型鼓组".to_string(),
        }
    }

    /// 创建Lo-Fi风格
    pub fn lofi() -> Self {
        let mut chord_dist = HashMap::new();
        chord_dist.insert("Major7".to_string(), 0.3);
        chord_dist.insert("Minor7".to_string(), 0.35);
        chord_dist.insert("9th".to_string(), 0.2);
        chord_dist.insert("11th".to_string(), 0.1);
        chord_dist.insert("6th".to_string(), 0.05);

        let mut modes = HashMap::new();
        modes.insert("Major".to_string(), 0.3);
        modes.insert("Minor".to_string(), 0.4);
        modes.insert("Dorian".to_string(), 0.3);

        Self {
            name: "Lo-Fi".to_string(),
            features: StyleFeatures {
                rhythm: RhythmFeatures {
                    tempo: 80.0,
                    density: 0.4,
                    syncopation: 0.5,
                    groove_strength: 0.6,
                    regularity: 0.4,
                    pattern: [1, 0, 0, 1, 0, 0, 1, 0, 0, 1, 0, 0, 1, 0, 0, 0],
                },
                harmony: HarmonyFeatures {
                    chord_type_distribution: chord_dist,
                    chord_density: 2.0,
                    preferred_modes: modes,
                    complexity: 0.5,
                    tonal_ambiguity: 0.4,
                },
                timbre: TimbreFeatures {
                    brightness: 0.3,
                    warmth: 0.8,
                    harmonic_richness: 0.5,
                    noise_component: 0.4,
                    dynamic_range: 0.3,
                    feature_vector: vec![0.0; 128],
                },
            },
            typical_pitch_range: (36, 84),
            typical_velocity_range: (40, 90),
            typical_tracks: vec![
                "Vinyl Drums".to_string(),
                "Rhodes".to_string(),
                "Bass".to_string(),
                "Pad".to_string(),
                "Tape FX".to_string(),
            ],
            description: "Lo-Fi风格：低保真音色，Jazz和弦，磁带噪声，慢速律动".to_string(),
        }
    }

    /// 从Pattern提取风格特征
    pub fn from_pattern(pattern: &Pattern) -> Self {
        let mut features = StyleFeatures::default();

        // 从MIDI音符提取节奏特征
        if !pattern.midi_notes.is_empty() {
            let avg_velocity: f64 = pattern
                .midi_notes
                .iter()
                .map(|n| n.velocity as f64)
                .sum::<f64>()
                / pattern.midi_notes.len() as f64;

            // 计算节奏密度
            features.rhythm.density = pattern.midi_notes.len() as f64 / pattern.length_beats;

            // 计算切分音比例
            let on_beat = pattern
                .midi_notes
                .iter()
                .filter(|n| (n.start_beat % 1.0).abs() < 0.1 || (n.start_beat % 0.5).abs() < 0.05)
                .count();
            features.rhythm.syncopation = 1.0 - on_beat as f64 / pattern.midi_notes.len() as f64;

            // 提取节奏模式
            for note in &pattern.midi_notes {
                let step = ((note.start_beat % 4.0) * 4.0) as usize;
                if step < 16 {
                    features.rhythm.pattern[step] = 1;
                }
            }

            // 音色特征从力度推断
            features.timbre.brightness = avg_velocity / 127.0;
            features.timbre.dynamic_range = {
                let min_v = pattern
                    .midi_notes
                    .iter()
                    .map(|n| n.velocity)
                    .min()
                    .unwrap_or(0);
                let max_v = pattern
                    .midi_notes
                    .iter()
                    .map(|n| n.velocity)
                    .max()
                    .unwrap_or(0);
                (max_v - min_v) as f64 / 127.0
            };
        }

        Self {
            name: format!("Derived from {}", pattern.name),
            features,
            typical_pitch_range: {
                if pattern.midi_notes.is_empty() {
                    (60, 72)
                } else {
                    let min = pattern.midi_notes.iter().map(|n| n.pitch).min().unwrap();
                    let max = pattern.midi_notes.iter().map(|n| n.pitch).max().unwrap();
                    (min, max)
                }
            },
            typical_velocity_range: {
                if pattern.midi_notes.is_empty() {
                    (80, 100)
                } else {
                    let min = pattern.midi_notes.iter().map(|n| n.velocity).min().unwrap();
                    let max = pattern.midi_notes.iter().map(|n| n.velocity).max().unwrap();
                    (min, max)
                }
            },
            typical_tracks: Vec::new(),
            description: "自动提取的风格特征".to_string(),
        }
    }
}

// ── 风格渐变器 ────────────────────────────────────────────

/// 风格渐变参数
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MorphParams {
    /// 渐变量 [0.0, 1.0]，0=源风格，1=目标风格
    pub amount: f64,
    /// 节奏渐变强度 [0.0, 1.0]
    pub rhythm_weight: f64,
    /// 和声渐变强度 [0.0, 1.0]
    pub harmony_weight: f64,
    /// 音色渐变强度 [0.0, 1.0]
    pub timbre_weight: f64,
}

impl Default for MorphParams {
    fn default() -> Self {
        Self {
            amount: 0.5,
            rhythm_weight: 1.0,
            harmony_weight: 1.0,
            timbre_weight: 1.0,
        }
    }
}

/// 风格渐变器
pub struct StyleMorpher {
    /// 源风格
    source: StyleProfile,
    /// 目标风格
    target: StyleProfile,
}

impl StyleMorpher {
    /// 创建新的风格渐变器
    pub fn new(source: StyleProfile, target: StyleProfile) -> Self {
        Self { source, target }
    }

    /// 在指定渐变量处生成中间风格
    pub fn morph(&self, params: &MorphParams) -> StyleProfile {
        let t = params.amount;

        let rhythm = RhythmFeatures {
            tempo: lerp(
                self.source.features.rhythm.tempo,
                self.target.features.rhythm.tempo,
                t * params.rhythm_weight,
            ),
            density: lerp(
                self.source.features.rhythm.density,
                self.target.features.rhythm.density,
                t * params.rhythm_weight,
            ),
            syncopation: lerp(
                self.source.features.rhythm.syncopation,
                self.target.features.rhythm.syncopation,
                t * params.rhythm_weight,
            ),
            groove_strength: lerp(
                self.source.features.rhythm.groove_strength,
                self.target.features.rhythm.groove_strength,
                t * params.rhythm_weight,
            ),
            regularity: lerp(
                self.source.features.rhythm.regularity,
                self.target.features.rhythm.regularity,
                t * params.rhythm_weight,
            ),
            pattern: morph_pattern(
                &self.source.features.rhythm.pattern,
                &self.target.features.rhythm.pattern,
                t,
            ),
        };

        let harmony = HarmonyFeatures {
            chord_density: lerp(
                self.source.features.harmony.chord_density,
                self.target.features.harmony.chord_density,
                t * params.harmony_weight,
            ),
            complexity: lerp(
                self.source.features.harmony.complexity,
                self.target.features.harmony.complexity,
                t * params.harmony_weight,
            ),
            tonal_ambiguity: lerp(
                self.source.features.harmony.tonal_ambiguity,
                self.target.features.harmony.tonal_ambiguity,
                t * params.harmony_weight,
            ),
            chord_type_distribution: morph_distribution(
                &self.source.features.harmony.chord_type_distribution,
                &self.target.features.harmony.chord_type_distribution,
                t,
            ),
            preferred_modes: morph_distribution(
                &self.source.features.harmony.preferred_modes,
                &self.target.features.harmony.preferred_modes,
                t,
            ),
        };

        let timbre = TimbreFeatures {
            brightness: lerp(
                self.source.features.timbre.brightness,
                self.target.features.timbre.brightness,
                t * params.timbre_weight,
            ),
            warmth: lerp(
                self.source.features.timbre.warmth,
                self.target.features.timbre.warmth,
                t * params.timbre_weight,
            ),
            harmonic_richness: lerp(
                self.source.features.timbre.harmonic_richness,
                self.target.features.timbre.harmonic_richness,
                t * params.timbre_weight,
            ),
            noise_component: lerp(
                self.source.features.timbre.noise_component,
                self.target.features.timbre.noise_component,
                t * params.timbre_weight,
            ),
            dynamic_range: lerp(
                self.source.features.timbre.dynamic_range,
                self.target.features.timbre.dynamic_range,
                t * params.timbre_weight,
            ),
            feature_vector: morph_feature_vector(
                &self.source.features.timbre.feature_vector,
                &self.target.features.timbre.feature_vector,
                t,
            ),
        };

        let typical_pitch_range = (
            lerp(
                self.source.typical_pitch_range.0 as f64,
                self.target.typical_pitch_range.0 as f64,
                t,
            )
            .round() as u8,
            lerp(
                self.source.typical_pitch_range.1 as f64,
                self.target.typical_pitch_range.1 as f64,
                t,
            )
            .round() as u8,
        );

        let typical_velocity_range = (
            lerp(
                self.source.typical_velocity_range.0 as f64,
                self.target.typical_velocity_range.0 as f64,
                t,
            )
            .round() as u8,
            lerp(
                self.source.typical_velocity_range.1 as f64,
                self.target.typical_velocity_range.1 as f64,
                t,
            )
            .round() as u8,
        );

        StyleProfile {
            name: format!(
                "{} → {} ({:.0}%)",
                self.source.name,
                self.target.name,
                t * 100.0
            ),
            features: StyleFeatures {
                rhythm,
                harmony,
                timbre,
            },
            typical_pitch_range,
            typical_velocity_range,
            typical_tracks: if t < 0.5 {
                self.source.typical_tracks.clone()
            } else {
                self.target.typical_tracks.clone()
            },
            description: format!(
                "从 {} 渐变到 {}，渐变量 {:.0}%",
                self.source.name,
                self.target.name,
                t * 100.0
            ),
        }
    }

    /// 生成一系列渐变步骤
    pub fn morph_sequence(&self, steps: usize) -> Vec<StyleProfile> {
        (0..=steps)
            .map(|i| {
                let params = MorphParams {
                    amount: i as f64 / steps as f64,
                    ..MorphParams::default()
                };
                self.morph(&params)
            })
            .collect()
    }

    /// 将Pattern从源风格迁移到目标风格
    pub fn transfer_pattern(&self, pattern: &Pattern, amount: f64) -> Pattern {
        let params = MorphParams {
            amount,
            ..MorphParams::default()
        };
        let morphed = self.morph(&params);

        let mut result = pattern.clone();

        // 调整节奏
        let tempo_ratio = morphed.features.rhythm.tempo / self.source.features.rhythm.tempo;
        if tempo_ratio.abs() > 0.01 {
            for note in &mut result.midi_notes {
                // 简化：调整起始位置模拟节奏变化
                let offset = note.start_beat * (tempo_ratio - 1.0) * amount;
                note.start_beat += offset;
            }
        }

        // 调整音高范围
        let source_center = (self.source.typical_pitch_range.0 as f64
            + self.source.typical_pitch_range.1 as f64)
            / 2.0;
        let target_center =
            (morphed.typical_pitch_range.0 as f64 + morphed.typical_pitch_range.1 as f64) / 2.0;
        let pitch_shift = ((target_center - source_center) * amount).round() as i8;

        if pitch_shift != 0 {
            result.transpose(pitch_shift);
        }

        // 调整力度范围
        let source_avg_v = (self.source.typical_velocity_range.0 as f64
            + self.source.typical_velocity_range.1 as f64)
            / 2.0;
        let target_avg_v = (morphed.typical_velocity_range.0 as f64
            + morphed.typical_velocity_range.1 as f64)
            / 2.0;
        let velocity_shift = ((target_avg_v - source_avg_v) * amount) as i16;

        for note in &mut result.midi_notes {
            let new_velocity = (note.velocity as i16 + velocity_shift).clamp(0, 127) as u8;
            note.velocity = new_velocity;
        }

        result.name = format!(
            "{} → {} ({:.0}%)",
            pattern.name,
            self.target.name,
            amount * 100.0
        );
        result.add_tag("style-transfer");

        result
    }
}

/// 线性插值
fn lerp(a: f64, b: f64, t: f64) -> f64 {
    a + (b - a) * t
}

/// 节奏模式渐变
fn morph_pattern(source: &[u8; 16], target: &[u8; 16], t: f64) -> [u8; 16] {
    let mut result = [0u8; 16];
    for i in 0..16 {
        result[i] = if lerp(source[i] as f64, target[i] as f64, t) > 0.5 {
            1
        } else {
            0
        };
    }
    result
}

/// 分布渐变
fn morph_distribution(
    source: &HashMap<String, f64>,
    target: &HashMap<String, f64>,
    t: f64,
) -> HashMap<String, f64> {
    let mut result = HashMap::new();

    // 合并所有键
    let mut all_keys: Vec<String> = source.keys().cloned().collect();
    for key in target.keys() {
        if !all_keys.contains(key) {
            all_keys.push(key.clone());
        }
    }

    for key in all_keys {
        let s = source.get(&key).copied().unwrap_or(0.0);
        let tgt = target.get(&key).copied().unwrap_or(0.0);
        result.insert(key, lerp(s, tgt, t));
    }

    // 归一化
    let total: f64 = result.values().sum();
    if total > 0.0 {
        for v in result.values_mut() {
            *v /= total;
        }
    }

    result
}

/// 特征向量渐变
fn morph_feature_vector(source: &[f64], target: &[f64], t: f64) -> Vec<f64> {
    source
        .iter()
        .zip(target.iter())
        .map(|(&s, &tgt)| lerp(s, tgt, t))
        .collect()
}

// ── 风格迁移引擎 ──────────────────────────────────────────

/// 风格迁移引擎
pub struct StyleTransferEngine {
    /// 预置风格库
    style_library: HashMap<String, StyleProfile>,
}

impl StyleTransferEngine {
    /// 创建新的风格迁移引擎
    pub fn new() -> Self {
        let mut library = HashMap::new();

        // 加载预置风格
        let profiles = vec![
            StyleProfile::classical(),
            StyleProfile::edm(),
            StyleProfile::jazz(),
            StyleProfile::pop(),
            StyleProfile::rock(),
            StyleProfile::lofi(),
        ];

        for profile in profiles {
            library.insert(profile.name.clone(), profile);
        }

        Self {
            style_library: library,
        }
    }

    /// 获取风格档案
    pub fn get_style(&self, name: &str) -> Option<&StyleProfile> {
        self.style_library.get(name)
    }

    /// 列出所有可用风格
    pub fn list_styles(&self) -> Vec<String> {
        let mut names: Vec<String> = self.style_library.keys().cloned().collect();
        names.sort();
        names
    }

    /// 创建风格渐变器
    pub fn create_morpher(&self, source: &str, target: &str) -> Option<StyleMorpher> {
        let src = self.style_library.get(source)?.clone();
        let tgt = self.style_library.get(target)?.clone();
        Some(StyleMorpher::new(src, tgt))
    }

    /// 预置迁移：Classical → EDM
    pub fn classical_to_edm(&self, pattern: &Pattern, amount: f64) -> Option<Pattern> {
        let morpher = self.create_morpher("Classical", "EDM")?;
        Some(morpher.transfer_pattern(pattern, amount))
    }

    /// 预置迁移：Jazz → Pop
    pub fn jazz_to_pop(&self, pattern: &Pattern, amount: f64) -> Option<Pattern> {
        let morpher = self.create_morpher("Jazz", "Pop")?;
        Some(morpher.transfer_pattern(pattern, amount))
    }

    /// 预置迁移：Rock → Lo-Fi
    pub fn rock_to_lofi(&self, pattern: &Pattern, amount: f64) -> Option<Pattern> {
        let morpher = self.create_morpher("Rock", "Lo-Fi")?;
        Some(morpher.transfer_pattern(pattern, amount))
    }

    /// 分析Pattern的风格
    pub fn analyze_style(&self, pattern: &Pattern) -> StyleProfile {
        StyleProfile::from_pattern(pattern)
    }

    /// 找到最接近的预置风格
    pub fn find_closest_style(&self, pattern: &Pattern) -> String {
        let extracted = StyleProfile::from_pattern(pattern);
        let mut best_name = String::new();
        let mut best_distance = f64::MAX;

        for (name, profile) in &self.style_library {
            let distance = Self::style_distance(&extracted, profile);
            if distance < best_distance {
                best_distance = distance;
                best_name = name.clone();
            }
        }

        best_name
    }

    /// 计算两个风格之间的距离
    fn style_distance(a: &StyleProfile, b: &StyleProfile) -> f64 {
        let rhythm_diff = (a.features.rhythm.tempo - b.features.rhythm.tempo).abs() / 200.0
            + (a.features.rhythm.density - b.features.rhythm.density).abs()
            + (a.features.rhythm.syncopation - b.features.rhythm.syncopation).abs();

        let harmony_diff = (a.features.harmony.complexity - b.features.harmony.complexity).abs()
            + (a.features.harmony.chord_density - b.features.harmony.chord_density).abs() / 4.0;

        let timbre_diff = (a.features.timbre.brightness - b.features.timbre.brightness).abs()
            + (a.features.timbre.warmth - b.features.timbre.warmth).abs()
            + (a.features.timbre.dynamic_range - b.features.timbre.dynamic_range).abs();

        rhythm_diff + harmony_diff + timbre_diff
    }

    /// 注册自定义风格
    pub fn register_style(&mut self, profile: StyleProfile) {
        self.style_library.insert(profile.name.clone(), profile);
    }
}

impl Default for StyleTransferEngine {
    fn default() -> Self {
        Self::new()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_style_profile_classical() {
        let profile = StyleProfile::classical();
        assert_eq!(profile.name, "Classical");
        assert!(profile.features.rhythm.tempo < 120.0);
    }

    #[test]
    fn test_style_profile_edm() {
        let profile = StyleProfile::edm();
        assert_eq!(profile.name, "EDM");
        assert!(profile.features.rhythm.tempo > 120.0);
    }

    #[test]
    fn test_style_profile_from_pattern() {
        let mut pattern = Pattern::midi("test", "Test", 4.0);
        pattern.add_note(MidiNote::new(60, 0.0, 1.0, 100));
        pattern.add_note(MidiNote::new(64, 0.5, 1.0, 80));

        let profile = StyleProfile::from_pattern(&pattern);
        assert!(profile.name.contains("Test"));
        assert!(profile.features.rhythm.density > 0.0);
    }

    #[test]
    fn test_style_morpher() {
        let source = StyleProfile::classical();
        let target = StyleProfile::edm();
        let morpher = StyleMorpher::new(source, target);

        let mid = morpher.morph(&MorphParams::default());
        // 在50%渐变量，tempo应该在源和目标之间
        assert!(mid.features.rhythm.tempo > 90.0);
        assert!(mid.features.rhythm.tempo < 128.0);
    }

    #[test]
    fn test_style_morpher_sequence() {
        let source = StyleProfile::jazz();
        let target = StyleProfile::pop();
        let morpher = StyleMorpher::new(source, target);

        let sequence = morpher.morph_sequence(5);
        assert_eq!(sequence.len(), 6); // 0, 1, 2, 3, 4, 5
        assert!(sequence[0].features.rhythm.tempo > 0.0);
    }

    #[test]
    fn test_style_transfer_engine() {
        let engine = StyleTransferEngine::new();
        let styles = engine.list_styles();
        assert!(styles.contains(&"Classical".to_string()));
        assert!(styles.contains(&"EDM".to_string()));
    }

    #[test]
    fn test_style_transfer_engine_morpher() {
        let engine = StyleTransferEngine::new();
        let morpher = engine.create_morpher("Classical", "EDM");
        assert!(morpher.is_some());

        let none = engine.create_morpher("NonExistent", "EDM");
        assert!(none.is_none());
    }

    #[test]
    fn test_classical_to_edm() {
        let engine = StyleTransferEngine::new();
        let mut pattern = Pattern::midi("test", "Test", 4.0);
        pattern.add_note(MidiNote::new(60, 0.0, 1.0, 80));

        let result = engine.classical_to_edm(&pattern, 0.5);
        assert!(result.is_some());
        let transferred = result.unwrap();
        assert!(transferred.name.contains("EDM"));
    }

    #[test]
    fn test_jazz_to_pop() {
        let engine = StyleTransferEngine::new();
        let mut pattern = Pattern::midi("test", "Test", 4.0);
        pattern.add_note(MidiNote::new(60, 0.0, 1.0, 80));

        let result = engine.jazz_to_pop(&pattern, 0.5);
        assert!(result.is_some());
    }

    #[test]
    fn test_rock_to_lofi() {
        let engine = StyleTransferEngine::new();
        let mut pattern = Pattern::midi("test", "Test", 4.0);
        pattern.add_note(MidiNote::new(60, 0.0, 1.0, 80));

        let result = engine.rock_to_lofi(&pattern, 0.5);
        assert!(result.is_some());
    }

    #[test]
    fn test_find_closest_style() {
        let engine = StyleTransferEngine::new();
        let mut pattern = Pattern::midi("edm_like", "EDM Like", 4.0);
        // 高密度，高力度
        for i in 0..16 {
            pattern.add_note(MidiNote::new(36 + (i % 12), i as f64 * 0.25, 0.25, 120));
        }

        let closest = engine.find_closest_style(&pattern);
        // 应该匹配某个风格（具体取决于特征距离）
        assert!(!closest.is_empty());
    }

    #[test]
    fn test_register_custom_style() {
        let mut engine = StyleTransferEngine::new();
        let custom = StyleProfile {
            name: "CustomStyle".to_string(),
            features: StyleFeatures::default(),
            typical_pitch_range: (40, 80),
            typical_velocity_range: (60, 100),
            typical_tracks: vec!["Custom".to_string()],
            description: "Custom style".to_string(),
        };
        engine.register_style(custom);

        assert!(engine.get_style("CustomStyle").is_some());
        assert!(engine.list_styles().contains(&"CustomStyle".to_string()));
    }

    #[test]
    fn test_morph_distribution() {
        let mut source = HashMap::new();
        source.insert("Major".to_string(), 0.7);
        source.insert("Minor".to_string(), 0.3);

        let mut target = HashMap::new();
        target.insert("Major".to_string(), 0.3);
        target.insert("Minor".to_string(), 0.5);
        target.insert("Dom7".to_string(), 0.2);

        let result = morph_distribution(&source, &target, 0.5);

        let major = result.get("Major").unwrap();
        assert!((*major - 0.5).abs() < 0.1);

        // 应包含Dom7
        assert!(result.contains_key("Dom7"));

        // 应该归一化
        let total: f64 = result.values().sum();
        assert!((total - 1.0).abs() < 0.01);
    }
}
