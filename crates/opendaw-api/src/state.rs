//! 应用状态 — 共享项目/引擎实例

use crate::models::{Project, ProjectInfo};
use opendaw_core::{
    PluginRegistry, PluginRepository, RepositorySource, ReviewManager,
    PluginCompatibility, PlatformTarget,
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

impl AppState {
    pub fn new() -> Self {
        let mut marketplace = MarketplaceState::new();
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
    pub async fn update_project(&self, id: Uuid, name: Option<String>, description: Option<String>) -> Option<Project> {
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
        let project = state.create_project("Test Project".into(), Some("A test".into())).await;
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
        let updated = state.update_project(created.id, Some("New".into()), Some("Desc".into())).await;
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
        let result = state.update_project(Uuid::new_v4(), Some("X".into()), None).await;
        assert!(result.is_none());
    }

    #[tokio::test]
    async fn test_marketplace_state_initialized() {
        let state = AppState::new();
        let mp = state.marketplace.read().await;
        let sources = mp.repository.list_sources();
        assert!(!sources.is_empty());
    }
}
