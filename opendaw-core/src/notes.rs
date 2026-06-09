//! 笔记系统 — 对标 Reaper Notes，支持 Markdown 所见即所得
//!
//! 三层笔记架构（对标 Reaper）：
//! - GlobalNote: 全局笔记，所有工程共享，存放主人的编曲混音理念和通用偏好
//! - ProjectNote: 项目笔记，绑定单个工程，存放项目意图和创作思路
//! - TrackNote: 轨道笔记，绑定单个音轨，存放音轨处理细节和混音说明
//!
//! Phase 37: 编曲混音知识系统
//! - 标签分类体系（编曲手法/混音技巧/侧链配置/效果器链/风格偏好等）
//! - 关联系统（笔记可关联到轨道、效果器、自动化、侧链等实体）
//! - 知识聚合接口（按标签/关联检索，智能体友好）
//! - 知识摘要导出（agent_knowledge_summary 为智能体提供风格画像）
//!
//! 智能体访问接口：
//! - NoteStore::read_all_notes() → 获取所有可见笔记内容
//! - NoteStore::read_track_notes(track_id) → 获取指定轨道笔记
//! - NoteStore::search_notes(query) → 语义搜索笔记内容
//! - NoteStore::filter_by_tags(tags) → 按标签筛选笔记
//! - NoteStore::filter_by_association(assoc) → 按关联实体筛选笔记
//! - NoteStore::agent_knowledge_summary() → 智能体知识画像摘要

use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::fs;
use std::path::{Path, PathBuf};

// ── 标签分类 ──────────────────────────────────────────────────────────

/// 标签类别 — 知识的分类体系，让经验不再零散
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum TagCategory {
    /// 编曲手法（副歌推动力、前奏编曲、段落衔接等）
    Arrangement,
    /// 混音技巧（EQ手法、压缩策略、空间处理等）
    Mixing,
    /// 侧链配置（底鼓侧链贝斯、侧链压缩参数等）
    Sidechain,
    /// 效果器链（效果器组合、信号路由、处理顺序等）
    EffectChain,
    /// 风格偏好（温暖/清亮/厚实/透明等主观倾向）
    Style,
    /// 自动化手法（渐变、呼吸感、动态控制等）
    Automation,
    /// 乐器编写（配器选择、声部安排、音色搭配等）
    Instrumentation,
    /// 创作意图（为什么这样处理的设计思路）
    Intent,
    /// 通用/未分类
    General,
}

impl TagCategory {
    /// 获取标签类别的中文名
    pub fn label(&self) -> &'static str {
        match self {
            TagCategory::Arrangement => "编曲手法",
            TagCategory::Mixing => "混音技巧",
            TagCategory::Sidechain => "侧链配置",
            TagCategory::EffectChain => "效果器链",
            TagCategory::Style => "风格偏好",
            TagCategory::Automation => "自动化手法",
            TagCategory::Instrumentation => "乐器编写",
            TagCategory::Intent => "创作意图",
            TagCategory::General => "通用",
        }
    }

    /// 获取所有类别
    pub fn all() -> Vec<TagCategory> {
        vec![
            TagCategory::Arrangement,
            TagCategory::Mixing,
            TagCategory::Sidechain,
            TagCategory::EffectChain,
            TagCategory::Style,
            TagCategory::Automation,
            TagCategory::Instrumentation,
            TagCategory::Intent,
            TagCategory::General,
        ]
    }
}

impl std::fmt::Display for TagCategory {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "{}", self.label())
    }
}

/// 结构化标签 — 带分类的标签，比纯字符串更有组织性
#[derive(Debug, Clone, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub struct NoteTag {
    /// 标签名称
    pub name: String,
    /// 标签类别
    pub category: TagCategory,
}

impl NoteTag {
    pub fn new(name: &str, category: TagCategory) -> Self {
        Self {
            name: name.to_string(),
            category,
        }
    }

    /// 从简单字符串创建（自动归入General类别）
    pub fn simple(name: &str) -> Self {
        Self {
            name: name.to_string(),
            category: TagCategory::General,
        }
    }

    /// 预定义编曲标签
    pub fn arrangement(name: &str) -> Self {
        Self::new(name, TagCategory::Arrangement)
    }

    /// 预定义混音标签
    pub fn mixing(name: &str) -> Self {
        Self::new(name, TagCategory::Mixing)
    }

    /// 预定义侧链标签
    pub fn sidechain(name: &str) -> Self {
        Self::new(name, TagCategory::Sidechain)
    }

    /// 预定义效果器链标签
    pub fn effect_chain(name: &str) -> Self {
        Self::new(name, TagCategory::EffectChain)
    }

    /// 预定义风格标签
    pub fn style(name: &str) -> Self {
        Self::new(name, TagCategory::Style)
    }

    /// 预定义创作意图标签
    pub fn intent(name: &str) -> Self {
        Self::new(name, TagCategory::Intent)
    }
}

// ── 关联系统 ──────────────────────────────────────────────────────────

/// 关联目标 — 笔记可以关联到的实体类型
#[derive(Debug, Clone, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum NoteAssociation {
    /// 关联到某个轨道
    Track { track_id: String },
    /// 关联到某个效果器插件
    Plugin { plugin_id: String },
    /// 关联到某个自动化轨
    Automation { automation_id: String },
    /// 关联到某个侧链配置
    Sidechain { source_id: String, target_id: String },
    /// 关联到某个效果器链
    EffectChain { chain_id: String },
    /// 关联到某个项目
    Project { project_id: String },
    /// 关联到某个编曲段落
    Section { section_name: String },
    /// 关联到某种乐器
    Instrument { instrument_name: String },
}

impl NoteAssociation {
    /// 获取关联类型的显示名
    pub fn assoc_type(&self) -> &'static str {
        match self {
            NoteAssociation::Track { .. } => "轨道",
            NoteAssociation::Plugin { .. } => "效果器",
            NoteAssociation::Automation { .. } => "自动化",
            NoteAssociation::Sidechain { .. } => "侧链",
            NoteAssociation::EffectChain { .. } => "效果器链",
            NoteAssociation::Project { .. } => "项目",
            NoteAssociation::Section { .. } => "段落",
            NoteAssociation::Instrument { .. } => "乐器",
        }
    }

    /// 获取关联实体的标识
    pub fn entity_id(&self) -> String {
        match self {
            NoteAssociation::Track { track_id } => track_id.clone(),
            NoteAssociation::Plugin { plugin_id } => plugin_id.clone(),
            NoteAssociation::Automation { automation_id } => automation_id.clone(),
            NoteAssociation::Sidechain { source_id, target_id } => {
                format!("{}→{}", source_id, target_id)
            }
            NoteAssociation::EffectChain { chain_id } => chain_id.clone(),
            NoteAssociation::Project { project_id } => project_id.clone(),
            NoteAssociation::Section { section_name } => section_name.clone(),
            NoteAssociation::Instrument { instrument_name } => instrument_name.clone(),
        }
    }
}

// ── Note 类型 ─────────────────────────────────────────────────────────

/// 笔记层级
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum NoteLevel {
    /// 全局笔记 — 所有工程共享
    Global,
    /// 项目笔记 — 绑定工程
    Project,
    /// 轨道笔记 — 绑定音轨
    Track,
}

impl std::fmt::Display for NoteLevel {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            NoteLevel::Global => write!(f, "Global"),
            NoteLevel::Project => write!(f, "Project"),
            NoteLevel::Track => write!(f, "Track"),
        }
    }
}

/// 单条笔记
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Note {
    /// 笔记 ID
    pub id: String,
    /// 笔记标题
    pub title: String,
    /// Markdown 正文
    pub content: String,
    /// 笔记层级
    pub level: NoteLevel,
    /// 关联的轨道 ID（仅 Track 级别有效）
    pub track_id: Option<String>,
    /// 创建时间 (Unix timestamp ms)
    pub created_at: i64,
    /// 更新时间 (Unix timestamp ms)
    pub updated_at: i64,
    /// 简单标签（向后兼容）
    #[serde(default)]
    pub tags: Vec<String>,
    /// 结构化标签（Phase 37 新增，带分类）
    #[serde(default)]
    pub structured_tags: Vec<NoteTag>,
    /// 关联实体（Phase 37 新增，笔记可关联到轨道、效果器等）
    #[serde(default)]
    pub associations: Vec<NoteAssociation>,
    /// 笔记来源（手动创建 / 从模板生成 / 从项目提取）
    #[serde(default = "default_source")]
    pub source: NoteSource,
}

/// 笔记来源
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum NoteSource {
    /// 用户手动创建
    Manual,
    /// 从技巧模板生成
    FromTemplate,
    /// 从项目数据自动提取
    AutoExtracted,
}

fn default_source() -> NoteSource {
    NoteSource::Manual
}

impl Note {
    /// 创建新笔记
    pub fn new(level: NoteLevel, title: &str, content: &str) -> Self {
        let now = chrono_now();
        Self {
            id: unique_note_id("note"),
            title: title.to_string(),
            content: content.to_string(),
            level,
            track_id: None,
            created_at: now,
            updated_at: now,
            tags: Vec::new(),
            structured_tags: Vec::new(),
            associations: Vec::new(),
            source: NoteSource::Manual,
        }
    }

    /// 创建轨道笔记
    pub fn new_for_track(track_id: &str, title: &str, content: &str) -> Self {
        let mut note = Self::new(NoteLevel::Track, title, content);
        note.track_id = Some(track_id.to_string());
        note.id = unique_note_id(&format!("note_track_{}", track_id));
        note.associations.push(NoteAssociation::Track {
            track_id: track_id.to_string(),
        });
        note
    }

    /// 更新内容
    pub fn update(&mut self, content: &str) {
        self.content = content.to_string();
        self.updated_at = chrono_now();
    }

    /// 添加简单标签（向后兼容）
    pub fn add_tag(&mut self, tag: &str) {
        if !self.tags.contains(&tag.to_string()) {
            self.tags.push(tag.to_string());
        }
    }

    /// 添加结构化标签
    pub fn add_structured_tag(&mut self, tag: NoteTag) {
        if !self.structured_tags.contains(&tag) {
            self.structured_tags.push(tag);
            // 同步到简单标签（向后兼容）
            if !self.tags.contains(&tag.name) {
                self.tags.push(tag.name.clone());
            }
        }
    }

    /// 批量添加结构化标签
    pub fn add_tags(&mut self, tags: Vec<NoteTag>) {
        for tag in tags {
            self.add_structured_tag(tag);
        }
    }

    /// 移除标签
    pub fn remove_tag(&mut self, tag_name: &str) {
        self.tags.retain(|t| t != tag_name);
        self.structured_tags.retain(|t| t.name != tag_name);
    }

    /// 添加关联
    pub fn add_association(&mut self, assoc: NoteAssociation) {
        if !self.associations.contains(&assoc) {
            self.associations.push(assoc);
        }
    }

    /// 移除关联
    pub fn remove_association(&mut self, assoc: &NoteAssociation) {
        self.associations.retain(|a| a != assoc);
    }

    /// 检查是否有关联到指定类型的实体
    pub fn has_association_type(&self, assoc_type: &str) -> bool {
        self.associations
            .iter()
            .any(|a| a.assoc_type() == assoc_type)
    }

    /// 获取所有标签名
    pub fn tag_names(&self) -> Vec<&str> {
        self.tags.iter().map(|s| s.as_str()).collect()
    }

    /// 检查是否包含指定标签
    pub fn has_tag(&self, tag: &str) -> bool {
        self.tags.iter().any(|t| t == tag)
    }

    /// 检查是否包含指定类别的标签
    pub fn has_tag_category(&self, category: TagCategory) -> bool {
        self.structured_tags.iter().any(|t| t.category == category)
    }

    /// 获取内容预览（前200字符）
    pub fn preview(&self) -> String {
        if self.content.len() > 200 {
            format!("{}...", &self.content[..200])
        } else {
            self.content.clone()
        }
    }

    /// 从 Markdown 文件加载
    pub fn from_markdown(
        path: &Path,
        level: NoteLevel,
        track_id: Option<String>,
    ) -> Result<Self, NoteError> {
        let content = fs::read_to_string(path)
            .map_err(|e| NoteError::IoError(format!("读取笔记文件失败: {}", e)))?;

        let filename = path
            .file_stem()
            .and_then(|s| s.to_str())
            .unwrap_or("untitled");

        let now = chrono_now();

        Ok(Self {
            id: format!("note_{}_{}", level, filename),
            title: filename.to_string(),
            content,
            level,
            track_id,
            created_at: now,
            updated_at: now,
            tags: Vec::new(),
            structured_tags: Vec::new(),
            associations: Vec::new(),
            source: NoteSource::Manual,
        })
    }

    /// 保存为 Markdown 文件
    pub fn save_to(&self, dir: &Path) -> Result<PathBuf, NoteError> {
        fs::create_dir_all(dir)
            .map_err(|e| NoteError::IoError(format!("创建笔记目录失败: {}", e)))?;

        let filename = match self.level {
            NoteLevel::Track => {
                let tid = self.track_id.as_deref().unwrap_or("unknown");
                format!("track_{}.md", tid)
            }
            NoteLevel::Project => format!("project_{}.md", sanitize_filename(&self.id)),
            NoteLevel::Global => format!("global_{}.md", sanitize_filename(&self.id)),
        };

        let path = dir.join(&filename);
        fs::write(&path, &self.content)
            .map_err(|e| NoteError::IoError(format!("写入笔记文件失败: {}", e)))?;

        Ok(path)
    }

    /// 导出为带元数据的 Markdown（含标签和关联信息）
    pub fn to_markdown_with_metadata(&self) -> String {
        let mut md = String::new();

        // YAML frontmatter
        md.push_str("---\n");
        md.push_str(&format!("id: {}\n", self.id));
        md.push_str(&format!("title: {}\n", self.title));
        md.push_str(&format!("level: {}\n", self.level));
        md.push_str(&format!("source: {:?}\n", self.source));
        md.push_str(&format!("created: {}\n", self.created_at));
        md.push_str(&format!("updated: {}\n", self.updated_at));

        if !self.tags.is_empty() {
            md.push_str(&format!("tags: [{}]\n", self.tags.join(", ")));
        }

        if !self.structured_tags.is_empty() {
            md.push_str("structured_tags:\n");
            for tag in &self.structured_tags {
                md.push_str(&format!("  - name: {}\n    category: {}\n", tag.name, tag.category));
            }
        }

        if !self.associations.is_empty() {
            md.push_str("associations:\n");
            for assoc in &self.associations {
                md.push_str(&format!("  - type: {}\n    entity: {}\n", assoc.assoc_type(), assoc.entity_id()));
            }
        }

        md.push_str("---\n\n");
        md.push_str(&self.content);

        md
    }
}

// ── Note Store ────────────────────────────────────────────────────────

/// 笔记存储 — 管理三层笔记的统一接口
pub struct NoteStore {
    /// 全局笔记目录 (~/.opendaw/notes/)
    global_dir: PathBuf,
    /// 项目笔记目录 ({project_dir}/notes/)
    project_dir: Option<PathBuf>,
    /// 已加载的笔记缓存
    cache: HashMap<String, Note>,
}

impl NoteStore {
    /// 创建笔记存储（仅全局）
    pub fn new() -> Self {
        let global_dir = dirs::home_dir()
            .unwrap_or_else(|| PathBuf::from("."))
            .join(".opendaw")
            .join("notes");

        Self {
            global_dir,
            project_dir: None,
            cache: HashMap::new(),
        }
    }

    /// 绑定项目目录
    pub fn with_project(mut self, project_dir: &Path) -> Self {
        self.project_dir = Some(project_dir.join("notes"));
        self
    }

    /// 加载所有笔记
    pub fn load_all(&mut self) -> Result<(), NoteError> {
        let global_dir = self.global_dir.clone();
        let project_dir = self.project_dir.clone();

        self.load_from_dir(&global_dir, NoteLevel::Global, None)?;

        if let Some(ref pd) = project_dir {
            self.load_from_dir(pd, NoteLevel::Project, None)?;

            let track_notes_dir = pd.join("tracks");
            if track_notes_dir.exists() {
                if let Ok(entries) = fs::read_dir(&track_notes_dir) {
                    for entry in entries.flatten() {
                        let path = entry.path();
                        if path.extension().and_then(|e| e.to_str()) == Some("md") {
                            let stem = path.file_stem().and_then(|s| s.to_str()).unwrap_or("");
                            let track_id = stem.strip_prefix("track_").unwrap_or(stem);
                            if let Ok(note) = Note::from_markdown(
                                &path,
                                NoteLevel::Track,
                                Some(track_id.to_string()),
                            ) {
                                self.cache.insert(note.id.clone(), note);
                            }
                        }
                    }
                }
            }
        }

        Ok(())
    }

    /// 从目录加载笔记
    fn load_from_dir(
        &mut self,
        dir: &Path,
        level: NoteLevel,
        track_id: Option<String>,
    ) -> Result<(), NoteError> {
        if !dir.exists() {
            return Ok(());
        }
        let entries = fs::read_dir(dir)
            .map_err(|e| NoteError::IoError(format!("读取笔记目录失败: {}", e)))?;

        for entry in entries.flatten() {
            let path = entry.path();
            if path.extension().and_then(|e| e.to_str()) == Some("md") {
                if path.is_dir() {
                    continue;
                }
                if let Ok(note) = Note::from_markdown(&path, level, track_id.clone()) {
                    self.cache.insert(note.id.clone(), note);
                }
            }
        }
        Ok(())
    }

    /// 读取所有笔记（供智能体访问）
    pub fn read_all_notes(&self) -> Vec<&Note> {
        self.cache.values().collect()
    }

    /// 按层级读取笔记
    pub fn read_notes_by_level(&self, level: NoteLevel) -> Vec<&Note> {
        self.cache.values().filter(|n| n.level == level).collect()
    }

    /// 读取轨道笔记
    pub fn read_track_notes(&self, track_id: &str) -> Vec<&Note> {
        self.cache
            .values()
            .filter(|n| n.level == NoteLevel::Track && n.track_id.as_deref() == Some(track_id))
            .collect()
    }

    /// 获取单条笔记
    pub fn get_note(&self, id: &str) -> Option<&Note> {
        self.cache.get(id)
    }

    /// 获取单条笔记（可变）
    pub fn get_note_mut(&mut self, id: &str) -> Option<&mut Note> {
        self.cache.get_mut(id)
    }

    /// 创建或更新笔记
    pub fn save_note(&mut self, note: Note) -> Result<(), NoteError> {
        let dir = match note.level {
            NoteLevel::Global => self.global_dir.clone(),
            NoteLevel::Project => self.project_dir.clone().ok_or(NoteError::NoProjectBound)?,
            NoteLevel::Track => {
                let base = self.project_dir.clone().ok_or(NoteError::NoProjectBound)?;
                base.join("tracks")
            }
        };

        note.save_to(&dir)?;
        self.cache.insert(note.id.clone(), note);
        Ok(())
    }

    /// 删除笔记
    pub fn delete_note(&mut self, id: &str) -> Result<(), NoteError> {
        if let Some(note) = self.cache.remove(id) {
            let dir = match note.level {
                NoteLevel::Global => self.global_dir.clone(),
                NoteLevel::Project => self.project_dir.clone().ok_or(NoteError::NoProjectBound)?,
                NoteLevel::Track => {
                    let base = self.project_dir.clone().ok_or(NoteError::NoProjectBound)?;
                    base.join("tracks")
                }
            };

            let filename = match note.level {
                NoteLevel::Track => {
                    format!("track_{}.md", note.track_id.as_deref().unwrap_or("unknown"))
                }
                _ => format!(
                    "{}_{}.md",
                    note.level.to_string().to_lowercase(),
                    sanitize_filename(&note.id)
                ),
            };

            let path = dir.join(&filename);
            if path.exists() {
                fs::remove_file(&path)
                    .map_err(|e| NoteError::IoError(format!("删除笔记文件失败: {}", e)))?;
            }
        }
        Ok(())
    }

    // ── Phase 37: 标签与关联查询 ──────────────────────────────────────

    /// 按标签筛选笔记（匹配任一标签）
    pub fn filter_by_tags(&self, tags: &[&str]) -> Vec<&Note> {
        self.cache
            .values()
            .filter(|n| tags.iter().any(|t| n.has_tag(t)))
            .collect()
    }

    /// 按标签类别筛选笔记
    pub fn filter_by_tag_category(&self, category: TagCategory) -> Vec<&Note> {
        self.cache
            .values()
            .filter(|n| n.has_tag_category(category))
            .collect()
    }

    /// 按关联实体筛选笔记
    pub fn filter_by_association(&self, assoc: &NoteAssociation) -> Vec<&Note> {
        self.cache
            .values()
            .filter(|n| n.associations.contains(assoc))
            .collect()
    }

    /// 按关联类型筛选笔记（如所有关联到"轨道"的笔记）
    pub fn filter_by_association_type(&self, assoc_type: &str) -> Vec<&Note> {
        self.cache
            .values()
            .filter(|n| n.has_association_type(assoc_type))
            .collect()
    }

    /// 获取所有标签（去重）
    pub fn get_all_tags(&self) -> Vec<String> {
        let mut tags: Vec<String> = self
            .cache
            .values()
            .flat_map(|n| n.tags.iter().cloned())
            .collect();
        tags.sort();
        tags.dedup();
        tags
    }

    /// 获取所有结构化标签（去重）
    pub fn get_all_structured_tags(&self) -> Vec<NoteTag> {
        let mut tags: Vec<NoteTag> = self
            .cache
            .values()
            .flat_map(|n| n.structured_tags.iter().cloned())
            .collect();
        tags.sort_by(|a, b| a.name.cmp(&b.name));
        tags.dedup();
        tags
    }

    /// 获取标签统计（标签名 → 使用次数）
    pub fn tag_stats(&self) -> HashMap<String, usize> {
        let mut stats = HashMap::new();
        for note in self.cache.values() {
            for tag in &note.tags {
                *stats.entry(tag.clone()).or_insert(0) += 1;
            }
        }
        stats
    }

    /// 获取按类别分组的标签统计
    pub fn tag_stats_by_category(&self) -> HashMap<TagCategory, Vec<(String, usize)>> {
        let mut stats: HashMap<TagCategory, Vec<(String, usize)>> = HashMap::new();
        for note in self.cache.values() {
            for tag in &note.structured_tags {
                let entry = stats.entry(tag.category).or_default();
                if let Some(item) = entry.iter_mut().find(|(n, _)| n == &tag.name) {
                    item.1 += 1;
                } else {
                    entry.push((tag.name.clone(), 1));
                }
            }
        }
        // Sort each category by frequency
        for v in stats.values_mut() {
            v.sort_by(|a, b| b.1.cmp(&a.1));
        }
        stats
    }

    /// 搜索笔记内容（关键词搜索，覆盖标题+内容+标签）
    pub fn search_notes(&self, query: &str) -> Vec<&Note> {
        let query_lower = query.to_lowercase();
        self.cache
            .values()
            .filter(|n| {
                n.title.to_lowercase().contains(&query_lower)
                    || n.content.to_lowercase().contains(&query_lower)
                    || n.tags
                        .iter()
                        .any(|t| t.to_lowercase().contains(&query_lower))
            })
            .collect()
    }

    /// 高级搜索 — 同时按关键词+标签+类别过滤
    pub fn search_advanced(
        &self,
        query: Option<&str>,
        tags: Option<&[&str]>,
        category: Option<TagCategory>,
        level: Option<NoteLevel>,
    ) -> Vec<&Note> {
        self.cache
            .values()
            .filter(|n| {
                // 关键词过滤
                if let Some(q) = query {
                    let q_lower = q.to_lowercase();
                    if !n.title.to_lowercase().contains(&q_lower)
                        && !n.content.to_lowercase().contains(&q_lower)
                        && !n.tags.iter().any(|t| t.to_lowercase().contains(&q_lower))
                    {
                        return false;
                    }
                }
                // 标签过滤
                if let Some(ts) = tags {
                    if !ts.iter().any(|t| n.has_tag(t)) {
                        return false;
                    }
                }
                // 类别过滤
                if let Some(cat) = category {
                    if !n.has_tag_category(cat) {
                        return false;
                    }
                }
                // 层级过滤
                if let Some(lvl) = level {
                    if n.level != lvl {
                        return false;
                    }
                }
                true
            })
            .collect()
    }

    // ── 智能体接口 ────────────────────────────────────────────────────

    /// 生成智能体友好的笔记摘要（包含所有笔记的结构化摘要）
    pub fn agent_summary(&self) -> String {
        let mut summary = String::from("# OpenDAW 笔记摘要\n\n");

        // 全局笔记
        let global = self.read_notes_by_level(NoteLevel::Global);
        if !global.is_empty() {
            summary.push_str("## 全局笔记（编曲混音理念）\n\n");
            for note in global {
                summary.push_str(&format!("### {}\n", note.title));
                if !note.structured_tags.is_empty() {
                    let tag_strs: Vec<String> = note
                        .structured_tags
                        .iter()
                        .map(|t| format!("[{}:{}]", t.category, t.name))
                        .collect();
                    summary.push_str(&format!("标签: {}\n", tag_strs.join(" ")));
                }
                summary.push_str(&format!("{}\n\n", note.content));
            }
        }

        // 项目笔记
        let project = self.read_notes_by_level(NoteLevel::Project);
        if !project.is_empty() {
            summary.push_str("## 项目笔记（项目意图）\n\n");
            for note in project {
                summary.push_str(&format!("### {}\n{}\n\n", note.title, note.content));
            }
        }

        // 轨道笔记
        let tracks = self.read_notes_by_level(NoteLevel::Track);
        if !tracks.is_empty() {
            summary.push_str("## 轨道笔记\n\n");
            for note in tracks {
                let tid = note.track_id.as_deref().unwrap_or("unknown");
                summary.push_str(&format!(
                    "### [{}] {}\n{}\n\n",
                    tid, note.title, note.content
                ));
            }
        }

        if summary.len() < 50 {
            summary.push_str("*暂无笔记*\n");
        }

        summary
    }

    /// 生成智能体知识画像 — 为AI混音/编曲提供用户风格偏好
    /// 聚合所有标签和关联，形成结构化的用户偏好画像
    pub fn agent_knowledge_summary(&self) -> KnowledgeSummary {
        let mut summary = KnowledgeSummary::default();

        for note in self.cache.values() {
            // 收集风格偏好
            for tag in &note.structured_tags {
                match tag.category {
                    TagCategory::Style => {
                        summary.style_preferences.push(tag.name.clone());
                    }
                    TagCategory::Arrangement => {
                        summary.arrangement_techniques.push(tag.name.clone());
                    }
                    TagCategory::Mixing => {
                        summary.mixing_techniques.push(tag.name.clone());
                    }
                    TagCategory::Sidechain => {
                        summary.sidechain_practices.push(tag.name.clone());
                    }
                    TagCategory::EffectChain => {
                        summary.effect_chain_preferences.push(tag.name.clone());
                    }
                    TagCategory::Automation => {
                        summary.automation_patterns.push(tag.name.clone());
                    }
                    TagCategory::Instrumentation => {
                        summary.instrumentation_preferences.push(tag.name.clone());
                    }
                    TagCategory::Intent => {
                        summary.design_intents.push(tag.name.clone());
                    }
                    TagCategory::General => {
                        summary.general_tags.push(tag.name.clone());
                    }
                }
            }

            // 收集关联实体
            for assoc in &note.associations {
                summary
                    .referenced_entities
                    .push((assoc.assoc_type().to_string(), assoc.entity_id()));
            }
        }

        // 去重
        let dedup = |v: &mut Vec<String>| {
            v.sort();
            v.dedup();
        };
        dedup(&mut summary.style_preferences);
        dedup(&mut summary.arrangement_techniques);
        dedup(&mut summary.mixing_techniques);
        dedup(&mut summary.sidechain_practices);
        dedup(&mut summary.effect_chain_preferences);
        dedup(&mut summary.automation_patterns);
        dedup(&mut summary.instrumentation_preferences);
        dedup(&mut summary.design_intents);
        dedup(&mut summary.general_tags);

        summary.total_notes = self.cache.len();
        summary
    }

    /// 笔记数量
    pub fn count(&self) -> usize {
        self.cache.len()
    }

    /// 按层级统计
    pub fn count_by_level(&self, level: NoteLevel) -> usize {
        self.cache.values().filter(|n| n.level == level).count()
    }
}

impl Default for NoteStore {
    fn default() -> Self {
        Self::new()
    }
}

// ── 知识画像 ──────────────────────────────────────────────────────────

/// 用户编曲混音知识画像 — 智能体可直接读取，学习用户风格
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct KnowledgeSummary {
    /// 笔记总数
    pub total_notes: usize,
    /// 风格偏好（温暖/清亮/厚实等）
    pub style_preferences: Vec<String>,
    /// 编曲手法
    pub arrangement_techniques: Vec<String>,
    /// 混音技巧
    pub mixing_techniques: Vec<String>,
    /// 侧链实践
    pub sidechain_practices: Vec<String>,
    /// 效果器链偏好
    pub effect_chain_preferences: Vec<String>,
    /// 自动化手法
    pub automation_patterns: Vec<String>,
    /// 配器偏好
    pub instrumentation_preferences: Vec<String>,
    /// 设计意图关键词
    pub design_intents: Vec<String>,
    /// 通用标签
    pub general_tags: Vec<String>,
    /// 引用过的实体 (type, id)
    pub referenced_entities: Vec<(String, String)>,
}

impl KnowledgeSummary {
    /// 导出为 YAML 格式（.omp.yaml 兼容）
    pub fn to_yaml(&self) -> Result<String, NoteError> {
        serde_yaml::to_string(self)
            .map_err(|e| NoteError::SerializationError(format!("YAML序列化失败: {}", e)))
    }

    /// 导出为 Markdown 摘要
    pub fn to_markdown(&self) -> String {
        let mut md = String::from("# 用户编曲混音知识画像\n\n");

        md.push_str(&format!("基于 {} 条笔记聚合\n\n", self.total_notes));

        let section = |title: &str, items: &[String]| -> String {
            if items.is_empty() {
                return String::new();
            }
            let mut s = format!("## {}\n\n", title);
            for item in items {
                s.push_str(&format!("- {}\n", item));
            }
            s.push('\n');
            s
        };

        md.push_str(&section("风格偏好", &self.style_preferences));
        md.push_str(&section("编曲手法", &self.arrangement_techniques));
        md.push_str(&section("混音技巧", &self.mixing_techniques));
        md.push_str(&section("侧链实践", &self.sidechain_practices));
        md.push_str(&section("效果器链偏好", &self.effect_chain_preferences));
        md.push_str(&section("自动化手法", &self.automation_patterns));
        md.push_str(&section("配器偏好", &self.instrumentation_preferences));
        md.push_str(&section("设计意图", &self.design_intents));

        md
    }
}

// ── Error ─────────────────────────────────────────────────────────────

#[derive(Debug, thiserror::Error)]
pub enum NoteError {
    #[error("IO错误: {0}")]
    IoError(String),
    #[error("未绑定项目目录")]
    NoProjectBound,
    #[error("笔记未找到: {0}")]
    NotFound(String),
    #[error("序列化错误: {0}")]
    SerializationError(String),
}

// ── Helpers ───────────────────────────────────────────────────────────

/// 毫秒级时间戳（避免 chrono 依赖）
fn chrono_now() -> i64 {
    std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .unwrap_or_default()
        .as_millis() as i64
}

/// 生成唯一ID（毫秒时间戳 + 随机后缀，避免同毫秒冲突）
fn unique_note_id(prefix: &str) -> String {
    use std::sync::atomic::{AtomicU64, Ordering};
    static COUNTER: AtomicU64 = AtomicU64::new(0);
    let ts = chrono_now();
    let cnt = COUNTER.fetch_add(1, Ordering::Relaxed);
    format!("{}_{}_{}", prefix, ts, cnt)
}

/// 文件名安全化
fn sanitize_filename(s: &str) -> String {
    s.chars()
        .map(|c| {
            if c.is_alphanumeric() || c == '-' || c == '_' {
                c
            } else {
                '_'
            }
        })
        .collect()
}

// ── Tests ─────────────────────────────────────────────────────────────

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_note_creation() {
        let note = Note::new(
            NoteLevel::Global,
            "混音理念",
            "我偏好温暖的混音风格，低频要厚实",
        );
        assert_eq!(note.level, NoteLevel::Global);
        assert_eq!(note.title, "混音理念");
        assert!(note.track_id.is_none());
        assert!(note.source == NoteSource::Manual);
    }

    #[test]
    fn test_track_note() {
        let note = Note::new_for_track("vocal", "人声处理", "人声需要温柔的压缩和适度的混响");
        assert_eq!(note.level, NoteLevel::Track);
        assert_eq!(note.track_id, Some("vocal".to_string()));
        // 应自动关联到轨道
        assert!(note.associations.contains(&NoteAssociation::Track {
            track_id: "vocal".to_string()
        }));
    }

    #[test]
    fn test_note_update() {
        let mut note = Note::new(NoteLevel::Project, "创作思路", "初稿");
        let old_updated = note.updated_at;
        note.update("修改后的内容");
        assert_eq!(note.content, "修改后的内容");
        assert!(note.updated_at >= old_updated);
    }

    #[test]
    fn test_structured_tags() {
        let mut note = Note::new(NoteLevel::Global, "副歌推动力", "副歌通过增加乐器和声像展开来推动");
        note.add_structured_tag(NoteTag::arrangement("副歌推动力"));
        note.add_structured_tag(NoteTag::mixing("声像展开"));
        note.add_structured_tag(NoteTag::intent("增加推动力"));

        assert!(note.has_tag("副歌推动力"));
        assert!(note.has_tag_category(TagCategory::Arrangement));
        assert!(note.has_tag_category(TagCategory::Mixing));
        assert!(note.has_tag_category(TagCategory::Intent));
        assert!(!note.has_tag_category(TagCategory::Sidechain));
    }

    #[test]
    fn test_tag_dedup() {
        let mut note = Note::new(NoteLevel::Global, "test", "content");
        note.add_structured_tag(NoteTag::mixing("压缩"));
        note.add_structured_tag(NoteTag::mixing("压缩")); // 重复
        assert_eq!(note.structured_tags.len(), 1);
        assert_eq!(note.tags.len(), 1);
    }

    #[test]
    fn test_remove_tag() {
        let mut note = Note::new(NoteLevel::Global, "test", "content");
        note.add_tag("混音");
        note.add_structured_tag(NoteTag::mixing("EQ"));
        note.remove_tag("混音");
        assert!(!note.has_tag("混音"));
        note.remove_tag("EQ");
        assert!(!note.has_tag("EQ"));
    }

    #[test]
    fn test_associations() {
        let mut note = Note::new(NoteLevel::Global, "底鼓侧链", "底鼓侧链贝斯，释放时间要快");
        note.add_association(NoteAssociation::Sidechain {
            source_id: "kick".to_string(),
            target_id: "bass".to_string(),
        });
        note.add_structured_tag(NoteTag::sidechain("底鼓→贝斯"));

        assert!(note.has_association_type("侧链"));
        assert!(note.associations.contains(&NoteAssociation::Sidechain {
            source_id: "kick".to_string(),
            target_id: "bass".to_string()
        }));
    }

    #[test]
    fn test_note_preview() {
        let long_content = "x".repeat(300);
        let note = Note::new(NoteLevel::Global, "test", &long_content);
        assert!(note.preview().ends_with("..."));
        assert!(note.preview().len() <= 203);
    }

    #[test]
    fn test_note_search() {
        let mut store = NoteStore::new();
        let mut note1 = Note::new(NoteLevel::Global, "混音理念", "温暖的混音风格");
        let mut note2 = Note::new(NoteLevel::Project, "编曲思路", "流行曲风编曲");
        note1.id = "note_test_search_1".to_string();
        note2.id = "note_test_search_2".to_string();
        note1.add_structured_tag(NoteTag::mixing("温暖"));
        note2.add_structured_tag(NoteTag::arrangement("流行"));
        store.cache.insert(note1.id.clone(), note1);
        store.cache.insert(note2.id.clone(), note2);

        let results = store.search_notes("混音");
        assert_eq!(results.len(), 1);

        let results2 = store.search_notes("编曲");
        assert_eq!(results2.len(), 1);
    }

    #[test]
    fn test_filter_by_tags() {
        let mut store = NoteStore::new();
        let mut note1 = Note::new(NoteLevel::Global, "n1", "c1");
        let mut note2 = Note::new(NoteLevel::Global, "n2", "c2");
        note1.id = "ft1".to_string();
        note2.id = "ft2".to_string();
        note1.add_structured_tag(NoteTag::mixing("压缩"));
        note1.add_structured_tag(NoteTag::sidechain("底鼓侧链"));
        note2.add_structured_tag(NoteTag::arrangement("副歌"));
        store.cache.insert(note1.id.clone(), note1);
        store.cache.insert(note2.id.clone(), note2);

        let results = store.filter_by_tags(&["压缩"]);
        assert_eq!(results.len(), 1);

        let results2 = store.filter_by_tag_category(TagCategory::Sidechain);
        assert_eq!(results2.len(), 1);
    }

    #[test]
    fn test_filter_by_association() {
        let mut store = NoteStore::new();
        let mut note = Note::new(NoteLevel::Global, "轨道笔记", "相关内容");
        note.id = "assoc_test".to_string();
        note.add_association(NoteAssociation::Track {
            track_id: "drums".to_string(),
        });
        store.cache.insert(note.id.clone(), note);

        let results = store.filter_by_association(&NoteAssociation::Track {
            track_id: "drums".to_string(),
        });
        assert_eq!(results.len(), 1);

        let results2 = store.filter_by_association_type("轨道");
        assert_eq!(results2.len(), 1);
    }

    #[test]
    fn test_knowledge_summary() {
        let mut store = NoteStore::new();
        let mut note = Note::new(NoteLevel::Global, "混音理念", "偏好温暖厚实的低频");
        note.id = "ks_test".to_string();
        note.add_structured_tag(NoteTag::style("温暖"));
        note.add_structured_tag(NoteTag::style("厚实"));
        note.add_structured_tag(NoteTag::mixing("低频增强"));
        note.add_association(NoteAssociation::Sidechain {
            source_id: "kick".to_string(),
            target_id: "bass".to_string(),
        });
        store.cache.insert(note.id.clone(), note);

        let summary = store.agent_knowledge_summary();
        assert_eq!(summary.total_notes, 1);
        assert!(summary.style_preferences.contains(&"温暖".to_string()));
        assert!(summary.style_preferences.contains(&"厚实".to_string()));
        assert!(summary.mixing_techniques.contains(&"低频增强".to_string()));
    }

    #[test]
    fn test_tag_category_label() {
        assert_eq!(TagCategory::Arrangement.label(), "编曲手法");
        assert_eq!(TagCategory::Mixing.label(), "混音技巧");
        assert_eq!(TagCategory::Sidechain.label(), "侧链配置");
    }

    #[test]
    fn test_advanced_search() {
        let mut store = NoteStore::new();
        let mut note1 = Note::new(NoteLevel::Global, "副歌处理", "增加推动力");
        let mut note2 = Note::new(NoteLevel::Project, "前奏设计", "安静开场");
        note1.id = "adv1".to_string();
        note2.id = "adv2".to_string();
        note1.add_structured_tag(NoteTag::arrangement("副歌"));
        note2.add_structured_tag(NoteTag::arrangement("前奏"));
        store.cache.insert(note1.id.clone(), note1);
        store.cache.insert(note2.id.clone(), note2);

        // 按类别+层级搜索
        let results = store.search_advanced(
            None,
            None,
            Some(TagCategory::Arrangement),
            Some(NoteLevel::Global),
        );
        assert_eq!(results.len(), 1);
        assert_eq!(results[0].title, "副歌处理");
    }

    #[test]
    fn test_note_level_display() {
        assert_eq!(format!("{}", NoteLevel::Global), "Global");
        assert_eq!(format!("{}", NoteLevel::Project), "Project");
        assert_eq!(format!("{}", NoteLevel::Track), "Track");
    }

    #[test]
    fn test_markdown_with_metadata() {
        let mut note = Note::new(NoteLevel::Global, "侧链经验", "底鼓侧链贝斯释放要快");
        note.add_structured_tag(NoteTag::sidechain("底鼓→贝斯"));
        note.add_association(NoteAssociation::Sidechain {
            source_id: "kick".to_string(),
            target_id: "bass".to_string(),
        });

        let md = note.to_markdown_with_metadata();
        assert!(md.contains("---")); // YAML frontmatter
        assert!(md.contains("structured_tags:"));
        assert!(md.contains("associations:"));
        assert!(md.contains("底鼓侧链贝斯释放要快"));
    }
}
