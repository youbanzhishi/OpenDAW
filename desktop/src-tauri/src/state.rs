//! OpenDAW Desktop — App State (v1.0.0)
//!
//! Pure Rust state management. No Python backend.

use audio_engine::AudioEngine;
use std::sync::Arc;

/// App State — manages Rust audio engine
pub struct AppState {
    /// Real-time audio engine
    pub engine: Arc<parking_lot::Mutex<AudioEngine>>,
}

impl AppState {
    pub fn new() -> Self {
        Self {
            engine: Arc::new(parking_lot::Mutex::new(AudioEngine::new())),
        }
    }
}

impl Default for AppState {
    fn default() -> Self {
        Self::new()
    }
}
