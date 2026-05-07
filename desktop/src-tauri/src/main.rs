//! VCMix Desktop — Main Entry Point (Phase 8.5)
//!
//! Tauri shell that wraps the VCMix FastAPI Web UI as a native desktop app.
//!
//! Startup flow:
//!   1. Spawn `python -m vcmix.web` as a child process
//!   2. Poll http://localhost:PORT/api/health until the backend is ready
//!   3. Open the Tauri webview pointed at http://localhost:PORT
//!   4. On app exit, kill the Python child process

use std::process::{Child, Command};
use std::sync::Mutex;
use std::thread;
use std::time::Duration;

// ── Configuration ────────────────────────────────────────────────────────

/// Port the FastAPI backend listens on. Must match uvicorn default.
const BACKEND_PORT: u16 = 8000;

/// Maximum seconds to wait for backend to become healthy.
const HEALTH_CHECK_TIMEOUT_SECS: u64 = 30;

/// Interval between health check attempts.
const HEALTH_CHECK_INTERVAL_SECS: u64 = 1;

/// Python module to run for the backend.
const BACKEND_MODULE: &str = "vcmix.web";

// ── Child Process Holder ────────────────────────────────────────────────

/// Global handle to the Python backend process.
/// Stored in a Mutex so the cleanup hook can access it.
static BACKEND_PROCESS: Mutex<Option<Child>> = Mutex::new(None);

// ── Backend Spawner ─────────────────────────────────────────────────────

/// Spawn the FastAPI backend as a child process.
///
/// On dev: runs `python -m vcmix.web` directly (requires vcmix installed).
/// On release: runs the bundled PyInstaller binary.
fn spawn_backend() -> Result<u32, String> {
    // Detect if we're in dev or release mode
    let (cmd, args) = if cfg!(debug_assertions) {
        // Dev mode: use system Python
        ("python", vec!["-m", BACKEND_MODULE])
    } else {
        // Release mode: use bundled PyInstaller binary
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

    // Store the child process handle globally for cleanup
    {
        let mut guard = BACKEND_PROCESS
            .lock()
            .map_err(|e| format!("Lock poisoned: {}", e))?;
        *guard = Some(child);
    }

    println!("[VCMix] Backend spawned with PID {}", pid);
    Ok(pid)
}

/// Determine the path to the bundled PyInstaller backend binary.
fn get_bundled_backend_path() -> String {
    // In a Tauri bundle, resources are placed alongside the executable.
    // The exact path depends on the OS:
    //   macOS:   VCMix.app/Contents/Resources/python-dist/vcmix-backend
    //   Windows: resources/python-dist/vcmix-backend.exe
    //   Linux:   resources/python-dist/vcmix-backend
    if cfg!(target_os = "macos") {
        // In development, fall back to system python
        "python".to_string()
    } else if cfg!(target_os = "windows") {
        "vcmix-backend.exe".to_string()
    } else {
        "vcmix-backend".to_string()
    }
}

// ── Health Check ─────────────────────────────────────────────────────────

/// Poll the backend's health endpoint until it responds or timeout.
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
                println!(
                    "[VCMix] Backend returned {}, retrying... ({}/{})",
                    resp.status(),
                    attempts + 1,
                    max_attempts
                );
            }
            Err(e) => {
                println!(
                    "[VCMix] Backend not ready: {} ({}/{})",
                    e,
                    attempts + 1,
                    max_attempts
                );
            }
        }

        attempts += 1;
        thread::sleep(Duration::from_secs(HEALTH_CHECK_INTERVAL_SECS));
    }

    Err(format!(
        "Backend did not become healthy within {}s",
        HEALTH_CHECK_TIMEOUT_SECS
    ))
}

// ── Cleanup ──────────────────────────────────────────────────────────────

/// Kill the Python backend process on application exit.
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
        // Wait to avoid zombie processes
        let _ = child.wait();
    }
}

// ── Main ─────────────────────────────────────────────────────────────────

fn main() {
    println!("╔══════════════════════════════════════════╗");
    println!("║   VCMix Desktop — Phase 8.5 Tauri Shell ║");
    println!("╚══════════════════════════════════════════╝");

    // ── Step 1: Spawn Python backend ────────────────────────────────────
    let backend_port = BACKEND_PORT;
    match spawn_backend() {
        Ok(pid) => println!("[VCMix] Backend PID: {}", pid),
        Err(e) => {
            eprintln!("[VCMix] FATAL: {}", e);
            eprintln!("[VCMix] Make sure Python and vcmix are installed:");
            eprintln!("        pip install -e /tmp/OpenDAW");
            std::process::exit(1);
        }
    }

    // ── Step 2: Wait for backend to be ready ────────────────────────────
    println!("[VCMix] Waiting for backend on port {}...", backend_port);
    if let Err(e) = wait_for_backend(backend_port) {
        eprintln!("[VCMix] FATAL: {}", e);
        kill_backend();
        std::process::exit(1);
    }

    // ── Step 3: Launch Tauri window ─────────────────────────────────────
    // Override the devUrl at runtime by setting the webview URL directly.
    println!("[VCMix] Launching Tauri window → http://localhost:{}", backend_port);

    // Register cleanup on Ctrl+C
    ctrlc::set_handler(|| {
        println!("\n[VCMix] Shutting down...");
        kill_backend();
        std::process::exit(0);
    })
    .unwrap_or_else(|e| eprintln!("[VCMix] Failed to set Ctrl+C handler: {}", e));

    // Run the Tauri app (lib.rs handles the actual window creation)
    vcmix_desktop_lib::run();

    // ── Step 4: Cleanup on exit ─────────────────────────────────────────
    println!("[VCMix] Application closing, cleaning up backend...");
    kill_backend();
}
