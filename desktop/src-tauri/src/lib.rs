//! VCMix Desktop — Tauri Shell (Phase 13)
//!
//! Tauri v2 desktop app for VCMix. Modular structure:
//!   - backend.rs  → BackendState, spawn/kill/wait backend
//!   - state.rs    → AppState, Rust engine + Python backend unified state
//!   - commands.rs → All #[tauri::command] functions
//!   - lib.rs      → Module declarations + run() entry point
//!   - main.rs     → fn main() { vcmix_desktop_lib::run() }

mod backend;
mod commands;
mod state;

pub use backend::BackendState;
pub use state::AppState;

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    println!("╔══════════════════════════════════════════╗");
    println!("║   VCMix Desktop — Tauri Shell           ║");
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
    println!("[VCMix] Launching Tauri window → http://localhost:{}", backend::BACKEND_PORT);

    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .manage(state::AppState::new())
        .invoke_handler(tauri::generate_handler![
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
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");

    println!("[VCMix] Application closing, cleaning up backend...");
    backend::kill_backend();
}
