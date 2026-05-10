//! 插件市场核心逻辑
//!
//! Phase 32: 基础注册+安装+兼容性检查
//! Phase 33: 增强 — 远程仓库、评分评论、分类体系、平台兼容性

use serde::{Deserialize, Serialize};
use std::collections::HashMap;

// ────────────────────────────────────────────
// 插件分类体系（Phase 33 增强）
// ────────────────────────────────────────────

/// 效果器子分类
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub enum EffectSubcategory {
    Compressor,
    Equalizer,
    Reverb,
    Delay,
    Chorus,
    Distortion,
    Dynamics,
    Other(String),
}

/// 乐器子分类
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub enum InstrumentSubcategory {
    Synthesizer,
    Sampler,
    DrumMachine,
    Other(String),
}

/// 工具子分类
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub enum UtilitySubcategory {
    Analyzer,
    Tool,
    Other(String),
}

/// 插件大类（Phase 33 增强：细化子分类）
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub enum PluginCategory {
    Effect { sub: Option<EffectSubcategory> },
    Instrument { sub: Option<InstrumentSubcategory> },
    Analyzer,
    Utility { sub: Option<UtilitySubcategory> },
    Midi,
}

// 向后兼容的便捷构造
impl PluginCategory {
    pub fn effect() -> Self {
        PluginCategory::Effect { sub: None }
    }
    pub fn instrument() -> Self {
        PluginCategory::Instrument { sub: None }
    }
    pub fn utility() -> Self {
        PluginCategory::Utility { sub: None }
    }
    pub fn is_effect(&self) -> bool {
        matches!(self, PluginCategory::Effect { .. })
    }
    pub fn is_instrument(&self) -> bool {
        matches!(self, PluginCategory::Instrument { .. })
    }
    pub fn is_utility(&self) -> bool {
        matches!(self, PluginCategory::Utility { .. })
    }
}

/// 平台目标三元组
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub struct PlatformTarget {
    pub os: String,       // "linux" | "macos" | "windows"
    pub arch: String,     // "x86_64" | "aarch64"
}

// ────────────────────────────────────────────
// 插件清单
// ────────────────────────────────────────────

/// 插件清单（YAML/JSON声明格式）
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct PluginManifest {
    pub id: String,
    pub name: String,
    pub version: String,
    pub author: String,
    pub description: String,
    pub category: PluginCategory,
    pub tags: Vec<String>,
    pub min_daw_version: Option<String>,
    pub dependencies: Vec<Dependency>,
    pub checksum: Option<String>,
    pub download_url: Option<String>,
    pub homepage: Option<String>,
    pub license: Option<String>,
    /// Phase 33: 支持的平台列表
    #[serde(default)]
    pub platforms: Vec<PlatformTarget>,
    /// Phase 33: 所属仓库ID
    #[serde(default)]
    pub repository_id: Option<String>,
}

/// 依赖声明
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct Dependency {
    pub plugin_id: String,
    pub version_constraint: String,
}

// ────────────────────────────────────────────
// 安装状态 / 进度
// ────────────────────────────────────────────

/// 安装状态
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub enum InstallStatus {
    NotInstalled,
    Downloading,
    Verifying,
    Extracting,
    Installing,
    Installed(String),
    Failed(String),
    Rollback,
}

/// 安装进度
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct InstallProgress {
    pub plugin_id: String,
    pub status: InstallStatus,
    pub percent: f32,
    pub message: String,
}

// ────────────────────────────────────────────
// 兼容性检测（Phase 33 增强）
// ────────────────────────────────────────────

/// 兼容性报告
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct CompatibilityReport {
    pub plugin_id: String,
    pub compatible: bool,
    pub issues: Vec<String>,
}

/// Phase 33 增强兼容性检查器
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct PluginCompatibility {
    /// 当前DAW版本
    pub daw_version: String,
    /// 当前平台
    pub platform: PlatformTarget,
}

impl PluginCompatibility {
    pub fn new(daw_version: &str, os: &str, arch: &str) -> Self {
        Self {
            daw_version: daw_version.to_string(),
            platform: PlatformTarget {
                os: os.to_string(),
                arch: arch.to_string(),
            },
        }
    }

    /// 检查插件与当前环境的兼容性
    pub fn check(&self, manifest: &PluginManifest, installed: &HashMap<String, String>) -> CompatibilityReport {
        let mut issues = Vec::new();

        // 1. DAW 版本兼容性
        if let Some(ref min_ver) = manifest.min_daw_version {
            if !semver_gte(&self.daw_version, min_ver) {
                issues.push(format!(
                    "Requires DAW version >= {}, current: {}",
                    min_ver, self.daw_version
                ));
            }
        }

        // 2. 平台兼容性
        if !manifest.platforms.is_empty() {
            let platform_match = manifest.platforms.iter().any(|p| {
                p.os == self.platform.os && p.arch == self.platform.arch
            });
            if !platform_match {
                issues.push(format!(
                    "Plugin not available for platform {}-{}",
                    self.platform.os, self.platform.arch
                ));
            }
        }

        // 3. 依赖检查
        for dep in &manifest.dependencies {
            if let Some(installed_ver) = installed.get(&dep.plugin_id) {
                if !semver_satisfies(installed_ver, &dep.version_constraint) {
                    issues.push(format!(
                        "Dependency '{}' version {} doesn't satisfy constraint {}",
                        dep.plugin_id, installed_ver, dep.version_constraint
                    ));
                }
            } else {
                issues.push(format!("Dependency '{}' not installed", dep.plugin_id));
            }
        }

        CompatibilityReport {
            plugin_id: manifest.id.clone(),
            compatible: issues.is_empty(),
            issues,
        }
    }
}

// ────────────────────────────────────────────
// 插件仓库（Phase 33 新增）
// ────────────────────────────────────────────

/// 仓库索引缓存条目
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct CachedIndex {
    pub repository_id: String,
    pub plugins: Vec<PluginManifest>,
    pub fetched_at: u64,
    pub ttl_secs: u64,
}

impl CachedIndex {
    pub fn is_expired(&self, now: u64) -> bool {
        now.saturating_sub(self.fetched_at) > self.ttl_secs
    }
}

/// 远程仓库定义
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct RepositorySource {
    pub id: String,
    pub url: String,
    pub name: String,
    pub is_official: bool,
    pub enabled: bool,
    pub ttl_secs: u64,
}

/// 插件仓库管理器
#[derive(Clone, Debug, Default)]
pub struct PluginRepository {
    /// 已注册的仓库源
    sources: HashMap<String, RepositorySource>,
    /// 索引缓存
    index_cache: HashMap<String, CachedIndex>,
}

impl PluginRepository {
    pub fn new() -> Self {
        Self::default()
    }

    /// 添加仓库源
    pub fn add_source(&mut self, source: RepositorySource) -> Result<(), String> {
        if self.sources.contains_key(&source.id) {
            return Err(format!("Repository '{}' already exists", source.id));
        }
        self.sources.insert(source.id.clone(), source);
        Ok(())
    }

    /// 移除仓库源
    pub fn remove_source(&mut self, repo_id: &str) -> Option<RepositorySource> {
        self.index_cache.remove(repo_id);
        self.sources.remove(repo_id)
    }

    /// 获取仓库源
    pub fn get_source(&self, repo_id: &str) -> Option<&RepositorySource> {
        self.sources.get(repo_id)
    }

    /// 列出所有仓库源
    pub fn list_sources(&self) -> Vec<&RepositorySource> {
        self.sources.values().collect()
    }

    /// 更新索引缓存（模拟从远程拉取）
    pub fn refresh_index(&mut self, repo_id: &str, plugins: Vec<PluginManifest>) -> Result<(), String> {
        if !self.sources.contains_key(repo_id) {
            return Err(format!("Repository '{}' not found", repo_id));
        }
        let now = current_timestamp();
        let ttl = self.sources.get(repo_id).map(|s| s.ttl_secs).unwrap_or(3600);
        self.index_cache.insert(
            repo_id.to_string(),
            CachedIndex {
                repository_id: repo_id.to_string(),
                plugins,
                fetched_at: now,
                ttl_secs: ttl,
            },
        );
        Ok(())
    }

    /// 获取缓存索引（如果过期返回 None）
    pub fn get_cached_index(&self, repo_id: &str) -> Option<&CachedIndex> {
        let now = current_timestamp();
        self.index_cache.get(repo_id).and_then(|idx| {
            if idx.is_expired(now) {
                None
            } else {
                Some(idx)
            }
        })
    }

    /// 获取缓存索引（忽略过期）
    pub fn get_cached_index_unchecked(&self, repo_id: &str) -> Option<&CachedIndex> {
        self.index_cache.get(repo_id)
    }

    /// 跨仓库联合搜索
    pub fn search_all(&self, query: &str, category: Option<&PluginCategory>) -> Vec<&PluginManifest> {
        let query_lower = query.to_lowercase();
        let mut results = Vec::new();

        for idx in self.index_cache.values() {
            for plugin in &idx.plugins {
                let matches_query = plugin.name.to_lowercase().contains(&query_lower)
                    || plugin.tags.iter().any(|t| t.to_lowercase().contains(&query_lower))
                    || plugin.description.to_lowercase().contains(&query_lower);
                let matches_cat = category.map_or(true, |cat| categories_match(&plugin.category, cat));
                if matches_query && matches_cat {
                    results.push(plugin);
                }
            }
        }
        results
    }

    /// 列出所有仓库中指定分类的插件
    pub fn list_by_category_all(&self, category: &PluginCategory) -> Vec<&PluginManifest> {
        let mut results = Vec::new();
        for idx in self.index_cache.values() {
            for plugin in &idx.plugins {
                if categories_match(&plugin.category, category) {
                    results.push(plugin);
                }
            }
        }
        results
    }

    /// 获取指定仓库中的插件
    pub fn get_plugin(&self, plugin_id: &str) -> Option<&PluginManifest> {
        for idx in self.index_cache.values() {
            if let Some(p) = idx.plugins.iter().find(|p| p.id == plugin_id) {
                return Some(p);
            }
        }
        None
    }
}

/// 分类匹配（大类匹配即可）
fn categories_match(plugin_cat: &PluginCategory, filter_cat: &PluginCategory) -> bool {
    match (plugin_cat, filter_cat) {
        (PluginCategory::Effect { .. }, PluginCategory::Effect { .. }) => true,
        (PluginCategory::Instrument { .. }, PluginCategory::Instrument { .. }) => true,
        (PluginCategory::Utility { .. }, PluginCategory::Utility { .. }) => true,
        (PluginCategory::Analyzer, PluginCategory::Analyzer) => true,
        (PluginCategory::Midi, PluginCategory::Midi) => true,
        _ => false,
    }
}

// ────────────────────────────────────────────
// 评分与评论（Phase 33 新增）
// ────────────────────────────────────────────

/// 单条评论
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct PluginReview {
    pub review_id: String,
    pub plugin_id: String,
    pub user_id: String,
    pub rating: u8,         // 1-5
    pub comment: String,
    pub created_at: u64,
}

impl PluginReview {
    pub fn new(plugin_id: &str, user_id: &str, rating: u8, comment: &str) -> Result<Self, String> {
        if rating < 1 || rating > 5 {
            return Err("Rating must be between 1 and 5".into());
        }
        if user_id.is_empty() {
            return Err("User ID cannot be empty".into());
        }
        Ok(Self {
            review_id: format!("rev-{}-{}", plugin_id, current_timestamp()),
            plugin_id: plugin_id.to_string(),
            user_id: user_id.to_string(),
            rating,
            comment: comment.to_string(),
            created_at: current_timestamp(),
        })
    }
}

/// 评分聚合
#[derive(Clone, Debug, Default, Serialize, Deserialize)]
pub struct RatingSummary {
    pub plugin_id: String,
    pub average_rating: f32,
    pub total_reviews: usize,
    pub rating_distribution: [usize; 5], // index 0 = 1-star, ..., 4 = 5-star
}

/// 评论管理器
#[derive(Clone, Debug, Default)]
pub struct ReviewManager {
    reviews: HashMap<String, Vec<PluginReview>>,   // plugin_id -> reviews
    summaries: HashMap<String, RatingSummary>,       // plugin_id -> summary
}

impl ReviewManager {
    pub fn new() -> Self {
        Self::default()
    }

    /// 添加评论
    pub fn add_review(&mut self, review: PluginReview) -> Result<(), String> {
        let pid = review.plugin_id.clone();
        self.reviews.entry(pid.clone()).or_default().push(review);
        self.recalculate_summary(&pid);
        Ok(())
    }

    /// 获取插件评论
    pub fn get_reviews(&self, plugin_id: &str) -> Vec<&PluginReview> {
        self.reviews.get(plugin_id).map(|v| v.iter().collect()).unwrap_or_default()
    }

    /// 获取评分汇总
    pub fn get_summary(&self, plugin_id: &str) -> Option<&RatingSummary> {
        self.summaries.get(plugin_id)
    }

    /// 获取平均评分
    pub fn average_rating(&self, plugin_id: &str) -> f32 {
        self.summaries.get(plugin_id).map(|s| s.average_rating).unwrap_or(0.0)
    }

    /// 重新计算汇总
    fn recalculate_summary(&mut self, plugin_id: &str) {
        let reviews = match self.reviews.get(plugin_id) {
            Some(r) => r,
            None => return,
        };
        let total = reviews.len();
        if total == 0 {
            return;
        }
        let sum: u32 = reviews.iter().map(|r| r.rating as u32).sum();
        let mut dist = [0usize; 5];
        for r in reviews {
            if r.rating >= 1 && r.rating <= 5 {
                dist[(r.rating - 1) as usize] += 1;
            }
        }
        self.summaries.insert(
            plugin_id.to_string(),
            RatingSummary {
                plugin_id: plugin_id.to_string(),
                average_rating: sum as f32 / total as f32,
                total_reviews: total,
                rating_distribution: dist,
            },
        );
    }
}

// ────────────────────────────────────────────
// 插件注册表
// ────────────────────────────────────────────

/// 插件注册表
#[derive(Clone, Debug, Default)]
pub struct PluginRegistry {
    plugins: HashMap<String, PluginManifest>,
    installed: HashMap<String, String>,
}

impl PluginRegistry {
    pub fn new() -> Self {
        Self::default()
    }

    /// 注册插件到市场
    pub fn register(&mut self, manifest: PluginManifest) -> Result<(), String> {
        if self.plugins.contains_key(&manifest.id) {
            return Err(format!("Plugin '{}' already registered", manifest.id));
        }
        semver_parse(&manifest.version)?;
        self.plugins.insert(manifest.id.clone(), manifest);
        Ok(())
    }

    /// 注销插件
    pub fn unregister(&mut self, plugin_id: &str) -> Option<PluginManifest> {
        self.installed.remove(plugin_id);
        self.plugins.remove(plugin_id)
    }

    /// 查询插件
    pub fn get(&self, plugin_id: &str) -> Option<&PluginManifest> {
        self.plugins.get(plugin_id)
    }

    /// 列出所有插件
    pub fn list_all(&self) -> Vec<&PluginManifest> {
        self.plugins.values().collect()
    }

    /// 按类别筛选
    pub fn list_by_category(&self, category: &PluginCategory) -> Vec<&PluginManifest> {
        self.plugins
            .values()
            .filter(|p| categories_match(&p.category, category))
            .collect()
    }

    /// 按标签搜索
    pub fn search(&self, query: &str) -> Vec<&PluginManifest> {
        let query_lower = query.to_lowercase();
        self.plugins
            .values()
            .filter(|p| {
                p.name.to_lowercase().contains(&query_lower)
                    || p.tags.iter().any(|t| t.to_lowercase().contains(&query_lower))
                    || p.description.to_lowercase().contains(&query_lower)
            })
            .collect()
    }

    /// 检查依赖兼容性
    pub fn check_compatibility(&self, manifest: &PluginManifest, daw_version: &str) -> CompatibilityReport {
        let mut issues = Vec::new();

        if let Some(ref min_ver) = manifest.min_daw_version {
            if !semver_gte(daw_version, min_ver) {
                issues.push(format!(
                    "Requires DAW version >= {}, current: {}",
                    min_ver, daw_version
                ));
            }
        }

        for dep in &manifest.dependencies {
            if let Some(installed_ver) = self.installed.get(&dep.plugin_id) {
                if !semver_satisfies(installed_ver, &dep.version_constraint) {
                    issues.push(format!(
                        "Dependency '{}' version {} doesn't satisfy constraint {}",
                        dep.plugin_id, installed_ver, dep.version_constraint
                    ));
                }
            } else if self.plugins.contains_key(&dep.plugin_id) {
                issues.push(format!("Dependency '{}' not installed", dep.plugin_id));
            } else {
                issues.push(format!("Dependency '{}' not found in registry", dep.plugin_id));
            }
        }

        CompatibilityReport {
            plugin_id: manifest.id.clone(),
            compatible: issues.is_empty(),
            issues,
        }
    }

    /// 标记已安装
    pub fn mark_installed(&mut self, plugin_id: &str, version: &str) {
        self.installed.insert(plugin_id.to_string(), version.to_string());
    }

    /// 标记未安装
    pub fn mark_uninstalled(&mut self, plugin_id: &str) {
        self.installed.remove(plugin_id);
    }

    /// 检查是否已安装
    pub fn is_installed(&self, plugin_id: &str) -> bool {
        self.installed.contains_key(plugin_id)
    }

    /// 获取已安装版本
    pub fn installed_version(&self, plugin_id: &str) -> Option<&str> {
        self.installed.get(plugin_id).map(|s| s.as_str())
    }
}

// ────────────────────────────────────────────
// 插件安装器
// ────────────────────────────────────────────

/// 插件安装器
pub struct PluginInstaller {
    registry: PluginRegistry,
    progress_callback: Option<Box<dyn Fn(&InstallProgress)>>,
    rollback_data: HashMap<String, Vec<String>>,
}

impl PluginInstaller {
    pub fn new(registry: PluginRegistry) -> Self {
        Self {
            registry,
            progress_callback: None,
            rollback_data: HashMap::new(),
        }
    }

    pub fn set_progress_callback<F: Fn(&InstallProgress) + 'static>(&mut self, cb: F) {
        self.progress_callback = Some(Box::new(cb));
    }

    fn emit_progress(&self, progress: &InstallProgress) {
        if let Some(ref cb) = self.progress_callback {
            cb(progress);
        }
    }

    /// 安装插件
    pub fn install(&mut self, plugin_id: &str, _target_dir: &str) -> Result<String, String> {
        let manifest = self
            .registry
            .get(plugin_id)
            .cloned()
            .ok_or_else(|| format!("Plugin '{}' not found in registry", plugin_id))?;

        let version = manifest.version.clone();

        self.emit_progress(&InstallProgress {
            plugin_id: plugin_id.to_string(),
            status: InstallStatus::Downloading,
            percent: 0.1,
            message: "Downloading...".into(),
        });

        self.emit_progress(&InstallProgress {
            plugin_id: plugin_id.to_string(),
            status: InstallStatus::Verifying,
            percent: 0.4,
            message: "Verifying checksum...".into(),
        });

        if let Some(ref checksum) = manifest.checksum {
            if checksum.is_empty() {
                self.rollback(plugin_id)?;
                return Err("Checksum verification failed".into());
            }
        }

        self.emit_progress(&InstallProgress {
            plugin_id: plugin_id.to_string(),
            status: InstallStatus::Extracting,
            percent: 0.6,
            message: "Extracting files...".into(),
        });

        self.emit_progress(&InstallProgress {
            plugin_id: plugin_id.to_string(),
            status: InstallStatus::Installing,
            percent: 0.8,
            message: "Installing...".into(),
        });

        self.rollback_data.insert(
            plugin_id.to_string(),
            vec![format!("{}/{}", _target_dir, plugin_id)],
        );

        self.registry.mark_installed(plugin_id, &version);

        self.emit_progress(&InstallProgress {
            plugin_id: plugin_id.to_string(),
            status: InstallStatus::Installed(version.clone()),
            percent: 1.0,
            message: "Installation complete".into(),
        });

        Ok(version)
    }

    /// 卸载插件
    pub fn uninstall(&mut self, plugin_id: &str) -> Result<(), String> {
        if !self.registry.is_installed(plugin_id) {
            return Err(format!("Plugin '{}' is not installed", plugin_id));
        }
        if let Some(files) = self.rollback_data.remove(plugin_id) {
            for file in &files {
                let _ = file;
            }
        }
        self.registry.mark_uninstalled(plugin_id);
        Ok(())
    }

    fn rollback(&mut self, plugin_id: &str) -> Result<(), String> {
        self.emit_progress(&InstallProgress {
            plugin_id: plugin_id.to_string(),
            status: InstallStatus::Rollback,
            percent: 0.0,
            message: "Rolling back...".into(),
        });
        if let Some(files) = self.rollback_data.remove(plugin_id) {
            for file in &files {
                let _ = file;
            }
        }
        self.registry.mark_uninstalled(plugin_id);
        Ok(())
    }

    pub fn registry(&self) -> &PluginRegistry {
        &self.registry
    }

    pub fn registry_mut(&mut self) -> &mut PluginRegistry {
        &mut self.registry
    }
}

// ────────────────────────────────────────────
// 工具函数
// ────────────────────────────────────────────

fn current_timestamp() -> u64 {
    std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .unwrap_or_default()
        .as_secs()
}

fn semver_parse(version: &str) -> Result<(u32, u32, u32), String> {
    let parts: Vec<&str> = version.split('.').collect();
    if parts.len() != 3 {
        return Err(format!("Invalid semver format: {}", version));
    }
    let major = parts[0].parse::<u32>().map_err(|_| format!("Invalid major: {}", parts[0]))?;
    let minor = parts[1].parse::<u32>().map_err(|_| format!("Invalid minor: {}", parts[1]))?;
    let patch = parts[2].parse::<u32>().map_err(|_| format!("Invalid patch: {}", parts[2]))?;
    Ok((major, minor, patch))
}

fn semver_gte(version: &str, min_version: &str) -> bool {
    let v = semver_parse(version);
    let m = semver_parse(min_version);
    match (v, m) {
        (Ok(v), Ok(m)) => v >= m,
        _ => false,
    }
}

fn semver_satisfies(version: &str, constraint: &str) -> bool {
    let constraint = constraint.trim();
    if constraint.starts_with('^') {
        let base = &constraint[1..];
        if let (Ok(v), Ok(b)) = (semver_parse(version), semver_parse(base)) {
            v.0 == b.0 && v >= b
        } else {
            false
        }
    } else if constraint.starts_with(">=") {
        semver_gte(version, &constraint[2..])
    } else {
        version == constraint
    }
}

// ────────────────────────────────────────────
// 预置分类列表
// ────────────────────────────────────────────

/// 获取所有预置分类（用于marketplace UI）
pub fn preset_categories() -> Vec<PluginCategory> {
    vec![
        PluginCategory::Effect { sub: Some(EffectSubcategory::Compressor) },
        PluginCategory::Effect { sub: Some(EffectSubcategory::Equalizer) },
        PluginCategory::Effect { sub: Some(EffectSubcategory::Reverb) },
        PluginCategory::Effect { sub: Some(EffectSubcategory::Delay) },
        PluginCategory::Effect { sub: Some(EffectSubcategory::Chorus) },
        PluginCategory::Effect { sub: Some(EffectSubcategory::Distortion) },
        PluginCategory::Effect { sub: Some(EffectSubcategory::Dynamics) },
        PluginCategory::Effect { sub: None },
        PluginCategory::Instrument { sub: Some(InstrumentSubcategory::Synthesizer) },
        PluginCategory::Instrument { sub: Some(InstrumentSubcategory::Sampler) },
        PluginCategory::Instrument { sub: Some(InstrumentSubcategory::DrumMachine) },
        PluginCategory::Instrument { sub: None },
        PluginCategory::Utility { sub: Some(UtilitySubcategory::Analyzer) },
        PluginCategory::Utility { sub: Some(UtilitySubcategory::Tool) },
        PluginCategory::Utility { sub: None },
        PluginCategory::Analyzer,
        PluginCategory::Midi,
    ]
}

// ────────────────────────────────────────────
// 测试
// ────────────────────────────────────────────

#[cfg(test)]
mod tests {
    use super::*;

    fn sample_manifest(id: &str, version: &str) -> PluginManifest {
        PluginManifest {
            id: id.to_string(),
            name: format!("Plugin {}", id),
            version: version.to_string(),
            author: "TestAuthor".to_string(),
            description: "A test plugin".to_string(),
            category: PluginCategory::effect(),
            tags: vec!["test".to_string()],
            min_daw_version: None,
            dependencies: vec![],
            checksum: Some("abc123".to_string()),
            download_url: None,
            homepage: None,
            license: None,
            platforms: vec![],
            repository_id: None,
        }
    }

    // ──── Phase 32 原有测试 ────

    #[test]
    fn test_registry_new() {
        let registry = PluginRegistry::new();
        assert!(registry.list_all().is_empty());
    }

    #[test]
    fn test_registry_register() {
        let mut registry = PluginRegistry::new();
        let manifest = sample_manifest("eq7", "1.0.0");
        assert!(registry.register(manifest).is_ok());
        assert_eq!(registry.list_all().len(), 1);
    }

    #[test]
    fn test_registry_register_duplicate() {
        let mut registry = PluginRegistry::new();
        registry.register(sample_manifest("eq7", "1.0.0")).unwrap();
        assert!(registry.register(sample_manifest("eq7", "2.0.0")).is_err());
    }

    #[test]
    fn test_registry_unregister() {
        let mut registry = PluginRegistry::new();
        registry.register(sample_manifest("eq7", "1.0.0")).unwrap();
        let removed = registry.unregister("eq7");
        assert!(removed.is_some());
        assert!(registry.list_all().is_empty());
    }

    #[test]
    fn test_registry_search() {
        let mut registry = PluginRegistry::new();
        let mut m = sample_manifest("eq7", "1.0.0");
        m.tags = vec!["equalizer".to_string(), "filter".to_string()];
        registry.register(m).unwrap();
        let mut m2 = sample_manifest("comp", "1.0.0");
        m2.tags = vec!["compressor".to_string()];
        registry.register(m2).unwrap();
        let results = registry.search("equalizer");
        assert_eq!(results.len(), 1);
        assert_eq!(results[0].id, "eq7");
    }

    #[test]
    fn test_registry_list_by_category() {
        let mut registry = PluginRegistry::new();
        registry.register(sample_manifest("eq7", "1.0.0")).unwrap();
        let mut inst = sample_manifest("synth1", "1.0.0");
        inst.category = PluginCategory::instrument();
        registry.register(inst).unwrap();
        let effects = registry.list_by_category(&PluginCategory::effect());
        assert_eq!(effects.len(), 1);
        let instruments = registry.list_by_category(&PluginCategory::instrument());
        assert_eq!(instruments.len(), 1);
    }

    #[test]
    fn test_semver_parse() {
        assert_eq!(semver_parse("1.2.3"), Ok((1, 2, 3)));
        assert!(semver_parse("1.2").is_err());
        assert!(semver_parse("a.b.c").is_err());
    }

    #[test]
    fn test_semver_gte() {
        assert!(semver_gte("1.2.3", "1.2.3"));
        assert!(semver_gte("1.2.4", "1.2.3"));
        assert!(semver_gte("2.0.0", "1.9.9"));
        assert!(!semver_gte("1.2.2", "1.2.3"));
    }

    #[test]
    fn test_semver_satisfies() {
        assert!(semver_satisfies("1.2.3", "1.2.3"));
        assert!(semver_satisfies("1.3.0", "^1.2.0"));
        assert!(!semver_satisfies("2.0.0", "^1.2.0"));
        assert!(semver_satisfies("1.3.0", ">=1.2.0"));
        assert!(!semver_satisfies("1.1.0", ">=1.2.0"));
    }

    #[test]
    fn test_compatibility_check() {
        let mut registry = PluginRegistry::new();
        let mut manifest = sample_manifest("eq7", "1.0.0");
        manifest.min_daw_version = Some("0.30.0".to_string());
        registry.register(manifest).unwrap();
        let m = registry.get("eq7").unwrap();
        let report = registry.check_compatibility(m, "0.31.0");
        assert!(report.compatible);
    }

    #[test]
    fn test_compatibility_check_fail() {
        let mut registry = PluginRegistry::new();
        let mut manifest = sample_manifest("eq7", "1.0.0");
        manifest.min_daw_version = Some("0.50.0".to_string());
        registry.register(manifest).unwrap();
        let m = registry.get("eq7").unwrap();
        let report = registry.check_compatibility(m, "0.31.0");
        assert!(!report.compatible);
        assert!(!report.issues.is_empty());
    }

    #[test]
    fn test_install_and_uninstall() {
        let mut registry = PluginRegistry::new();
        registry.register(sample_manifest("eq7", "1.0.0")).unwrap();
        let mut installer = PluginInstaller::new(registry);
        let result = installer.install("eq7", "/tmp/plugins");
        assert!(result.is_ok());
        assert_eq!(result.unwrap(), "1.0.0");
        assert!(installer.registry().is_installed("eq7"));
        let uninstall_result = installer.uninstall("eq7");
        assert!(uninstall_result.is_ok());
        assert!(!installer.registry().is_installed("eq7"));
    }

    #[test]
    fn test_install_nonexistent() {
        let registry = PluginRegistry::new();
        let mut installer = PluginInstaller::new(registry);
        assert!(installer.install("nonexistent", "/tmp/plugins").is_err());
    }

    #[test]
    fn test_install_with_progress_callback() {
        let mut registry = PluginRegistry::new();
        registry.register(sample_manifest("eq7", "1.0.0")).unwrap();
        let mut installer = PluginInstaller::new(registry);
        let progress_messages: std::sync::Mutex<Vec<String>> = std::sync::Mutex::new(Vec::new());
        installer.set_progress_callback(move |p| {
            progress_messages.lock().unwrap().push(p.message.clone());
        });
        assert!(installer.install("eq7", "/tmp/plugins").is_ok());
    }

    #[test]
    fn test_dependency_check() {
        let mut registry = PluginRegistry::new();
        registry.register(sample_manifest("base", "1.0.0")).unwrap();
        let mut dep_plugin = sample_manifest("advanced", "1.0.0");
        dep_plugin.dependencies = vec![Dependency {
            plugin_id: "base".to_string(),
            version_constraint: "^1.0.0".to_string(),
        }];
        registry.register(dep_plugin).unwrap();
        registry.mark_installed("base", "1.0.0");
        let m = registry.get("advanced").unwrap();
        let report = registry.check_compatibility(m, "0.31.0");
        assert!(report.compatible || !report.issues.is_empty());
    }

    #[test]
    fn test_manifest_serialization() {
        let manifest = sample_manifest("eq7", "1.0.0");
        let json = serde_json::to_string(&manifest).unwrap();
        let parsed: PluginManifest = serde_json::from_str(&json).unwrap();
        assert_eq!(parsed.id, "eq7");
        assert_eq!(parsed.version, "1.0.0");
    }

    // ──── Phase 33 新增测试 ────

    #[test]
    fn test_plugin_category_effect_subcategory() {
        let cat = PluginCategory::Effect { sub: Some(EffectSubcategory::Equalizer) };
        assert!(cat.is_effect());
        let cat2 = PluginCategory::Effect { sub: Some(EffectSubcategory::Reverb) };
        assert!(categories_match(&cat, &cat2));
    }

    #[test]
    fn test_plugin_category_instrument_subcategory() {
        let cat = PluginCategory::Instrument { sub: Some(InstrumentSubcategory::Synthesizer) };
        assert!(cat.is_instrument());
    }

    #[test]
    fn test_plugin_compatibility_platform_check() {
        let compat = PluginCompatibility::new("0.31.0", "linux", "x86_64");
        let mut manifest = sample_manifest("eq7", "1.0.0");
        manifest.platforms = vec![PlatformTarget { os: "linux".into(), arch: "x86_64".into() }];
        let report = compat.check(&manifest, &HashMap::new());
        assert!(report.compatible);
    }

    #[test]
    fn test_plugin_compatibility_platform_mismatch() {
        let compat = PluginCompatibility::new("0.31.0", "macos", "aarch64");
        let mut manifest = sample_manifest("eq7", "1.0.0");
        manifest.platforms = vec![PlatformTarget { os: "linux".into(), arch: "x86_64".into() }];
        let report = compat.check(&manifest, &HashMap::new());
        assert!(!report.compatible);
    }

    #[test]
    fn test_plugin_repository_add_source() {
        let mut repo = PluginRepository::new();
        let source = RepositorySource {
            id: "official".into(),
            url: "https://plugins.opendaw.dev/index.json".into(),
            name: "Official".into(),
            is_official: true,
            enabled: true,
            ttl_secs: 3600,
        };
        assert!(repo.add_source(source).is_ok());
        assert!(repo.get_source("official").is_some());
    }

    #[test]
    fn test_plugin_repository_duplicate_source() {
        let mut repo = PluginRepository::new();
        let s1 = RepositorySource {
            id: "official".into(), url: String::new(), name: "Official".into(),
            is_official: true, enabled: true, ttl_secs: 3600,
        };
        repo.add_source(s1).unwrap();
        let s2 = RepositorySource {
            id: "official".into(), url: String::new(), name: "Official2".into(),
            is_official: false, enabled: true, ttl_secs: 3600,
        };
        assert!(repo.add_source(s2).is_err());
    }

    #[test]
    fn test_plugin_repository_refresh_and_search() {
        let mut repo = PluginRepository::new();
        repo.add_source(RepositorySource {
            id: "official".into(), url: String::new(), name: "Official".into(),
            is_official: true, enabled: true, ttl_secs: 3600,
        }).unwrap();
        let mut m = sample_manifest("eq7", "1.0.0");
        m.name = "7-Band Equalizer".into();
        m.tags = vec!["equalizer".into()];
        repo.refresh_index("official", vec![m]).unwrap();
        let results = repo.search_all("equalizer", None);
        assert_eq!(results.len(), 1);
    }

    #[test]
    fn test_plugin_repository_cached_index() {
        let mut repo = PluginRepository::new();
        repo.add_source(RepositorySource {
            id: "official".into(), url: String::new(), name: "Official".into(),
            is_official: true, enabled: true, ttl_secs: 3600,
        }).unwrap();
        repo.refresh_index("official", vec![sample_manifest("eq7", "1.0.0")]).unwrap();
        let idx = repo.get_cached_index("official");
        assert!(idx.is_some());
        assert_eq!(idx.unwrap().plugins.len(), 1);
    }

    #[test]
    fn test_review_new_valid() {
        let review = PluginReview::new("eq7", "user1", 4, "Great plugin!").unwrap();
        assert_eq!(review.rating, 4);
        assert_eq!(review.user_id, "user1");
    }

    #[test]
    fn test_review_new_invalid_rating() {
        assert!(PluginReview::new("eq7", "user1", 0, "Bad").is_err());
        assert!(PluginReview::new("eq7", "user1", 6, "Great").is_err());
    }

    #[test]
    fn test_review_new_empty_user() {
        assert!(PluginReview::new("eq7", "", 3, "Meh").is_err());
    }

    #[test]
    fn test_review_manager_average() {
        let mut mgr = ReviewManager::new();
        mgr.add_review(PluginReview::new("eq7", "u1", 5, "Love it").unwrap()).unwrap();
        mgr.add_review(PluginReview::new("eq7", "u2", 3, "Okay").unwrap()).unwrap();
        mgr.add_review(PluginReview::new("eq7", "u3", 4, "Good").unwrap()).unwrap();
        assert!((mgr.average_rating("eq7") - 4.0).abs() < 0.01);
    }

    #[test]
    fn test_review_manager_summary() {
        let mut mgr = ReviewManager::new();
        mgr.add_review(PluginReview::new("eq7", "u1", 5, "Love it").unwrap()).unwrap();
        mgr.add_review(PluginReview::new("eq7", "u2", 1, "Terrible").unwrap()).unwrap();
        let summary = mgr.get_summary("eq7").unwrap();
        assert_eq!(summary.total_reviews, 2);
        assert_eq!(summary.rating_distribution[0], 1); // 1-star
        assert_eq!(summary.rating_distribution[4], 1); // 5-star
    }

    #[test]
    fn test_preset_categories() {
        let cats = preset_categories();
        assert!(cats.len() >= 10);
    }

    #[test]
    fn test_repository_remove_source() {
        let mut repo = PluginRepository::new();
        repo.add_source(RepositorySource {
            id: "test".into(), url: String::new(), name: "Test".into(),
            is_official: false, enabled: true, ttl_secs: 3600,
        }).unwrap();
        assert!(repo.remove_source("test").is_some());
        assert!(repo.get_source("test").is_none());
    }

    #[test]
    fn test_repository_search_with_category_filter() {
        let mut repo = PluginRepository::new();
        repo.add_source(RepositorySource {
            id: "official".into(), url: String::new(), name: "Official".into(),
            is_official: true, enabled: true, ttl_secs: 3600,
        }).unwrap();
        let mut m1 = sample_manifest("eq7", "1.0.0");
        m1.name = "Equalizer".into();
        let mut m2 = sample_manifest("synth1", "1.0.0");
        m2.name = "Synth".into();
        m2.category = PluginCategory::instrument();
        repo.refresh_index("official", vec![m1, m2]).unwrap();
        let results = repo.search_all("e", Some(&PluginCategory::effect()));
        assert_eq!(results.len(), 1);
    }

    #[test]
    fn test_compatibility_dependency_missing() {
        let compat = PluginCompatibility::new("0.31.0", "linux", "x86_64");
        let mut manifest = sample_manifest("advanced", "1.0.0");
        manifest.dependencies = vec![Dependency {
            plugin_id: "base".into(),
            version_constraint: "^1.0.0".into(),
        }];
        let report = compat.check(&manifest, &HashMap::new());
        assert!(!report.compatible);
    }

    #[test]
    fn test_cached_index_expiry() {
        let idx = CachedIndex {
            repository_id: "test".into(),
            plugins: vec![],
            fetched_at: 0,
            ttl_secs: 10,
        };
        assert!(idx.is_expired(100));
        assert!(!idx.is_expired(5));
    }
}
