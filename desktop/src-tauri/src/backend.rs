//! VCMix Desktop — Backend Management
//!
//! Handles spawning, health-checking, and cleanup of the Python backend process.

use std::process::{Child, Command};
use std::thread;
use std::time::Duration;

// ── Configuration ────────────────────────────────────────────────────────

pub const BACKEND_PORT: u16 = 8000;
const HEALTH_CHECK_TIMEOUT_SECS: u64 = 30;
const HEALTH_CHECK_INTERVAL_SECS: u64 = 1;
const BACKEND_MODULE: &str = "vcmix.web";

// ── Shared State ─────────────────────────────────────────────────────────

pub struct BackendState {
    pub pid: parking_lot::Mutex<Option<u32>>,
    pub base_url: String,
}

impl Default for BackendState {
    fn default() -> Self {
        Self {
            pid: parking_lot::Mutex::new(None),
            base_url: format!("http://localhost:{}", BACKEND_PORT),
        }
    }
}

static BACKEND_PROCESS: parking_lot::Mutex<Option<Child>> = parking_lot::Mutex::new(None);

// ── Backend Management ───────────────────────────────────────────────────

pub fn spawn_backend() -> Result<u32, String> {
    let cmd: String;
    let args: Vec<String>;

    if cfg!(debug_assertions) {
        cmd = "python".to_string();
        args = vec!["-m".to_string(), BACKEND_MODULE.to_string()];
    } else {
        let (python_bin, module_arg) = get_bundled_backend_cmd();
        cmd = python_bin;
        args = module_arg;
    };

    println!("[VCMix] Spawning backend: {} {}", cmd, args.join(" "));

    let child = Command::new(&cmd)
        .args(&args)
        .env("VCMIX_PORT", BACKEND_PORT.to_string())
        .env("VCMIX_NO_OPEN_BROWSER", "1")
        .spawn()
        .map_err(|e| format!("Failed to spawn Python backend: {}", e))?;

    let pid = child.id();

    {
        *BACKEND_PROCESS.lock() = Some(child);
    }

    println!("[VCMix] Backend spawned with PID {}", pid);
    Ok(pid)
}

/// Returns (python_executable, module_args) for the bundled Python backend.
/// On macOS: looks for backend-venv/ at OpenDAW.app/Contents/Resources/ (same level as Contents/)
/// via the executable at Contents/MacOS/OpenDAW → go up twice to find Resources.
fn get_bundled_backend_cmd() -> (String, Vec<String>) {
    let exe_path = std::env::current_exe().ok();
    let exe_dir = exe_path
        .as_ref()
        .and_then(|p| p.parent().map(|p| p.to_path_buf()));

    let python_path = if cfg!(target_os = "macos") {
        // macOS app structure: OpenDAW.app/Contents/MacOS/OpenDAW
        // Resources: OpenDAW.app/Contents/Resources/
        // Backend venv bundled at Contents/Resources/backend-venv/
        // From MacOS/ dir: go up twice to get to app bundle root, then into Resources
        let app_bundle_root = exe_dir
            .as_ref()
            .and_then(|d| d.parent()) // up from MacOS -> Contents
            .and_then(|d| d.parent()); // up from Contents -> OpenDAW.app
                                       // CI post-build copies venv to: OpenDAW.app/Contents/Resources/backend-venv/
                                       // From Contents/MacOS/OpenDAW: go up 2x to app bundle root, then into Contents/Resources
        let venv_python = app_bundle_root.map(|r| {
            r.join("Contents")
                .join("Resources")
                .join("backend-venv")
                .join("bin")
                .join("python")
        });
        venv_python
            .filter(|p| p.exists())
            .map(|p| p.to_string_lossy().to_string())
            .unwrap_or_else(|| "python3".to_string())
    } else if cfg!(target_os = "windows") {
        // Windows: backend-venv/ next to the .exe
        let venv_python = exe_dir
            .as_ref()
            .map(|d| d.join("backend-venv").join("Scripts").join("python.exe"));
        venv_python
            .filter(|p| p.exists())
            .map(|p| p.to_string_lossy().to_string())
            .unwrap_or_else(|| "python".to_string())
    } else {
        // Linux: backend-venv/ next to the executable
        let venv_python = exe_dir
            .as_ref()
            .map(|d| d.join("backend-venv").join("bin").join("python"));
        venv_python
            .filter(|p| p.exists())
            .map(|p| p.to_string_lossy().to_string())
            .unwrap_or_else(|| "python3".to_string())
    };

    (
        python_path,
        vec!["-m".to_string(), BACKEND_MODULE.to_string()],
    )
}

pub fn wait_for_backend(port: u16) -> Result<(), String> {
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
                println!(
                    "[VCMix] Backend is healthy after {}s",
                    attempts * HEALTH_CHECK_INTERVAL_SECS
                );
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

pub fn kill_backend() {
    let mut guard = BACKEND_PROCESS.lock();
    if let Some(ref mut child) = *guard {
        match child.kill() {
            Ok(_) => println!("[VCMix] Backend process killed"),
            Err(e) => eprintln!("[VCMix] Failed to kill backend: {}", e),
        }
        let _ = child.wait();
    }
}
