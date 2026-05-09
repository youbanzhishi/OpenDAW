//! VCMix Desktop — Tauri Shell (v0.24.0)
//!
//! Tauri v2 desktop app for VCMix. Modular structure:
//!   - backend.rs  → BackendState, spawn/kill/wait backend
//!   - state.rs    → AppState, Rust engine + Python backend unified state
//!   - commands.rs → All #[tauri::command] functions
//!   - lib.rs      → Module declarations + run() entry point
//!   - main.rs     → fn main() { vcmix_desktop_lib::run() }
//!
//! v0.24.0 additions:
//!   - transport_play / transport_stop / list_projects / get_project
//!   - create_project / add_track / delete_track / agent_chat / automix_project

mod backend;
mod commands;
mod state;

pub use backend::BackendState;
pub use state::AppState;

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    println!("╔══════════════════════════════════════════╗");
    println!("║   VCMix Desktop — Tauri Shell (v0.24.0) ║");
    println!("╚══════════════════════════════════════════╝");

    // Spawn Python backend
    match backend::spawn_backend() {
        Ok(pid) => println!("[VCMix] Backend PID: {}", pid),
        Err(e) => {
            eprintln!("[VCMix] FATAL: {}", e);
            eprintln!("[VCMix] Make sure Python and vcmix are installed");
            std::process::exit(1);
        }
    }

    // Wait for backend
    println!("[VCMix] Waiting for backend on port {}...", backend::BACKEND_PORT);
    if let Err(e) = backend::wait_for_backend(backend::BACKEND_PORT) {
        eprintln!("[VCMix] FATAL: {}", e);
        backend::kill_backend();
        std::process::exit(1);
    }

    // Register cleanup on Ctrl+C
    let _ = ctrlc::set_handler(|| {
        println!("\n[VCMix] Shutting down...");
        backend::kill_backend();
        std::process::exit(0);
    });

    // Launch Tauri
    println!("[VCMix] Launching Tauri window → serving frontend from ./frontend");

    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .manage(state::AppState::new())
        .invoke_handler(tauri::generate_handler![
            // Phase 13 commands
            commands::check_backend_health,
            commands::set_backend_pid,
            commands::get_backend_pid,
            commands::render_project,
            commands::get_analysis,
            commands::list_presets,
            commands::open_file_dialog,
            commands::get_waveform,
            commands::get_spectrum,
            commands::get_midi_notes,
            // v0.24.0 commands
            commands::transport_play,
            commands::transport_stop,
            commands::list_projects,
            commands::get_project,
            commands::create_project,
            commands::add_track,
            commands::delete_track,
            commands::agent_chat,
            commands::automix_project,
            // v0.24.0 Engine Commands
            commands::engine_get_state,
            commands::engine_start,
            commands::engine_stop,
            commands::engine_pause,
            commands::engine_get_position,
            commands::engine_set_position,
            commands::engine_register_track,
            commands::engine_load_wav,
            commands::engine_track_count,
            commands::engine_set_track_volume,
            commands::engine_set_master_volume,
            commands::engine_toggle_track_mute,
            // v0.24.0 Registry Commands
            commands::registry_stats,
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");

    println!("[VCMix] Application closing, cleaning up backend...");
    backend::kill_backend();
}
