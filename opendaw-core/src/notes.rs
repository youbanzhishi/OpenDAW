//! 笔记系统 — 对标 Reaper Notes，支持 Markdown 所见即所得
//!
//! 三层笔记架构（对标 Reaper）：
//! - GlobalNote: 全局笔记，所有工程共享，存放主人的编曲混音理念和通用偏好
//! - ProjectNote: 项目笔记，绑定单个工程，存放项目意图和创作思路
//! - TrackNote: 轨道笔记，绑定单个音轨，存放音轨处理细节和混音说明
//!
//! 智能体访问接口：
//! - NoteStore::read_all_notes() → 获取所有可见笔记内容
//! - NoteStore::read_track_notes(track_id) → 获取指定轨道笔记
//! - NoteStore::search_notes(query) → 语义搜索笔记内容
//!
//! 存储方式：
//! - 全局笔记：~/.opendaw/notes/ 目录
//! - 项目笔记：{project_dir}/notes/ 目录
//! - 轨道笔记：{project_dir}/notes/tracks/{track_id}.md

use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::fs;
use std::path::{Path, PathBuf};

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
    /// 创建时间 (Unix timestamp)
    pub created_at: i64,
    /// 更新时间 (Unix timestamp)
    pub updated_at: i64,
    /// 标签
    #[serde(default)]
    pub tags: Vec<String>,
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
        }
    }

    /// 创建轨道笔记
    pub fn new_for_track(track_id: &str, title: &str, content: &str) -> Self {
        let mut note = Self::new(NoteLevel::Track, title, content);
        note.track_id = Some(track_id.to_string());
        note.id = unique_note_id(&format!("note_track_{}", track_id));
        note
    }

    /// 更新内容
    pub fn update(&mut self, content: &str) {
        self.content = content.to_string();
        self.updated_at = chrono_now();
    }

    /// 添加标签
    pub fn add_tag(&mut self, tag: &str) {
        if !self.tags.contains(&tag.to_string()) {
            self.tags.push(tag.to_string());
        }
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
        // Clone dirs to avoid borrow checker conflict
        let global_dir = self.global_dir.clone();
        let project_dir = self.project_dir.clone();

        // 加载全局笔记
        self.load_from_dir(&global_dir, NoteLevel::Global, None)?;

        // 加载项目笔记
        if let Some(ref pd) = project_dir {
            self.load_from_dir(pd, NoteLevel::Project, None)?;

            // 加载轨道笔记
            let track_notes_dir = pd.join("tracks");
            if track_notes_dir.exists() {
                if let Ok(entries) = fs::read_dir(&track_notes_dir) {
                    for entry in entries.flatten() {
                        let path = entry.path();
                        if path.extension().and_then(|e| e.to_str()) == Some("md") {
                            let stem = path.file_stem().and_then(|s| s.to_str()).unwrap_or("");
                            // track_XXX.md → track_id = XXX
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
                // 跳过 tracks 子目录（单独处理）
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

    /// 搜索笔记内容（简单关键词搜索，未来可升级为语义搜索）
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

    /// 生成智能体友好的笔记摘要（包含所有笔记的结构化摘要）
    pub fn agent_summary(&self) -> String {
        let mut summary = String::from("# OpenDAW 笔记摘要\n\n");

        // 全局笔记
        let global = self.read_notes_by_level(NoteLevel::Global);
        if !global.is_empty() {
            summary.push_str("## 全局笔记（编曲混音理念）\n\n");
            for note in global {
                summary.push_str(&format!("### {}\n{}\n\n", note.title, note.content));
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

// ── Error ─────────────────────────────────────────────────────────────

#[derive(Debug, thiserror::Error)]
pub enum NoteError {
    #[error("IO错误: {0}")]
    IoError(String),
    #[error("未绑定项目目录")]
    NoProjectBound,
    #[error("笔记未找到: {0}")]
    NotFound(String),
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
    }

    #[test]
    fn test_track_note() {
        let note = Note::new_for_track("vocal", "人声处理", "人声需要温柔的压缩和适度的混响");
        assert_eq!(note.level, NoteLevel::Track);
        assert_eq!(note.track_id, Some("vocal".to_string()));
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
        // 强制不同ID避免同毫秒冲突
        note1.id = "note_test_search_1".to_string();
        note2.id = "note_test_search_2".to_string();
        store.cache.insert(note1.id.clone(), note1);
        store.cache.insert(note2.id.clone(), note2);

        let results = store.search_notes("混音");
        assert_eq!(results.len(), 1);

        let results2 = store.search_notes("编曲");
        assert_eq!(results2.len(), 1);
    }

    #[test]
    fn test_agent_summary() {
        let mut store = NoteStore::new();
        let note = Note::new(NoteLevel::Global, "混音理念", "偏好温暖厚实的低频");
        store.cache.insert(note.id.clone(), note);

        let summary = store.agent_summary();
        assert!(summary.contains("混音理念"));
        assert!(summary.contains("偏好温暖厚实的低频"));
    }

    #[test]
    fn test_note_level_display() {
        assert_eq!(format!("{}", NoteLevel::Global), "Global");
        assert_eq!(format!("{}", NoteLevel::Project), "Project");
        assert_eq!(format!("{}", NoteLevel::Track), "Track");
    }
}
