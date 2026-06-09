//! 编曲混音报告导出 — .omr.md 格式
//!
//! OpenDAW Mix Report (OMR) 是一种开放标准格式，
//! 用于从DAW项目中导出完整的编曲混音分析报告。
//!
//! 格式版本: 0.1.0-draft
//! 文件扩展名: .omr.md
//! 内容: Markdown + YAML frontmatter
//!
//! 报告包含：
//! - 项目概览（BPM、调性、时长、轨道数）
//! - 乐器与编排分析（配器、声部安排、编曲手法）
//! - 混音分析（效果器链、EQ/压缩/混响/延迟参数、信号路由）
//! - 自动化与侧链（自动化曲线、侧链配置、设计意图）
//! - 设计意图（为什么这样处理、主观偏好、经验总结）
//! - 知识关联（关联到Global Note中的标签和条目）

use crate::notes::{KnowledgeSummary, NoteStore, NoteTag, TagCategory};
use serde::{Deserialize, Serialize};
use std::collections::HashMap;

// ── 报告数据结构 ──────────────────────────────────────────────────────

/// 编曲混音报告 — 完整的项目分析数据
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MixReport {
    /// 报告元数据
    pub meta: ReportMeta,
    /// 项目概览
    pub project_overview: ProjectOverview,
    /// 乐器与编排分析
    pub arrangement: ArrangementAnalysis,
    /// 混音分析
    pub mixing: MixingAnalysis,
    /// 自动化与侧链
    pub automation_and_sidechain: AutomationSidechainSection,
    /// 设计意图
    pub design_intent: DesignIntentSection,
    /// 知识关联
    pub knowledge_links: KnowledgeLinks,
}

/// 报告元数据
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ReportMeta {
    /// OMR格式版本
    pub format_version: String,
    /// 生成时间 (ISO 8601)
    pub generated_at: String,
    /// OpenDAW版本
    pub opendaw_version: String,
    /// 项目名称
    pub project_name: String,
}

/// 项目概览
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct ProjectOverview {
    /// BPM
    pub bpm: Option<f64>,
    /// 调性
    pub key: Option<String>,
    /// 时长（秒）
    pub duration_seconds: Option<f64>,
    /// 轨道总数
    pub track_count: Option<usize>,
    /// 音频轨道数
    pub audio_track_count: Option<usize>,
    /// MIDI轨道数
    pub midi_track_count: Option<usize>,
    /// 采样率
    pub sample_rate: Option<u32>,
    /// 位深度
    pub bit_depth: Option<u16>,
    /// 段落结构（前奏/主歌/副歌/桥段/尾声等）
    pub sections: Vec<SectionInfo>,
}

/// 段落信息
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SectionInfo {
    /// 段落名称
    pub name: String,
    /// 起始时间（秒）
    pub start: f64,
    /// 结束时间（秒）
    pub end: f64,
    /// 段落特征描述
    pub characteristics: Vec<String>,
}

/// 编曲分析
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct ArrangementAnalysis {
    /// 乐器列表
    pub instruments: Vec<InstrumentInfo>,
    /// 编曲手法
    pub techniques: Vec<ArrangementTechnique>,
    /// 声部安排
    pub voice_arrangement: Vec<String>,
    /// 动态变化（段落间的编排差异）
    pub dynamic_changes: Vec<DynamicChange>,
}

/// 乐器信息
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct InstrumentInfo {
    /// 乐器名称
    pub name: String,
    /// 轨道名称
    pub track_name: String,
    /// 乐器类型
    pub instrument_type: InstrumentType,
    /// 出现的段落
    pub sections: Vec<String>,
    /// 备注
    pub notes: Option<String>,
}

/// 乐器类型
#[derive(Debug, Clone, Copy, PartialEq, Serialize, Deserialize)]
pub enum InstrumentType {
    /// 鼓组
    Drums,
    /// 贝斯
    Bass,
    /// 和声乐器（钢琴/吉他/合成器pad等）
    Harmony,
    /// 主旋律
    Lead,
    /// 人声
    Vocal,
    /// 效果/氛围
    FX,
    /// 其他
    Other,
}

/// 编曲手法
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ArrangementTechnique {
    /// 手法名称
    pub name: String,
    /// 描述
    pub description: String,
    /// 应用段落
    pub applied_in: Vec<String>,
    /// 关联的轨道
    pub related_tracks: Vec<String>,
    /// 设计意图（为什么要用这个手法）
    pub intent: Option<String>,
}

/// 动态变化
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DynamicChange {
    /// 变化描述
    pub description: String,
    /// 从哪个段落
    pub from_section: String,
    /// 到哪个段落
    pub to_section: String,
    /// 变化类型
    pub change_type: String,
}

/// 混音分析
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct MixingAnalysis {
    /// 效果器链
    pub effect_chains: Vec<EffectChainInfo>,
    /// 轨道混音参数
    pub track_mix_params: Vec<TrackMixParams>,
    /// 总线处理
    pub bus_processing: Vec<BusProcessingInfo>,
}

/// 效果器链信息
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct EffectChainInfo {
    /// 所属轨道/总线
    pub target: String,
    /// 效果器列表（按顺序）
    pub chain: Vec<EffectInfo>,
    /// 链的设计意图
    pub intent: Option<String>,
}

/// 效果器信息
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct EffectInfo {
    /// 效果器名称
    pub name: String,
    /// 效果器类型
    pub effect_type: EffectType,
    /// 关键参数
    pub key_params: HashMap<String, String>,
    /// 作用描述
    pub purpose: Option<String>,
}

/// 效果器类型
#[derive(Debug, Clone, Copy, PartialEq, Serialize, Deserialize)]
pub enum EffectType {
    EQ,
    Compressor,
    Reverb,
    Delay,
    Chorus,
    Limiter,
    Gate,
    DeEsser,
    Saturation,
    Other,
}

/// 轨道混音参数
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TrackMixParams {
    /// 轨道名称
    pub track_name: String,
    /// 音量 (dB)
    pub volume_db: Option<f64>,
    /// 声像 (-1.0 ~ 1.0)
    pub pan: Option<f64>,
    /// 静音
    pub muted: bool,
    /// 独奏
    pub solo: bool,
    /// 发送量
    pub sends: Vec<SendInfo>,
}

/// 发送信息
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SendInfo {
    /// 目标总线
    pub target_bus: String,
    /// 发送量 (dB)
    pub level_db: f64,
}

/// 总线处理信息
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct BusProcessingInfo {
    /// 总线名称
    pub bus_name: String,
    /// 处理链
    pub processing: Vec<EffectInfo>,
    /// 设计意图
    pub intent: Option<String>,
}

/// 自动化与侧链部分
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct AutomationSidechainSection {
    /// 自动化曲线
    pub automations: Vec<AutomationInfo>,
    /// 侧链配置
    pub sidechains: Vec<SidechainInfo>,
}

/// 自动化信息
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AutomationInfo {
    /// 目标参数
    pub target_param: String,
    /// 所属轨道
    pub track_name: String,
    /// 自动化类型
    pub automation_type: String,
    /// 曲线描述
    pub curve_description: String,
    /// 设计意图
    pub intent: Option<String>,
}

/// 侧链信息
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SidechainInfo {
    /// 源轨道
    pub source_track: String,
    /// 目标轨道/效果器
    pub target: String,
    /// 侧链类型
    pub sidechain_type: String,
    /// 关键参数
    pub params: HashMap<String, String>,
    /// 作用描述
    pub purpose: Option<String>,
    /// 设计意图
    pub intent: Option<String>,
}

/// 设计意图部分
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct DesignIntentSection {
    /// 整体混音理念
    pub overall_philosophy: Option<String>,
    /// 各段落的设计意图
    pub section_intents: Vec<SectionIntent>,
    /// 用户偏好总结
    pub preference_summary: Option<String>,
}

/// 段落设计意图
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SectionIntent {
    /// 段落名称
    pub section_name: String,
    /// 意图描述
    pub intent: String,
    /// 实现手法
    pub techniques: Vec<String>,
}

/// 知识关联 — 将报告内容与Global Note知识库关联
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct KnowledgeLinks {
    /// 引用的标签
    pub referenced_tags: Vec<String>,
    /// 引用的笔记条目
    pub referenced_notes: Vec<String>,
    /// 用户风格画像摘要
    pub style_summary: Option<String>,
}

// ── 报告生成器 ────────────────────────────────────────────────────────

/// 编曲混音报告生成器
pub struct MixReportGenerator {
    /// 项目名称
    project_name: String,
    /// 报告数据
    data: MixReport,
}

impl MixReportGenerator {
    /// 创建新的报告生成器
    pub fn new(project_name: &str) -> Self {
        let now = chrono_now_iso();
        Self {
            project_name: project_name.to_string(),
            data: MixReport {
                meta: ReportMeta {
                    format_version: "0.1.0-draft".to_string(),
                    generated_at: now,
                    opendaw_version: env!("CARGO_PKG_VERSION").to_string(),
                    project_name: project_name.to_string(),
                },
                project_overview: ProjectOverview::default(),
                arrangement: ArrangementAnalysis::default(),
                mixing: MixingAnalysis::default(),
                automation_and_sidechain: AutomationSidechainSection::default(),
                design_intent: DesignIntentSection::default(),
                knowledge_links: KnowledgeLinks::default(),
            },
        }
    }

    /// 设置项目概览
    pub fn with_overview(mut self, overview: ProjectOverview) -> Self {
        self.data.project_overview = overview;
        self
    }

    /// 设置编曲分析
    pub fn with_arrangement(mut self, arrangement: ArrangementAnalysis) -> Self {
        self.data.arrangement = arrangement;
        self
    }

    /// 设置混音分析
    pub fn with_mixing(mut self, mixing: MixingAnalysis) -> Self {
        self.data.mixing = mixing;
        self
    }

    /// 设置自动化与侧链
    pub fn with_automation_sidechain(mut self, section: AutomationSidechainSection) -> Self {
        self.data.automation_and_sidechain = section;
        self
    }

    /// 设置设计意图
    pub fn with_design_intent(mut self, intent: DesignIntentSection) -> Self {
        self.data.design_intent = intent;
        self
    }

    /// 从NoteStore关联知识
    pub fn with_knowledge_links(mut self, store: &NoteStore) -> Self {
        let summary = store.agent_knowledge_summary();
        self.data.knowledge_links = KnowledgeLinks {
            referenced_tags: summary.style_preferences
                [..summary.style_preferences.len().min(10)]
                .to_vec(),
            referenced_notes: Vec::new(),
            style_summary: Some(summary.to_markdown()),
        };
        self
    }

    /// 生成 .omr.md 报告
    pub fn generate(&self) -> String {
        let mut report = String::new();

        // YAML frontmatter
        report.push_str("---\n");
        report.push_str(&format!("format: omr-md\n"));
        report.push_str(&format!("version: {}\n", self.data.meta.format_version));
        report.push_str(&format!("project: {}\n", self.data.meta.project_name));
        report.push_str(&format!("generated: {}\n", self.data.meta.generated_at));
        report.push_str(&format!("opendaw: {}\n", self.data.meta.opendaw_version));
        report.push_str("---\n\n");

        // 标题
        report.push_str(&format!(
            "# 编曲混音报告：{}\n\n",
            self.data.meta.project_name
        ));

        // 项目概览
        report.push_str("## 项目概览\n\n");
        let ov = &self.data.project_overview;
        if let Some(bpm) = ov.bpm {
            report.push_str(&format!("- **BPM**: {}\n", bpm));
        }
        if let Some(ref key) = ov.key {
            report.push_str(&format!("- **调性**: {}\n", key));
        }
        if let Some(dur) = ov.duration_seconds {
            report.push_str(&format!("- **时长**: {:.1}s ({:.1}min)\n", dur, dur / 60.0));
        }
        if let Some(tc) = ov.track_count {
            report.push_str(&format!("- **轨道数**: {}", tc));
            if let Some(atc) = ov.audio_track_count {
                report.push_str(&format!(" (音频{}, ", atc));
            }
            if let Some(mtc) = ov.midi_track_count {
                report.push_str(&format!("MIDI{})", mtc));
            }
            report.push('\n');
        }
        if let Some(sr) = ov.sample_rate {
            report.push_str(&format!("- **采样率**: {}Hz\n", sr));
        }
        if !ov.sections.is_empty() {
            report.push_str("\n### 段落结构\n\n");
            for s in &ov.sections {
                report.push_str(&format!(
                    "- **{}** ({:.0}s ~ {:.0}s): {}\n",
                    s.name,
                    s.start,
                    s.end,
                    s.characteristics.join("、")
                ));
            }
        }
        report.push('\n');

        // 编曲分析
        let arr = &self.data.arrangement;
        if !arr.instruments.is_empty() || !arr.techniques.is_empty() {
            report.push_str("## 乐器与编排\n\n");

            if !arr.instruments.is_empty() {
                report.push_str("### 乐器配置\n\n");
                report.push_str("| 乐器 | 轨道 | 类型 | 出现段落 | 备注 |\n");
                report.push_str("|------|------|------|----------|------|\n");
                for inst in &arr.instruments {
                    let type_str = match inst.instrument_type {
                        InstrumentType::Drums => "鼓组",
                        InstrumentType::Bass => "贝斯",
                        InstrumentType::Harmony => "和声",
                        InstrumentType::Lead => "主旋律",
                        InstrumentType::Vocal => "人声",
                        InstrumentType::FX => "效果",
                        InstrumentType::Other => "其他",
                    };
                    report.push_str(&format!(
                        "| {} | {} | {} | {} | {} |\n",
                        inst.name,
                        inst.track_name,
                        type_str,
                        inst.sections.join("、"),
                        inst.notes.as_deref().unwrap_or("-")
                    ));
                }
                report.push('\n');
            }

            if !arr.techniques.is_empty() {
                report.push_str("### 编曲手法\n\n");
                for tech in &arr.techniques {
                    report.push_str(&format!("**{}**\n\n", tech.name));
                    report.push_str(&format!("{}\n\n", tech.description));
                    report.push_str(&format!(
                        "- 应用段落: {}\n",
                        tech.applied_in.join("、")
                    ));
                    if !tech.related_tracks.is_empty() {
                        report.push_str(&format!(
                            "- 相关轨道: {}\n",
                            tech.related_tracks.join("、")
                        ));
                    }
                    if let Some(ref intent) = tech.intent {
                        report.push_str(&format!("- 设计意图: {}\n", intent));
                    }
                    report.push('\n');
                }
            }
        }

        // 混音分析
        let mix = &self.data.mixing;
        if !mix.effect_chains.is_empty() || !mix.track_mix_params.is_empty() {
            report.push_str("## 混音分析\n\n");

            if !mix.effect_chains.is_empty() {
                report.push_str("### 效果器链\n\n");
                for chain in &mix.effect_chains {
                    report.push_str(&format!("**{}**\n\n", chain.target));
                    for (i, fx) in chain.chain.iter().enumerate() {
                        let type_str = match fx.effect_type {
                            EffectType::EQ => "EQ",
                            EffectType::Compressor => "压缩",
                            EffectType::Reverb => "混响",
                            EffectType::Delay => "延迟",
                            EffectType::Chorus => "合唱",
                            EffectType::Limiter => "限制",
                            EffectType::Gate => "门限",
                            EffectType::DeEsser => "齿音消除",
                            EffectType::Saturation => "饱和",
                            EffectType::Other => "其他",
                        };
                        let params_str = fx
                            .key_params
                            .iter()
                            .map(|(k, v)| format!("{}={}", k, v))
                            .collect::<Vec<_>>()
                            .join(", ");
                        report.push_str(&format!(
                            "{}. **{}** ({}) — {}\n",
                            i + 1,
                            fx.name,
                            type_str,
                            params_str
                        ));
                        if let Some(ref purpose) = fx.purpose {
                            report.push_str(&format!("   作用: {}\n", purpose));
                        }
                    }
                    if let Some(ref intent) = chain.intent {
                        report.push_str(&format!("\n设计意图: {}\n", intent));
                    }
                    report.push('\n');
                }
            }

            if !mix.track_mix_params.is_empty() {
                report.push_str("### 轨道混音参数\n\n");
                report.push_str("| 轨道 | 音量 | 声像 | 发送 |\n");
                report.push_str("|------|------|------|------|\n");
                for track in &mix.track_mix_params {
                    let vol = track
                        .volume_db
                        .map(|v| format!("{:.1}dB", v))
                        .unwrap_or_else(|| "-".to_string());
                    let pan = track
                        .pan
                        .map(|p| {
                            if p < -0.01 {
                                format!("L{:.0}", p.abs() * 100.0)
                            } else if p > 0.01 {
                                format!("R{:.0}", p * 100.0)
                            } else {
                                "C".to_string()
                            }
                        })
                        .unwrap_or_else(|| "-".to_string());
                    let sends = track
                        .sends
                        .iter()
                        .map(|s| format!("{}→{:.0}dB", s.target_bus, s.level_db))
                        .collect::<Vec<_>>()
                        .join(", ");
                    report.push_str(&format!(
                        "| {} | {} | {} | {} |\n",
                        track.track_name, vol, pan, sends
                    ));
                }
                report.push('\n');
            }
        }

        // 自动化与侧链
        let asc = &self.data.automation_and_sidechain;
        if !asc.automations.is_empty() || !asc.sidechains.is_empty() {
            report.push_str("## 自动化与侧链\n\n");

            if !asc.automations.is_empty() {
                report.push_str("### 自动化\n\n");
                for auto in &asc.automations {
                    report.push_str(&format!(
                        "**{}** → {} ({}): {}\n",
                        auto.track_name, auto.target_param, auto.automation_type, auto.curve_description
                    ));
                    if let Some(ref intent) = auto.intent {
                        report.push_str(&format!("  意图: {}\n", intent));
                    }
                }
                report.push('\n');
            }

            if !asc.sidechains.is_empty() {
                report.push_str("### 侧链配置\n\n");
                for sc in &asc.sidechains {
                    report.push_str(&format!(
                        "**{}** → **{}** ({})\n",
                        sc.source_track, sc.target, sc.sidechain_type
                    ));
                    let params_str = sc
                        .params
                        .iter()
                        .map(|(k, v)| format!("{}={}", k, v))
                        .collect::<Vec<_>>()
                        .join(", ");
                    report.push_str(&format!("  参数: {}\n", params_str));
                    if let Some(ref purpose) = sc.purpose {
                        report.push_str(&format!("  作用: {}\n", purpose));
                    }
                    if let Some(ref intent) = sc.intent {
                        report.push_str(&format!("  意图: {}\n", intent));
                    }
                }
                report.push('\n');
            }
        }

        // 设计意图
        let di = &self.data.design_intent;
        if di.overall_philosophy.is_some() || !di.section_intents.is_empty() {
            report.push_str("## 设计意图\n\n");
            if let Some(ref philosophy) = di.overall_philosophy {
                report.push_str(&format!("### 整体混音理念\n\n{}\n\n", philosophy));
            }
            if !di.section_intents.is_empty() {
                report.push_str("### 各段落意图\n\n");
                for si in &di.section_intents {
                    report.push_str(&format!("**{}**: {}\n", si.section_name, si.intent));
                    if !si.techniques.is_empty() {
                        report.push_str(&format!(
                            "  手法: {}\n",
                            si.techniques.join("、")
                        ));
                    }
                }
                report.push('\n');
            }
        }

        // 知识关联
        let kl = &self.data.knowledge_links;
        if !kl.referenced_tags.is_empty() || kl.style_summary.is_some() {
            report.push_str("## 知识关联\n\n");
            if !kl.referenced_tags.is_empty() {
                report.push_str(&format!(
                    "关联标签: {}\n\n",
                    kl.referenced_tags.join("、")
                ));
            }
            if let Some(ref summary) = kl.style_summary {
                report.push_str(summary);
            }
        }

        report
    }

    /// 导出为 .omr.md 文件内容
    pub fn export_omr_md(&self) -> String {
        self.generate()
    }

    /// 获取报告数据（供序列化）
    pub fn data(&self) -> &MixReport {
        &self.data
    }
}

// ── Helpers ───────────────────────────────────────────────────────────

fn chrono_now_iso() -> String {
    // Simple ISO 8601 timestamp without chrono dependency
    let now = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .unwrap_or_default()
        .as_secs();
    // Rough ISO format - just use Unix timestamp in a readable way
    format!("{}", now)
}

// ── Tests ─────────────────────────────────────────────────────────────

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_basic_report_generation() {
        let generator = MixReportGenerator::new("测试项目")
            .with_overview(ProjectOverview {
                bpm: Some(120.0),
                key: Some("C Major".to_string()),
                duration_seconds: Some(240.0),
                track_count: Some(8),
                ..Default::default()
            });

        let report = generator.generate();
        assert!(report.contains("测试项目"));
        assert!(report.contains("120"));
        assert!(report.contains("C Major"));
        assert!(report.contains("---")); // YAML frontmatter
    }

    #[test]
    fn test_arrangement_section() {
        let generator = MixReportGenerator::new("编曲测试").with_arrangement(ArrangementAnalysis {
            instruments: vec![InstrumentInfo {
                name: "底鼓".to_string(),
                track_name: "Drums".to_string(),
                instrument_type: InstrumentType::Drums,
                sections: vec!["前奏".to_string(), "主歌".to_string()],
                notes: Some("使用808底鼓".to_string()),
            }],
            techniques: vec![ArrangementTechnique {
                name: "副歌推动力".to_string(),
                description: "通过增加声像宽度和乐器密度来增强副歌能量".to_string(),
                applied_in: vec!["副歌".to_string()],
                related_tracks: vec!["Synth Pad".to_string()],
                intent: Some("让副歌更有冲击力".to_string()),
            }],
            ..Default::default()
        });

        let report = generator.generate();
        assert!(report.contains("底鼓"));
        assert!(report.contains("副歌推动力"));
        assert!(report.contains("让副歌更有冲击力"));
    }

    #[test]
    fn test_sidechain_section() {
        let generator = MixReportGenerator::new("侧链测试").with_automation_sidechain(
            AutomationSidechainSection {
                sidechains: vec![SidechainInfo {
                    source_track: "底鼓".to_string(),
                    target: "贝斯压缩器".to_string(),
                    sidechain_type: "压缩侧链".to_string(),
                    params: {
                        let mut p = HashMap::new();
                        p.insert("阈值".to_string(), "-20dB".to_string());
                        p.insert("比率".to_string(), "4:1".to_string());
                        p.insert("释放".to_string(), "50ms".to_string());
                        p
                    },
                    purpose: Some("让底鼓和贝斯不冲突".to_string()),
                    intent: Some("底鼓侧链贝斯是标准做法，释放时间要快避免抽吸感".to_string()),
                }],
                ..Default::default()
            },
        );

        let report = generator.generate();
        assert!(report.contains("底鼓"));
        assert!(report.contains("贝斯压缩器"));
        assert!(report.contains("释放时间要快"));
    }

    #[test]
    fn test_effect_chain() {
        let generator = MixReportGenerator::new("效果器测试").with_mixing(MixingAnalysis {
            effect_chains: vec![EffectChainInfo {
                target: "人声轨道".to_string(),
                chain: vec![
                    EffectInfo {
                        name: "Tube Compressor".to_string(),
                        effect_type: EffectType::Compressor,
                        key_params: {
                            let mut p = HashMap::new();
                            p.insert("阈值".to_string(), "-18dB".to_string());
                            p.insert("比率".to_string(), "3:1".to_string());
                            p
                        },
                        purpose: Some("控制动态范围".to_string()),
                    },
                    EffectInfo {
                        name: "Hall Reverb".to_string(),
                        effect_type: EffectType::Reverb,
                        key_params: {
                            let mut p = HashMap::new();
                            p.insert("衰减".to_string(), "2.5s".to_string());
                            p.insert("预延迟".to_string(), "30ms".to_string());
                            p
                        },
                        purpose: Some("营造空间感".to_string()),
                    },
                ],
                intent: Some("人声需要温柔的压缩和适度的混响".to_string()),
            }],
            ..Default::default()
        });

        let report = generator.generate();
        assert!(report.contains("Tube Compressor"));
        assert!(report.contains("Hall Reverb"));
        assert!(report.contains("温柔的压缩"));
    }
}
