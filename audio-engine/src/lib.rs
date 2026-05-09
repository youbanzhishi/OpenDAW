//! # OpenDAW 音频引擎核心
//!
//! 提供实时音频 I/O、音轨管理、播放控制等核心功能。
//!
//! ## Feature Flags
//!
//! - `audio`: 启用 CPAL 实时音频播放（需要系统音频库，如 ALSA/CoreAudio）
//!
//! ## 快速开始
//!
//! ```no_run
//! use audio_engine::AudioEngine;
//! use audio_engine::buffer::AudioBuffer;
//!
//! let mut engine = AudioEngine::new();
//!
//! // 注册音轨
//! engine.register_track("demo").unwrap();
//!
//! // 生成1秒正弦波
//! let sr = 44100.0;
//! let mut buf = AudioBuffer::new(2, 44100, sr);
//! for i in 0..44100 {
//!     let sample = (2.0 * std::f64::consts::PI * 440.0 * (i as f64 / sr)).sin() as f32;
//!     buf.set_sample(0, i, sample);
//!     buf.set_sample(1, i, sample);
//! }
//! engine.inject_buffer("demo", buf).unwrap();
//!
//! // 播放
//! engine.start(sr, 256).unwrap();
//! std::thread::sleep(std::time::Duration::from_secs(1));
//! engine.stop().unwrap();
//! ```

pub mod buffer;
pub mod engine;
pub mod scheduler;
pub mod state;
pub mod track;

// ==================== 公共接口重导出 ====================

pub use buffer::{AudioBuffer, RingBuffer};
pub use engine::AudioEngine;
pub use scheduler::{ProcessCallback, Scheduler};
pub use state::{EngineError, EngineState};
pub use track::Track;

/// 兼容别名（opendaw-core 使用此名称）
pub type EngineAudioBuffer = AudioBuffer;
