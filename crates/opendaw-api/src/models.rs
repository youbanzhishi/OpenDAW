//! API 请求/响应模型
//! BUG修复: 添加Tracks相关模型 (BUG-DAW-002)

use serde::{Deserialize, Serialize};
use uuid::Uuid;

// ──── 项目模型 ────

/// 项目模型
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct Project {
    pub id: Uuid,
    pub name: String,
    pub description: Option<String>,
    pub tracks: Vec<TrackInfo>,
    pub sample_rate: u32,
    pub bpm: f64,
    pub created_at: String,
    pub updated_at: String,
}

/// 轨道信息
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct TrackInfo {
    pub id: Uuid,
    pub name: String,
    pub volume: f32,
    pub pan: f32,
    pub muted: bool,
    pub solo: bool,
    pub plugin_count: usize,
}

/// 项目列表项
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct ProjectInfo {
    pub id: Uuid,
    pub name: String,
    pub description: Option<String>,
    pub created_at: String,
    pub updated_at: String,
    pub track_count: usize,
}

/// 创建项目请求
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct CreateProjectRequest {
    pub name: String,
    pub description: Option<String>,
    pub bpm: Option<f64>,
    pub sample_rate: Option<u32>,
}

/// 更新项目请求
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct UpdateProjectRequest {
    pub name: Option<String>,
    pub description: Option<String>,
    pub bpm: Option<f64>,
}

// ──── Tracks 模型 (BUG-DAW-002新增) ────

/// 创建轨道请求
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct CreateTrackRequest {
    pub project_id: Option<Uuid>,  // 如果不指定，则创建独立轨道
    pub name: Option<String>,
    pub volume: Option<f32>,
    pub pan: Option<f32>,
    pub muted: Option<bool>,
    pub solo: Option<bool>,
}

/// 更新轨道请求
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct UpdateTrackRequest {
    pub name: Option<String>,
    pub volume: Option<f32>,
    pub pan: Option<f32>,
    pub muted: Option<bool>,
    pub solo: Option<bool>,
}

// ──── 渲染 & AI ────

/// 渲染请求
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct RenderRequest {
    pub format: Option<String>,
    pub output_path: Option<String>,
    pub start_beat: Option<f64>,
    pub end_beat: Option<f64>,
}

/// 渲染响应
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct RenderResponse {
    pub task_id: Uuid,
    pub project_id: Uuid,
    pub status: String,
    pub message: String,
}

/// AI自动混音请求
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct AutoMixRequest {
    pub style: Option<String>,
    pub target_loudness: Option<f32>,
}

/// AI自动混音响应
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct AutoMixResponse {
    pub project_id: Uuid,
    pub suggestions: Vec<MixSuggestionItem>,
    pub applied: bool,
}

/// 混音建议项
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct MixSuggestionItem {
    pub track_name: String,
    pub action: String,
    pub current_value: Option<f32>,
    pub suggested_value: f32,
    pub reason: String,
}

/// 扒带请求
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct TranscribeRequest {
    pub audio_path: String,
    pub sensitivity: Option<f32>,
}

/// 扒带响应
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct TranscribeResponse {
    pub project_id: Uuid,
    pub notes_detected: usize,
    pub tracks_created: usize,
    pub key_estimate: Option<String>,
}

// ──── 插件模型 (BUG-DAW-003修复) ────

/// 插件信息
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct PluginInfo {
    pub id: String,
    pub name: String,
    pub version: String,
    pub plugin_type: String,
    pub author: Option<String>,
    pub description: Option<String>,
}

/// 插件列表响应 (BUG-DAW-003修复)
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct PluginsResponse {
    pub total: usize,
    pub plugins: Vec<PluginInfo>,
}

/// 混音建议响应
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct MixerSuggestionsResponse {
    pub project_id: Uuid,
    pub suggestions: Vec<MixSuggestionItem>,
    pub overall_score: f32,
}

/// 通用API响应
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct ApiResponse<T: Serialize + std::fmt::Debug> {
    pub success: bool,
    pub data: Option<T>,
    pub error: Option<String>,
}

impl<T: Serialize + std::fmt::Debug> ApiResponse<T> {
    pub fn ok(data: T) -> Self {
        Self {
            success: true,
            data: Some(data),
            error: None,
        }
    }

    pub fn err(msg: impl Into<String>) -> Self {
        Self {
            success: false,
            data: None,
            error: Some(msg.into()),
        }
    }
}

impl Project {
    pub fn new(name: String, description: Option<String>) -> Self {
        let now = chrono::Utc::now().to_rfc3339();
        Self {
            id: Uuid::new_v4(),
            name,
            description,
            tracks: Vec::new(),
            sample_rate: 44100,
            bpm: 120.0,
            created_at: now.clone(),
            updated_at: now,
        }
    }
}

// ──── Phase 33: Marketplace 模型 ────

/// 市场插件搜索结果
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct MarketplacePlugin {
    pub id: String,
    pub name: String,
    pub version: String,
    pub author: String,
    pub description: String,
    pub category: String,
    pub tags: Vec<String>,
    pub average_rating: f32,
    pub review_count: usize,
    pub download_url: Option<String>,
    pub platforms: Vec<String>,
    pub compatible: bool,
}

/// 提交评价请求
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct SubmitReviewRequest {
    pub user_id: String,
    pub rating: u8,
    pub comment: String,
}

/// 评价响应
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct ReviewResponse {
    pub review_id: String,
    pub plugin_id: String,
    pub rating: u8,
    pub comment: String,
}

/// 插件详情响应
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct PluginDetailResponse {
    pub id: String,
    pub name: String,
    pub version: String,
    pub author: String,
    pub description: String,
    pub category: String,
    pub tags: Vec<String>,
    pub average_rating: f32,
    pub review_count: usize,
    pub rating_distribution: [usize; 5],
    pub download_url: Option<String>,
    pub homepage: Option<String>,
    pub license: Option<String>,
    pub platforms: Vec<String>,
    pub compatible: bool,
    pub compatibility_issues: Vec<String>,
}

/// 安装响应
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct InstallResponse {
    pub plugin_id: String,
    pub version: String,
    pub status: String,
    pub message: String,
}

/// 分类列表项
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct CategoryItem {
    pub name: String,
    pub subcategory: Option<String>,
    pub count: usize,
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_project_new() {
        let p = Project::new("Test".into(), Some("Desc".into()));
        assert_eq!(p.name, "Test");
        assert_eq!(p.description, Some("Desc".into()));
        assert_eq!(p.sample_rate, 44100);
        assert_eq!(p.bpm, 120.0);
    }

    #[test]
    fn test_project_new_no_desc() {
        let p = Project::new("Test".into(), None);
        assert!(p.description.is_none());
    }

    #[test]
    fn test_api_response_ok() {
        let resp = ApiResponse::ok(42);
        assert!(resp.success);
        assert_eq!(resp.data, Some(42));
        assert!(resp.error.is_none());
    }

    #[test]
    fn test_api_response_err() {
        let resp: ApiResponse<String> = ApiResponse::err("something failed");
        assert!(!resp.success);
        assert!(resp.data.is_none());
        assert_eq!(resp.error, Some("something failed".into()));
    }

    #[test]
    fn test_create_project_request_deserialize() {
        let json = r#"{"name":"MyProject","description":"Hello","bpm":140}"#;
        let req: CreateProjectRequest = serde_json::from_str(json).unwrap();
        assert_eq!(req.name, "MyProject");
        assert_eq!(req.bpm, Some(140.0));
    }

    #[test]
    fn test_render_request_defaults() {
        let json = r#"{}"#;
        let req: RenderRequest = serde_json::from_str(json).unwrap();
        assert!(req.format.is_none());
        assert!(req.output_path.is_none());
    }

    #[test]
    fn test_plugin_info_serialize() {
        let info = PluginInfo {
            id: "eq7".into(),
            name: "7-Band EQ".into(),
            version: "1.0.0".into(),
            plugin_type: "effect".into(),
            author: Some("OpenDAW".into()),
            description: None,
        };
        let json = serde_json::to_string(&info).unwrap();
        assert!(json.contains("eq7"));
    }

    #[test]
    fn test_track_info() {
        let t = TrackInfo {
            id: Uuid::new_v4(),
            name: "Guitar".into(),
            volume: 0.8,
            pan: -0.3,
            muted: false,
            solo: false,
            plugin_count: 2,
        };
        assert_eq!(t.name, "Guitar");
        assert_eq!(t.plugin_count, 2);
    }

    #[test]
    fn test_create_track_request() {
        let json = r#"{"project_id":"550e8400-e29b-41d4-a716-446655440000","name":"Drums","volume":0.9}"#;
        let req: CreateTrackRequest = serde_json::from_str(json).unwrap();
        assert_eq!(req.name, Some("Drums".into()));
        assert_eq!(req.volume, Some(0.9));
    }

    #[test]
    fn test_update_track_request() {
        let json = r#"{"volume":0.5,"muted":true}"#;
        let req: UpdateTrackRequest = serde_json::from_str(json).unwrap();
        assert_eq!(req.volume, Some(0.5));
        assert_eq!(req.muted, Some(true));
        assert!(req.name.is_none());
    }

    #[test]
    fn test_mix_suggestion_item() {
        let item = MixSuggestionItem {
            track_name: "Vocals".into(),
            action: "reduce_volume".into(),
            current_value: Some(-3.0),
            suggested_value: -6.0,
            reason: "Too loud in mix".into(),
        };
        assert_eq!(item.action, "reduce_volume");
    }

    #[test]
    fn test_submit_review_request() {
        let req = SubmitReviewRequest {
            user_id: "u1".into(),
            rating: 4,
            comment: "Great".into(),
        };
        assert_eq!(req.rating, 4);
    }

    #[test]
    fn test_marketplace_plugin() {
        let mp = MarketplacePlugin {
            id: "eq7".into(),
            name: "7-Band EQ".into(),
            version: "1.0.0".into(),
            author: "OpenDAW".into(),
            description: "An EQ".into(),
            category: "effect".into(),
            tags: vec!["equalizer".into()],
            average_rating: 4.5,
            review_count: 10,
            download_url: None,
            platforms: vec!["linux-x86_64".into()],
            compatible: true,
        };
        assert_eq!(mp.id, "eq7");
        assert!(mp.compatible);
    }

    #[test]
    fn test_plugins_response() {
        let resp = PluginsResponse {
            total: 2,
            plugins: vec![
                PluginInfo {
                    id: "eq7".into(),
                    name: "7-Band EQ".into(),
                    version: "1.0.0".into(),
                    plugin_type: "Effect".into(),
                    author: Some("OpenDAW".into()),
                    description: Some("An EQ".into()),
                },
            ],
        };
        assert_eq!(resp.total, 2);
        assert_eq!(resp.plugins.len(), 1);
    }
}
