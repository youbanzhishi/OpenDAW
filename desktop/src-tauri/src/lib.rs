//! VCMix Desktop — Tauri Shell (v0.25.0)
//!
//! Tauri v2 desktop app for VCMix. Modular structure:
//!   - backend.rs      → BackendState, spawn/kill/wait backend
//!   - state.rs        → AppState, Rust engine + Python backend unified state
//!   - audio_output.rs → DesktopAudioOutput, CPAL audio playback
//!   - commands.rs     → All #[tauri::command] functions
//!   - lib.rs         → Module declarations + run() entry point
//!   - main.rs        → fn main() { vcmix_desktop_lib::run() }
//!
//! v0.25.0 additions:
//!   - Real-time audio playback via CPAL
//!   - Channel-based audio frame transport from AudioEngine
//!   - Frontend UI bindings for play/stop/load_wav/volume controls

mod audio_output;
mod backend;
mod commands;
mod state;

pub use audio_output::{
    AudioOutputState, DesktopAudioOutput, OutputConfig, OutputError, OutputState,
};
pub use backend::BackendState;
pub use state::AppState;

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    println!("╔══════════════════════════════════════════╗");
    println!("║   VCMix Desktop — Tauri Shell (v0.25.0) ║");
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
    println!(
        "[VCMix] Waiting for backend on port {}...",
        backend::BACKEND_PORT
    );
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
            // v0.25.0 Audio Playback Commands
            commands::audio_init,
            commands::audio_get_status,
            commands::audio_play,
            commands::audio_stop,
            commands::audio_pause,
            commands::audio_resume,
            commands::audio_load_and_play,
            commands::audio_set_master_volume,
            commands::audio_get_devices,
            // v0.26.0 Import Commands
            commands::list_import_formats,
            commands::import_project,
            // Phase 36: Note System Commands
            commands::notes_list,
            commands::notes_list_by_level,
            commands::notes_get,
            commands::notes_save,
            commands::notes_delete,
            commands::notes_search,
            commands::notes_agent_summary,
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");

    println!("[VCMix] Application closing, cleaning up backend...");
    backend::kill_backend();
}
