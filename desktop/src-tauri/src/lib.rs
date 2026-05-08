//! VCMix Desktop — Tauri Shell (Phase 13)
//!
//! Tauri v2 desktop app for VCMix. Commands and entry point in one file.
//! The run() function spawns the Python backend, waits for it to be healthy,
//! then launches the Tauri window.

use serde::{Deserialize, Serialize};
use std::process::{Child, Command};
use std::sync::Mutex;
use std::thread;
use std::time::Duration;
use tauri::State;

// ── Configuration ────────────────────────────────────────────────────────

const BACKEND_PORT: u16 = 8000;
const HEALTH_CHECK_TIMEOUT_SECS: u64 = 30;
const HEALTH_CHECK_INTERVAL_SECS: u64 = 1;
const BACKEND_MODULE: &str = "vcmix.web";

// ── Shared State ─────────────────────────────────────────────────────────

pub struct BackendState {
    pub pid: Mutex<Option<u32>>,
    pub base_url: String,
}

impl Default for BackendState {
    fn default() -> Self {
        Self {
            pid: Mutex::new(None),
            base_url: format!("http://localhost:{}", BACKEND_PORT),
        }
    }
}

static BACKEND_PROCESS: Mutex<Option<Child>> = Mutex::new(None);

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

// ── Backend Management ───────────────────────────────────────────────────

fn spawn_backend() -> Result<u32, String> {
    let (cmd, args) = if cfg!(debug_assertions) {
        ("python", vec!["-m", BACKEND_MODULE])
    } else {
        let binary_path = get_bundled_backend_path();
        (binary_path.as_str(), vec![])
    };

    println!("[VCMix] Spawning backend: {} {}", cmd, args.join(" "));

    let child = Command::new(cmd)
        .args(&args)
        .env("VCMIX_PORT", BACKEND_PORT.to_string())
        .env("VCMIX_NO_OPEN_BROWSER", "1")
        .spawn()
        .map_err(|e| format!("Failed to spawn Python backend: {}", e))?;

    let pid = child.id();

    {
        let mut guard = BACKEND_PROCESS
            .lock()
            .map_err(|e| format!("Lock poisoned: {}", e))?;
        *guard = Some(child);
    }

    println!("[VCMix] Backend spawned with PID {}", pid);
    Ok(pid)
}

fn get_bundled_backend_path() -> String {
    if cfg!(target_os = "macos") {
        "python".to_string()
    } else if cfg!(target_os = "windows") {
        "vcmix-backend.exe".to_string()
    } else {
        "vcmix-backend".to_string()
    }
}

fn wait_for_backend(port: u16) -> Result<(), String> {
    let url = format!("http://localhost:{}/api/health", port);
    let client = reqwest::blocking::Client::builder()
        .timeout(Duration::from_secs(2))
        .build()
        .map_err(|e| format!("HTTP client error: {}", e))?;

    let mut attempts = 0;
    let max_attempts = HEALTH_CHECK_TIMEOUT_SECS / HEALTH_CHECK_INTERVAL_SECS;

    while attempts < max_attempts {
        match client.get(&url).send() {
            Ok(resp) if resp.status().is_success() => {
                println!("[VCMix] Backend is healthy after {}s", attempts * HEALTH_CHECK_INTERVAL_SECS);
                return Ok(());
            }
            Ok(resp) => {
                println!("[VCMix] Backend returned {}, retrying... ({}/{})", resp.status(), attempts + 1, max_attempts);
            }
            Err(e) => {
                println!("[VCMix] Backend not ready: {} ({}/{})", e, attempts + 1, max_attempts);
            }
        }
        attempts += 1;
        thread::sleep(Duration::from_secs(HEALTH_CHECK_INTERVAL_SECS));
    }

    Err(format!("Backend did not become healthy within {}s", HEALTH_CHECK_TIMEOUT_SECS))
}

fn kill_backend() {
    let mut guard = match BACKEND_PROCESS.lock() {
        Ok(g) => g,
        Err(_) => {
            eprintln!("[VCMix] Failed to acquire lock for backend cleanup");
            return;
        }
    };
    if let Some(ref mut child) = *guard {
        match child.kill() {
            Ok(_) => println!("[VCMix] Backend process killed"),
            Err(e) => eprintln!("[VCMix] Failed to kill backend: {}", e),
        }
        let _ = child.wait();
    }
}

// ── Tauri Commands ───────────────────────────────────────────────────────

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
pub fn set_backend_pid(state: State<'_, BackendState>, pid: u32) -> Result<(), String> {
    let mut guard = state.pid.lock().map_err(|e| e.to_string())?;
    *guard = Some(pid);
    Ok(())
}

#[tauri::command]
pub fn get_backend_pid(state: State<'_, BackendState>) -> Result<Option<u32>, String> {
    let guard = state.pid.lock().map_err(|e| e.to_string())?;
    Ok(*guard)
}

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
        job_id: data.get("job_id").and_then(|v| v.as_str()).unwrap_or("unknown").to_string(),
        status: data.get("status").and_then(|v| v.as_str()).unwrap_or("unknown").to_string(),
        message: data.get("message").and_then(|v| v.as_str()).unwrap_or("").to_string(),
    })
}

#[tauri::command]
pub async fn get_analysis(
    state: State<'_, BackendState>,
    project_id: String,
) -> Result<AnalysisResult, String> {
    let url = format!("{}/api/v1/projects/{}/analysis", state.base_url, project_id);

    let resp = reqwest::get(&url)
        .await
        .map_err(|e| format!("Request failed: {}", e))?;

    let data: serde_json::Value = resp
        .json()
        .await
        .map_err(|e| format!("JSON parse error: {}", e))?;

    Ok(AnalysisResult {
        project: data.get("project").and_then(|v| v.as_str()).unwrap_or("").to_string(),
        bpm: data.get("bpm").and_then(|v| v.as_f64()).unwrap_or(120.0),
        sample_rate: data.get("sample_rate").and_then(|v| v.as_u64()).unwrap_or(44100) as u32,
        tracks: data.get("tracks").and_then(|v| v.as_array()).cloned().unwrap_or_default(),
        master: data.get("master").cloned().unwrap_or(serde_json::Value::Null),
    })
}

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
            name: p.get("name").and_then(|v| v.as_str()).unwrap_or("").to_string(),
            description: p.get("description").and_then(|v| v.as_str()).unwrap_or("").to_string(),
        })
        .collect();

    Ok(PresetList { count: presets.len(), presets })
}

#[tauri::command]
pub async fn open_file_dialog(
    _title: String,
    _filters: Vec<Vec<String>>,
) -> Result<FileDialogResult, String> {
    Ok(FileDialogResult { path: None, cancelled: true })
}

#[tauri::command]
pub async fn get_waveform(
    state: State<'_, BackendState>,
    project_id: String,
    track: String,
) -> Result<WaveformData, String> {
    let url = format!("{}/api/v1/waveform/{}/{}", state.base_url, project_id, track);

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
    state: State<'_, BackendState>,
    project_id: String,
    track: String,
) -> Result<SpectrumData, String> {
    let url = format!("{}/api/v1/spectrum/{}/{}", state.base_url, project_id, track);

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
    state: State<'_, BackendState>,
    project_id: String,
    track: String,
) -> Result<MidiNoteData, String> {
    let url = format!("{}/api/v1/midi/{}/{}", state.base_url, project_id, track);

    let resp = reqwest::get(&url).await.map_err(|e| format!("Request failed: {}", e))?;
    let data: serde_json::Value = resp.json().await.map_err(|e| format!("JSON parse error: {}", e))?;

    Ok(MidiNoteData {
        notes: data.get("notes").and_then(|v| v.as_array()).cloned().unwrap_or_default(),
        note_count: data.get("note_count").and_then(|v| v.as_u64()).unwrap_or(0) as usize,
        bpm: data.get("bpm").and_then(|v| v.as_f64()).unwrap_or(120.0),
        total_beats: data.get("total_beats").and_then(|v| v.as_f64()).unwrap_or(0.0),
    })
}

// ── Tauri Entry Point ────────────────────────────────────────────────────

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    println!("╔══════════════════════════════════════════╗");
    println!("║   VCMix Desktop — Tauri Shell           ║");
    println!("╚══════════════════════════════════════════╝");

    // Spawn Python backend
    match spawn_backend() {
        Ok(pid) => println!("[VCMix] Backend PID: {}", pid),
        Err(e) => {
            eprintln!("[VCMix] FATAL: {}", e);
            eprintln!("[VCMix] Make sure Python and vcmix are installed");
            std::process::exit(1);
        }
    }

    // Wait for backend
    println!("[VCMix] Waiting for backend on port {}...", BACKEND_PORT);
    if let Err(e) = wait_for_backend(BACKEND_PORT) {
        eprintln!("[VCMix] FATAL: {}", e);
        kill_backend();
        std::process::exit(1);
    }

    // Register cleanup on Ctrl+C
    let _ = ctrlc::set_handler(|| {
        println!("\n[VCMix] Shutting down...");
        kill_backend();
        std::process::exit(0);
    });

    // Launch Tauri
    println!("[VCMix] Launching Tauri window → http://localhost:{}", BACKEND_PORT);

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

    println!("[VCMix] Application closing, cleaning up backend...");
    kill_backend();
}
