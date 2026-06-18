//! OpenDAW Desktop — Tauri Shell (v1.0.0)
//!
//! OpenDAW v1.0.0 is pure Rust. No Python backend required.

mod commands;
mod state;

pub use state::AppState;

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    println!("╔══════════════════════════════════════════╗");
    println!("║         OpenDAW Desktop v1.0.0           ║");
    println!("╚══════════════════════════════════════════╝");
    println!("[OpenDAW] Pure Rust — no Python backend needed");

    // Register cleanup on Ctrl+C
    let _ = ctrlc::set_handler(|| {
        println!("\n[OpenDAW] Shutting down...");
        std::process::exit(0);
    });

    // Launch Tauri
    println!("[OpenDAW] Launching window...");

    // Initialize app state
    let app_state = state::AppState::new();

    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .manage(app_state)
        .invoke_handler(tauri::generate_handler![
            // Project Management
            commands::init_project,
            commands::list_projects,
            commands::get_project,
            commands::save_project,
            commands::delete_project,
            // Transport
            commands::transport_play,
            commands::transport_stop,
            commands::transport_pause,
            commands::get_position,
            commands::set_position,
            // Track Management
            commands::add_track,
            commands::remove_track,
            commands::get_tracks,
            commands::set_track_volume,
            commands::set_track_pan,
            commands::mute_track,
            commands::unmute_track,
            // Audio Engine
            commands::load_audio,
            commands::render,
            commands::export_wav,
            // Plugin Management
            commands::list_plugins,
            commands::scan_plugins,
            commands::insert_plugin,
            commands::remove_plugin,
            // AI Agent
            commands::agent_chat,
            commands::agent_analyze,
            // System
            commands::get_status,
            commands::get_devices,
            commands::set_device,
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");

    println!("[OpenDAW] Application closed.");
}
