//! Tauri Commands for VCMix Desktop

use crate::state::AppState;
use serde::{Deserialize, Serialize};
use tauri::State;

// ── Response Types ───────────────────────────────────────────────────────

#[derive(Debug, Serialize)]
pub struct HealthStatus {
    pub healthy: bool,
    pub message: String,
}

#[derive(Debug, Serialize)]
pub struct RenderResult {
    pub job_id: String,
    pub status: String,
    pub message: String,
}

#[derive(Debug, Serialize)]
pub struct AnalysisResult {
    pub project: String,
    // bpm: currently not in ProjectConfig, using default 120.0
    pub sample_rate: u32,
    pub tracks: Vec<serde_json::Value>,
    pub master: serde_json::Value,
}

#[derive(Debug, Serialize)]
pub struct PresetInfo {
    pub name: String,
    pub description: String,
}

#[derive(Debug, Serialize)]
pub struct PresetList {
    pub presets: Vec<PresetInfo>,
    pub count: usize,
}

#[derive(Debug, Serialize)]
pub struct WaveformData {
    pub peaks: Vec<f64>,
    pub sample_count: usize,
    pub sample_rate: u32,
    pub duration_s: f64,
    pub channels: u32,
}

#[derive(Debug, Serialize)]
pub struct SpectrumData {
    pub frequencies: Vec<f64>,
    pub magnitudes: Vec<f64>,
    pub sample_rate: u32,
    pub fft_size: usize,
}

#[derive(Debug, Serialize)]
pub struct MidiNoteData {
    pub notes: Vec<serde_json::Value>,
    pub note_count: usize,
    // bpm: currently not in ProjectConfig, using default 120.0
    pub total_beats: f64,
}

#[derive(Debug, Serialize)]
pub struct FileDialogResult {
    pub path: Option<String>,
    pub cancelled: bool,
}

#[derive(Debug, Deserialize)]
pub struct BackendResponse {
    #[serde(default)]
    status: Option<String>,
    #[serde(default)]
    job_id: Option<String>,
    #[serde(default)]
    message: Option<String>,
}

// ── Commands ─────────────────────────────────────────────────────────────

#[tauri::command]
pub async fn check_backend_health(port: u16) -> Result<HealthStatus, String> {
    let url = format!("http://localhost:{}/api/health", port);
    match reqwest::get(&url).await {
        Ok(resp) if resp.status().is_success() => Ok(HealthStatus {
            healthy: true,
            message: "Backend is running".into(),
        }),
        Ok(resp) => Ok(HealthStatus {
            healthy: false,
            message: format!("Backend returned status {}", resp.status()),
        }),
        Err(e) => Ok(HealthStatus {
            healthy: false,
            message: format!("Cannot reach backend: {}", e),
        }),
    }
}

#[tauri::command]
pub fn set_backend_pid(state: State<'_, AppState>, pid: u32) -> Result<(), String> {
    *state.backend.pid.lock() = Some(pid);
    Ok(())
}

#[tauri::command]
pub fn get_backend_pid(state: State<'_, AppState>) -> Result<Option<u32>, String> {
    Ok(*state.backend.pid.lock())
}

#[tauri::command]
pub async fn render_project(
    state: State<'_, AppState>,
    yaml_path: String,
) -> Result<RenderResult, String> {
    let url = format!(
        "{}/api/render/file?project_path={}",
        state.backend.base_url,
        urlencoding::encode(&yaml_path)
    );
    let client = reqwest::Client::new();
    let resp = client
        .post(&url)
        .send()
        .await
        .map_err(|e| format!("Request failed: {}", e))?;
    let data: serde_json::Value = resp
        .json()
        .await
        .map_err(|e| format!("JSON parse error: {}", e))?;
    Ok(RenderResult {
        job_id: data
            .get("job_id")
            .and_then(|v| v.as_str())
            .unwrap_or("unknown")
            .to_string(),
        status: data
            .get("status")
            .and_then(|v| v.as_str())
            .unwrap_or("unknown")
            .to_string(),
        message: data
            .get("message")
            .and_then(|v| v.as_str())
            .unwrap_or("")
            .to_string(),
    })
}

#[tauri::command]
pub async fn get_analysis(
    state: State<'_, AppState>,
    project_id: String,
) -> Result<AnalysisResult, String> {
    let url = format!(
        "{}/api/v1/projects/{}/analysis",
        state.backend.base_url, project_id
    );
    let resp = reqwest::get(&url)
        .await
        .map_err(|e| format!("Request failed: {}", e))?;
    let data: serde_json::Value = resp
        .json()
        .await
        .map_err(|e| format!("JSON parse error: {}", e))?;
    Ok(AnalysisResult {
        project: data
            .get("project")
            .and_then(|v| v.as_str())
            .unwrap_or("")
            .to_string(),
        bpm: data.get("bpm").and_then(|v| v.as_f64()).unwrap_or(120.0),
        sample_rate: data
            .get("sample_rate")
            .and_then(|v| v.as_u64())
            .unwrap_or(44100) as u32,
        tracks: data
            .get("tracks")
            .and_then(|v| v.as_array())
            .cloned()
            .unwrap_or_default(),
        master: data
            .get("master")
            .cloned()
            .unwrap_or(serde_json::Value::Null),
    })
}

#[tauri::command]
pub async fn list_presets(state: State<'_, AppState>) -> Result<PresetList, String> {
    let url = format!("{}/api/presets", state.backend.base_url);
    let resp = reqwest::get(&url)
        .await
        .map_err(|e| format!("Request failed: {}", e))?;
    let data: serde_json::Value = resp
        .json()
        .await
        .map_err(|e| format!("JSON parse error: {}", e))?;
    let presets: Vec<PresetInfo> = data
        .get("presets")
        .and_then(|v| v.as_array())
        .cloned()
        .unwrap_or_default()
        .iter()
        .map(|p| PresetInfo {
            name: p
                .get("name")
                .and_then(|v| v.as_str())
                .unwrap_or("")
                .to_string(),
            description: p
                .get("description")
                .and_then(|v| v.as_str())
                .unwrap_or("")
                .to_string(),
        })
        .collect();
    Ok(PresetList {
        count: presets.len(),
        presets,
    })
}

#[tauri::command]
pub async fn open_file_dialog(
    _title: String,
    _filters: Vec<Vec<String>>,
) -> Result<FileDialogResult, String> {
    Ok(FileDialogResult {
        path: None,
        cancelled: true,
    })
}

#[tauri::command]
pub async fn get_waveform(
    state: State<'_, AppState>,
    project_id: String,
    track: String,
) -> Result<WaveformData, String> {
    let url = format!(
        "{}/api/v1/waveform/{}/{}",
        state.backend.base_url, project_id, track
    );
    let resp = reqwest::get(&url)
        .await
        .map_err(|e| format!("Request failed: {}", e))?;
    let data: serde_json::Value = resp
        .json()
        .await
        .map_err(|e| format!("JSON parse error: {}", e))?;
    Ok(WaveformData {
        peaks: data
            .get("peaks")
            .and_then(|v| v.as_array())
            .cloned()
            .unwrap_or_default()
            .iter()
            .filter_map(|v| v.as_f64())
            .collect(),
        sample_count: data
            .get("sample_count")
            .and_then(|v| v.as_u64())
            .unwrap_or(0) as usize,
        sample_rate: data
            .get("sample_rate")
            .and_then(|v| v.as_u64())
            .unwrap_or(44100) as u32,
        duration_s: data
            .get("duration_s")
            .and_then(|v| v.as_f64())
            .unwrap_or(0.0),
        channels: data.get("channels").and_then(|v| v.as_u64()).unwrap_or(1) as u32,
    })
}

#[tauri::command]
pub async fn get_spectrum(
    state: State<'_, AppState>,
    project_id: String,
    track: String,
) -> Result<SpectrumData, String> {
    let url = format!(
        "{}/api/v1/spectrum/{}/{}",
        state.backend.base_url, project_id, track
    );
    let resp = reqwest::get(&url)
        .await
        .map_err(|e| format!("Request failed: {}", e))?;
    let data: serde_json::Value = resp
        .json()
        .await
        .map_err(|e| format!("JSON parse error: {}", e))?;
    Ok(SpectrumData {
        frequencies: data
            .get("frequencies")
            .and_then(|v| v.as_array())
            .cloned()
            .unwrap_or_default()
            .iter()
            .filter_map(|v| v.as_f64())
            .collect(),
        magnitudes: data
            .get("magnitudes")
            .and_then(|v| v.as_array())
            .cloned()
            .unwrap_or_default()
            .iter()
            .filter_map(|v| v.as_f64())
            .collect(),
        sample_rate: data
            .get("sample_rate")
            .and_then(|v| v.as_u64())
            .unwrap_or(44100) as u32,
        fft_size: data
            .get("fft_size")
            .and_then(|v| v.as_u64())
            .unwrap_or(2048) as usize,
    })
}

#[tauri::command]
pub async fn get_midi_notes(
    state: State<'_, AppState>,
    project_id: String,
    track: String,
) -> Result<MidiNoteData, String> {
    let url = format!(
        "{}/api/v1/midi/{}/{}",
        state.backend.base_url, project_id, track
    );
    let resp = reqwest::get(&url)
        .await
        .map_err(|e| format!("Request failed: {}", e))?;
    let data: serde_json::Value = resp
        .json()
        .await
        .map_err(|e| format!("JSON parse error: {}", e))?;
    Ok(MidiNoteData {
        notes: data
            .get("notes")
            .and_then(|v| v.as_array())
            .cloned()
            .unwrap_or_default(),
        note_count: data.get("note_count").and_then(|v| v.as_u64()).unwrap_or(0) as usize,
        bpm: data.get("bpm").and_then(|v| v.as_f64()).unwrap_or(120.0),
        total_beats: data
            .get("total_beats")
            .and_then(|v| v.as_f64())
            .unwrap_or(0.0),
    })
}

// ═══════════════════════════════════════════════════════════════════════
// Phase 14 — Transport & Track Commands
// ═══════════════════════════════════════════════════════════════════════

#[derive(Debug, Serialize)]
pub struct TransportStatus {
    pub playing: bool,
    pub recording: bool,
    pub current_time_s: f64,
    // bpm: currently not in ProjectConfig, using default 120.0
    pub time_sig: String,
}

#[derive(Debug, Serialize)]
pub struct TrackInfo {
    pub id: String,
    pub name: String,
    pub r#type: String,
    pub gain_db: f64,
    pub pan: f64,
    pub mute: bool,
    pub solo: bool,
}

#[derive(Debug, Serialize)]
pub struct ProjectInfo {
    pub id: String,
    pub name: String,
    // bpm: currently not in ProjectConfig, using default 120.0
    pub sample_rate: u32,
    pub tracks: Vec<TrackInfo>,
}

#[derive(Debug, Serialize)]
pub struct ProjectList {
    pub projects: Vec<serde_json::Value>,
    pub count: usize,
}

#[derive(Debug, Serialize)]
pub struct AgentChatResponse {
    pub message: String,
    pub actions: Vec<serde_json::Value>,
    pub thinking: String,
}

#[tauri::command]
pub async fn transport_play(state: State<'_, AppState>) -> Result<TransportStatus, String> {
    // Transport is managed in the frontend JS; this is a backend sync hook
    Ok(TransportStatus {
        playing: true,
        recording: false,
        current_time_s: 0.0,
        bpm: 120.0,
        time_sig: "4/4".into(),
    })
}

#[tauri::command]
pub async fn transport_stop(state: State<'_, AppState>) -> Result<TransportStatus, String> {
    Ok(TransportStatus {
        playing: false,
        recording: false,
        current_time_s: 0.0,
        bpm: 120.0,
        time_sig: "4/4".into(),
    })
}

#[tauri::command]
pub async fn list_projects(state: State<'_, AppState>) -> Result<ProjectList, String> {
    let url = format!("{}/api/v1/projects", state.backend.base_url);
    let resp = reqwest::get(&url)
        .await
        .map_err(|e| format!("Request failed: {}", e))?;
    let data: serde_json::Value = resp
        .json()
        .await
        .map_err(|e| format!("JSON parse error: {}", e))?;
    let projects = data
        .get("projects")
        .and_then(|v| v.as_array())
        .cloned()
        .unwrap_or_default();
    Ok(ProjectList {
        count: projects.len(),
        projects,
    })
}

#[tauri::command]
pub async fn get_project(
    state: State<'_, AppState>,
    project_id: String,
) -> Result<ProjectInfo, String> {
    let url = format!("{}/api/v1/projects/{}", state.backend.base_url, project_id);
    let resp = reqwest::get(&url)
        .await
        .map_err(|e| format!("Request failed: {}", e))?;
    let data: serde_json::Value = resp
        .json()
        .await
        .map_err(|e| format!("JSON parse error: {}", e))?;

    let tracks: Vec<TrackInfo> = data
        .get("tracks")
        .and_then(|v| v.as_array())
        .cloned()
        .unwrap_or_default()
        .iter()
        .map(|t| TrackInfo {
            id: t
                .get("id")
                .or(t.get("name"))
                .and_then(|v| v.as_str())
                .unwrap_or("")
                .to_string(),
            name: t
                .get("name")
                .and_then(|v| v.as_str())
                .unwrap_or("Track")
                .to_string(),
            r#type: t
                .get("type")
                .and_then(|v| v.as_str())
                .unwrap_or("audio")
                .to_string(),
            gain_db: t.get("gain").and_then(|v| v.as_f64()).unwrap_or(0.0),
            pan: t.get("pan").and_then(|v| v.as_f64()).unwrap_or(0.0),
            mute: t.get("mute").and_then(|v| v.as_bool()).unwrap_or(false),
            solo: t.get("solo").and_then(|v| v.as_bool()).unwrap_or(false),
        })
        .collect();

    Ok(ProjectInfo {
        id: project_id,
        name: data
            .get("name")
            .and_then(|v| v.as_str())
            .unwrap_or("Untitled")
            .to_string(),
        bpm: data.get("bpm").and_then(|v| v.as_f64()).unwrap_or(120.0),
        sample_rate: data
            .get("sample_rate")
            .and_then(|v| v.as_u64())
            .unwrap_or(44100) as u32,
        tracks,
    })
}

#[tauri::command]
pub async fn create_project(
    state: State<'_, AppState>,
    name: String,
) -> Result<serde_json::Value, String> {
    let url = format!("{}/api/v1/projects", state.backend.base_url);
    let client = reqwest::Client::new();
    let resp = client
        .post(&url)
        .json(&serde_json::json!({ "name": name }))
        .send()
        .await
        .map_err(|e| format!("Request failed: {}", e))?;
    let data: serde_json::Value = resp
        .json()
        .await
        .map_err(|e| format!("JSON parse error: {}", e))?;
    Ok(data)
}

#[tauri::command]
pub async fn add_track(
    state: State<'_, AppState>,
    project_id: String,
    name: String,
    track_type: String,
) -> Result<serde_json::Value, String> {
    let url = format!(
        "{}/api/v1/projects/{}/tracks",
        state.backend.base_url, project_id
    );
    let client = reqwest::Client::new();
    let resp = client
        .post(&url)
        .json(&serde_json::json!({ "name": name, "type": track_type }))
        .send()
        .await
        .map_err(|e| format!("Request failed: {}", e))?;
    let data: serde_json::Value = resp
        .json()
        .await
        .map_err(|e| format!("JSON parse error: {}", e))?;
    Ok(data)
}

#[tauri::command]
pub async fn delete_track(
    state: State<'_, AppState>,
    project_id: String,
    track_name: String,
) -> Result<serde_json::Value, String> {
    let url = format!(
        "{}/api/v1/projects/{}/tracks/{}",
        state.backend.base_url,
        project_id,
        urlencoding::encode(&track_name)
    );
    let client = reqwest::Client::new();
    let resp = client
        .delete(&url)
        .send()
        .await
        .map_err(|e| format!("Request failed: {}", e))?;
    let data: serde_json::Value = resp.json().await.unwrap_or(serde_json::Value::Null);
    Ok(data)
}

#[tauri::command]
pub async fn agent_chat(
    state: State<'_, AppState>,
    message: String,
    project_id: Option<String>,
) -> Result<AgentChatResponse, String> {
    let url = format!("{}/api/v1/agent/chat", state.backend.base_url);
    let client = reqwest::Client::new();
    let body = serde_json::json!({
        "message": message,
        "project_id": project_id
    });
    let resp = client
        .post(&url)
        .json(&body)
        .send()
        .await
        .map_err(|e| format!("Agent chat failed: {}", e))?;

    let data: serde_json::Value = resp
        .json()
        .await
        .map_err(|e| format!("JSON parse error: {}", e))?;

    Ok(AgentChatResponse {
        message: data
            .get("message")
            .and_then(|v| v.as_str())
            .unwrap_or("")
            .to_string(),
        actions: data
            .get("actions")
            .and_then(|v| v.as_array())
            .cloned()
            .unwrap_or_default(),
        thinking: data
            .get("thinking")
            .and_then(|v| v.as_str())
            .unwrap_or("")
            .to_string(),
    })
}

#[tauri::command]
pub async fn automix_project(
    state: State<'_, AppState>,
    project_id: String,
) -> Result<serde_json::Value, String> {
    let url = format!("{}/api/automix", state.backend.base_url);
    let client = reqwest::Client::new();
    let resp = client
        .post(&url)
        .json(&serde_json::json!({ "project_id": project_id }))
        .send()
        .await
        .map_err(|e| format!("Automix failed: {}", e))?;
    let data: serde_json::Value = resp
        .json()
        .await
        .map_err(|e| format!("JSON parse error: {}", e))?;
    Ok(data)
}

// ═══════════════════════════════════════════════════════════════════════
// v0.24.0 — Engine & Registry Commands
// ═══════════════════════════════════════════════════════════════════════

/// Engine State Response
#[derive(Debug, Serialize)]
pub struct EngineStateResponse {
    pub state: String,
}

impl From<audio_engine::state::EngineState> for EngineStateResponse {
    fn from(s: audio_engine::state::EngineState) -> Self {
        let state_str = match s {
            audio_engine::state::EngineState::Stopped => "Stopped",
            audio_engine::state::EngineState::Playing => "Playing",
            audio_engine::state::EngineState::Paused => "Paused",
            audio_engine::state::EngineState::Recording => "Recording",
        };
        Self {
            state: state_str.to_string(),
        }
    }
}

/// Registry Stats Response
#[derive(Debug, Serialize)]
pub struct RegistryStatsResponse {
    pub plugins: usize,
    pub scripts: usize,
    pub models: usize,
    pub hook_events: usize,
}

impl From<opendaw_extension::registry::RegistryStats> for RegistryStatsResponse {
    fn from(s: opendaw_extension::registry::RegistryStats) -> Self {
        Self {
            plugins: s.plugins,
            scripts: s.scripts,
            models: s.models,
            hook_events: s.hook_events,
        }
    }
}

// ── Engine基础命令 ──────────────────────────────────────────────────────

/// 获取引擎当前状态
#[tauri::command]
pub fn engine_get_state(state: State<'_, AppState>) -> Result<EngineStateResponse, String> {
    let engine = state.engine.lock();
    Ok(engine.get_state().into())
}

/// 启动音频引擎
#[tauri::command]
pub fn engine_start(
    state: State<'_, AppState>,
    sample_rate: f64,
    buffer_size: usize,
) -> Result<(), String> {
    let mut engine = state.engine.lock();
    engine
        .start(sample_rate, buffer_size)
        .map_err(|e| e.to_string())
}

/// 停止音频引擎
#[tauri::command]
pub fn engine_stop(state: State<'_, AppState>) -> Result<(), String> {
    let mut engine = state.engine.lock();
    engine.stop().map_err(|e| e.to_string())
}

/// 暂停音频引擎
#[tauri::command]
pub fn engine_pause(state: State<'_, AppState>) -> Result<(), String> {
    let mut engine = state.engine.lock();
    engine.pause().map_err(|e| e.to_string())
}

/// 获取当前播放位置（秒）
#[tauri::command]
pub fn engine_get_position(state: State<'_, AppState>) -> Result<f64, String> {
    let engine = state.engine.lock();
    Ok(engine.get_position())
}

/// 设置播放位置（秒）
#[tauri::command]
pub fn engine_set_position(state: State<'_, AppState>, pos: f64) -> Result<(), String> {
    let mut engine = state.engine.lock();
    engine.set_position(pos);
    Ok(())
}

/// 注册新音轨
#[tauri::command]
pub fn engine_register_track(state: State<'_, AppState>, track_id: String) -> Result<(), String> {
    let mut engine = state.engine.lock();
    engine.register_track(&track_id).map_err(|e| e.to_string())
}

/// 从WAV文件加载音频到指定音轨
#[tauri::command]
pub fn engine_load_wav(
    state: State<'_, AppState>,
    track_id: String,
    file_path: String,
) -> Result<(), String> {
    let mut engine = state.engine.lock();
    engine
        .load_wav(&track_id, &file_path)
        .map_err(|e| e.to_string())
}

/// 获取音轨数量
#[tauri::command]
pub fn engine_track_count(state: State<'_, AppState>) -> Result<usize, String> {
    let engine = state.engine.lock();
    Ok(engine.track_count())
}

// ── Engine音频控制 ─────────────────────────────────────────────────────

/// 设置音轨音量
#[tauri::command]
pub fn engine_set_track_volume(
    state: State<'_, AppState>,
    track_id: String,
    volume_db: f64,
) -> Result<(), String> {
    let mut engine = state.engine.lock();
    engine
        .set_track_volume(&track_id, volume_db)
        .map_err(|e| e.to_string())
}

/// 设置主音量
#[tauri::command]
pub fn engine_set_master_volume(state: State<'_, AppState>, volume_db: f64) -> Result<(), String> {
    let mut engine = state.engine.lock();
    engine.set_master_volume(volume_db);
    Ok(())
}

/// 切换音轨静音状态
#[tauri::command]
pub fn engine_toggle_track_mute(
    state: State<'_, AppState>,
    track_id: String,
) -> Result<bool, String> {
    let mut engine = state.engine.lock();
    engine
        .toggle_track_mute(&track_id)
        .map_err(|e| e.to_string())
}

// ═══════════════════════════════════════════════════════════════════════════
// v0.25.0: Audio Playback Commands
// ═══════════════════════════════════════════════════════════════════════════

use crate::audio_output::{OutputConfig, OutputState as AudioOutputState};

#[derive(Debug, Serialize)]
pub struct AudioPlaybackStatus {
    pub engine_state: String,
    pub output_state: String,
    pub track_count: usize,
    pub has_audio_loaded: bool,
}

/// 初始化音频输出
#[tauri::command]
pub fn audio_init(
    state: State<'_, AppState>,
    sample_rate: Option<f64>,
    buffer_size: Option<usize>,
) -> Result<(), String> {
    let sr = sample_rate.unwrap_or(44100.0) as f64;
    let bs = buffer_size.unwrap_or(256);
    let audio_output = state.audio_output.lock();
    audio_output.init(sr, bs).map_err(|e| e.to_string())
}

/// 获取音频播放状态
#[tauri::command]
pub fn audio_get_status(state: State<'_, AppState>) -> Result<AudioPlaybackStatus, String> {
    let audio_output = state.audio_output.lock();
    let engine = state.engine.lock();

    // 检查是否有音频加载
    let has_audio_loaded = engine.track_count() > 0 && {
        let first_track = engine
            .get_buffer("main")
            .or_else(|| engine.get_buffer("track_0"));
        first_track.map(|b| b.frames > 0).unwrap_or(false)
    };

    Ok(AudioPlaybackStatus {
        engine_state: format!("{:?}", engine.get_state()),
        output_state: format!("{:?}", audio_output.output_state()),
        track_count: engine.track_count(),
        has_audio_loaded,
    })
}

/// 启动音频播放
#[tauri::command]
pub fn audio_play(state: State<'_, AppState>) -> Result<(), String> {
    let audio_output = state.audio_output.lock();
    audio_output.start().map_err(|e| e.to_string())
}

/// 停止音频播放
#[tauri::command]
pub fn audio_stop(state: State<'_, AppState>) -> Result<(), String> {
    let audio_output = state.audio_output.lock();
    audio_output.stop();
    Ok(())
}

/// 暂停音频播放
#[tauri::command]
pub fn audio_pause(state: State<'_, AppState>) -> Result<(), String> {
    let audio_output = state.audio_output.lock();
    audio_output.pause();
    Ok(())
}

/// 恢复音频播放
#[tauri::command]
pub fn audio_resume(state: State<'_, AppState>) -> Result<(), String> {
    let audio_output = state.audio_output.lock();
    audio_output.resume();
    Ok(())
}

/// 加载WAV文件到主音轨并播放
#[tauri::command]
pub fn audio_load_and_play(
    state: State<'_, AppState>,
    file_path: String,
    track_id: Option<String>,
) -> Result<(), String> {
    let track = track_id.unwrap_or_else(|| "main".to_string());

    // 初始化音频输出
    {
        let audio_output = state.audio_output.lock();
        audio_output.init(44100.0, 256).map_err(|e| e.to_string())?;
    }

    // 注册音轨并加载WAV
    {
        let audio_output = state.audio_output.lock();
        audio_output.register_track(&track)?;
        audio_output.load_wav(&track, &file_path)?;
    }

    // 启动播放
    {
        let audio_output = state.audio_output.lock();
        audio_output.start().map_err(|e| e.to_string())?;
    }

    Ok(())
}

/// 设置主音量
#[tauri::command]
pub fn audio_set_master_volume(state: State<'_, AppState>, volume_db: f64) -> Result<(), String> {
    let audio_output = state.audio_output.lock();
    audio_output.set_master_volume(volume_db);
    Ok(())
}

/// 获取可用音频设备列表
#[tauri::command]
pub fn audio_get_devices() -> Result<Vec<String>, String> {
    use crate::DesktopAudioOutput;
    DesktopAudioOutput::device_info().map_err(|e| e.to_string())
}

// ── Registry命令 ───────────────────────────────────────────────────────

/// 获取扩展注册中心统计信息
#[tauri::command]
pub fn registry_stats(state: State<'_, AppState>) -> Result<RegistryStatsResponse, String> {
    let registry = state.registry.lock();
    Ok(registry.stats().into())
}

// ═══════════════════════════════════════════════════════════════════════
// 单元测试
// ═══════════════════════════════════════════════════════════════════════

// ═══════════════════════════════════════════════════════════════════════
// v0.26.0 — Project Import Commands (Reaper RPP / Ableton ALS)
// ═══════════════════════════════════════════════════════════════════════

use opendaw_core::import::{FormatDetector, ImportFormat, ImportRegistry};

/// Supported import format info for the frontend
#[derive(Debug, Serialize)]
pub struct ImportFormatInfo {
    pub id: String,
    pub name: String,
    pub extensions: Vec<String>,
}

/// Import project result
#[derive(Debug, Serialize)]
pub struct ImportProjectResult {
    pub success: bool,
    pub format: String,
    pub project_name: String,
    // bpm: currently not in ProjectConfig, using default 120.0
    pub track_count: usize,
    pub message: String,
}

/// List supported import formats
#[tauri::command]
pub fn list_import_formats() -> Result<Vec<ImportFormatInfo>, String> {
    Ok(vec![
        ImportFormatInfo {
            id: "reaper_rpp".into(),
            name: "Reaper Project (.rpp)".into(),
            extensions: vec!["rpp".into()],
        },
        ImportFormatInfo {
            id: "ableton_als".into(),
            name: "Ableton Live Project (.als)".into(),
            extensions: vec!["als".into()],
        },
        ImportFormatInfo {
            id: "opendaw_yaml".into(),
            name: "OpenDAW Project (.yaml/.yml)".into(),
            extensions: vec!["yaml".into(), "yml".into()],
        },
        ImportFormatInfo {
            id: "opendaw_json".into(),
            name: "OpenDAW Project (.json)".into(),
            extensions: vec!["json".into()],
        },
        ImportFormatInfo {
            id: "midi_file".into(),
            name: "Standard MIDI File (.mid/.midi)".into(),
            extensions: vec!["mid".into(), "midi".into()],
        },
    ])
}

/// Import a project file (Reaper RPP, Ableton ALS, etc.) and convert to OpenDAW project
#[tauri::command]
pub fn import_project(file_path: String) -> Result<ImportProjectResult, String> {
    use std::path::Path;

    let path = Path::new(&file_path);
    if !path.exists() {
        return Err(format!("File not found: {}", file_path));
    }

    // Detect format
    let format = FormatDetector::detect(path).map_err(|e| e.to_string())?;

    // Import and convert
    let registry = ImportRegistry::new();
    let config = registry
        .import_as_project(path)
        .map_err(|e| e.to_string())?;

    let format_name = match format {
        ImportFormat::ReaperRpp => "Reaper RPP",
        ImportFormat::AbletonAls => "Ableton ALS",
        ImportFormat::OpenDawYaml | ImportFormat::OpenDawJson => "OpenDAW",
        ImportFormat::MidiFile => "MIDI",
        _ => "Unknown",
    };

    Ok(ImportProjectResult {
        success: true,
        format: format_name.to_string(),
        project_name: config.name.clone(),
        bpm: 120.0,
        track_count: config.tracks.len(),
        message: format!(
            "Successfully imported {} project: {} ({} tracks, {} BPM)",
            format_name,
            &config.name,
            config.tracks.len(),
            120.0
        ),
    })
}

// ═══════════════════════════════════════════════════════════════════════
// Phase 36 — Note System Commands (Markdown Notes)
// ═══════════════════════════════════════════════════════════════════════

use opendaw_core::notes::{Note, NoteLevel, NoteStore};
use std::sync::Mutex;

/// Global NoteStore (lazy-initialized)
static NOTE_STORE: once_cell::sync::Lazy<Mutex<NoteStore>> =
    once_cell::sync::Lazy::new(|| Mutex::new(NoteStore::new()));

/// Note info for frontend display
#[derive(Debug, Serialize)]
pub struct NoteInfo {
    pub id: String,
    pub title: String,
    pub level: String,
    pub track_id: Option<String>,
    pub preview: String,
    pub updated_at: i64,
    pub tags: Vec<String>,
}

impl From<&Note> for NoteInfo {
    fn from(n: &Note) -> Self {
        Self {
            id: n.id.clone(),
            title: n.title.clone(),
            level: n.level.to_string(),
            track_id: n.track_id.clone(),
            preview: n.preview(),
            updated_at: n.updated_at,
            tags: n.tags.clone(),
        }
    }
}

/// List all notes
#[tauri::command]
pub fn notes_list() -> Result<Vec<NoteInfo>, String> {
    let store = NOTE_STORE.lock().map_err(|e| e.to_string())?;
    Ok(store.read_all_notes().iter().map(NoteInfo::from).collect())
}

/// List notes by level (Global/Project/Track)
#[tauri::command]
pub fn notes_list_by_level(level: String) -> Result<Vec<NoteInfo>, String> {
    let lvl = match level.as_str() {
        "Global" => NoteLevel::Global,
        "Project" => NoteLevel::Project,
        "Track" => NoteLevel::Track,
        _ => return Err(format!("Invalid note level: {}", level)),
    };
    let store = NOTE_STORE.lock().map_err(|e| e.to_string())?;
    Ok(store
        .read_notes_by_level(lvl)
        .iter()
        .map(NoteInfo::from)
        .collect())
}

/// Get a specific note's full content
#[tauri::command]
pub fn notes_get(id: String) -> Result<String, String> {
    let store = NOTE_STORE.lock().map_err(|e| e.to_string())?;
    let note = store
        .get_note(&id)
        .ok_or_else(|| format!("Note not found: {}", id))?;
    Ok(note.content.clone())
}

/// Create or update a note
#[tauri::command]
pub fn notes_save(
    id: Option<String>,
    level: String,
    title: String,
    content: String,
    track_id: Option<String>,
) -> Result<NoteInfo, String> {
    let lvl = match level.as_str() {
        "Global" => NoteLevel::Global,
        "Project" => NoteLevel::Project,
        "Track" => NoteLevel::Track,
        _ => return Err(format!("Invalid note level: {}", level)),
    };

    let mut note = if let Some(tid) = &track_id {
        Note::new_for_track(tid, &title, &content)
    } else {
        Note::new(lvl, &title, &content)
    };

    // If updating existing note, preserve the id
    if let Some(existing_id) = id {
        note.id = existing_id;
    }

    let info = NoteInfo::from(&note);
    let mut store = NOTE_STORE.lock().map_err(|e| e.to_string())?;
    store.save_note(note).map_err(|e| e.to_string())?;
    Ok(info)
}

/// Delete a note
#[tauri::command]
pub fn notes_delete(id: String) -> Result<(), String> {
    let mut store = NOTE_STORE.lock().map_err(|e| e.to_string())?;
    store.delete_note(&id).map_err(|e| e.to_string())
}

/// Search notes by keyword
#[tauri::command]
pub fn notes_search(query: String) -> Result<Vec<NoteInfo>, String> {
    let store = NOTE_STORE.lock().map_err(|e| e.to_string())?;
    Ok(store
        .search_notes(&query)
        .iter()
        .map(NoteInfo::from)
        .collect())
}

/// Get agent summary of all notes (for AI assistant context)
#[tauri::command]
pub fn notes_agent_summary() -> Result<String, String> {
    let store = NOTE_STORE.lock().map_err(|e| e.to_string())?;
    Ok(store.agent_summary())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_engine_state_response_conversion() {
        use audio_engine::state::EngineState;

        assert_eq!(
            EngineStateResponse::from(EngineState::Stopped).state,
            "Stopped"
        );
        assert_eq!(
            EngineStateResponse::from(EngineState::Playing).state,
            "Playing"
        );
        assert_eq!(
            EngineStateResponse::from(EngineState::Paused).state,
            "Paused"
        );
        assert_eq!(
            EngineStateResponse::from(EngineState::Recording).state,
            "Recording"
        );
    }

    #[test]
    fn test_registry_stats_response_conversion() {
        use opendaw_extension::registry::RegistryStats;

        let stats = RegistryStats {
            plugins: 5,
            scripts: 3,
            models: 2,
            hook_events: 10,
        };
        let resp: RegistryStatsResponse = stats.into();
        assert_eq!(resp.plugins, 5);
        assert_eq!(resp.scripts, 3);
        assert_eq!(resp.models, 2);
        assert_eq!(resp.hook_events, 10);
    }
}
