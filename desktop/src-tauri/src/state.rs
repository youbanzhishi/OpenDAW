//! AppState — Tauri managed state, holding Rust engine + Python backend

use std::sync::Arc;
use parking_lot::Mutex;
use audio_engine::AudioEngine;
use opendaw_core::ExtensionRegistry;

pub struct AppState {
    /// 实时音频引擎
    pub engine: Arc<Mutex<AudioEngine>>,
    /// 扩展注册中心
    pub registry: Arc<Mutex<ExtensionRegistry>>,
    /// Python后端状态（兼容旧流程）
    pub backend: crate::backend::BackendState,
}

impl AppState {
    pub fn new() -> Self {
        Self {
            engine: Arc::new(Mutex::new(AudioEngine::new())),
            registry: Arc::new(Mutex::new(ExtensionRegistry::new())),
            backend: crate::backend::BackendState::default(),
        }
    }
}
