//! 风格画像导出 — .omp.yaml 格式
//!
//! OpenDAW Mix Profile (OMP) 是一种开放标准格式，
//! 用于从多个项目中聚合用户的编曲混音风格特征。
//!
//! 格式版本: 0.1.0-draft
//! 文件扩展名: .omp.yaml
//!
//! 风格画像包含：
//! - 元数据（用户/创建时间/项目数）
//! - 速度偏好（BPM分布/常用拍号）
//! - 编曲偏好（常用乐器组合/段落结构模式/动态手法）
//! - 混音偏好（常用效果器/参数偏好/信号路由习惯）
//! - 侧链/自动化习惯
//! - 置信度评分（随项目增长自动提高）

use crate::export::mix_report::{
    ArrangementAnalysis, AutomationSidechainSection, InstrumentType, MixingAnalysis,
    ProjectOverview,
};
use serde::{Deserialize, Serialize};
use std::collections::HashMap;

// ── 风格画像数据结构 ──────────────────────────────────────────────────

/// 风格画像 — 从多个项目聚合的用户风格特征
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct StyleProfile {
    /// 画像元数据
    pub meta: ProfileMeta,
    /// 速度偏好
    pub tempo_preference: TempoPreference,
    /// 编曲偏好
    pub arrangement_preference: ArrangementPreference,
    /// 混音偏好
    pub mixing_preference: MixingPreference,
    /// 侧链/自动化习惯
    pub automation_habits: AutomationHabits,
    /// 置信度
    pub confidence: ConfidenceScore,
}

/// 画像元数据
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ProfileMeta {
    /// OMP格式版本
    pub format_version: String,
    /// 用户标识
    pub user_id: Option<String>,
    /// 创建时间
    pub created_at: String,
    /// 最后更新时间
    pub updated_at: String,
    /// 已聚合的项目数
    pub project_count: u32,
}

/// 速度偏好
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct TempoPreference {
    /// BPM分布（BPM区间 → 出现次数）
    #[serde(default)]
    pub bpm_distribution: HashMap<String, u32>,
    /// 最常用BPM
    pub preferred_bpm: Option<f64>,
    /// 常用拍号
    #[serde(default)]
    pub time_signatures: Vec<String>,
}

/// 编曲偏好
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct ArrangementPreference {
    /// 常用乐器组合（Top-N）
    #[serde(default)]
    pub common_instrument_combos: Vec<InstrumentCombo>,
    /// 段落结构模式
    #[serde(default)]
    pub section_patterns: Vec<String>,
    /// 常用编曲手法
    #[serde(default)]
    pub common_techniques: Vec<FrequencyItem>,
    /// 常用调性
    #[serde(default)]
    pub common_keys: Vec<FrequencyItem>,
}

/// 乐器组合
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct InstrumentCombo {
    /// 乐器列表
    pub instruments: Vec<InstrumentType>,
    /// 出现频率 (0.0-1.0)
    pub frequency: f64,
}

/// 频率项（名称+频率）
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FrequencyItem {
    /// 名称
    pub name: String,
    /// 频率 (0.0-1.0)
    pub frequency: f64,
}

/// 混音偏好
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct MixingPreference {
    /// 常用效果器类型（Top-N）
    #[serde(default)]
    pub common_effects: Vec<FrequencyItem>,
    /// 参数偏好（效果器类型 → 常用参数范围）
    #[serde(default)]
    pub param_preferences: HashMap<String, ParamPreference>,
    /// 常用信号路由模式
    #[serde(default)]
    pub routing_patterns: Vec<FrequencyItem>,
}

/// 参数偏好
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ParamPreference {
    /// 参数名
    pub param_name: String,
    /// 常用值
    pub common_values: Vec<String>,
    /// 平均值
    pub average: Option<String>,
}

/// 侧链/自动化习惯
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct AutomationHabits {
    /// 常用侧链配置
    #[serde(default)]
    pub common_sidechains: Vec<FrequencyItem>,
    /// 常用自动化类型
    #[serde(default)]
    pub common_automations: Vec<FrequencyItem>,
}

/// 置信度评分 — 随项目数量增长
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct ConfidenceScore {
    /// 整体置信度 (0.0-1.0)
    pub overall: f64,
    /// 编曲置信度
    pub arrangement: f64,
    /// 混音置信度
    pub mixing: f64,
    /// 自动化置信度
    pub automation: f64,
}

impl ConfidenceScore {
    /// 根据项目数量计算置信度
    /// 使用对数增长：1项目→0.3, 3项目→0.5, 10项目→0.7, 30项目→0.85
    pub fn from_project_count(count: u32) -> Self {
        let calc = |n: u32| -> f64 {
            if n == 0 {
                return 0.0;
            }
            (1.0 + (n as f64).ln() / 3.5).min(1.0)
        };

        Self {
            overall: calc(count),
            arrangement: calc(count),
            mixing: calc(count),
            automation: calc(count),
        }
    }
}

// ── 风格画像聚合器 ────────────────────────────────────────────────────

/// 风格画像聚合器 — 从多个项目的数据中提取风格特征
#[derive(Debug)]
pub struct ProfileAggregator {
    /// 已聚合的项目数
    project_count: u32,
    /// BPM记录
    bpm_values: Vec<f64>,
    /// 调性记录
    key_values: Vec<String>,
    /// 效果器类型频率
    effect_type_freq: HashMap<String, u32>,
    /// 侧链配置频率
    sidechain_freq: HashMap<String, u32>,
    /// 自动化类型频率
    automation_freq: HashMap<String, u32>,
    /// 编曲手法频率
    technique_freq: HashMap<String, u32>,
}

impl ProfileAggregator {
    /// 创建新的聚合器
    pub fn new() -> Self {
        Self {
            project_count: 0,
            bpm_values: Vec::new(),
            key_values: Vec::new(),
            effect_type_freq: HashMap::new(),
            sidechain_freq: HashMap::new(),
            automation_freq: HashMap::new(),
            technique_freq: HashMap::new(),
        }
    }

    /// 聚合一个项目的数据
    pub fn ingest_project(
        &mut self,
        overview: &ProjectOverview,
        arrangement: &ArrangementAnalysis,
        mixing: &MixingAnalysis,
        automation: &AutomationSidechainSection,
    ) {
        self.project_count += 1;

        // BPM
        if let Some(bpm) = overview.bpm {
            self.bpm_values.push(bpm);
        }

        // 调性
        if let Some(ref key) = overview.key {
            self.key_values.push(key.clone());
        }

        // 效果器类型频率
        for chain in &mixing.effect_chains {
            for effect in &chain.chain {
                let type_name = format!("{:?}", effect.effect_type);
                *self.effect_type_freq.entry(type_name).or_insert(0) += 1;
            }
        }

        // 侧链频率
        for sc in &automation.sidechains {
            let key = format!("{}→{}", sc.source_track, sc.target);
            *self.sidechain_freq.entry(key).or_insert(0) += 1;
        }

        // 自动化频率
        for auto_info in &automation.automations {
            *self
                .automation_freq
                .entry(auto_info.automation_type.clone())
                .or_insert(0) += 1;
        }

        // 编曲手法频率
        for tech in &arrangement.techniques {
            *self.technique_freq.entry(tech.name.clone()).or_insert(0) += 1;
        }
    }

    /// 生成风格画像
    pub fn build_profile(&self, user_id: Option<String>) -> StyleProfile {
        let timestamp = chrono_now_iso();
        let total = self.project_count.max(1);

        // BPM分布
        let mut bpm_distribution: HashMap<String, u32> = HashMap::new();
        for &bpm in &self.bpm_values {
            let bucket = match bpm {
                b if b < 90.0 => "60-90".to_string(),
                b if b < 120.0 => "90-120".to_string(),
                b if b < 150.0 => "120-150".to_string(),
                _ => "150+".to_string(),
            };
            *bpm_distribution.entry(bucket).or_insert(0) += 1;
        }

        // 最常用BPM
        let preferred_bpm = if !self.bpm_values.is_empty() {
            let sum: f64 = self.bpm_values.iter().sum();
            Some(sum / self.bpm_values.len() as f64)
        } else {
            None
        };

        // 效果器偏好
        let common_effects = self.top_n(&self.effect_type_freq, 10, total);

        // 侧链习惯
        let common_sidechains = self.top_n(&self.sidechain_freq, 5, total);

        // 自动化习惯
        let common_automations = self.top_n(&self.automation_freq, 5, total);

        // 编曲手法
        let common_techniques = self.top_n(&self.technique_freq, 10, total);

        // 调性偏好
        let common_keys = self.top_n_from_vec(&self.key_values, 5, total);

        StyleProfile {
            meta: ProfileMeta {
                format_version: "0.1.0-draft".to_string(),
                user_id,
                created_at: timestamp.clone(),
                updated_at: timestamp,
                project_count: self.project_count,
            },
            tempo_preference: TempoPreference {
                bpm_distribution,
                preferred_bpm,
                time_signatures: Vec::new(),
            },
            arrangement_preference: ArrangementPreference {
                common_instrument_combos: Vec::new(),
                section_patterns: Vec::new(),
                common_techniques,
                common_keys,
            },
            mixing_preference: MixingPreference {
                common_effects,
                param_preferences: HashMap::new(),
                routing_patterns: Vec::new(),
            },
            automation_habits: AutomationHabits {
                common_sidechains,
                common_automations,
            },
            confidence: ConfidenceScore::from_project_count(self.project_count),
        }
    }

    /// 导出为 .omp.yaml 格式
    pub fn export_yaml(profile: &StyleProfile) -> Result<String, serde_yaml::Error> {
        serde_yaml::to_string(profile)
    }

    /// 从 .omp.yaml 导入
    pub fn import_yaml(yaml: &str) -> Result<StyleProfile, serde_yaml::Error> {
        serde_yaml::from_str(yaml)
    }

    /// 从频率Map取Top-N
    fn top_n(&self, freq: &HashMap<String, u32>, n: usize, total: u32) -> Vec<FrequencyItem> {
        let mut items: Vec<_> = freq.iter().collect();
        items.sort_by(|a, b| b.1.cmp(a.1));
        items
            .into_iter()
            .take(n)
            .map(|(name, &count)| FrequencyItem {
                name: name.clone(),
                frequency: count as f64 / total as f64,
            })
            .collect()
    }

    /// 从Vec取Top-N
    fn top_n_from_vec(&self, values: &[String], n: usize, total: u32) -> Vec<FrequencyItem> {
        let mut freq: HashMap<String, u32> = HashMap::new();
        for v in values {
            *freq.entry(v.clone()).or_insert(0) += 1;
        }
        self.top_n(&freq, n, total)
    }
}

impl Default for ProfileAggregator {
    fn default() -> Self {
        Self::new()
    }
}

// ── Helpers ───────────────────────────────────────────────────────────

fn chrono_now_iso() -> String {
    let now = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .unwrap_or_default()
        .as_secs();
    format!("{}", now)
}

// ── Tests ─────────────────────────────────────────────────────────────

#[cfg(test)]
mod tests {
    use super::*;
    use crate::export::mix_report::{
        ArrangementTechnique, AutomationInfo, EffectChainInfo, EffectInfo, SidechainInfo,
    };
    use std::collections::HashMap;

    #[test]
    fn test_confidence_score() {
        let c0 = ConfidenceScore::from_project_count(0);
        assert_eq!(c0.overall, 0.0);

        let c1 = ConfidenceScore::from_project_count(1);
        assert!(c1.overall > 0.0);
        assert!(c1.overall < 0.5);

        let c10 = ConfidenceScore::from_project_count(10);
        assert!(c10.overall > c1.overall);

        let c100 = ConfidenceScore::from_project_count(100);
        assert!(c100.overall > c10.overall);
        assert!(c100.overall <= 1.0);
    }

    #[test]
    fn test_profile_aggregator_single_project() {
        let mut aggregator = ProfileAggregator::new();

        let overview = ProjectOverview {
            bpm: Some(128.0),
            key: Some("C Major".to_string()),
            ..Default::default()
        };

        let arrangement = ArrangementAnalysis {
            techniques: vec![ArrangementTechnique {
                name: "副歌推动力".to_string(),
                description: "增加密度".to_string(),
                applied_in: vec!["副歌".to_string()],
                related_tracks: vec!["Synth".to_string()],
                intent: None,
            }],
            ..Default::default()
        };

        let mixing = MixingAnalysis {
            effect_chains: vec![EffectChainInfo {
                target: "人声".to_string(),
                chain: vec![EffectInfo {
                    name: "Compressor".to_string(),
                    effect_type: EffectType::Compressor,
                    key_params: HashMap::new(),
                    purpose: None,
                }],
                intent: None,
            }],
            ..Default::default()
        };

        let automation = AutomationSidechainSection {
            sidechains: vec![SidechainInfo {
                source_track: "底鼓".to_string(),
                target: "贝斯".to_string(),
                sidechain_type: "压缩".to_string(),
                params: HashMap::new(),
                purpose: None,
                intent: None,
            }],
            automations: vec![AutomationInfo {
                target_param: "volume".to_string(),
                track_name: "Synth".to_string(),
                automation_type: "渐入".to_string(),
                curve_description: "线性上升".to_string(),
                intent: None,
            }],
        };

        aggregator.ingest_project(&overview, &arrangement, &mixing, &automation);
        let profile = aggregator.build_profile(Some("user1".to_string()));

        assert_eq!(profile.meta.project_count, 1);
        assert_eq!(profile.tempo_preference.preferred_bpm, Some(128.0));
        assert!(profile.confidence.overall > 0.0);
    }

    #[test]
    fn test_profile_yaml_roundtrip() {
        let mut aggregator = ProfileAggregator::new();

        let overview = ProjectOverview {
            bpm: Some(120.0),
            key: Some("A Minor".to_string()),
            ..Default::default()
        };

        aggregator.ingest_project(
            &overview,
            &ArrangementAnalysis::default(),
            &MixingAnalysis::default(),
            &AutomationSidechainSection::default(),
        );

        let profile = aggregator.build_profile(None);
        let yaml = ProfileAggregator::export_yaml(&profile).unwrap();
        let parsed = ProfileAggregator::import_yaml(&yaml).unwrap();

        assert_eq!(parsed.meta.project_count, 1);
        assert_eq!(parsed.tempo_preference.preferred_bpm, Some(120.0));
    }
}
