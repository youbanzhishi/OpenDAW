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
        cmd = get_bundled_backend_path();
        args = vec![];
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

fn get_bundled_backend_path() -> String {
    if cfg!(target_os = "macos") {
        "python".to_string()
    } else if cfg!(target_os = "windows") {
        "vcmix-backend.exe".to_string()
    } else {
        "vcmix-backend".to_string()
    }
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
