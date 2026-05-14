//! 应用状态 — 共享项目/引擎实例
//! BUG修复: BUG-DAW-003 预注册内置插件

use crate::models::{Project, ProjectInfo};
use opendaw_core::{
    EffectSubcategory, InstrumentSubcategory, PluginCategory, PluginCompatibility, PluginManifest,
    PluginRegistry, PluginRepository, RepositorySource, ReviewManager, UtilitySubcategory,
};
use std::collections::HashMap;
use std::sync::Arc;
use tokio::sync::RwLock;
use uuid::Uuid;

/// 应用共享状态
#[derive(Clone, Debug)]
pub struct AppState {
    pub projects: Arc<RwLock<HashMap<Uuid, Project>>>,
    pub render_tasks: Arc<RwLock<HashMap<Uuid, RenderTask>>>,
    /// Phase 33: Marketplace 状态
    pub marketplace: Arc<RwLock<MarketplaceState>>,
}

/// 渲染任务状态
#[derive(Clone, Debug, serde::Serialize, serde::Deserialize)]
pub struct RenderTask {
    pub project_id: Uuid,
    pub status: RenderStatus,
    pub progress: f32,
    pub output_path: Option<String>,
    pub error: Option<String>,
}

/// 渲染状态枚举
#[derive(Clone, Debug, PartialEq, serde::Serialize, serde::Deserialize)]
pub enum RenderStatus {
    Pending,
    Running,
    Completed,
    Failed,
}

/// Phase 33: Marketplace 聚合状态
#[derive(Debug)]
pub struct MarketplaceState {
    pub registry: PluginRegistry,
    pub repository: PluginRepository,
    pub reviews: ReviewManager,
    pub compatibility: PluginCompatibility,
}

impl MarketplaceState {
    pub fn new() -> Self {
        Self {
            registry: PluginRegistry::new(),
            repository: PluginRepository::new(),
            reviews: ReviewManager::new(),
            compatibility: PluginCompatibility::new("0.31.0", "linux", "x86_64"),
        }
    }
}

/// 预注册内置插件 (BUG-DAW-003修复)
fn register_builtin_plugins(registry: &mut PluginRegistry) {
    // 内置效果器
    let builtin_effects = vec![
        PluginManifest {
            id: "builtin-eq7".into(),
            name: "7-Band Equalizer".into(),
            version: "1.0.0".into(),
            author: "OpenDAW Team".into(),
            description: "Professional 7-band parametric EQ with visual feedback".into(),
            category: PluginCategory::Effect { sub: Some(EffectSubcategory::Equalizer) },
            tags: vec!["eq".into(), "equalizer".into(), "frequency".into()],
            min_daw_version: Some("1.0.0".into()),
            dependencies: vec![],
            checksum: None,
            download_url: None,
            homepage: None,
            license: Some("MIT".into()),
            platforms: vec![opendaw_core::PlatformTarget {
                os: "linux".into(),
                arch: "x86_64".into(),
            }],
            repository_id: Some("builtin".into()),
        },
        PluginManifest {
            id: "builtin-compressor".into(),
            name: "Dynamic Compressor".into(),
            version: "1.0.0".into(),
            author: "OpenDAW Team".into(),
            description: "Studio-quality dynamics processor with attack, release, ratio and threshold controls".into(),
            category: PluginCategory::Effect { sub: Some(EffectSubcategory::Dynamics) },
            tags: vec!["compressor".into(), "dynamics".into(), "limiter".into()],
            min_daw_version: Some("1.0.0".into()),
            dependencies: vec![],
            checksum: None,
            download_url: None,
            homepage: None,
            license: Some("MIT".into()),
            platforms: vec![opendaw_core::PlatformTarget {
                os: "linux".into(),
                arch: "x86_64".into(),
            }],
            repository_id: Some("builtin".into()),
        },
        PluginManifest {
            id: "builtin-reverb".into(),
            name: "Hall Reverb".into(),
            version: "1.0.0".into(),
            author: "OpenDAW Team".into(),
            description: "Convolver-based reverb with hall, room and plate presets".into(),
            category: PluginCategory::Effect { sub: Some(EffectSubcategory::Reverb) },
            tags: vec!["reverb".into(), "hall".into(), "room".into(), "ambience".into()],
            min_daw_version: Some("1.0.0".into()),
            dependencies: vec![],
            checksum: None,
            download_url: None,
            homepage: None,
            license: Some("MIT".into()),
            platforms: vec![opendaw_core::PlatformTarget {
                os: "linux".into(),
                arch: "x86_64".into(),
            }],
            repository_id: Some("builtin".into()),
        },
        PluginManifest {
            id: "builtin-delay".into(),
            name: "Echo Delay".into(),
            version: "1.0.0".into(),
            author: "OpenDAW Team".into(),
            description: "Tempo-synced delay with ping-pong mode".into(),
            category: PluginCategory::Effect { sub: Some(EffectSubcategory::Delay) },
            tags: vec!["delay".into(), "echo".into(), "tempo".into()],
            min_daw_version: Some("1.0.0".into()),
            dependencies: vec![],
            checksum: None,
            download_url: None,
            homepage: None,
            license: Some("MIT".into()),
            platforms: vec![opendaw_core::PlatformTarget {
                os: "linux".into(),
                arch: "x86_64".into(),
            }],
            repository_id: Some("builtin".into()),
        },
        PluginManifest {
            id: "builtin-chorus".into(),
            name: "Chorus/Flanger".into(),
            version: "1.0.0".into(),
            author: "OpenDAW Team".into(),
            description: "Modulation effect combining chorus and flanger".into(),
            category: PluginCategory::Effect { sub: Some(EffectSubcategory::Chorus) },
            tags: vec!["chorus".into(), "flanger".into(), "modulation".into()],
            min_daw_version: Some("1.0.0".into()),
            dependencies: vec![],
            checksum: None,
            download_url: None,
            homepage: None,
            license: Some("MIT".into()),
            platforms: vec![opendaw_core::PlatformTarget {
                os: "linux".into(),
                arch: "x86_64".into(),
            }],
            repository_id: Some("builtin".into()),
        },
        PluginManifest {
            id: "builtin-distortion".into(),
            name: "Distortion/Overdrive".into(),
            version: "1.0.0".into(),
            author: "OpenDAW Team".into(),
            description: "Classic guitar distortion and overdrive simulation".into(),
            category: PluginCategory::Effect { sub: Some(EffectSubcategory::Distortion) },
            tags: vec!["distortion".into(), "overdrive".into(), "saturation".into()],
            min_daw_version: Some("1.0.0".into()),
            dependencies: vec![],
            checksum: None,
            download_url: None,
            homepage: None,
            license: Some("MIT".into()),
            platforms: vec![opendaw_core::PlatformTarget {
                os: "linux".into(),
                arch: "x86_64".into(),
            }],
            repository_id: Some("builtin".into()),
        },
    ];

    // 内置乐器
    let builtin_instruments = vec![
        PluginManifest {
            id: "builtin-synth".into(),
            name: "Poly Synth".into(),
            version: "1.0.0".into(),
            author: "OpenDAW Team".into(),
            description: "8-voice polyphonic synthesizer with oscillators and filters".into(),
            category: PluginCategory::Instrument {
                sub: Some(InstrumentSubcategory::Synthesizer),
            },
            tags: vec!["synth".into(), "synthesizer".into(), "polyphonic".into()],
            min_daw_version: Some("1.0.0".into()),
            dependencies: vec![],
            checksum: None,
            download_url: None,
            homepage: None,
            license: Some("MIT".into()),
            platforms: vec![opendaw_core::PlatformTarget {
                os: "linux".into(),
                arch: "x86_64".into(),
            }],
            repository_id: Some("builtin".into()),
        },
        PluginManifest {
            id: "builtin-sampler".into(),
            name: "Sample Player".into(),
            version: "1.0.0".into(),
            author: "OpenDAW Team".into(),
            description: "Multi-layer sampler with ADSR envelope".into(),
            category: PluginCategory::Instrument {
                sub: Some(InstrumentSubcategory::Sampler),
            },
            tags: vec!["sampler".into(), "sample".into(), "drum".into()],
            min_daw_version: Some("1.0.0".into()),
            dependencies: vec![],
            checksum: None,
            download_url: None,
            homepage: None,
            license: Some("MIT".into()),
            platforms: vec![opendaw_core::PlatformTarget {
                os: "linux".into(),
                arch: "x86_64".into(),
            }],
            repository_id: Some("builtin".into()),
        },
        PluginManifest {
            id: "builtin-drums".into(),
            name: "Drum Machine".into(),
            version: "1.0.0".into(),
            author: "OpenDAW Team".into(),
            description: "16-pad drum machine with step sequencer".into(),
            category: PluginCategory::Instrument {
                sub: Some(InstrumentSubcategory::DrumMachine),
            },
            tags: vec!["drums".into(), "drum machine".into(), "beats".into()],
            min_daw_version: Some("1.0.0".into()),
            dependencies: vec![],
            checksum: None,
            download_url: None,
            homepage: None,
            license: Some("MIT".into()),
            platforms: vec![opendaw_core::PlatformTarget {
                os: "linux".into(),
                arch: "x86_64".into(),
            }],
            repository_id: Some("builtin".into()),
        },
    ];

    // 内置工具
    let builtin_utilities = vec![
        PluginManifest {
            id: "builtin-gain".into(),
            name: "Gain/Pan".into(),
            version: "1.0.0".into(),
            author: "OpenDAW Team".into(),
            description: "Volume control with pan and mute".into(),
            category: PluginCategory::Utility {
                sub: Some(UtilitySubcategory::Tool),
            },
            tags: vec!["gain".into(), "volume".into(), "pan".into(), "mute".into()],
            min_daw_version: Some("1.0.0".into()),
            dependencies: vec![],
            checksum: None,
            download_url: None,
            homepage: None,
            license: Some("MIT".into()),
            platforms: vec![opendaw_core::PlatformTarget {
                os: "linux".into(),
                arch: "x86_64".into(),
            }],
            repository_id: Some("builtin".into()),
        },
        PluginManifest {
            id: "builtin-analyzer".into(),
            name: "Spectrum Analyzer".into(),
            version: "1.0.0".into(),
            author: "OpenDAW Team".into(),
            description: "Real-time FFT spectrum analyzer".into(),
            category: PluginCategory::Utility {
                sub: Some(UtilitySubcategory::Analyzer),
            },
            tags: vec![
                "analyzer".into(),
                "spectrum".into(),
                "fft".into(),
                "visualization".into(),
            ],
            min_daw_version: Some("1.0.0".into()),
            dependencies: vec![],
            checksum: None,
            download_url: None,
            homepage: None,
            license: Some("MIT".into()),
            platforms: vec![opendaw_core::PlatformTarget {
                os: "linux".into(),
                arch: "x86_64".into(),
            }],
            repository_id: Some("builtin".into()),
        },
    ];

    // 注册所有内置插件
    for plugin in builtin_effects {
        let _ = registry.register(plugin);
    }
    for plugin in builtin_instruments {
        let _ = registry.register(plugin);
    }
    for plugin in builtin_utilities {
        let _ = registry.register(plugin);
    }
}

impl AppState {
    pub fn new() -> Self {
        let mut marketplace = MarketplaceState::new();

        // 预注册内置插件 (BUG-DAW-003修复)
        register_builtin_plugins(&mut marketplace.registry);

        // 预注册官方仓库
        let _ = marketplace.repository.add_source(RepositorySource {
            id: "official".into(),
            url: "https://plugins.opendaw.dev/index.json".into(),
            name: "OpenDAW Official".into(),
            is_official: true,
            enabled: true,
            ttl_secs: 3600,
        });

        Self {
            projects: Arc::new(RwLock::new(HashMap::new())),
            render_tasks: Arc::new(RwLock::new(HashMap::new())),
            marketplace: Arc::new(RwLock::new(marketplace)),
        }
    }

    /// 列出所有项目信息
    pub async fn list_projects(&self) -> Vec<ProjectInfo> {
        let projects = self.projects.read().await;
        projects
            .values()
            .map(|p| ProjectInfo {
                id: p.id,
                name: p.name.clone(),
                description: p.description.clone(),
                created_at: p.created_at.clone(),
                updated_at: p.updated_at.clone(),
                track_count: p.tracks.len(),
            })
            .collect()
    }

    /// 获取单个项目
    pub async fn get_project(&self, id: Uuid) -> Option<Project> {
        let projects = self.projects.read().await;
        projects.get(&id).cloned()
    }

    /// 创建项目
    pub async fn create_project(&self, name: String, description: Option<String>) -> Project {
        let project = Project::new(name, description);
        let id = project.id;
        let mut projects = self.projects.write().await;
        projects.insert(id, project.clone());
        project
    }

    /// 更新项目
    pub async fn update_project(
        &self,
        id: Uuid,
        name: Option<String>,
        description: Option<String>,
    ) -> Option<Project> {
        let mut projects = self.projects.write().await;
        if let Some(project) = projects.get_mut(&id) {
            if let Some(n) = name {
                project.name = n;
            }
            if let Some(d) = description {
                project.description = Some(d);
            }
            project.updated_at = chrono::Utc::now().to_rfc3339();
            let updated = project.clone();
            Some(updated)
        } else {
            None
        }
    }

    /// 删除项目
    pub async fn delete_project(&self, id: Uuid) -> bool {
        let mut projects = self.projects.write().await;
        projects.remove(&id).is_some()
    }

    /// 创建渲染任务
    pub async fn create_render_task(&self, project_id: Uuid) -> RenderTask {
        let task = RenderTask {
            project_id,
            status: RenderStatus::Pending,
            progress: 0.0,
            output_path: None,
            error: None,
        };
        let mut tasks = self.render_tasks.write().await;
        tasks.insert(project_id, task.clone());
        task
    }

    /// 获取渲染任务
    pub async fn get_render_task(&self, project_id: Uuid) -> Option<RenderTask> {
        let tasks = self.render_tasks.read().await;
        tasks.get(&project_id).cloned()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[tokio::test]
    async fn test_app_state_new() {
        let state = AppState::new();
        let projects = state.projects.read().await;
        assert!(projects.is_empty());
    }

    #[tokio::test]
    async fn test_create_project() {
        let state = AppState::new();
        let project = state
            .create_project("Test Project".into(), Some("A test".into()))
            .await;
        assert_eq!(project.name, "Test Project");
        assert_eq!(project.description, Some("A test".into()));
    }

    #[tokio::test]
    async fn test_list_projects() {
        let state = AppState::new();
        state.create_project("P1".into(), None).await;
        state.create_project("P2".into(), None).await;
        let list = state.list_projects().await;
        assert_eq!(list.len(), 2);
    }

    #[tokio::test]
    async fn test_get_project() {
        let state = AppState::new();
        let created = state.create_project("MyProject".into(), None).await;
        let fetched = state.get_project(created.id).await;
        assert!(fetched.is_some());
        assert_eq!(fetched.unwrap().name, "MyProject");
    }

    #[tokio::test]
    async fn test_update_project() {
        let state = AppState::new();
        let created = state.create_project("Old".into(), None).await;
        let updated = state
            .update_project(created.id, Some("New".into()), Some("Desc".into()))
            .await;
        assert!(updated.is_some());
        assert_eq!(updated.unwrap().name, "New");
    }

    #[tokio::test]
    async fn test_delete_project() {
        let state = AppState::new();
        let created = state.create_project("ToDelete".into(), None).await;
        assert!(state.delete_project(created.id).await);
        assert!(!state.delete_project(created.id).await);
    }

    #[tokio::test]
    async fn test_render_task() {
        let state = AppState::new();
        let id = Uuid::new_v4();
        let task = state.create_render_task(id).await;
        assert_eq!(task.project_id, id);
        assert_eq!(task.status, RenderStatus::Pending);
    }

    #[tokio::test]
    async fn test_get_render_task() {
        let state = AppState::new();
        let id = Uuid::new_v4();
        state.create_render_task(id).await;
        let fetched = state.get_render_task(id).await;
        assert!(fetched.is_some());
    }

    #[tokio::test]
    async fn test_get_nonexistent_project() {
        let state = AppState::new();
        let result = state.get_project(Uuid::new_v4()).await;
        assert!(result.is_none());
    }

    #[tokio::test]
    async fn test_update_nonexistent_project() {
        let state = AppState::new();
        let result = state
            .update_project(Uuid::new_v4(), Some("X".into()), None)
            .await;
        assert!(result.is_none());
    }

    #[tokio::test]
    async fn test_marketplace_state_initialized() {
        let state = AppState::new();
        let mp = state.marketplace.read().await;
        let sources = mp.repository.list_sources();
        assert!(!sources.is_empty());
    }

    #[tokio::test]
    async fn test_builtin_plugins_registered() {
        // BUG-DAW-003 测试：验证内置插件已注册
        let state = AppState::new();
        let mp = state.marketplace.read().await;
        let plugins = mp.registry.list_all();

        // 应该至少有内置插件
        assert!(!plugins.is_empty(), "Builtin plugins should be registered");

        // 验证特定插件存在
        let eq7 = mp.registry.get("builtin-eq7");
        assert!(eq7.is_some(), "builtin-eq7 should exist");

        let synth = mp.registry.get("builtin-synth");
        assert!(synth.is_some(), "builtin-synth should exist");
    }
}

// ──── 文件上传：数据目录管理 ────

impl AppState {
    /// 获取项目数据目录路径
    /// 优先级：环境变量 OPENDAW_DATA_DIR > ~/.opendaw/data
    pub fn get_data_dir(&self) -> std::path::PathBuf {
        if let Ok(dir) = std::env::var("OPENDAW_DATA_DIR") {
            let path = std::path::PathBuf::from(dir);
            if path.exists() {
                return path;
            }
        }

        // 默认路径：~/.opendaw/data
        let home = std::env::var("HOME").unwrap_or_else(|_| ".".to_string());
        std::path::PathBuf::from(home).join(".opendaw/data")
    }

    /// 确保项目音频目录存在
    pub fn ensure_audio_dir(&self, project_id: Uuid, track_id: Uuid) -> std::path::PathBuf {
        let data_dir = self.get_data_dir();
        let audio_dir = data_dir
            .join("projects")
            .join(project_id.to_string())
            .join("audio")
            .join(track_id.to_string());

        // 创建目录（如果不存在）
        if !audio_dir.exists() {
            if let Err(e) = std::fs::create_dir_all(&audio_dir) {
                tracing::warn!("Failed to create audio dir: {}", e);
            }
        }

        audio_dir
    }

    /// 获取项目导入目录
    pub fn get_import_dir(&self) -> std::path::PathBuf {
        let data_dir = self.get_data_dir();
        let import_dir = data_dir.join("imports");

        if !import_dir.exists() {
            if let Err(e) = std::fs::create_dir_all(&import_dir) {
                tracing::warn!("Failed to create import dir: {}", e);
            }
        }

        import_dir
    }
}
