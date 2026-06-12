//! 技巧模板导出 — .omt.yaml 格式
//!
//! OpenDAW Mix Technique (OMT) 是一种开放标准格式，
//! 用于从混音报告中提取可复用的处理链和手法模板。
//!
//! 格式版本: 0.1.0-draft
//! 文件扩展名: .omt.yaml
//!
//! 模板包含：
//! - 元数据（名称/分类/标签/来源项目）
//! - 适用条件（风格/BPM范围/乐器类型/段落类型）
//! - 处理链（效果器序列+参数范围+设计意图）
//! - 编曲手法（名称/描述/触发条件）
//! - 实战tips（注意事项/常见陷阱/替代方案）
//! - 评分与使用统计

use crate::export::mix_report::{
    ArrangementTechnique, EffectChainInfo, EffectInfo, EffectType, InstrumentType,
};
use serde::{Deserialize, Serialize};
use std::collections::HashMap;

// ── 模板数据结构 ──────────────────────────────────────────────────────

/// 技巧模板 — 可复用的处理链/手法
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TechniqueTemplate {
    /// 模板元数据
    pub meta: TemplateMeta,
    /// 适用条件
    pub conditions: UsageConditions,
    /// 处理链模板
    #[serde(default)]
    pub processing_chains: Vec<ProcessingChainTemplate>,
    /// 编曲手法模板
    #[serde(default)]
    pub arrangement_techniques: Vec<ArrangementTechniqueTemplate>,
    /// 实战提示
    #[serde(default)]
    pub tips: Vec<TemplateTip>,
    /// 使用统计
    #[serde(default)]
    pub stats: TemplateStats,
}

/// 模板元数据
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TemplateMeta {
    /// OMT格式版本
    pub format_version: String,
    /// 模板名称
    pub name: String,
    /// 模板分类
    pub category: TemplateCategory,
    /// 标签
    #[serde(default)]
    pub tags: Vec<String>,
    /// 来源项目
    pub source_project: Option<String>,
    /// 创建时间
    pub created_at: String,
    /// 最后更新时间
    pub updated_at: String,
}

/// 模板分类
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum TemplateCategory {
    /// 混音处理链
    MixingChain,
    /// 编曲手法
    ArrangementTechnique,
    /// 侧链/自动化
    SidechainAutomation,
    /// 效果器预设
    EffectPreset,
    /// 综合技巧
    Composite,
}

/// 适用条件
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct UsageConditions {
    /// 适用风格
    #[serde(default)]
    pub genres: Vec<String>,
    /// BPM范围 (min, max)
    pub bpm_range: Option<(f64, f64)>,
    /// 适用乐器类型
    #[serde(default)]
    pub instrument_types: Vec<InstrumentType>,
    /// 适用段落
    #[serde(default)]
    pub section_types: Vec<String>,
    /// 前置条件（使用此模板前需要满足的条件）
    #[serde(default)]
    pub prerequisites: Vec<String>,
}

/// 处理链模板
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ProcessingChainTemplate {
    /// 目标轨道类型
    pub target_type: String,
    /// 效果器步骤
    pub steps: Vec<ProcessingStep>,
    /// 整体设计意图
    pub intent: Option<String>,
}

/// 处理步骤
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ProcessingStep {
    /// 效果器类别
    pub effect_category: EffectType,
    /// 参数范围（参数名 → (min, max, 推荐值)）
    #[serde(default)]
    pub param_ranges: HashMap<String, ParamRange>,
    /// 作用说明
    pub purpose: Option<String>,
}

/// 参数范围
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ParamRange {
    /// 最小值
    pub min: String,
    /// 最大值
    pub max: String,
    /// 推荐值
    pub recommended: String,
    /// 单位
    pub unit: Option<String>,
}

/// 编曲手法模板
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ArrangementTechniqueTemplate {
    /// 手法名称
    pub name: String,
    /// 描述
    pub description: String,
    /// 触发条件（何时应用此手法）
    pub trigger_conditions: Vec<String>,
    /// 实施步骤
    pub steps: Vec<String>,
    /// 设计意图
    pub intent: Option<String>,
}

/// 实战提示
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TemplateTip {
    /// 提示类型
    pub tip_type: TipType,
    /// 内容
    pub content: String,
}

/// 提示类型
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum TipType {
    /// 注意事项
    Caution,
    /// 常见陷阱
    Pitfall,
    /// 替代方案
    Alternative,
    /// 进阶技巧
    Advanced,
}

/// 使用统计
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct TemplateStats {
    /// 使用次数
    pub use_count: u32,
    /// 成功率（0.0-1.0）
    pub success_rate: Option<f64>,
    /// 用户评分（1-5）
    pub rating: Option<f64>,
}

// ── 模板生成器 ────────────────────────────────────────────────────────

/// 技巧模板提取器 — 从MixReport数据中提取可复用模板
#[derive(Debug)]
pub struct TechniqueExtractor {
    /// 来源项目名称
    source_project: String,
}

impl TechniqueExtractor {
    /// 创建新的提取器
    pub fn new(source_project: &str) -> Self {
        Self {
            source_project: source_project.to_string(),
        }
    }

    /// 从效果器链信息提取处理链模板
    pub fn extract_processing_chains(
        &self,
        effect_chains: &[EffectChainInfo],
        category: TemplateCategory,
    ) -> Vec<TechniqueTemplate> {
        effect_chains
            .iter()
            .filter(|chain| !chain.chain.is_empty())
            .map(|chain| {
                let steps: Vec<ProcessingStep> = chain
                    .chain
                    .iter()
                    .map(|effect| {
                        let param_ranges: HashMap<String, ParamRange> = effect
                            .key_params
                            .iter()
                            .map(|(k, v)| {
                                (
                                    k.clone(),
                                    ParamRange {
                                        min: v.clone(),
                                        max: v.clone(),
                                        recommended: v.clone(),
                                        unit: None,
                                    },
                                )
                            })
                            .collect();

                        ProcessingStep {
                            effect_category: effect.effect_type,
                            param_ranges,
                            purpose: effect.purpose.clone(),
                        }
                    })
                    .collect();

                let timestamp = chrono_now_iso();

                TechniqueTemplate {
                    meta: TemplateMeta {
                        format_version: "0.1.0-draft".to_string(),
                        name: format!("{}处理链", chain.target),
                        category,
                        tags: vec![chain.target.clone()],
                        source_project: Some(self.source_project.clone()),
                        created_at: timestamp.clone(),
                        updated_at: timestamp,
                    },
                    conditions: UsageConditions::default(),
                    processing_chains: vec![ProcessingChainTemplate {
                        target_type: chain.target.clone(),
                        steps,
                        intent: chain.intent.clone(),
                    }],
                    arrangement_techniques: Vec::new(),
                    tips: Vec::new(),
                    stats: TemplateStats::default(),
                }
            })
            .collect()
    }

    /// 从编曲手法信息提取编曲手法模板
    pub fn extract_arrangement_techniques(
        &self,
        techniques: &[ArrangementTechnique],
    ) -> Vec<TechniqueTemplate> {
        techniques
            .iter()
            .map(|tech| {
                let timestamp = chrono_now_iso();

                TechniqueTemplate {
                    meta: TemplateMeta {
                        format_version: "0.1.0-draft".to_string(),
                        name: tech.name.clone(),
                        category: TemplateCategory::ArrangementTechnique,
                        tags: tech.applied_in.clone(),
                        source_project: Some(self.source_project.clone()),
                        created_at: timestamp.clone(),
                        updated_at: timestamp,
                    },
                    conditions: UsageConditions {
                        section_types: tech.applied_in.clone(),
                        ..Default::default()
                    },
                    processing_chains: Vec::new(),
                    arrangement_techniques: vec![ArrangementTechniqueTemplate {
                        name: tech.name.clone(),
                        description: tech.description.clone(),
                        trigger_conditions: Vec::new(),
                        steps: Vec::new(),
                        intent: tech.intent.clone(),
                    }],
                    tips: Vec::new(),
                    stats: TemplateStats::default(),
                }
            })
            .collect()
    }

    /// 导出为 .omt.yaml 格式
    pub fn export_yaml(template: &TechniqueTemplate) -> Result<String, serde_yaml::Error> {
        serde_yaml::to_string(template)
    }

    /// 从 .omt.yaml 导入
    pub fn import_yaml(yaml: &str) -> Result<TechniqueTemplate, serde_yaml::Error> {
        serde_yaml::from_str(yaml)
    }
}

// ── 模板库 ────────────────────────────────────────────────────────────

/// 技巧模板库 — 管理和搜索模板
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct TechniqueLibrary {
    /// 模板列表
    pub templates: Vec<TechniqueTemplate>,
}

impl TechniqueLibrary {
    /// 创建空模板库
    pub fn new() -> Self {
        Self::default()
    }

    /// 添加模板
    pub fn add(&mut self, template: TechniqueTemplate) {
        self.templates.push(template);
    }

    /// 按分类搜索
    pub fn search_by_category(&self, category: TemplateCategory) -> Vec<&TechniqueTemplate> {
        self.templates
            .iter()
            .filter(|t| t.meta.category == category)
            .collect()
    }

    /// 按标签搜索
    pub fn search_by_tag(&self, tag: &str) -> Vec<&TechniqueTemplate> {
        self.templates
            .iter()
            .filter(|t| t.meta.tags.iter().any(|t| t == tag))
            .collect()
    }

    /// 按风格搜索
    pub fn search_by_genre(&self, genre: &str) -> Vec<&TechniqueTemplate> {
        self.templates
            .iter()
            .filter(|t| t.conditions.genres.iter().any(|g| g == genre))
            .collect()
    }

    /// 导出整个模板库为YAML
    pub fn export_yaml(&self) -> Result<String, serde_yaml::Error> {
        serde_yaml::to_string(self)
    }

    /// 从YAML导入模板库
    pub fn import_yaml(yaml: &str) -> Result<Self, serde_yaml::Error> {
        serde_yaml::from_str(yaml)
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
    use crate::export::mix_report::EffectInfo;
    use std::collections::HashMap;

    #[test]
    fn test_extract_processing_chain() {
        let extractor = TechniqueExtractor::new("测试项目");

        let chains = vec![EffectChainInfo {
            target: "人声".to_string(),
            chain: vec![EffectInfo {
                name: "Compressor".to_string(),
                effect_type: EffectType::Compressor,
                key_params: {
                    let mut p = HashMap::new();
                    p.insert("threshold".to_string(), "-18dB".to_string());
                    p
                },
                purpose: Some("控制动态".to_string()),
            }],
            intent: Some("温柔压缩".to_string()),
        }];

        let templates = extractor.extract_processing_chains(&chains, TemplateCategory::MixingChain);
        assert_eq!(templates.len(), 1);
        assert_eq!(templates[0].meta.category, TemplateCategory::MixingChain);
        assert_eq!(templates[0].processing_chains[0].steps.len(), 1);
        assert_eq!(
            templates[0].processing_chains[0].steps[0].param_ranges["threshold"].recommended,
            "-18dB"
        );
    }

    #[test]
    fn test_extract_arrangement_technique() {
        let extractor = TechniqueExtractor::new("测试项目");

        let techniques = vec![ArrangementTechnique {
            name: "副歌推动力".to_string(),
            description: "增加声像宽度和乐器密度".to_string(),
            applied_in: vec!["副歌".to_string()],
            related_tracks: vec!["Synth Pad".to_string()],
            intent: Some("增强冲击力".to_string()),
        }];

        let templates = extractor.extract_arrangement_techniques(&techniques);
        assert_eq!(templates.len(), 1);
        assert_eq!(templates[0].meta.name, "副歌推动力");
        assert_eq!(
            templates[0].arrangement_techniques[0].intent,
            Some("增强冲击力".to_string())
        );
    }

    #[test]
    fn test_yaml_roundtrip() {
        let template = TechniqueTemplate {
            meta: TemplateMeta {
                format_version: "0.1.0-draft".to_string(),
                name: "人声处理链".to_string(),
                category: TemplateCategory::MixingChain,
                tags: vec!["人声".to_string(), "压缩".to_string()],
                source_project: Some("测试项目".to_string()),
                created_at: "12345".to_string(),
                updated_at: "12345".to_string(),
            },
            conditions: UsageConditions {
                genres: vec!["Pop".to_string()],
                bpm_range: Some((80.0, 140.0)),
                instrument_types: vec![InstrumentType::Vocal],
                section_types: vec!["主歌".to_string(), "副歌".to_string()],
                prerequisites: Vec::new(),
            },
            processing_chains: Vec::new(),
            arrangement_techniques: Vec::new(),
            tips: vec![TemplateTip {
                tip_type: TipType::Caution,
                content: "注意压缩比不要太高".to_string(),
            }],
            stats: TemplateStats {
                use_count: 5,
                success_rate: Some(0.9),
                rating: Some(4.5),
            },
        };

        let yaml = TechniqueExtractor::export_yaml(&template).unwrap();
        let parsed = TechniqueExtractor::import_yaml(&yaml).unwrap();
        assert_eq!(parsed.meta.name, "人声处理链");
        assert_eq!(parsed.tips.len(), 1);
        assert_eq!(parsed.stats.use_count, 5);
    }

    #[test]
    fn test_library_search() {
        let mut library = TechniqueLibrary::new();

        library.add(TechniqueTemplate {
            meta: TemplateMeta {
                format_version: "0.1.0-draft".to_string(),
                name: "人声处理链".to_string(),
                category: TemplateCategory::MixingChain,
                tags: vec!["人声".to_string()],
                source_project: None,
                created_at: "12345".to_string(),
                updated_at: "12345".to_string(),
            },
            conditions: UsageConditions {
                genres: vec!["Pop".to_string(), "Rock".to_string()],
                bpm_range: None,
                instrument_types: Vec::new(),
                section_types: Vec::new(),
                prerequisites: Vec::new(),
            },
            processing_chains: Vec::new(),
            arrangement_techniques: Vec::new(),
            tips: Vec::new(),
            stats: TemplateStats::default(),
        });

        library.add(TechniqueTemplate {
            meta: TemplateMeta {
                format_version: "0.1.0-draft".to_string(),
                name: "副歌推动力".to_string(),
                category: TemplateCategory::ArrangementTechnique,
                tags: vec!["副歌".to_string()],
                source_project: None,
                created_at: "12345".to_string(),
                updated_at: "12345".to_string(),
            },
            conditions: UsageConditions::default(),
            processing_chains: Vec::new(),
            arrangement_techniques: Vec::new(),
            tips: Vec::new(),
            stats: TemplateStats::default(),
        });

        assert_eq!(
            library
                .search_by_category(TemplateCategory::MixingChain)
                .len(),
            1
        );
        assert_eq!(library.search_by_tag("人声").len(), 1);
        assert_eq!(library.search_by_genre("Pop").len(), 1);
        assert_eq!(library.search_by_genre("Jazz").len(), 0);
    }
}
