//! AppState — Tauri managed state, holding Rust engine + Python backend + Audio Output

use crate::audio_output::AudioOutputState;
use audio_engine::AudioEngine;
use opendaw_core::ExtensionRegistry;
use parking_lot::Mutex;
use std::sync::Arc;

pub struct AppState {
    /// 实时音频引擎
    pub engine: Arc<Mutex<AudioEngine>>,
    /// 扩展注册中心
    pub registry: Arc<Mutex<ExtensionRegistry>>,
    /// Python后端状态（兼容旧流程）
    pub backend: crate::backend::BackendState,
    /// 音频输出状态（v0.25.0 新增）
    pub audio_output: Arc<Mutex<AudioOutputState>>,
}

impl AppState {
    pub fn new() -> Self {
        Self {
            engine: Arc::new(Mutex::new(AudioEngine::new())),
            registry: Arc::new(Mutex::new(ExtensionRegistry::new())),
            backend: crate::backend::BackendState::default(),
            audio_output: Arc::new(Mutex::new(AudioOutputState::new())),
        }
    }
}
