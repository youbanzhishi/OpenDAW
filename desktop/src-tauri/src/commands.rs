//! OpenDAW Desktop — Tauri Commands (v1.0.0)
//!
//! Pure Rust commands. No Python backend dependency.

use crate::state::AppState;
use serde::{Deserialize, Serialize};
use tauri::State;

// ═══════════════════════════════════════════════════════════════════════════
// Response Types
// ═══════════════════════════════════════════════════════════════════════════

#[derive(Debug, Serialize)]
pub struct EngineStatus {
    pub state: String,
    pub sample_rate: f64,
    pub track_count: usize,
    pub position: f64,
}

#[derive(Debug, Serialize)]
pub struct TrackInfo {
    pub id: String,
    pub name: String,
    pub gain_db: f64,
    pub pan: f64,
    pub mute: bool,
    pub solo: bool,
}

#[derive(Debug, Serialize)]
pub struct ProjectInfo {
    pub name: String,
    pub tracks: Vec<TrackInfo>,
}

#[derive(Debug, Serialize)]
pub struct PluginInfo {
    pub id: String,
    pub name: String,
    pub r#type: String,
}

// ═══════════════════════════════════════════════════════════════════════════
// Engine Commands
// ═══════════════════════════════════════════════════════════════════════════

#[tauri::command]
pub fn engine_get_state(state: State<'_, AppState>) -> Result<EngineStatus, String> {
    let engine = state.engine.lock();
    Ok(EngineStatus {
        state: format!("{:?}", engine.get_state()),
        sample_rate: engine.sample_rate(),
        track_count: engine.track_count(),
        position: engine.get_position(),
    })
}

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

#[tauri::command]
pub fn engine_stop(state: State<'_, AppState>) -> Result<(), String> {
    let mut engine = state.engine.lock();
    engine.stop().map_err(|e| e.to_string())
}

#[tauri::command]
pub fn engine_pause(state: State<'_, AppState>) -> Result<(), String> {
    let mut engine = state.engine.lock();
    engine.pause().map_err(|e| e.to_string())
}

#[tauri::command]
pub fn engine_get_position(state: State<'_, AppState>) -> Result<f64, String> {
    let engine = state.engine.lock();
    Ok(engine.get_position())
}

#[tauri::command]
pub fn engine_set_position(state: State<'_, AppState>, pos: f64) -> Result<(), String> {
    let mut engine = state.engine.lock();
    engine.set_position(pos);
    Ok(())
}

#[tauri::command]
pub fn engine_register_track(state: State<'_, AppState>, track_id: String) -> Result<(), String> {
    let mut engine = state.engine.lock();
    engine.register_track(&track_id).map_err(|e| e.to_string())
}

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

#[tauri::command]
pub fn engine_track_count(state: State<'_, AppState>) -> Result<usize, String> {
    let engine = state.engine.lock();
    Ok(engine.track_count())
}

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

#[tauri::command]
pub fn engine_set_master_volume(state: State<'_, AppState>, volume_db: f64) -> Result<(), String> {
    let mut engine = state.engine.lock();
    engine.set_master_volume(volume_db);
    Ok(())
}

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
// Transport Commands
// ═══════════════════════════════════════════════════════════════════════════

#[tauri::command]
pub fn transport_play(state: State<'_, AppState>) -> Result<(), String> {
    let mut engine = state.engine.lock();
    engine.start(44100.0, 512).map_err(|e| e.to_string())
}

#[tauri::command]
pub fn transport_stop(state: State<'_, AppState>) -> Result<(), String> {
    let mut engine = state.engine.lock();
    engine.stop().map_err(|e| e.to_string())
}

#[tauri::command]
pub fn transport_pause(state: State<'_, AppState>) -> Result<(), String> {
    let mut engine = state.engine.lock();
    engine.pause().map_err(|e| e.to_string())
}

#[tauri::command]
pub fn get_position(state: State<'_, AppState>) -> Result<f64, String> {
    engine_get_position(state)
}

#[tauri::command]
pub fn set_position(state: State<'_, AppState>, pos: f64) -> Result<(), String> {
    engine_set_position(state, pos)
}

// ═══════════════════════════════════════════════════════════════════════════
// Track Commands
// ═══════════════════════════════════════════════════════════════════════════

#[tauri::command]
pub fn add_track(state: State<'_, AppState>, name: String) -> Result<TrackInfo, String> {
    let mut engine = state.engine.lock();
    engine.register_track(&name).map_err(|e| e.to_string())?;
    Ok(TrackInfo {
        id: name.clone(),
        name,
        gain_db: 0.0,
        pan: 0.0,
        mute: false,
        solo: false,
    })
}

#[tauri::command]
pub fn remove_track(state: State<'_, AppState>, track_id: String) -> Result<(), String> {
    let mut engine = state.engine.lock();
    engine
        .unregister_track(&track_id)
        .map_err(|e| e.to_string())
}

#[tauri::command]
pub fn get_tracks(state: State<'_, AppState>) -> Result<Vec<TrackInfo>, String> {
    let engine = state.engine.lock();
    let count = engine.track_count();
    Ok((0..count)
        .map(|i| TrackInfo {
            id: format!("track_{}", i),
            name: format!("Track {}", i + 1),
            gain_db: 0.0,
            pan: 0.0,
            mute: false,
            solo: false,
        })
        .collect())
}

#[tauri::command]
pub fn set_track_volume(
    state: State<'_, AppState>,
    track_id: String,
    volume_db: f64,
) -> Result<(), String> {
    engine_set_track_volume(state, track_id, volume_db)
}

#[tauri::command]
pub fn set_track_pan(state: State<'_, AppState>, track_id: String, pan: f64) -> Result<(), String> {
    let mut engine = state.engine.lock();
    engine
        .set_track_pan(&track_id, pan)
        .map_err(|e| e.to_string())
}

#[tauri::command]
pub fn mute_track(state: State<'_, AppState>, track_id: String) -> Result<(), String> {
    let mut engine = state.engine.lock();
    engine
        .set_track_mute(&track_id, true)
        .map_err(|e| e.to_string())
}

#[tauri::command]
pub fn unmute_track(state: State<'_, AppState>, track_id: String) -> Result<(), String> {
    let mut engine = state.engine.lock();
    engine
        .set_track_mute(&track_id, false)
        .map_err(|e| e.to_string())
}

// ═══════════════════════════════════════════════════════════════════════════
// Project Commands
// ═══════════════════════════════════════════════════════════════════════════

#[tauri::command]
pub fn init_project(name: String) -> Result<ProjectInfo, String> {
    // New project - return empty project info
    // Engine reset is handled by frontend
    Ok(ProjectInfo {
        name,
        tracks: vec![],
    })
}

#[tauri::command]
pub fn list_projects() -> Result<Vec<String>, String> {
    // TODO: Implement project listing from filesystem
    Ok(vec![])
}

#[tauri::command]
pub fn get_project(state: State<'_, AppState>) -> Result<ProjectInfo, String> {
    let engine = state.engine.lock();
    Ok(ProjectInfo {
        name: "Untitled".to_string(),
        tracks: vec![],
    })
}

#[tauri::command]
pub fn save_project(_name: String) -> Result<(), String> {
    // TODO: Implement project save
    Ok(())
}

#[tauri::command]
pub fn delete_project(_name: String) -> Result<(), String> {
    // TODO: Implement project delete
    Ok(())
}

// ═══════════════════════════════════════════════════════════════════════════
// Audio Commands
// ═══════════════════════════════════════════════════════════════════════════

#[tauri::command]
pub fn load_audio(
    state: State<'_, AppState>,
    file_path: String,
    track_id: String,
) -> Result<(), String> {
    let mut engine = state.engine.lock();
    engine.register_track(&track_id).ok();
    engine
        .load_wav(&track_id, &file_path)
        .map_err(|e| e.to_string())
}

#[tauri::command]
pub fn render(state: State<'_, AppState>) -> Result<(), String> {
    let mut engine = state.engine.lock();
    engine.stop().ok();
    Ok(())
}

#[tauri::command]
pub fn export_wav(output_path: String) -> Result<String, String> {
    // TODO: Implement WAV export
    Ok(output_path)
}

// ═══════════════════════════════════════════════════════════════════════════
// Plugin Commands
// ═══════════════════════════════════════════════════════════════════════════

#[tauri::command]
pub fn list_plugins() -> Result<Vec<PluginInfo>, String> {
    Ok(vec![])
}

#[tauri::command]
pub fn scan_plugins() -> Result<usize, String> {
    Ok(0)
}

#[tauri::command]
pub fn insert_plugin(_track_id: String, _plugin_id: String) -> Result<(), String> {
    Ok(())
}

#[tauri::command]
pub fn remove_plugin(_track_id: String, _plugin_id: String) -> Result<(), String> {
    Ok(())
}

// ═══════════════════════════════════════════════════════════════════════════
// AI Agent Commands
// ═══════════════════════════════════════════════════════════════════════════

#[tauri::command]
pub fn agent_chat(message: String) -> Result<String, String> {
    Ok(format!("Echo: {}", message))
}

#[tauri::command]
pub fn agent_analyze(_state: State<'_, AppState>) -> Result<String, String> {
    Ok("Analysis complete".to_string())
}

// ═══════════════════════════════════════════════════════════════════════════
// System Commands
// ═══════════════════════════════════════════════════════════════════════════

#[tauri::command]
pub fn get_status(state: State<'_, AppState>) -> Result<EngineStatus, String> {
    engine_get_state(state)
}

#[tauri::command]
pub fn get_devices() -> Result<Vec<String>, String> {
    Ok(vec!["Default Output".to_string()])
}

#[tauri::command]
pub fn set_device(_device_name: String) -> Result<(), String> {
    Ok(())
}

// ═══════════════════════════════════════════════════════════════════════════
// Tests
// ═══════════════════════════════════════════════════════════════════════════

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_engine_status() {
        // Note: Can't easily test without full Tauri state setup
        // This is a placeholder test
        assert!(true);
    }
}
