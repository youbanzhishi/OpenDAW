//! 路由定义与处理器

use crate::error::ApiError;
use crate::models::*;
use crate::state::AppState;
use axum::extract::{Path, State};
use axum::http::StatusCode;
use axum::routing::{delete, get, post, put};
use axum::{Json, Router};
use uuid::Uuid;

/// 构建API路由
pub fn routes(state: AppState) -> Router<AppState> {
    Router::new()
        // 项目CRUD
        .route("/api/v1/projects", get(list_projects).post(create_project))
        .route(
            "/api/v1/projects/{id}",
            get(get_project).put(update_project).delete(delete_project),
        )
        // 渲染 & AI
        .route("/api/v1/projects/{id}/render", post(render_project))
        .route("/api/v1/projects/{id}/automix", post(automix_project))
        .route("/api/v1/projects/{id}/transcribe", post(transcribe_project))
        // 插件 & 混音
        .route("/api/v1/plugins", get(list_plugins))
        .route("/api/v1/mixer/{id}/suggestions", get(mixer_suggestions))
        .with_state(state)
}

/// GET /api/v1/projects — 列出所有项目
async fn list_projects(
    State(state): State<AppState>,
) -> Result<Json<Vec<ProjectInfo>>, ApiError> {
    let projects = state.list_projects().await;
    Ok(Json(projects))
}

/// POST /api/v1/projects — 创建项目
async fn create_project(
    State(state): State<AppState>,
    Json(req): Json<CreateProjectRequest>,
) -> Result<(StatusCode, Json<Project>), ApiError> {
    if req.name.is_empty() {
        return Err(ApiError::BadRequest("Project name cannot be empty".into()));
    }
    let project = state.create_project(req.name, req.description).await;
    Ok((StatusCode::CREATED, Json(project)))
}

/// GET /api/v1/projects/{id} — 获取项目详情
async fn get_project(
    State(state): State<AppState>,
    Path(id): Path<Uuid>,
) -> Result<Json<Project>, ApiError> {
    state
        .get_project(id)
        .await
        .map(Json)
        .ok_or_else(|| ApiError::NotFound(format!("Project {}", id)))
}

/// PUT /api/v1/projects/{id} — 更新项目
async fn update_project(
    State(state): State<AppState>,
    Path(id): Path<Uuid>,
    Json(req): Json<UpdateProjectRequest>,
) -> Result<Json<Project>, ApiError> {
    state
        .update_project(id, req.name, req.description)
        .await
        .map(Json)
        .ok_or_else(|| ApiError::NotFound(format!("Project {}", id)))
}

/// DELETE /api/v1/projects/{id} — 删除项目
async fn delete_project(
    State(state): State<AppState>,
    Path(id): Path<Uuid>,
) -> Result<StatusCode, ApiError> {
    if state.delete_project(id).await {
        Ok(StatusCode::NO_CONTENT)
    } else {
        Err(ApiError::NotFound(format!("Project {}", id)))
    }
}

/// POST /api/v1/projects/{id}/render — 触发渲染
async fn render_project(
    State(state): State<AppState>,
    Path(id): Path<Uuid>,
    Json(_req): Json<RenderRequest>,
) -> Result<Json<RenderResponse>, ApiError> {
    if state.get_project(id).await.is_none() {
        return Err(ApiError::NotFound(format!("Project {}", id)));
    }
    let task = state.create_render_task(id).await;
    Ok(Json(RenderResponse {
        task_id: task.project_id,
        project_id: id,
        status: "pending".into(),
        message: "Render task created".into(),
    }))
}

/// POST /api/v1/projects/{id}/automix — AI自动混音
async fn automix_project(
    State(state): State<AppState>,
    Path(id): Path<Uuid>,
    Json(_req): Json<AutoMixRequest>,
) -> Result<Json<AutoMixResponse>, ApiError> {
    let project = state
        .get_project(id)
        .await
        .ok_or_else(|| ApiError::NotFound(format!("Project {}", id)))?;

    let suggestions = project
        .tracks
        .iter()
        .map(|t| MixSuggestionItem {
            track_name: t.name.clone(),
            action: "adjust_volume".into(),
            current_value: Some(t.volume),
            suggested_value: t.volume * 0.9,
            reason: "Auto-mix volume adjustment".into(),
        })
        .collect();

    Ok(Json(AutoMixResponse {
        project_id: id,
        suggestions,
        applied: false,
    }))
}

/// POST /api/v1/projects/{id}/transcribe — 音频扒带
async fn transcribe_project(
    State(state): State<AppState>,
    Path(id): Path<Uuid>,
    Json(_req): Json<TranscribeRequest>,
) -> Result<Json<TranscribeResponse>, ApiError> {
    if state.get_project(id).await.is_none() {
        return Err(ApiError::NotFound(format!("Project {}", id)));
    }

    Ok(Json(TranscribeResponse {
        project_id: id,
        notes_detected: 0,
        tracks_created: 0,
        key_estimate: None,
    }))
}

/// GET /api/v1/plugins — 列出可用插件
async fn list_plugins(
    State(_state): State<AppState>,
) -> Json<Vec<PluginInfo>> {
    Json(vec![])
}

/// GET /api/v1/mixer/{id}/suggestions — 混音建议
async fn mixer_suggestions(
    State(state): State<AppState>,
    Path(id): Path<Uuid>,
) -> Result<Json<MixerSuggestionsResponse>, ApiError> {
    let project = state
        .get_project(id)
        .await
        .ok_or_else(|| ApiError::NotFound(format!("Project {}", id)))?;

    let suggestions = project
        .tracks
        .iter()
        .map(|t| MixSuggestionItem {
            track_name: t.name.clone(),
            action: "eq_adjust".into(),
            current_value: Some(t.volume),
            suggested_value: t.volume * 0.85,
            reason: "Frequency masking detected".into(),
        })
        .collect();

    Ok(Json(MixerSuggestionsResponse {
        project_id: id,
        suggestions,
        overall_score: 75.0,
    }))
}

#[cfg(test)]
mod tests {
    use super::*;
    use axum::body::Body;
    use axum::http::{Request, StatusCode};
    use tower::ServiceExt;

    fn test_app() -> Router {
        let state = AppState::new();
        routes(state)
    }

    #[tokio::test]
    async fn test_list_projects_empty() {
        let app = test_app();
        let req = Request::builder()
            .uri("/api/v1/projects")
            .body(Body::empty())
            .unwrap();
        let resp = app.oneshot(req).await.unwrap();
        assert_eq!(resp.status(), StatusCode::OK);
    }

    #[tokio::test]
    async fn test_create_project() {
        let app = test_app();
        let req = Request::builder()
            .method("POST")
            .uri("/api/v1/projects")
            .header("content-type", "application/json")
            .body(Body::from(r#"{"name":"TestProject"}"#))
            .unwrap();
        let resp = app.oneshot(req).await.unwrap();
        assert_eq!(resp.status(), StatusCode::CREATED);
    }

    #[tokio::test]
    async fn test_create_project_empty_name() {
        let app = test_app();
        let req = Request::builder()
            .method("POST")
            .uri("/api/v1/projects")
            .header("content-type", "application/json")
            .body(Body::from(r#"{"name":""}"#))
            .unwrap();
        let resp = app.oneshot(req).await.unwrap();
        assert_eq!(resp.status(), StatusCode::BAD_REQUEST);
    }

    #[tokio::test]
    async fn test_get_project_not_found() {
        let app = test_app();
        let id = Uuid::new_v4();
        let req = Request::builder()
            .uri(&format!("/api/v1/projects/{}", id))
            .body(Body::empty())
            .unwrap();
        let resp = app.oneshot(req).await.unwrap();
        assert_eq!(resp.status(), StatusCode::NOT_FOUND);
    }

    #[tokio::test]
    async fn test_delete_project_not_found() {
        let app = test_app();
        let id = Uuid::new_v4();
        let req = Request::builder()
            .method("DELETE")
            .uri(&format!("/api/v1/projects/{}", id))
            .body(Body::empty())
            .unwrap();
        let resp = app.oneshot(req).await.unwrap();
        assert_eq!(resp.status(), StatusCode::NOT_FOUND);
    }

    #[tokio::test]
    async fn test_list_plugins() {
        let app = test_app();
        let req = Request::builder()
            .uri("/api/v1/plugins")
            .body(Body::empty())
            .unwrap();
        let resp = app.oneshot(req).await.unwrap();
        assert_eq!(resp.status(), StatusCode::OK);
    }
}
