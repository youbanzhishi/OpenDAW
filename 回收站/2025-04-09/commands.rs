//! Tauri Commands for VCMix Desktop

use serde::{Deserialize, Serialize};
use tauri::State;
use crate::state::AppState;

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
    pub bpm: f64,
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
    pub bpm: f64,
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
    let resp = client.post(&url).send().await.map_err(|e| format!("Request failed: {}", e))?;
    let data: serde_json::Value = resp.json().await.map_err(|e| format!("JSON parse error: {}", e))?;
    Ok(RenderResult {
        job_id: data.get("job_id").and_then(|v| v.as_str()).unwrap_or("unknown").to_string(),
        status: data.get("status").and_then(|v| v.as_str()).unwrap_or("unknown").to_string(),
        message: data.get("message").and_then(|v| v.as_str()).unwrap_or("").to_string(),
    })
}

#[tauri::command]
pub async fn get_analysis(
    state: State<'_, AppState>,
    project_id: String,
) -> Result<AnalysisResult, String> {
    let url = format!("{}/api/v1/projects/{}/analysis", state.backend.base_url, project_id);
    let resp = reqwest::get(&url).await.map_err(|e| format!("Request failed: {}", e))?;
    let data: serde_json::Value = resp.json().await.map_err(|e| format!("JSON parse error: {}", e))?;
    Ok(AnalysisResult {
        project: data.get("project").and_then(|v| v.as_str()).unwrap_or("").to_string(),
        bpm: data.get("bpm").and_then(|v| v.as_f64()).unwrap_or(120.0),
        sample_rate: data.get("sample_rate").and_then(|v| v.as_u64()).unwrap_or(44100) as u32,
        tracks: data.get("tracks").and_then(|v| v.as_array()).cloned().unwrap_or_default(),
        master: data.get("master").cloned().unwrap_or(serde_json::Value::Null),
    })
}

#[tauri::command]
pub async fn list_presets(state: State<'_, AppState>) -> Result<PresetList, String> {
    let url = format!("{}/api/presets", state.backend.base_url);
    let resp = reqwest::get(&url).await.map_err(|e| format!("Request failed: {}", e))?;
    let data: serde_json::Value = resp.json().await.map_err(|e| format!("JSON parse error: {}", e))?;
    let presets: Vec<PresetInfo> = data.get("presets").and_then(|v| v.as_array()).cloned().unwrap_or_default()
        .iter().map(|p| PresetInfo {
            name: p.get("name").and_then(|v| v.as_str()).unwrap_or("").to_string(),
            description: p.get("description").and_then(|v| v.as_str()).unwrap_or("").to_string(),
        }).collect();
    Ok(PresetList { count: presets.len(), presets })
}

#[tauri::command]
pub async fn open_file_dialog(_title: String, _filters: Vec<Vec<String>>) -> Result<FileDialogResult, String> {
    Ok(FileDialogResult { path: None, cancelled: true })
}

#[tauri::command]
pub async fn get_waveform(
    state: State<'_, AppState>, project_id: String, track: String,
) -> Result<WaveformData, String> {
    let url = format!("{}/api/v1/waveform/{}/{}", state.backend.base_url, project_id, track);
    let resp = reqwest::get(&url).await.map_err(|e| format!("Request failed: {}", e))?;
    let data: serde_json::Value = resp.json().await.map_err(|e| format!("JSON parse error: {}", e))?;
    Ok(WaveformData {
        peaks: data.get("peaks").and_then(|v| v.as_array()).cloned().unwrap_or_default().iter().filter_map(|v| v.as_f64()).collect(),
        sample_count: data.get("sample_count").and_then(|v| v.as_u64()).unwrap_or(0) as usize,
        sample_rate: data.get("sample_rate").and_then(|v| v.as_u64()).unwrap_or(44100) as u32,
        duration_s: data.get("duration_s").and_then(|v| v.as_f64()).unwrap_or(0.0),
        channels: data.get("channels").and_then(|v| v.as_u64()).unwrap_or(1) as u32,
    })
}

#[tauri::command]
pub async fn get_spectrum(
    state: State<'_, AppState>, project_id: String, track: String,
) -> Result<SpectrumData, String> {
    let url = format!("{}/api/v1/spectrum/{}/{}", state.backend.base_url, project_id, track);
    let resp = reqwest::get(&url).await.map_err(|e| format!("Request failed: {}", e))?;
    let data: serde_json::Value = resp.json().await.map_err(|e| format!("JSON parse error: {}", e))?;
    Ok(SpectrumData {
        frequencies: data.get("frequencies").and_then(|v| v.as_array()).cloned().unwrap_or_default().iter().filter_map(|v| v.as_f64()).collect(),
        magnitudes: data.get("magnitudes").and_then(|v| v.as_array()).cloned().unwrap_or_default().iter().filter_map(|v| v.as_f64()).collect(),
        sample_rate: data.get("sample_rate").and_then(|v| v.as_u64()).unwrap_or(44100) as u32,
        fft_size: data.get("fft_size").and_then(|v| v.as_u64()).unwrap_or(2048) as usize,
    })
}

#[tauri::command]
pub async fn get_midi_notes(
    state: State<'_, AppState>, project_id: String, track: String,
) -> Result<MidiNoteData, String> {
    let url = format!("{}/api/v1/midi/{}/{}", state.backend.base_url, project_id, track);
    let resp = reqwest::get(&url).await.map_err(|e| format!("Request failed: {}", e))?;
    let data: serde_json::Value = resp.json().await.map_err(|e| format!("JSON parse error: {}", e))?;
    Ok(MidiNoteData {
        notes: data.get("notes").and_then(|v| v.as_array()).cloned().unwrap_or_default(),
        note_count: data.get("note_count").and_then(|v| v.as_u64()).unwrap_or(0) as usize,
        bpm: data.get("bpm").and_then(|v| v.as_f64()).unwrap_or(120.0),
        total_beats: data.get("total_beats").and_then(|v| v.as_f64()).unwrap_or(0.0),
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
    pub bpm: f64,
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
    pub bpm: f64,
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
    let resp = reqwest::get(&url).await.map_err(|e| format!("Request failed: {}", e))?;
    let data: serde_json::Value = resp.json().await.map_err(|e| format!("JSON parse error: {}", e))?;
    let projects = data.get("projects").and_then(|v| v.as_array()).cloned().unwrap_or_default();
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
    let resp = reqwest::get(&url).await.map_err(|e| format!("Request failed: {}", e))?;
    let data: serde_json::Value = resp.json().await.map_err(|e| format!("JSON parse error: {}", e))?;

    let tracks: Vec<TrackInfo> = data.get("tracks")
        .and_then(|v| v.as_array())
        .cloned()
        .unwrap_or_default()
        .iter()
        .map(|t| TrackInfo {
            id: t.get("id").or(t.get("name")).and_then(|v| v.as_str()).unwrap_or("").to_string(),
            name: t.get("name").and_then(|v| v.as_str()).unwrap_or("Track").to_string(),
            r#type: t.get("type").and_then(|v| v.as_str()).unwrap_or("audio").to_string(),
            gain_db: t.get("gain").and_then(|v| v.as_f64()).unwrap_or(0.0),
            pan: t.get("pan").and_then(|v| v.as_f64()).unwrap_or(0.0),
            mute: t.get("mute").and_then(|v| v.as_bool()).unwrap_or(false),
            solo: t.get("solo").and_then(|v| v.as_bool()).unwrap_or(false),
        })
        .collect();

    Ok(ProjectInfo {
        id: project_id,
        name: data.get("name").and_then(|v| v.as_str()).unwrap_or("Untitled").to_string(),
        bpm: data.get("bpm").and_then(|v| v.as_f64()).unwrap_or(120.0),
        sample_rate: data.get("sample_rate").and_then(|v| v.as_u64()).unwrap_or(44100) as u32,
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
    let data: serde_json::Value = resp.json().await.map_err(|e| format!("JSON parse error: {}", e))?;
    Ok(data)
}

#[tauri::command]
pub async fn add_track(
    state: State<'_, AppState>,
    project_id: String,
    name: String,
    track_type: String,
) -> Result<serde_json::Value, String> {
    let url = format!("{}/api/v1/projects/{}/tracks", state.backend.base_url, project_id);
    let client = reqwest::Client::new();
    let resp = client
        .post(&url)
        .json(&serde_json::json!({ "name": name, "type": track_type }))
        .send()
        .await
        .map_err(|e| format!("Request failed: {}", e))?;
    let data: serde_json::Value = resp.json().await.map_err(|e| format!("JSON parse error: {}", e))?;
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

    let data: serde_json::Value = resp.json().await.map_err(|e| format!("JSON parse error: {}", e))?;

    Ok(AgentChatResponse {
        message: data.get("message").and_then(|v| v.as_str()).unwrap_or("").to_string(),
        actions: data.get("actions").and_then(|v| v.as_array()).cloned().unwrap_or_default(),
        thinking: data.get("thinking").and_then(|v| v.as_str()).unwrap_or("").to_string(),
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
    let data: serde_json::Value = resp.json().await.map_err(|e| format!("JSON parse error: {}", e))?;
    Ok(data)
}
