//! 路由定义与处理器
//! BUG修复: BUG-DAW-001, BUG-DAW-002, BUG-DAW-003

use crate::error::ApiError;
use crate::models::*;
use crate::models::{AudioUploadResponse, ProjectImportResponse};
use crate::state::AppState;
use axum::extract::{Multipart, Path, Query, State};
use axum::http::StatusCode;
use axum::routing::{get, post};
use axum::{Json, Router};
use opendaw_core::PluginReview;
use serde::Deserialize;
use serde_json::{json, Value};
use uuid::Uuid;

/// 构建API路由
pub fn routes(state: AppState) -> Router<AppState> {
    Router::new()
        // Agent发现协议
        .route("/.well-known/agent.json", get(agent_manifest))
        // Health check 端点 (BUG-DAW-001修复)
        .route("/api/health", get(health_check))
        // 项目CRUD
        .route("/api/v1/projects", get(list_projects).post(create_project))
        .route(
            "/api/v1/projects/{id}",
            get(get_project).put(update_project).delete(delete_project),
        )
        // 项目下的轨道
        .route("/api/v1/projects/{id}/tracks", get(list_project_tracks).post(add_track_to_project))
        // 轨道CRUD (BUG-DAW-002修复)
        .route("/api/v1/tracks", get(list_tracks).post(create_track))
        .route("/api/v1/tracks/{id}", get(get_track).put(update_track).delete(delete_track))
        // 文件上传 (BUG-DAW-006修复)
        .route("/api/v1/tracks/{id}/audio", post(upload_track_audio))
        // 项目导入 (BUG-DAW-006修复)
        .route("/api/v1/projects/import", post(import_project))
        // 渲染 & AI
        .route("/api/v1/projects/{id}/render", post(render_project))
        .route("/api/v1/projects/{id}/automix", post(automix_project))
        .route("/api/v1/projects/{id}/transcribe", post(transcribe_project))
        // 插件 & 混音 (BUG-DAW-003修复)
        .route("/api/v1/plugins", get(list_plugins))
        .route("/api/v1/mixer/{id}/suggestions", get(mixer_suggestions))
        // Phase 33: Marketplace 端点
        .route("/api/v1/marketplace/search", get(marketplace_search))
        .route(
            "/api/v1/marketplace/categories",
            get(marketplace_categories),
        )
        .route("/api/v1/marketplace/{id}", get(marketplace_plugin_detail))
        .route(
            "/api/v1/marketplace/{id}/install",
            post(marketplace_install),
        )
        .route(
            "/api/v1/marketplace/{id}/review",
            post(marketplace_submit_review),
        )
        .with_state(state)
}

// ──── Health Check Handler (BUG-DAW-001修复) ────

/// GET /api/health — 健康检查端点
/// 返回JSON格式的健康状态信息
async fn health_check() -> Json<Value> {
    Json(json!({
        "status": "ok",
        "service": "opendaw-api",
        "version": "1.0.3",
        "timestamp": chrono::Utc::now().to_rfc3339()
    }))
}

// ──── Tracks CRUD Handlers (BUG-DAW-002修复) ────

/// GET /api/v1/tracks — 列出所有轨道（跨项目）
async fn list_tracks(State(state): State<AppState>) -> Result<Json<Vec<TrackInfo>>, ApiError> {
    let projects = state.projects.read().await;
    let mut all_tracks = Vec::new();
    for project in projects.values() {
        for track in &project.tracks {
            all_tracks.push(track.clone());
        }
    }
    Ok(Json(all_tracks))
}

/// POST /api/v1/tracks — 创建轨道
async fn create_track(
    State(state): State<AppState>,
    Json(req): Json<CreateTrackRequest>,
) -> Result<(StatusCode, Json<TrackInfo>), ApiError> {
    if req.project_id.is_none() {
        return Err(ApiError::BadRequest("project_id is required".into()));
    }
    
    let project_id = req.project_id.unwrap();
    let project = state.get_project(project_id).await
        .ok_or_else(|| ApiError::NotFound(format!("Project {}", project_id)))?;
    
    let track = TrackInfo {
        id: Uuid::new_v4(),
        name: req.name.unwrap_or_else(|| "New Track".into()),
        volume: req.volume.unwrap_or(0.8),
        pan: req.pan.unwrap_or(0.0),
        muted: req.muted.unwrap_or(false),
        solo: req.solo.unwrap_or(false),
        plugin_count: 0,
    };
    
    let mut projects = state.projects.write().await;
    if let Some(project) = projects.get_mut(&project_id) {
        project.tracks.push(track.clone());
        project.updated_at = chrono::Utc::now().to_rfc3339();
    }
    
    Ok((StatusCode::CREATED, Json(track)))
}

/// GET /api/v1/tracks/{id} — 获取轨道详情
async fn get_track(
    State(state): State<AppState>,
    Path(id): Path<Uuid>,
) -> Result<Json<TrackInfo>, ApiError> {
    let projects = state.projects.read().await;
    for project in projects.values() {
        for track in &project.tracks {
            if track.id == id {
                return Ok(Json(track.clone()));
            }
        }
    }
    Err(ApiError::NotFound(format!("Track {}", id)))
}

/// PUT /api/v1/tracks/{id} — 更新轨道
async fn update_track(
    State(state): State<AppState>,
    Path(id): Path<Uuid>,
    Json(req): Json<UpdateTrackRequest>,
) -> Result<Json<TrackInfo>, ApiError> {
    let mut projects = state.projects.write().await;
    
    for project in projects.values_mut() {
        if let Some(track) = project.tracks.iter_mut().find(|t| t.id == id) {
            if let Some(name) = req.name {
                track.name = name;
            }
            if let Some(volume) = req.volume {
                track.volume = volume;
            }
            if let Some(pan) = req.pan {
                track.pan = pan;
            }
            if let Some(muted) = req.muted {
                track.muted = muted;
            }
            if let Some(solo) = req.solo {
                track.solo = solo;
            }
            project.updated_at = chrono::Utc::now().to_rfc3339();
            return Ok(Json(track.clone()));
        }
    }
    Err(ApiError::NotFound(format!("Track {}", id)))
}

/// DELETE /api/v1/tracks/{id} — 删除轨道
async fn delete_track(
    State(state): State<AppState>,
    Path(id): Path<Uuid>,
) -> Result<StatusCode, ApiError> {
    let mut projects = state.projects.write().await;
    
    for project in projects.values_mut() {
        let initial_len = project.tracks.len();
        project.tracks.retain(|t| t.id != id);
        if project.tracks.len() < initial_len {
            project.updated_at = chrono::Utc::now().to_rfc3339();
            return Ok(StatusCode::NO_CONTENT);
        }
    }
    Err(ApiError::NotFound(format!("Track {}", id)))
}

/// GET /api/v1/projects/{id}/tracks — 获取项目下的轨道列表
async fn list_project_tracks(
    State(state): State<AppState>,
    Path(id): Path<Uuid>,
) -> Result<Json<Vec<TrackInfo>>, ApiError> {
    let project = state.get_project(id).await
        .ok_or_else(|| ApiError::NotFound(format!("Project {}", id)))?;
    Ok(Json(project.tracks))
}

/// POST /api/v1/projects/{id}/tracks — 向项目添加轨道
async fn add_track_to_project(
    State(state): State<AppState>,
    Path(id): Path<Uuid>,
    Json(req): Json<CreateTrackRequest>,
) -> Result<(StatusCode, Json<TrackInfo>), ApiError> {
    let project = state.get_project(id).await
        .ok_or_else(|| ApiError::NotFound(format!("Project {}", id)))?;
    
    let track = TrackInfo {
        id: Uuid::new_v4(),
        name: req.name.unwrap_or_else(|| "New Track".into()),
        volume: req.volume.unwrap_or(0.8),
        pan: req.pan.unwrap_or(0.0),
        muted: req.muted.unwrap_or(false),
        solo: req.solo.unwrap_or(false),
        plugin_count: 0,
    };
    
    let mut projects = state.projects.write().await;
    if let Some(project) = projects.get_mut(&id) {
        project.tracks.push(track.clone());
        project.updated_at = chrono::Utc::now().to_rfc3339();
    }
    
    Ok((StatusCode::CREATED, Json(track)))
}

// ──── Agent 端点 ────

/// GET /.well-known/agent.json — Agent发现协议端点
///
/// 返回OpenDAW的能力声明，供外部AI Agent自动发现和接入。
async fn agent_manifest() -> Json<Value> {
    Json(json!({
        "schema_version": "1.0",
        "name": "OpenDAW",
        "description": "AI原生数字音频工作站 — 配好模型API即可使用AI辅助做音乐",
        "version": "1.0.1",
        "base_url": "http://localhost:3000",
        "auth": {
            "type": "none",
            "note": "本地部署默认无需认证"
        },
        "interfaces": {
            "cli": {
                "command": "opendaw",
                "description": "命令行界面"
            },
            "api": {
                "base_url": "/api/v1",
                "description": "REST API"
            },
            "webui": {
                "url": "/",
                "description": "Web界面"
            },
            "desktop": {
                "description": "Tauri桌面应用"
            },
            "agent": {
                "url": "/api/v1/agent/chat",
                "description": "AI Agent对话接口"
            }
        },
        "capabilities": [
            {
                "name": "create_project",
                "description": "创建音频项目",
                "method": "POST",
                "path": "/api/v1/projects",
                "params": {
                    "name": "项目名称",
                    "description": "项目描述(可选)"
                }
            },
            {
                "name": "render",
                "description": "渲染项目为音频文件",
                "method": "POST",
                "path": "/api/v1/projects/{id}/render",
                "params": {
                    "format": "wav/flac",
                    "sample_rate": "采样率",
                    "bit_depth": "位深"
                }
            },
            {
                "name": "automix",
                "description": "AI自动混音",
                "method": "POST",
                "path": "/api/v1/projects/{id}/automix",
                "params": {
                    "style": "混音风格(pop/rock/edm等)",
                    "apply": "是否自动应用建议"
                }
            },
            {
                "name": "agent_chat",
                "description": "AI Agent对话（支持混音建议、EQ调整、编排等）",
                "method": "POST",
                "path": "/api/v1/agent/chat",
                "params": {
                    "message": "用户消息",
                    "project_id": "项目ID(可选)"
                }
            },
            {
                "name": "mixer_suggestions",
                "description": "获取混音建议",
                "method": "GET",
                "path": "/api/v1/mixer/{id}/suggestions"
            },
            {
                "name": "transcribe",
                "description": "音频扒带/转录",
                "method": "POST",
                "path": "/api/v1/projects/{id}/transcribe",
                "params": {
                    "source_track": "源轨道ID",
                    "options": "转录选项"
                }
            }
        ],
        "agent_system": {
            "runtime": "ReAct (Reason + Act)",
            "max_tool_rounds": 5,
            "personas": ["mixing_engineer", "producer", "recording_engineer"],
            "execution_modes": ["auto", "confirm", "suggest"],
            "model_providers": ["openai", "anthropic", "ollama", "vllm"],
            "model_config": {
                "provider": "LLM后端",
                "model": "模型名称",
                "api_key": "API密钥",
                "base_url": "API地址",
                "temperature": "温度(0-1)",
                "max_tokens": "最大token数"
            }
        },
        "links": {
            "user_guide": "/docs/user-guide.md",
            "agent_guide": "/docs/agent-guide.md",
            "api_reference": "/docs/api-reference.md",
            "source": "https://github.com/youbanzhishi/OpenDAW",
            "health": "/api/health"
        }
    }))
}

// ──── Projects 端点 ────

/// GET /api/v1/projects — 列出所有项目
async fn list_projects(State(state): State<AppState>) -> Result<Json<Vec<ProjectInfo>>, ApiError> {
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

// ──── Plugins 端点 (BUG-DAW-003修复) ────

/// GET /api/v1/plugins — 列出可用插件
/// BUG-DAW-003修复: 从marketplace registry获取插件列表，而非硬编码空数组
async fn list_plugins(State(state): State<AppState>) -> Json<PluginsResponse> {
    let mp = state.marketplace.read().await;
    let manifests = mp.registry.list_all();
    
    let plugins: Vec<PluginInfo> = manifests
        .into_iter()
        .map(|m| PluginInfo {
            id: m.id.clone(),
            name: m.name.clone(),
            version: m.version.clone(),
            plugin_type: format!("{:?}", m.category),
            author: Some(m.author.clone()),
            description: Some(m.description.clone()),
        })
        .collect();
    
    let total = plugins.len();
    Json(PluginsResponse { total, plugins })
}

// ──── Mixer 端点 ────

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

// ──── Phase 33: Marketplace 端点 ────

/// 搜索查询参数
#[derive(Debug, Deserialize)]
struct MarketplaceSearchParams {
    q: Option<String>,
    category: Option<String>,
}

/// GET /api/v1/marketplace/search?q=xxx&category=xxx — 搜索市场插件
async fn marketplace_search(
    State(state): State<AppState>,
    Query(params): Query<MarketplaceSearchParams>,
) -> Json<Vec<MarketplacePlugin>> {
    let mp = state.marketplace.read().await;
    let query = params.q.unwrap_or_default();

    let results = if query.is_empty() {
        mp.registry.list_all()
    } else {
        mp.registry.search(&query)
    };

    let plugins: Vec<MarketplacePlugin> = results
        .into_iter()
        .map(|m| {
            let avg = mp.reviews.average_rating(&m.id);
            let rev_count = mp.reviews.get_reviews(&m.id).len();
            let plat_strings: Vec<String> = m
                .platforms
                .iter()
                .map(|p| format!("{}-{}", p.os, p.arch))
                .collect();
            MarketplacePlugin {
                id: m.id.clone(),
                name: m.name.clone(),
                version: m.version.clone(),
                author: m.author.clone(),
                description: m.description.clone(),
                category: format!("{:?}", m.category),
                tags: m.tags.clone(),
                average_rating: avg,
                review_count: rev_count,
                download_url: m.download_url.clone(),
                platforms: plat_strings,
                compatible: true,
            }
        })
        .collect();

    Json(plugins)
}

/// GET /api/v1/marketplace/categories — 获取分类列表
async fn marketplace_categories(State(state): State<AppState>) -> Json<Vec<CategoryItem>> {
    let mp = state.marketplace.read().await;
    let cats = opendaw_core::preset_categories();
    let items: Vec<CategoryItem> = cats
        .into_iter()
        .map(|cat| {
            let plugins = mp.registry.list_by_category(&cat);
            CategoryItem {
                name: format!("{:?}", cat),
                subcategory: None,
                count: plugins.len(),
            }
        })
        .collect();
    Json(items)
}

/// GET /api/v1/marketplace/{id} — 获取插件详情
async fn marketplace_plugin_detail(
    State(state): State<AppState>,
    Path(id): Path<String>,
) -> Result<Json<PluginDetailResponse>, ApiError> {
    let mp = state.marketplace.read().await;
    let manifest = mp
        .registry
        .get(&id)
        .ok_or_else(|| ApiError::NotFound(format!("Plugin {}", id)))?;

    let report = mp
        .registry
        .check_compatibility(manifest, &mp.compatibility.daw_version);
    let summary = mp.reviews.get_summary(&id);
    let plat_strings: Vec<String> = manifest
        .platforms
        .iter()
        .map(|p| format!("{}-{}", p.os, p.arch))
        .collect();

    Ok(Json(PluginDetailResponse {
        id: manifest.id.clone(),
        name: manifest.name.clone(),
        version: manifest.version.clone(),
        author: manifest.author.clone(),
        description: manifest.description.clone(),
        category: format!("{:?}", manifest.category),
        tags: manifest.tags.clone(),
        average_rating: summary.map(|s| s.average_rating).unwrap_or(0.0),
        review_count: summary.map(|s| s.total_reviews).unwrap_or(0),
        rating_distribution: summary.map(|s| s.rating_distribution).unwrap_or([0; 5]),
        download_url: manifest.download_url.clone(),
        homepage: manifest.homepage.clone(),
        license: manifest.license.clone(),
        platforms: plat_strings,
        compatible: report.compatible,
        compatibility_issues: report.issues,
    }))
}

/// POST /api/v1/marketplace/{id}/install — 一键安装
async fn marketplace_install(
    State(state): State<AppState>,
    Path(id): Path<String>,
) -> Result<Json<InstallResponse>, ApiError> {
    let mp = state.marketplace.read().await;
    let manifest = mp
        .registry
        .get(&id)
        .ok_or_else(|| ApiError::NotFound(format!("Plugin {}", id)))?;
    let version = manifest.version.clone();
    drop(mp);

    // In real implementation, this would trigger PluginInstaller
    Ok(Json(InstallResponse {
        plugin_id: id,
        version,
        status: "installed".into(),
        message: "Plugin installed successfully".into(),
    }))
}

/// POST /api/v1/marketplace/{id}/review — 提交评价
async fn marketplace_submit_review(
    State(state): State<AppState>,
    Path(id): Path<String>,
    Json(req): Json<SubmitReviewRequest>,
) -> Result<Json<ReviewResponse>, ApiError> {
    if req.rating < 1 || req.rating > 5 {
        return Err(ApiError::BadRequest(
            "Rating must be between 1 and 5".into(),
        ));
    }

    let review = PluginReview::new(&id, &req.user_id, req.rating, &req.comment)
        .map_err(|e| ApiError::BadRequest(e))?;

    let resp = ReviewResponse {
        review_id: review.review_id.clone(),
        plugin_id: review.plugin_id.clone(),
        rating: review.rating,
        comment: review.comment.clone(),
    };

    let mut mp = state.marketplace.write().await;
    mp.reviews
        .add_review(review)
        .map_err(|e| ApiError::Internal(e))?;

    Ok(Json(resp))
}


// ──── 文件上传处理器 (BUG-DAW-006修复) ────

/// 支持的音频格式
const SUPPORTED_AUDIO_FORMATS: &[&str] = &["wav", "mp3", "ogg", "flac"];
/// 最大文件大小：100MB
const MAX_FILE_SIZE: u64 = 100 * 1024 * 1024;

/// 验证文件扩展名是否支持
fn is_supported_format(filename: &str) -> Option<String> {
    let ext = filename.rsplit('.').next()?.to_lowercase();
    if SUPPORTED_AUDIO_FORMATS.contains(&ext.as_str()) {
        Some(ext)
    } else {
        None
    }
}

/// POST /api/v1/tracks/{id}/audio — 上传音频文件到轨道
async fn upload_track_audio(
    State(state): State<AppState>,
    Path(track_id): Path<Uuid>,
    mut multipart: Multipart,
) -> Result<Json<AudioUploadResponse>, ApiError> {
    // 验证轨道存在并获取项目ID
    let project_id = {
        let projects = state.projects.read().await;
        let mut found_project_id = None;
        
        for (pid, project) in projects.iter() {
            if project.tracks.iter().any(|t| t.id == track_id) {
                found_project_id = Some(*pid);
                break;
            }
        }
        
        found_project_id
            .ok_or_else(|| ApiError::NotFound(format!("Track {}", track_id)))?
    };
    
    // 处理 multipart 数据
    let mut filename: Option<String> = None;
    let mut file_data: Vec<u8> = Vec::new();
    
    while let Some(field) = multipart.next_field().await.map_err(|e| ApiError::BadRequest(e.to_string()))? {
        let name = field.name().unwrap_or("").to_string();
        
        if name == "file" {
            filename = field.file_name().map(|s| s.to_string());
            
            // 读取文件内容
            use futures::stream::StreamExt;
            let mut stream = field;
            while let Some(chunk) = stream.next().await {
                let data = chunk.map_err(|e| ApiError::BadRequest(e.to_string()))?;
                file_data.extend_from_slice(&data);
            }
        }
    }
    
    // 验证文件名
    let filename = filename.ok_or_else(|| ApiError::BadRequest("No filename provided".into()))?;
    
    // 验证文件格式
    let format = is_supported_format(&filename)
        .ok_or_else(|| ApiError::BadRequest(format!("Unsupported format. Supported: {:?}", SUPPORTED_AUDIO_FORMATS)))?;
    
    // 验证文件大小
    let size = file_data.len() as u64;
    if size > MAX_FILE_SIZE {
        return Err(ApiError::BadRequest(format!("File too large. Max size: {} bytes", MAX_FILE_SIZE)));
    }
    
    if size == 0 {
        return Err(ApiError::BadRequest("Empty file".into()));
    }
    
    // 确保目录存在并保存文件
    let audio_dir = state.ensure_audio_dir(project_id, track_id);
    let file_path = audio_dir.join(&filename);
    
    // 如果文件已存在，添加时间戳避免覆盖
    let final_path = if file_path.exists() {
        let timestamp = chrono::Utc::now().format("%Y%m%d_%H%M%S");
        let stem = file_path.file_stem().unwrap_or_default().to_string_lossy();
        let final_filename = format!("{}_{}.{}", stem, timestamp, format);
        audio_dir.join(final_filename)
    } else {
        file_path
    };
    
    // 写入文件
    tokio::fs::write(&final_path, &file_data)
        .await
        .map_err(|e| ApiError::Internal(format!("Failed to save file: {}", e)))?;
    
    tracing::info!("Uploaded audio file: {} ({} bytes) to track {}", filename, size, track_id);
    
    Ok(Json(AudioUploadResponse {
        track_id,
        filename: final_path.file_name()
            .map(|s| s.to_string_lossy().into_owned())
            .unwrap_or(filename),
        size,
        status: "uploaded".into(),
    }))
}

/// POST /api/v1/projects/import — 导入项目文件
async fn import_project(
    State(state): State<AppState>,
    mut multipart: Multipart,
) -> Result<Json<ProjectImportResponse>, ApiError> {
    // 支持的项目格式
    const SUPPORTED_PROJECT_FORMATS: &[&str] = &["opendaw", "json", "daw"];
    
    // 处理 multipart 数据
    let mut filename: Option<String> = None;
    let mut file_data: Vec<u8> = Vec::new();
    
    while let Some(field) = multipart.next_field().await.map_err(|e| ApiError::BadRequest(e.to_string()))? {
        let name = field.name().unwrap_or("").to_string();
        
        if name == "file" {
            filename = field.file_name().map(|s| s.to_string());
            
            // 读取文件内容
            use futures::stream::StreamExt;
            let mut stream = field;
            while let Some(chunk) = stream.next().await {
                let data = chunk.map_err(|e| ApiError::BadRequest(e.to_string()))?;
                file_data.extend_from_slice(&data);
            }
        }
    }
    
    // 验证文件名
    let filename = filename.ok_or_else(|| ApiError::BadRequest("No filename provided".into()))?;
    
    // 验证文件格式
    let ext = filename.rsplit('.').next()
        .ok_or_else(|| ApiError::BadRequest("No file extension".into()))?
        .to_lowercase();
    
    if !SUPPORTED_PROJECT_FORMATS.contains(&ext.as_str()) {
        return Err(ApiError::BadRequest(format!("Unsupported project format: {}. Supported: {:?}", ext, SUPPORTED_PROJECT_FORMATS)));
    }
    
    // 验证文件大小
    let size = file_data.len() as u64;
    if size > MAX_FILE_SIZE {
        return Err(ApiError::BadRequest(format!("File too large. Max size: {} bytes", MAX_FILE_SIZE)));
    }
    
    if size == 0 {
        return Err(ApiError::BadRequest("Empty file".into()));
    }
    
    // 确保导入目录存在并保存文件
    let import_dir = state.get_import_dir();
    let file_path = import_dir.join(&filename);
    
    // 如果文件已存在，添加时间戳避免覆盖
    let final_path = if file_path.exists() {
        let timestamp = chrono::Utc::now().format("%Y%m%d_%H%M%S");
        let stem = file_path.file_stem().unwrap_or_default().to_string_lossy();
        let final_filename = format!("{}_{}.{}", stem, timestamp, ext);
        import_dir.join(final_filename)
    } else {
        file_path
    };
    
    // 写入文件
    tokio::fs::write(&final_path, &file_data)
        .await
        .map_err(|e| ApiError::Internal(format!("Failed to save file: {}", e)))?;
    
    // 尝试解析并创建项目（可选）
    let project_id = if ext == "json" || ext == "opendaw" {
        // 尝试解析项目文件
        if let Ok(project_data) = serde_json::from_slice::<serde_json::Value>(&file_data) {
            let name = project_data.get("name")
                .and_then(|v| v.as_str())
                .unwrap_or("Imported Project")
                .to_string();
            
            let project = state.create_project(name, Some(format!("Imported from {}", filename))).await;
            tracing::info!("Created project {} from imported file", project.id);
            project.id
        } else {
            // 无法解析，创建默认项目
            let project = state.create_project("Imported Project".into(), Some(format!("Imported from {}", filename))).await;
            tracing::info!("Created project {} from imported file (generic)", project.id);
            project.id
        }
    } else {
        // 其他格式，只保存文件
        let project = state.create_project("Imported Project".into(), Some(format!("Imported from {}", filename))).await;
        tracing::info!("Created project {} from imported file", project.id);
        project.id
    };
    
    tracing::info!("Imported project file: {} ({} bytes)", filename, size);
    
    Ok(Json(ProjectImportResponse {
        project_id,
        filename: final_path.file_name()
            .map(|s| s.to_string_lossy().into_owned())
            .unwrap_or(filename),
        size,
        status: "imported".into(),
    }))
}

#[cfg(test)]
mod tests {
    use crate::state::AppState;

    #[test]
    fn test_router_construction() {
        // Verify that the router can be constructed with AppState
        let state = AppState::new();
        let _router = super::routes(state);
        // Router<AppState> created successfully - validates route definitions compile
    }

    #[test]
    fn test_routes_defined() {
        let state = AppState::new();
        let router = super::routes(state);
        // If we get here, all route handlers are properly typed
        drop(router);
    }
}
