//! VCMix Desktop — Tauri Shell (Phase 13)
//!
//! This library crate provides the Tauri plugin/commands for the VCMix desktop app.
//! Phase 13 adds: render_project, get_analysis, list_presets, open_file_dialog,
//! get_waveform, get_spectrum, get_midi_notes commands.

use serde::{Deserialize, Serialize};
use std::sync::Mutex;
use tauri::State;

// ── Shared State ─────────────────────────────────────────────────────────

/// Holds the PID of the spawned Python backend process.
pub struct BackendState {
    pub pid: Mutex<Option<u32>>,
    /// Base URL for the FastAPI backend
    pub base_url: String,
}

impl Default for BackendState {
    fn default() -> Self {
        Self {
            pid: Mutex::new(None),
            base_url: "http://localhost:8000".to_string(),
        }
    }
}

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

// ── Tauri Commands ───────────────────────────────────────────────────────

/// Check if the FastAPI backend is responding.
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

/// Record the PID of the spawned Python process (called from main.rs).
#[tauri::command]
pub fn set_backend_pid(state: State<'_, BackendState>, pid: u32) -> Result<(), String> {
    let mut guard = state.pid.lock().map_err(|e| e.to_string())?;
    *guard = Some(pid);
    Ok(())
}

/// Get the recorded backend PID.
#[tauri::command]
pub fn get_backend_pid(state: State<'_, BackendState>) -> Result<Option<u32>, String> {
    let guard = state.pid.lock().map_err(|e| e.to_string())?;
    Ok(*guard)
}

/// Render a VCMix project by calling the backend API.
#[tauri::command]
pub async fn render_project(
    state: State<'_, BackendState>,
    yaml_path: String,
) -> Result<RenderResult, String> {
    let url = format!(
        "{}/api/render/file?project_path={}",
        state.base_url,
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

/// Get audio analysis for a project from the AI Agent API.
#[tauri::command]
pub async fn get_analysis(
    state: State<'_, BackendState>,
    project_id: String,
) -> Result<AnalysisResult, String> {
    let url = format!(
        "{}/api/v1/projects/{}/analysis",
        state.base_url, project_id
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

/// List available effect presets from the backend.
#[tauri::command]
pub async fn list_presets(state: State<'_, BackendState>) -> Result<PresetList, String> {
    let url = format!("{}/api/presets", state.base_url);

    let resp = reqwest::get(&url)
        .await
        .map_err(|e| format!("Request failed: {}", e))?;

    let data: serde_json::Value = resp
        .json()
        .await
        .map_err(|e| format!("JSON parse error: {}", e))?;

    let presets = data
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

/// Open a native file dialog and return the selected path.
///
/// Uses Tauri's dialog plugin to open a file picker.
/// In production, integrate with tauri-plugin-dialog.
#[tauri::command]
pub async fn open_file_dialog(
    title: String,
    filters: Vec<Vec<String>>,
) -> Result<FileDialogResult, String> {
    // Note: Tauri 2.x file dialog requires tauri-plugin-dialog.
    // This is a placeholder that returns a path; in production,
    // integrate with tauri-plugin-dialog.
    Ok(FileDialogResult {
        path: None,
        cancelled: true,
    })
}

/// Get waveform peak data for a track.
#[tauri::command]
pub async fn get_waveform(
    state: State<'_, BackendState>,
    project_id: String,
    track: String,
) -> Result<WaveformData, String> {
    let url = format!(
        "{}/api/v1/waveform/{}/{}",
        state.base_url, project_id, track
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
        channels: data
            .get("channels")
            .and_then(|v| v.as_u64())
            .unwrap_or(1) as u32,
    })
}

/// Get FFT spectrum data for a track.
#[tauri::command]
pub async fn get_spectrum(
    state: State<'_, BackendState>,
    project_id: String,
    track: String,
) -> Result<SpectrumData, String> {
    let url = format!(
        "{}/api/v1/spectrum/{}/{}",
        state.base_url, project_id, track
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

/// Get MIDI note data for a track.
#[tauri::command]
pub async fn get_midi_notes(
    state: State<'_, BackendState>,
    project_id: String,
    track: String,
) -> Result<MidiNoteData, String> {
    let url = format!(
        "{}/api/v1/midi/{}/{}",
        state.base_url, project_id, track
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
        note_count: data
            .get("note_count")
            .and_then(|v| v.as_u64())
            .unwrap_or(0) as usize,
        bpm: data.get("bpm").and_then(|v| v.as_f64()).unwrap_or(120.0),
        total_beats: data
            .get("total_beats")
            .and_then(|v| v.as_f64())
            .unwrap_or(0.0),
    })
}

// ── Tauri Plugin Registration ────────────────────────────────────────────

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .manage(BackendState::default())
        .invoke_handler(tauri::generate_handler![
            check_backend_health,
            set_backend_pid,
            get_backend_pid,
            render_project,
            get_analysis,
            list_presets,
            open_file_dialog,
            get_waveform,
            get_spectrum,
            get_midi_notes,
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
