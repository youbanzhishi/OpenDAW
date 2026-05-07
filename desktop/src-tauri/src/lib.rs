//! VCMix Desktop — Tauri Shell (Phase 8.5)
//!
//! This library crate provides the Tauri plugin/commands for the VCMix desktop app.
//! The main logic for spawning the Python backend and health-checking lives here.

use serde::Serialize;
use std::sync::Mutex;
use tauri::State;

// ── Shared State ─────────────────────────────────────────────────────────

/// Holds the PID of the spawned Python backend process.
pub struct BackendState {
    pub pid: Mutex<Option<u32>>,
}

impl Default for BackendState {
    fn default() -> Self {
        Self {
            pid: Mutex::new(None),
        }
    }
}

// ── Tauri Commands ───────────────────────────────────────────────────────

#[derive(Debug, Serialize)]
pub struct HealthStatus {
    pub healthy: bool,
    pub message: String,
}

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
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
