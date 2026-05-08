//! Plugin Host — 插件宿主
//!
//! 加载/管理/调度插件链，支持多种插件格式：
//!
//! - **VC-CLI**: OpenDAW 原生 CLI 插件协议（23效果器+3乐器）
//! - **CLAP**: CLAP 开放插件标准（需要 `clap` feature + Rust 1.85+）
//! - **VST3**: Steinberg VST3 标准（需要 `vst3` feature）
//! - **LV2**: LV2 开放标准（预留）
//!
//! # 架构
//!
//! 所有插件格式通过 `VcPlugin` trait 统一接口，
//! 由 `PluginHost` 管理生命周期，`PluginChain` 调度信号处理。
//! `PluginScanner` 统一发现系统中的插件。
//!
//! ```text
//! ┌─────────────┐     ┌──────────────┐
//! │ ClapAdapter ├──┐   │ Vst3Adapter ├──┐
//! │  (CLAP)     │  │   │  (VST3)      │  │
//! └─────────────┘  │   └──────────────┘  │
//!                   │                     │
//! ┌─────────────┐  │   ┌──────────────┐  │
//! │VcPluginAdptr├──┤   │  (LV2)       ├──┤
//! │  (VC-CLI)   │  │   │  (预留)      │  │
//! └─────────────┘  │   └──────────────┘  │
//!                   ▼                     ▼
//!              ┌────────────────────────────┐
//!              │     VcPlugin trait          │
//!              └────────────┬───────────────┘
//!                           │
//!              ┌────────────▼───────────────┐
//!              │     PluginHost              │
//!              │  ┌──────────────────────┐  │
//!              │  │  PluginChain          │  │
//!              │  │  ParamManager         │  │
//!              │  │  PresetManager        │  │
//!              │  └──────────────────────┘  │
//!              └────────────────────────────┘
//! ```
//!
//! # Feature Flags
//!
//! - `clap` — 启用 CLAP 插件支持（需要 Rust 1.85+，因为 clack-host 使用 edition 2024）
//! - `vst3` — 启用 VST3 插件支持（需要 vst3 FFI 依赖）

pub mod host;
pub mod chain;
pub mod param;
pub mod vc_adapter;
pub mod preset;
pub mod scanner;

// 条件编译的适配器模块
#[cfg(feature = "clap")]
pub mod clap_adapter;
#[cfg(feature = "vst3")]
pub mod vst3_adapter;

// 公共接口重导出
pub use host::PluginHost;
pub use chain::PluginChain;
pub use param::ParamManager;
pub use vc_adapter::{VcPluginAdapter, all_known_plugin_ids};
pub use preset::PresetManager;
pub use scanner::{PluginScanner, ScannedPlugin, PluginFormat, ScanStats};

// 条件导出适配器
#[cfg(feature = "clap")]
pub use clap_adapter::ClapAdapter;
#[cfg(feature = "vst3")]
pub use vst3_adapter::Vst3Adapter;
