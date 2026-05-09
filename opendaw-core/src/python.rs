//! PyO3 Python Bindings for OpenDAW Core
//! 
//! Exposes Rust audio engine to Python for hybrid architecture.
//! Uses pyo3 0.22 with extension-module feature.

use pyo3::prelude::*;
use pyo3::types::PyDict;
use pyo3::exceptions::PyRuntimeError;
use std::sync::Arc;
use parking_lot::RwLock;

/// Engine state enum for Python
#[pyclass(module = "opendaw_core")]
#[derive(Debug, Clone, PartialEq)]
pub enum PyEngineState {
    Stopped,
    Playing,
    Paused,
    Rendering,
}

impl From<crate::EngineState> for PyEngineState {
    fn from(state: crate::EngineState) -> Self {
        match state {
            crate::EngineState::Stopped => PyEngineState::Stopped,
            crate::EngineState::Playing => PyEngineState::Playing,
            crate::EngineState::Paused => PyEngineState::Paused,
            crate::EngineState::Rendering => PyEngineState::Rendering,
        }
    }
}

/// RustEngine - PyO3 class wrapping AudioEngine + ExtensionRegistry
/// 
/// Provides Python-friendly interface to Rust audio engine with GIL management.
#[pyclass(module = "opendaw_core")]
pub struct RustEngine {
    engine: Arc<RwLock<crate::AudioEngine>>,
    registry: Arc<RwLock<crate::ExtensionRegistry>>,
}

#[pymethods]
impl RustEngine {
    /// Create a new RustEngine instance
    #[new]
    fn new() -> Self {
        log::info!("Creating RustEngine instance");
        Self {
            engine: Arc::new(RwLock::new(crate::AudioEngine::new())),
            registry: Arc::new(RwLock::new(crate::ExtensionRegistry::new())),
        }
    }

    /// Start audio playback
    /// 
    /// Args:
    ///     sample_rate: Audio sample rate (default 44100)
    ///     buffer_size: Buffer size in frames (default 512)
    /// 
    /// Returns:
    ///     True on success
    /// 
    /// Raises:
    ///     RuntimeError: If engine fails to start
    fn play(&self, sample_rate: u32, buffer_size: usize) -> PyResult<bool> {
        // Release GIL during potentially blocking operation
        let result = pyo3::Python::with_gil(|py| {
            py.allow_threads(|| {
                let mut engine = self.engine.write();
                engine.configure(sample_rate, buffer_size);
                engine.play()
            })
        });

        match result {
            Ok(_) => {
                log::info!("RustEngine.play: success ({}/{})", sample_rate, buffer_size);
                Ok(true)
            }
            Err(e) => {
                log::error!("RustEngine.play failed: {}", e);
                Err(PyRuntimeError::new_err(e.to_string()))
            }
        }
    }

    /// Stop audio playback
    /// 
    /// Returns:
    ///     True on success
    /// 
    /// Raises:
    ///     RuntimeError: If engine fails to stop
    fn stop(&self) -> PyResult<bool> {
        let result = pyo3::Python::with_gil(|py| {
            py.allow_threads(|| {
                let mut engine = self.engine.write();
                engine.stop()
            })
        });

        match result {
            Ok(_) => {
                log::info!("RustEngine.stop: success");
                Ok(true)
            }
            Err(e) => {
                log::error!("RustEngine.stop failed: {}", e);
                Err(PyRuntimeError::new_err(e.to_string()))
            }
        }
    }

    /// Pause audio playback
    fn pause(&self) -> PyResult<bool> {
        let result = pyo3::Python::with_gil(|py| {
            py.allow_threads(|| {
                let mut engine = self.engine.write();
                engine.pause()
            })
        });

        match result {
            Ok(_) => Ok(true),
            Err(e) => Err(PyRuntimeError::new_err(e.to_string())),
        }
    }

    /// Resume audio playback
    fn resume(&self) -> PyResult<bool> {
        let result = pyo3::Python::with_gil(|py| {
            py.allow_threads(|| {
                let mut engine = self.engine.write();
                engine.resume()
            })
        });

        match result {
            Ok(_) => Ok(true),
            Err(e) => Err(PyRuntimeError::new_err(e.to_string())),
        }
    }

    /// Get current engine state
    /// 
    /// Returns:
    ///     String representing engine state: "stopped", "playing", "paused", or "rendering"
    fn get_state(&self) -> String {
        let state = {
            let engine = self.engine.read();
            engine.get_state()
        };

        match state {
            crate::EngineState::Stopped => "stopped".to_string(),
            crate::EngineState::Playing => "playing".to_string(),
            crate::EngineState::Paused => "paused".to_string(),
            crate::EngineState::Rendering => "rendering".to_string(),
        }
    }

    /// Render audio offline from YAML configuration
    /// 
    /// Args:
    ///     yaml_path: Path to YAML configuration file
    ///     output_path: Path for output audio file
    /// 
    /// Returns:
    ///     Success message string
    /// 
    /// Raises:
    ///     RuntimeError: If rendering fails
    fn render_offline(&self, yaml_path: String, output_path: String) -> PyResult<String> {
        log::info!("RustEngine.render_offline: {} -> {}", yaml_path, output_path);
        
        let result = pyo3::Python::with_gil(|py| {
            py.allow_threads(|| {
                // Use the existing offline renderer
                crate::OfflineRenderer::new()
                    .load_project_from_yaml(&yaml_path)
                    .and_then(|r| r.render_to_file(&output_path))
            })
        });

        match result {
            Ok(msg) => {
                log::info!("RustEngine.render_offline: success");
                Ok(msg)
            }
            Err(e) => {
                log::error!("RustEngine.render_offline failed: {}", e);
                Err(PyRuntimeError::new_err(e.to_string()))
            }
        }
    }

    /// Register a plugin extension
    fn register_plugin(&self, name: String) -> PyResult<()> {
        let registry = self.registry.read();
        registry.register_plugin(&name);
        Ok(())
    }

    /// Register a script extension
    fn register_script(&self, name: String) -> PyResult<()> {
        let registry = self.registry.read();
        registry.register_script(&name);
        Ok(())
    }

    /// List registered plugins
    fn list_plugins(&self) -> Vec<String> {
        let registry = self.registry.read();
        registry.list_plugins()
    }

    /// List registered scripts
    fn list_scripts(&self) -> Vec<String> {
        let registry = self.registry.read();
        registry.list_scripts()
    }

    /// Get engine info as dictionary
    fn get_info(&self) -> PyResult<Py<PyDict>> {
        pyo3::Python::with_gil(|py| {
            let info = PyDict::new(py);
            
            let engine = self.engine.read();
            let state = engine.get_state();
            let state_str = match state {
                crate::EngineState::Stopped => "stopped",
                crate::EngineState::Playing => "playing",
                crate::EngineState::Paused => "paused",
                crate::EngineState::Rendering => "rendering",
            };
            
            info.set_item("state", state_str)?;
            info.set_item("sample_rate", engine.sample_rate())?;
            info.set_item("buffer_size", engine.buffer_size())?;
            info.set_item("version", env!("CARGO_PKG_VERSION"))?;
            
            Ok(info.into())
        })
    }
}

// ============================================================================
// Module Definition
// ============================================================================

/// Python module definition for opendaw_core
#[pymodule]
pub fn opendaw_core(m: &PyModule) -> PyResult<()> {
    // Initialize logger
    env_logger::Builder::from_env(env_logger::Env::default().default_filter_or("info"))
        .format_timestamp_millis()
        .init();
    
    log::info!("Initializing opendaw_core Python module v{}", env!("CARGO_PKG_VERSION"));
    
    // Register classes
    m.add_class::<RustEngine>()?;
    m.add_class::<PyEngineState>()?;
    
    // Module info
    m.add("__version__", env!("CARGO_PKG_VERSION"))?;
    m.add("__author__", "OpenDAW Team")?;
    
    log::info!("opendaw_core module initialized successfully");
    Ok(())
}
