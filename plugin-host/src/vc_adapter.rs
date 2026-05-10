//! VC-Plugin CLI 适配器 — 把 CLI 二进制包装成 VcPlugin trait
//!
//! 核心思路（沿用 Python 实现 `vc_plugins.py` 的协议）：
//!   1. 把 input AudioBuffer 编码为 WAV 写入临时文件
//!   2. 构建命令行：binary_path input.wav output.wav --param1 value1 ...
//!   3. 通过 subprocess 调用 CLI
//!   4. 解码 output.wav 到 output AudioBuffer
//!   5. 超时保护：5秒超时，防止卡死
//!
//! # CLI 路径解析优先级
//!
//! 1. 环境变量 `VC_{NAME}_CLI`（如 `VC_REVERB_CLI`）
//! 2. 默认搜索目录 `$VC_AUDIOFX_DIR` 下的 `VC-{Name}/VC-{Name}-CLI-Standalone`
//! 3. 回退到 `/tmp/AudioFX`
//!
//! # 支持26个VC插件
//!
//! Gen1(16): VC-EQ, VC-Comp, VC-Gain, VC-DeEsser, VC-Saturator,
//!           VC-Limiter, VC-Delay, VC-Reverb, VC-DynamicEQ, VC-Smooth,
//!           VC-SurgicalDeEsser, VC-Distortion, VC-Noise, VC-Tune,
//!           VC-Gate, VC-Chorus
//! Gen2(4):  VC-Stereo, VC-PitchShift, VC-MultiBand, VC-Harmonizer
//! 乐器(3):  (待确认具体名称，通过scan自动发现)
//! 其他(3):  (待确认，通过scan自动发现)

use std::collections::HashMap;
use std::env;
use std::fs;
use std::path::{Path, PathBuf};
use std::process::Command;

use opendaw_extension::{AudioBuffer, ParamInfo, PluginError, PluginType, VcPlugin};

// ── 常量 ──────────────────────────────────────────────────────────────────

/// CLI 调用超时（毫秒），防止卡死
#[allow(dead_code)]
const PROCESS_TIMEOUT_MS: u64 = 5000;

/// 目录扫描时匹配的文件名模式
const CLI_BINARY_PATTERN: &str = "CLI-Standalone";

// ── 内置参数映射 ──────────────────────────────────────────────────────────

/// 单个插件的参数定义
struct BuiltinParam {
    id: &'static str,
    name: &'static str,
    cli_flag: &'static str,
    min: f64,
    max: f64,
    default: f64,
    unit: &'static str,
}

/// 所有已知插件的参数定义 + CLI二进制相对路径
struct BuiltinPluginDef {
    plugin_id: &'static str,
    cli_relpath: &'static str,
    params: &'static [BuiltinParam],
}

/// 内置插件定义表 — 沿用 Python 实现 `_VC_CLI_DEFAULTS` 和 `_PARAM_MAPS`
/// 并补充了完整的参数范围信息（min/max/default/unit）
static BUILTIN_PLUGINS: &[BuiltinPluginDef] = &[
    // ── Gen1: 16个效果器 ─────────────────────────────────────────
    BuiltinPluginDef {
        plugin_id: "vc-eq",
        cli_relpath: "VC-EQ/VC-EQ-CLI-Standalone",
        params: &[
            BuiltinParam { id: "low_cut",   name: "Low Cut",       cli_flag: "--low-cut",   min: 20.0,    max: 20000.0, default: 20.0,    unit: "Hz" },
            BuiltinParam { id: "high_cut",  name: "High Cut",      cli_flag: "--high-cut",  min: 20.0,    max: 20000.0, default: 20000.0, unit: "Hz" },
            BuiltinParam { id: "low_shelf", name: "Low Shelf Gain",cli_flag: "--low-shelf", min: -24.0,   max: 24.0,    default: 0.0,     unit: "dB" },
            BuiltinParam { id: "high_shelf",name: "High Shelf Gain",cli_flag:"--high-shelf", min: -24.0,   max: 24.0,    default: 0.0,     unit: "dB" },
            BuiltinParam { id: "peak_freq", name: "Peak Frequency",cli_flag: "--peak-freq", min: 20.0,    max: 20000.0, default: 1000.0,  unit: "Hz" },
            BuiltinParam { id: "peak_gain", name: "Peak Gain",     cli_flag: "--peak-gain", min: -24.0,   max: 24.0,    default: 0.0,     unit: "dB" },
            BuiltinParam { id: "peak_q",    name: "Peak Q",        cli_flag: "--peak-q",    min: 0.1,     max: 30.0,    default: 1.0,     unit: "" },
        ],
    },
    BuiltinPluginDef {
        plugin_id: "vc-comp",
        cli_relpath: "VC-Comp/VC-Comp-CLI-Standalone",
        params: &[
            BuiltinParam { id: "threshold", name: "Threshold", cli_flag: "--threshold", min: -60.0, max: 0.0,    default: -20.0, unit: "dB" },
            BuiltinParam { id: "ratio",     name: "Ratio",     cli_flag: "--ratio",     min: 1.0,   max: 20.0,   default: 4.0,   unit: ":1" },
            BuiltinParam { id: "attack",    name: "Attack",    cli_flag: "--attack",    min: 0.1,   max: 100.0,  default: 10.0,  unit: "ms" },
            BuiltinParam { id: "release",   name: "Release",   cli_flag: "--release",   min: 10.0,  max: 1000.0, default: 100.0, unit: "ms" },
            BuiltinParam { id: "makeup",    name: "Makeup Gain",cli_flag: "--makeup",   min: 0.0,   max: 24.0,   default: 0.0,   unit: "dB" },
        ],
    },
    BuiltinPluginDef {
        plugin_id: "vc-gain",
        cli_relpath: "VC-Gain/VC-Gain-CLI-Standalone",
        params: &[
            BuiltinParam { id: "gain", name: "Gain", cli_flag: "--gain", min: -60.0, max: 60.0, default: 0.0, unit: "dB" },
        ],
    },
    BuiltinPluginDef {
        plugin_id: "vc-deesser",
        cli_relpath: "VC-DeEsser/VC-DeEsser-CLI-Standalone",
        params: &[
            BuiltinParam { id: "threshold", name: "Threshold", cli_flag: "--threshold", min: -60.0, max: 0.0,   default: -30.0, unit: "dB" },
            BuiltinParam { id: "reduction", name: "Reduction", cli_flag: "--reduction", min: 0.0,   max: 24.0,  default: 6.0,   unit: "dB" },
            BuiltinParam { id: "frequency", name: "Frequency", cli_flag: "--frequency", min: 2000.0,max: 12000.0,default: 6000.0,unit: "Hz" },
        ],
    },
    BuiltinPluginDef {
        plugin_id: "vc-saturator",
        cli_relpath: "VC-Saturator/VC-Saturator-CLI-Standalone",
        params: &[
            BuiltinParam { id: "drive", name: "Drive", cli_flag: "--drive", min: 0.0, max: 100.0, default: 30.0, unit: "%" },
            BuiltinParam { id: "mix",   name: "Mix",   cli_flag: "--mix",   min: 0.0, max: 100.0, default: 50.0, unit: "%" },
        ],
    },
    BuiltinPluginDef {
        plugin_id: "vc-limiter",
        cli_relpath: "VC-Limiter/VC-Limiter-CLI-Standalone",
        params: &[
            BuiltinParam { id: "ceiling", name: "Ceiling", cli_flag: "--ceiling", min: -12.0, max: 0.0,   default: -1.0,  unit: "dB" },
            BuiltinParam { id: "release", name: "Release", cli_flag: "--release", min: 10.0,  max: 1000.0,default: 50.0,  unit: "ms" },
        ],
    },
    BuiltinPluginDef {
        plugin_id: "vc-delay",
        cli_relpath: "VC-Delay/VC-Delay-CLI-Standalone",
        params: &[
            BuiltinParam { id: "time",     name: "Delay Time", cli_flag: "--time",     min: 1.0,  max: 2000.0, default: 250.0, unit: "ms" },
            BuiltinParam { id: "feedback", name: "Feedback",   cli_flag: "--feedback", min: 0.0,  max: 100.0,  default: 30.0,  unit: "%" },
            BuiltinParam { id: "mix",      name: "Mix",        cli_flag: "--mix",      min: 0.0,  max: 100.0,  default: 30.0,  unit: "%" },
        ],
    },
    BuiltinPluginDef {
        plugin_id: "vc-reverb",
        cli_relpath: "VC-Reverb/VC-Reverb-CLI-Standalone",
        params: &[
            BuiltinParam { id: "room",     name: "Room Size",  cli_flag: "--room",     min: 0.0,  max: 100.0,   default: 30.0,  unit: "%" },
            BuiltinParam { id: "decay",    name: "Decay",      cli_flag: "--decay",    min: 0.0,  max: 100.0,   default: 35.0,  unit: "%" },
            BuiltinParam { id: "damping",  name: "Damping",    cli_flag: "--damping",  min: 0.0,  max: 100.0,   default: 50.0,  unit: "%" },
            BuiltinParam { id: "mix",      name: "Mix",        cli_flag: "--mix",      min: 0.0,  max: 100.0,   default: 20.0,  unit: "%" },
            BuiltinParam { id: "predelay", name: "Pre-delay",  cli_flag: "--predelay", min: 0.0,  max: 100.0,   default: 0.0,   unit: "ms" },
            BuiltinParam { id: "wetlpf",   name: "Wet LPF",    cli_flag: "--wetlpf",   min: 100.0,max: 20000.0, default: 8000.0,unit: "Hz" },
        ],
    },
    BuiltinPluginDef {
        plugin_id: "vc-dynamiceq",
        cli_relpath: "VC-DynamicEQ/VC-DynamicEQ-CLI-Standalone",
        params: &[
            BuiltinParam { id: "frequency", name: "Frequency", cli_flag: "--frequency", min: 20.0,  max: 20000.0, default: 1000.0, unit: "Hz" },
            BuiltinParam { id: "threshold", name: "Threshold", cli_flag: "--threshold", min: -60.0, max: 0.0,    default: -20.0,  unit: "dB" },
            BuiltinParam { id: "q",         name: "Q",         cli_flag: "--q",         min: 0.1,   max: 30.0,   default: 1.0,    unit: "" },
            BuiltinParam { id: "attack",    name: "Attack",    cli_flag: "--attack",    min: 0.1,   max: 100.0,  default: 10.0,   unit: "ms" },
            BuiltinParam { id: "release",   name: "Release",   cli_flag: "--release",   min: 10.0,  max: 1000.0, default: 100.0,  unit: "ms" },
        ],
    },
    BuiltinPluginDef {
        plugin_id: "vc-smooth",
        cli_relpath: "VC-Smooth/VC-Smooth-CLI-Standalone",
        params: &[
            BuiltinParam { id: "amount", name: "Amount", cli_flag: "--amount", min: 0.0, max: 100.0, default: 50.0, unit: "%" },
        ],
    },
    BuiltinPluginDef {
        plugin_id: "vc-surgicaldeesser",
        cli_relpath: "VC-SurgicalDeEsser/VC-SurgicalDeEsser-CLI-Standalone",
        params: &[
            BuiltinParam { id: "threshold", name: "Threshold", cli_flag: "--threshold", min: -60.0, max: 0.0,   default: -30.0, unit: "dB" },
            BuiltinParam { id: "reduction", name: "Reduction", cli_flag: "--reduction", min: 0.0,   max: 24.0,  default: 6.0,   unit: "dB" },
            BuiltinParam { id: "frequency", name: "Frequency", cli_flag: "--frequency", min: 2000.0,max: 12000.0,default: 6000.0,unit: "Hz" },
        ],
    },
    BuiltinPluginDef {
        plugin_id: "vc-distortion",
        cli_relpath: "VC-Distortion/VC-Distortion-CLI-Standalone",
        params: &[
            BuiltinParam { id: "mode",  name: "Mode",  cli_flag: "--mode",  min: 0.0, max: 5.0,   default: 0.0,  unit: "" },
            BuiltinParam { id: "drive", name: "Drive", cli_flag: "--drive", min: 0.0, max: 100.0, default: 50.0, unit: "%" },
            BuiltinParam { id: "mix",   name: "Mix",   cli_flag: "--mix",   min: 0.0, max: 100.0, default: 50.0, unit: "%" },
        ],
    },
    BuiltinPluginDef {
        plugin_id: "vc-noise",
        cli_relpath: "VC-Noise/VC-Noise-CLI-Standalone",
        params: &[
            BuiltinParam { id: "type",  name: "Noise Type", cli_flag: "--type",  min: 0.0,  max: 3.0,  default: 0.0,  unit: "" },
            BuiltinParam { id: "level", name: "Level",       cli_flag: "--level", min: -60.0,max: 0.0,  default: -30.0,unit: "dB" },
        ],
    },
    BuiltinPluginDef {
        plugin_id: "vc-tune",
        cli_relpath: "VC-Tune/VC-Tune-CLI-Standalone",
        params: &[
            BuiltinParam { id: "speed",     name: "Speed",     cli_flag: "--speed",     min: 0.0,   max: 100.0, default: 50.0,  unit: "%" },
            BuiltinParam { id: "scale",     name: "Scale",     cli_flag: "--scale",     min: 0.0,   max: 24.0,  default: 0.0,   unit: "" },
            BuiltinParam { id: "transpose", name: "Transpose", cli_flag: "--transpose", min: -24.0, max: 24.0,  default: 0.0,   unit: "st" },
            BuiltinParam { id: "cents",     name: "Cents",     cli_flag: "--cents",     min: -100.0,max: 100.0, default: 0.0,   unit: "cents" },
            BuiltinParam { id: "formant",   name: "Formant",   cli_flag: "--formant",   min: -12.0, max: 12.0,  default: 0.0,   unit: "st" },
            BuiltinParam { id: "autokey",   name: "Auto Key",  cli_flag: "--autokey",   min: 0.0,   max: 1.0,   default: 1.0,   unit: "" },
        ],
    },
    BuiltinPluginDef {
        plugin_id: "vc-gate",
        cli_relpath: "VC-Gate/VC-Gate-CLI-Standalone",
        params: &[
            BuiltinParam { id: "threshold", name: "Threshold", cli_flag: "--threshold", min: -60.0, max: 0.0,   default: -40.0, unit: "dB" },
            BuiltinParam { id: "ratio",     name: "Ratio",     cli_flag: "--ratio",     min: 1.0,   max: 20.0,  default: 10.0,  unit: ":1" },
            BuiltinParam { id: "attack",    name: "Attack",    cli_flag: "--attack",    min: 0.1,   max: 100.0, default: 1.0,   unit: "ms" },
            BuiltinParam { id: "hold",      name: "Hold",      cli_flag: "--hold",      min: 0.0,   max: 500.0, default: 50.0,  unit: "ms" },
            BuiltinParam { id: "release",   name: "Release",   cli_flag: "--release",   min: 10.0,  max: 1000.0,default: 100.0, unit: "ms" },
            BuiltinParam { id: "range",     name: "Range",     cli_flag: "--range",     min: 0.0,   max: 60.0,  default: 60.0,  unit: "dB" },
        ],
    },
    BuiltinPluginDef {
        plugin_id: "vc-chorus",
        cli_relpath: "VC-Chorus/VC-Chorus-CLI-Standalone",
        params: &[
            BuiltinParam { id: "rate",     name: "Rate",     cli_flag: "--rate",     min: 0.1,  max: 10.0,  default: 1.0,  unit: "Hz" },
            BuiltinParam { id: "depth",    name: "Depth",    cli_flag: "--depth",    min: 0.0,  max: 100.0, default: 30.0, unit: "%" },
            BuiltinParam { id: "voices",   name: "Voices",   cli_flag: "--voices",   min: 2.0,  max: 8.0,   default: 3.0,  unit: "" },
            BuiltinParam { id: "mix",      name: "Mix",      cli_flag: "--mix",      min: 0.0,  max: 100.0, default: 50.0, unit: "%" },
            BuiltinParam { id: "delay",    name: "Delay",    cli_flag: "--delay",    min: 0.0,  max: 50.0,  default: 10.0, unit: "ms" },
            BuiltinParam { id: "width",    name: "Width",    cli_flag: "--width",    min: 0.0,  max: 100.0, default: 80.0, unit: "%" },
            BuiltinParam { id: "feedback", name: "Feedback", cli_flag: "--feedback", min: 0.0,  max: 100.0, default: 20.0, unit: "%" },
        ],
    },
    // ── Gen2: 4个新/升级效果器 ───────────────────────────────────
    BuiltinPluginDef {
        plugin_id: "vc-stereo",
        cli_relpath: "VC-Stereo/VC-Stereo-CLI-Standalone",
        params: &[
            BuiltinParam { id: "width",  name: "Width",       cli_flag: "--width",  min: 0.0,   max: 200.0, default: 100.0, unit: "%" },
            BuiltinParam { id: "center", name: "Center Level",cli_flag: "--center", min: -60.0, max: 0.0,   default: 0.0,   unit: "dB" },
            BuiltinParam { id: "sides",  name: "Sides Level", cli_flag: "--sides",  min: -60.0, max: 0.0,   default: 0.0,   unit: "dB" },
        ],
    },
    BuiltinPluginDef {
        plugin_id: "vc-pitchshift",
        cli_relpath: "VC-PitchShift/VC-PitchShift-CLI-Standalone",
        params: &[
            BuiltinParam { id: "semitones", name: "Semitones",    cli_flag: "--semitones", min: -24.0, max: 24.0, default: 0.0, unit: "st" },
            BuiltinParam { id: "cents",     name: "Cents",        cli_flag: "--cents",     min: -100.0,max: 100.0,default: 0.0, unit: "cents" },
            BuiltinParam { id: "formant",   name: "Formant Shift",cli_flag: "--formant",   min: -12.0, max: 12.0, default: 0.0, unit: "st" },
            BuiltinParam { id: "mode",      name: "Mode",         cli_flag: "--mode",      min: 0.0,   max: 3.0,  default: 0.0, unit: "" },
        ],
    },
    BuiltinPluginDef {
        plugin_id: "vc-multiband",
        cli_relpath: "VC-MultiBand/VC-MultiBand-CLI-Standalone",
        params: &[
            BuiltinParam { id: "low_freq",  name: "Low/Mid Crossover",cli_flag: "--low-freq",  min: 20.0,  max: 2000.0, default: 200.0,  unit: "Hz" },
            BuiltinParam { id: "mid_freq",  name: "Mid/High Crossover",cli_flag:"--mid-freq",  min: 2000.0,max: 20000.0,default: 5000.0, unit: "Hz" },
            BuiltinParam { id: "low_gain",  name: "Low Gain",   cli_flag: "--low-gain",  min: -24.0, max: 24.0,   default: 0.0,   unit: "dB" },
            BuiltinParam { id: "mid_gain",  name: "Mid Gain",   cli_flag: "--mid-gain",  min: -24.0, max: 24.0,   default: 0.0,   unit: "dB" },
            BuiltinParam { id: "high_gain", name: "High Gain",  cli_flag: "--high-gain", min: -24.0, max: 24.0,   default: 0.0,   unit: "dB" },
        ],
    },
    BuiltinPluginDef {
        plugin_id: "vc-harmonizer",
        cli_relpath: "VC-Harmonizer/VC-Harmonizer-CLI-Standalone",
        params: &[
            BuiltinParam { id: "shift1", name: "Voice 1 Shift", cli_flag: "--shift1", min: -24.0, max: 24.0, default: 3.0,  unit: "st" },
            BuiltinParam { id: "shift2", name: "Voice 2 Shift", cli_flag: "--shift2", min: -24.0, max: 24.0, default: 7.0,  unit: "st" },
            BuiltinParam { id: "mix1",   name: "Voice 1 Mix",   cli_flag: "--mix1",   min: 0.0,   max: 100.0,default: 50.0, unit: "%" },
            BuiltinParam { id: "mix2",   name: "Voice 2 Mix",   cli_flag: "--mix2",   min: 0.0,   max: 100.0,default: 30.0, unit: "%" },
        ],
    },
];

/// 根据插件ID查找内置参数定义，返回 ParamInfo 列表
fn get_builtin_params(plugin_id: &str) -> Vec<ParamInfo> {
    BUILTIN_PLUGINS
        .iter()
        .find(|def| def.plugin_id == plugin_id)
        .map(|def| {
            def.params
                .iter()
                .map(|p| ParamInfo::new(p.id, p.name, p.min, p.max, p.default, p.unit))
                .collect()
        })
        .unwrap_or_default()
}

/// 根据插件ID查找默认CLI二进制相对路径
fn get_default_cli_relpath(plugin_id: &str) -> Option<&'static str> {
    BUILTIN_PLUGINS
        .iter()
        .find(|def| def.plugin_id == plugin_id)
        .map(|def| def.cli_relpath)
}

/// 所有已知插件的ID列表
pub fn all_known_plugin_ids() -> Vec<&'static str> {
    BUILTIN_PLUGINS.iter().map(|def| def.plugin_id).collect()
}

/// 默认插件搜索目录
fn default_plugin_dir() -> PathBuf {
    // 1. 环境变量 $VC_AUDIOFX_DIR
    if let Ok(dir) = env::var("VC_AUDIOFX_DIR") {
        let p = PathBuf::from(&dir);
        if p.exists() {
            return p;
        }
    }
    // 2. 用户目录 ~/.opendaw/plugins/
    if let Ok(home) = env::var("HOME") {
        let p = PathBuf::from(home).join(".opendaw/plugins");
        if p.exists() {
            return p;
        }
    }
    // 3. 默认 /tmp/AudioFX（沿用Python实现）
    PathBuf::from("/tmp/AudioFX")
}

// ── VcPluginAdapter ───────────────────────────────────────────────────────

/// VC-Plugin CLI 适配器
///
/// 将 VC-*-CLI-Standalone 二进制包装为实现 VcPlugin trait 的结构体，
/// 通过 subprocess + 临时 WAV 文件进行音频处理。
///
/// # 生命周期
///
/// ```text
/// from_binary() / from_plugin_id() / scan_directory()
///     ↓
/// init(sample_rate, buffer_size)
///     ↓
/// [process(input, output)]*  ← 可多次调用
///     ↓
/// destroy()
/// ```
pub struct VcPluginAdapter {
    /// 插件ID（如 "vc-eq"）
    id: String,
    /// 插件显示名称（如 "VC-EQ"）
    name: String,
    /// CLI 二进制路径
    binary_path: PathBuf,
    /// 参数列表
    params: Vec<ParamInfo>,
    /// 参数当前值映射 param_id → value
    param_values: HashMap<String, f64>,
    /// 采样率
    sample_rate: f64,
    /// 缓冲区大小
    buffer_size: usize,
    /// 是否已初始化
    initialized: bool,
}

impl VcPluginAdapter {
    /// 扫描目录下所有 VC-CLI 插件
    ///
    /// 递归扫描 `dir`，查找所有文件名包含 `CLI-Standalone` 的可执行文件，
    /// 为每个找到的二进制创建 VcPluginAdapter 实例。
    ///
    /// # 参数
    ///
    /// - `dir`: 要扫描的目录（如 `/tmp/AudioFX`）
    ///
    /// # 返回
    ///
    /// 成功发现的适配器列表。单个插件失败不影响其他插件的发现。
    pub fn scan_directory(dir: &Path) -> Result<Vec<VcPluginAdapter>, PluginError> {
        if !dir.exists() {
            return Err(PluginError::ProcessFailed(format!(
                "扫描目录不存在: {}",
                dir.display()
            )));
        }
        if !dir.is_dir() {
            return Err(PluginError::ProcessFailed(format!(
                "路径不是目录: {}",
                dir.display()
            )));
        }

        let mut adapters = Vec::new();
        scan_for_cli_binaries(dir, &mut adapters)?;

        log::info!(
            "[VcPluginAdapter] 扫描完成: 在 {} 中发现 {} 个VC插件",
            dir.display(),
            adapters.len()
        );

        Ok(adapters)
    }

    /// 从单个二进制文件创建适配器
    ///
    /// 根据二进制文件路径推断 plugin_id 和 plugin_name，
    /// 并加载内置参数定义（如果存在）。
    pub fn from_binary(path: &Path) -> Result<Self, PluginError> {
        // 验证文件存在
        if !path.exists() {
            return Err(PluginError::ProcessFailed(format!(
                "文件不存在: {}",
                path.display()
            )));
        }

        // 验证文件可执行（Unix）
        #[cfg(unix)]
        {
            use std::os::unix::fs::PermissionsExt;
            let metadata = fs::metadata(path).map_err(|e| {
                PluginError::ProcessFailed(format!(
                    "无法读取文件元数据 {}: {}",
                    path.display(),
                    e
                ))
            })?;
            let mode = metadata.permissions().mode();
            if mode & 0o111 == 0 {
                return Err(PluginError::ProcessFailed(format!(
                    "文件不可执行: {}",
                    path.display()
                )));
            }
        }

        // 从文件名推断 plugin_id 和 plugin_name
        let (plugin_id, plugin_name) = infer_plugin_info(path);

        // 加载内置参数定义
        let params = get_builtin_params(&plugin_id);
        let mut param_values = HashMap::new();
        for p in &params {
            param_values.insert(p.id.clone(), p.value);
        }

        log::debug!(
            "[VcPluginAdapter] 创建适配器: id={}, name={}, binary={}",
            plugin_id,
            plugin_name,
            path.display()
        );

        Ok(Self {
            id: plugin_id,
            name: plugin_name,
            binary_path: path.to_path_buf(),
            params,
            param_values,
            sample_rate: 0.0,
            buffer_size: 0,
            initialized: false,
        })
    }

    /// 从 plugin_id 创建适配器（自动搜索二进制）
    ///
    /// 按优先级搜索二进制：
    ///   1. 环境变量 `VC_{NAME}_CLI`（如 `VC_REVERB_CLI`）
    ///   2. 默认搜索目录下的 `VC-{Name}/VC-{Name}-CLI-Standalone`
    pub fn from_plugin_id(plugin_id: &str) -> Result<Self, PluginError> {
        // 1. 尝试环境变量
        let env_key = plugin_id.to_uppercase().replace('-', "_") + "_CLI";
        if let Ok(env_val) = env::var(&env_key) {
            let p = PathBuf::from(&env_val);
            if p.exists() {
                log::debug!(
                    "[VcPluginAdapter] 通过环境变量 {} 找到: {}",
                    env_key,
                    env_val
                );
                return Self::from_binary(&p);
            }
        }

        // 2. 尝试默认搜索目录
        let base_dir = default_plugin_dir();
        if let Some(relpath) = get_default_cli_relpath(plugin_id) {
            let full_path = base_dir.join(relpath);
            if full_path.exists() {
                log::debug!(
                    "[VcPluginAdapter] 在默认目录找到: {}",
                    full_path.display()
                );
                return Self::from_binary(&full_path);
            }
        }

        // 3. 尝试在默认目录下直接搜索
        if base_dir.exists() {
            if let Ok(found) = Self::scan_directory(&base_dir) {
                if let Some(adapter) = found.into_iter().find(|a| a.id == plugin_id) {
                    return Ok(adapter);
                }
            }
        }

        Err(PluginError::ProcessFailed(format!(
            "未找到VC插件 '{}' 的CLI二进制（已检查环境变量 {} 和默认目录 {}）",
            plugin_id,
            env_key,
            base_dir.display()
        )))
    }

    /// 获取CLI二进制路径
    pub fn binary_path(&self) -> &Path {
        &self.binary_path
    }

    /// 是否已初始化
    pub fn is_initialized(&self) -> bool {
        self.initialized
    }

    /// 发现插件参数（尝试运行 --help）
    ///
    /// 如果内置参数表已有定义，直接返回。
    /// 否则尝试运行 CLI 的 --help 来解析参数列表。
    fn discover_params(&mut self) -> Result<(), PluginError> {
        // 内置参数表已有定义，无需运行CLI
        if !self.params.is_empty() {
            return Ok(());
        }

        // 尝试运行 --help 解析参数
        let output = Command::new(&self.binary_path)
            .arg("--help")
            .output()
            .map_err(|e| {
                PluginError::InitFailed(format!(
                    "运行 --help 失败 ({}): {}",
                    self.id, e
                ))
            })?;

        let stdout = String::from_utf8_lossy(&output.stdout);
        let stderr = String::from_utf8_lossy(&output.stderr);

        // 简单解析：查找 --xxx 模式的参数
        let help_text = format!("{}\n{}", stdout, stderr);
        let discovered = parse_help_for_params(&help_text);

        if discovered.is_empty() {
            log::warn!(
                "[VcPluginAdapter] 无法从 --help 解析参数，插件 {} 将没有可调参数",
                self.id
            );
        } else {
            log::info!(
                "[VcPluginAdapter] 从 --help 发现 {} 个参数: {:?}",
                discovered.len(),
                discovered.iter().map(|p| &p.id).collect::<Vec<_>>()
            );
        }

        self.params = discovered;
        for p in &self.params {
            self.param_values.insert(p.id.clone(), p.value);
        }

        Ok(())
    }

    /// 通过 stdin/stdout 管道流式处理音频
    ///
    /// 使用子进程的 stdin/stdout 进行音频数据通信，
    /// 避免临时文件的开销。
    ///
    /// 协议格式（每帧一行）：
    /// - 输入：`in CH0 CH1 ...` （浮点数，空格分隔）
    /// - 输出：`out CH0 CH1 ...`
    /// - 设置参数：`param ID VALUE`
    /// - 结束：`end`
    ///
    /// 此方法为实验性功能，需要 CLI 支持 streaming 模式。
    #[allow(dead_code)]
    fn process_streaming(
        &mut self,
        input: &AudioBuffer,
        output: &mut AudioBuffer,
    ) -> Result<(), PluginError> {
        use std::io::{Write, BufRead};
        use std::process::Stdio;

        let mut child = Command::new(&self.binary_path)
            .arg("--streaming")
            .arg("--sample-rate")
            .arg(format!("{}", self.sample_rate as u32))
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::piped())
            .spawn()
            .map_err(|e| PluginError::ProcessFailed(
                format!("启动 streaming 模式失败: {}", e)
            ))?;

        let stdin = child.stdin.as_mut()
            .ok_or_else(|| PluginError::ProcessFailed("无法获取 stdin".to_string()))?;

        // 发送参数
        for (param_id, value) in &self.param_values {
            writeln!(stdin, "param {} {:.6}", param_id, value)
                .map_err(|e| PluginError::ProcessFailed(
                    format!("写入参数失败: {}", e)
                ))?;
        }

        // 发送音频帧
        for frame in 0..input.frames {
            write!(stdin, "in").map_err(|e| PluginError::ProcessFailed(
                format!("写入帧头失败: {}", e)
            ))?;
            for ch in 0..input.channels {
                write!(stdin, " {:.6}", input.sample(ch, frame))
                    .map_err(|e| PluginError::ProcessFailed(
                        format!("写入采样失败: {}", e)
                    ))?;
            }
            writeln!(stdin).map_err(|e| PluginError::ProcessFailed(
                format!("写入帧尾失败: {}", e)
            ))?;
        }

        writeln!(stdin, "end").map_err(|e| PluginError::ProcessFailed(
            format!("写入结束标记失败: {}", e)
        ))?;
        let _ = stdin; // 释放 stdin 以发送 EOF

        // 读取输出
        let stdout = child.stdout.as_mut()
            .ok_or_else(|| PluginError::ProcessFailed("无法获取 stdout".to_string()))?;

        let reader = std::io::BufReader::new(stdout);
        let mut frame_idx = 0;

        for line in reader.lines() {
            let line = line.map_err(|e| PluginError::ProcessFailed(
                format!("读取输出行失败: {}", e)
            ))?;
            let line = line.trim();
            if line.starts_with("out ") {
                let values: Vec<f64> = line[4..]
                    .split_whitespace()
                    .filter_map(|s| s.parse().ok())
                    .collect();
                if frame_idx < output.frames {
                    for (ch, &val) in values.iter().enumerate() {
                        if ch < output.channels {
                            output.set_sample(ch, frame_idx, val);
                        }
                    }
                    frame_idx += 1;
                }
            }
        }

        // 等待进程结束
        let status = child.wait().map_err(|e| PluginError::ProcessFailed(
            format!("等待进程结束失败: {}", e)
        ))?;

        if !status.success() {
            return Err(PluginError::ProcessFailed(
                format!("streaming 进程退出码: {:?}", status.code())
            ));
        }

        Ok(())
    }
}

// ── VcPlugin trait 实现 ───────────────────────────────────────────────────

impl VcPlugin for VcPluginAdapter {
    fn plugin_id(&self) -> &str {
        &self.id
    }

    fn plugin_name(&self) -> &str {
        &self.name
    }

    fn plugin_type(&self) -> PluginType {
        // 当前所有VC插件都是效果器
        PluginType::Effect
    }

    fn version(&self) -> &str {
        "1.0.0"
    }

    fn init(&mut self, sample_rate: f64, buffer_size: usize) -> Result<(), PluginError> {
        // 验证二进制仍然存在
        if !self.binary_path.exists() {
            return Err(PluginError::ProcessFailed(format!(
                "插件 {} 的二进制文件不存在: {}",
                self.id,
                self.binary_path.display()
            )));
        }

        self.sample_rate = sample_rate;
        self.buffer_size = buffer_size;

        // 尝试发现参数（如果还没有）
        if self.params.is_empty() {
            let _ = self.discover_params();
        }

        self.initialized = true;

        log::info!(
            "[VcPluginAdapter] 初始化 {} (sr={}, buf={})",
            self.id,
            sample_rate,
            buffer_size
        );

        Ok(())
    }

    fn process(&mut self, input: &AudioBuffer, output: &mut AudioBuffer) {
        if !self.initialized {
            // 未初始化时直通
            output.data.copy_from_slice(&input.data);
            return;
        }

        let sample_rate = if self.sample_rate > 0.0 {
            self.sample_rate
        } else {
            44100.0
        };

        // 1. 创建临时目录
        let tmp_dir = match tempfile::tempdir() {
            Ok(d) => d,
            Err(e) => {
                log::error!("[VcPluginAdapter] 创建临时目录失败: {}", e);
                output.data.copy_from_slice(&input.data);
                return;
            }
        };

        let in_path = tmp_dir.path().join("input.wav");
        let out_path = tmp_dir.path().join("output.wav");

        // 2. 把 input AudioBuffer 编码为 WAV
        if let Err(e) = write_audio_buffer_to_wav(input, &in_path, sample_rate as u32) {
            log::error!("[VcPluginAdapter] 写入WAV失败: {}", e);
            output.data.copy_from_slice(&input.data);
            return;
        }

        // 3. 构建 CLI 命令
        let mut cmd = Command::new(&self.binary_path);
        cmd.arg(&in_path);
        cmd.arg(&out_path);

        // 添加当前参数值作为命令行参数
        for (param_id, value) in &self.param_values {
            // 查找参数的 CLI flag
            if self.params.iter().any(|p| p.id == *param_id) {
                // 使用内置BuiltinParam的cli_flag映射
                // 先尝试从BUILTIN_PLUGINS查找精确的cli_flag
                let cli_flag = find_cli_flag_for_param(&self.id, param_id)
                    .unwrap_or_else(|| format!("--{}", param_id.replace('_', "-")));
                cmd.arg(cli_flag);
                cmd.arg(format!("{}", value));
            }
        }

        log::trace!("[VcPluginAdapter] 执行: {:?}", cmd);

        // 4. 执行 CLI（带超时保护）
        // PROCESS_TIMEOUT_MS 用于配置超时，后续可通过 spawn+wait_timeout 实现
        let result = cmd.output();

        match result {
            Ok(proc_output) => {
                if !proc_output.status.success() {
                    let stderr = String::from_utf8_lossy(&proc_output.stderr);
                    log::error!(
                        "[VcPluginAdapter] CLI {} 返回错误 (exit {}): {}",
                        self.id,
                        proc_output.status.code().unwrap_or(-1),
                        &stderr[..stderr.len().min(500)]
                    );
                    output.data.copy_from_slice(&input.data);
                    return;
                }
            }
            Err(e) => {
                log::error!("[VcPluginAdapter] CLI {} 执行失败: {}", self.id, e);
                output.data.copy_from_slice(&input.data);
                return;
            }
        }

        // 5. 读取输出 WAV
        if !out_path.exists() {
            log::error!("[VcPluginAdapter] CLI {} 未生成输出文件", self.id);
            output.data.copy_from_slice(&input.data);
            return;
        }

        match read_wav_to_audio_buffer(&out_path, output) {
            Ok(()) => {}
            Err(e) => {
                log::error!("[VcPluginAdapter] 读取输出WAV失败: {}", e);
                output.data.copy_from_slice(&input.data);
            }
        }
    }

    fn get_params(&self) -> Vec<ParamInfo> {
        // 返回带有当前值的参数列表
        self.params
            .iter()
            .map(|p| {
                let mut p = p.clone();
                if let Some(v) = self.param_values.get(&p.id) {
                    p.value = *v;
                }
                p
            })
            .collect()
    }

    fn set_param(&mut self, id: &str, value: f64) -> Result<(), PluginError> {
        // 查找参数定义
        let param = self.params.iter().find(|p| p.id == id).ok_or_else(|| {
            PluginError::ParamNotFound(format!(
                "插件 {} 没有参数 '{}'",
                self.id, id
            ))
        })?;

        let clamped = value.clamp(param.min, param.max);
        self.param_values.insert(id.to_string(), clamped);

        Ok(())
    }

    fn get_param(&self, id: &str) -> Option<f64> {
        self.param_values.get(id).copied()
    }

    fn get_info(&self) -> opendaw_extension::PluginInfo {
        opendaw_extension::PluginInfo {
            id: self.id.clone(),
            name: self.name.clone(),
            author: "VC-AudioFX".to_string(),
            version: self.version().to_string(),
            plugin_type: self.plugin_type(),
            parameters: self.get_params(),
        }
    }

    fn destroy(&mut self) {
        self.initialized = false;
        log::debug!("[VcPluginAdapter] 销毁 {}", self.id);
    }
}

// ── 内部辅助函数 ──────────────────────────────────────────────────────────

/// 递归扫描目录查找 CLI 二进制
fn scan_for_cli_binaries(
    dir: &Path,
    adapters: &mut Vec<VcPluginAdapter>,
) -> Result<(), PluginError> {
    let entries = fs::read_dir(dir).map_err(|e| {
        PluginError::ProcessFailed(format!("无法读取目录 {}: {}", dir.display(), e))
    })?;

    for entry in entries {
        let entry = match entry {
            Ok(e) => e,
            Err(e) => {
                log::warn!("[VcPluginAdapter] 读取目录条目失败: {}", e);
                continue;
            }
        };

        let path = entry.path();

        if path.is_dir() {
            // 递归扫描子目录
            scan_for_cli_binaries(&path, adapters)?;
        } else if path.is_file() {
            // 检查文件名是否匹配 *CLI-Standalone* 模式
            let file_name = path.file_name().unwrap_or_default().to_string_lossy();

            if file_name.contains(CLI_BINARY_PATTERN) {
                match VcPluginAdapter::from_binary(&path) {
                    Ok(adapter) => {
                        log::info!(
                            "[VcPluginAdapter] 发现插件: {} → {}",
                            adapter.id,
                            path.display()
                        );
                        adapters.push(adapter);
                    }
                    Err(e) => {
                        log::warn!(
                            "[VcPluginAdapter] 跳过无效二进制 {}: {}",
                            path.display(),
                            e
                        );
                    }
                }
            }
        }
    }

    Ok(())
}

/// 从二进制路径推断 plugin_id 和 plugin_name
///
/// 文件名格式：`VC-{Name}-CLI-Standalone`
/// → plugin_id = `vc-{name}` (小写)
/// → plugin_name = `VC-{Name}`
fn infer_plugin_info(path: &Path) -> (String, String) {
    let file_name = path
        .file_name()
        .unwrap_or_default()
        .to_string_lossy();

    // 尝试从文件名提取：VC-{Name}-CLI-Standalone
    if let Some(rest) = file_name.strip_prefix("VC-") {
        if let Some(name_part) = rest.strip_suffix("-CLI-Standalone") {
            let plugin_id = format!("vc-{}", name_part.to_lowercase());
            let plugin_name = format!("VC-{}", name_part);
            return (plugin_id, plugin_name);
        }
    }

    // 回退：使用文件名（去掉扩展名）
    let stem = path
        .file_stem()
        .unwrap_or_default()
        .to_string_lossy()
        .to_string();
    let plugin_id = stem.to_lowercase();
    let plugin_name = stem;
    (plugin_id, plugin_name)
}

/// 查找参数对应的精确CLI flag
fn find_cli_flag_for_param(plugin_id: &str, param_id: &str) -> Option<String> {
    BUILTIN_PLUGINS
        .iter()
        .find(|def| def.plugin_id == plugin_id)
        .and_then(|def| {
            def.params
                .iter()
                .find(|p| p.id == param_id)
                .map(|p| p.cli_flag.to_string())
        })
}

/// 将 AudioBuffer 写入 WAV 文件
///
/// 使用 hound 库进行标准 WAV 编码（32-bit float），
/// 数据以交错格式存储（L, R, L, R, ...）
fn write_audio_buffer_to_wav(
    buffer: &AudioBuffer,
    path: &Path,
    sample_rate: u32,
) -> Result<(), String> {
    let channels = buffer.channels as u16;
    let frames = buffer.frames;

    if channels == 0 || frames == 0 {
        return Err("音频缓冲区为空（0声道或0帧）".to_string());
    }

    let spec = hound::WavSpec {
        channels,
        sample_rate,
        bits_per_sample: 32,
        sample_format: hound::SampleFormat::Float,
    };

    let mut writer = hound::WavWriter::create(path, spec)
        .map_err(|e| format!("创建WAV文件失败 {}: {}", path.display(), e))?;

    // AudioBuffer.data 是非交错存储: data[channel * frames + frame]
    // hound 需要按帧写入（交错顺序）
    for frame in 0..frames {
        for ch in 0..(channels as usize) {
            let sample = buffer.data[ch * frames + frame] as f32;
            writer
                .write_sample(sample)
                .map_err(|e| format!("写入采样数据失败: {}", e))?;
        }
    }

    writer
        .finalize()
        .map_err(|e| format!("WAV写入完成失败: {}", e))?;

    Ok(())
}

/// 从 WAV 文件读取到 AudioBuffer
///
/// 读取 WAV 文件，将数据转换为 AudioBuffer 的非交错格式。
/// 自动调整 output 的 channels 和 frames。
fn read_wav_to_audio_buffer(path: &Path, output: &mut AudioBuffer) -> Result<(), String> {
    let mut reader = hound::WavReader::open(path)
        .map_err(|e| format!("打开WAV文件失败 {}: {}", path.display(), e))?;

    let spec = reader.spec();
    let channels = spec.channels as usize;

    // 读取所有采样
    let samples: Vec<f32> = reader
        .samples::<f32>()
        .collect::<Result<Vec<_>, _>>()
        .map_err(|e| format!("读取WAV采样数据失败: {}", e))?;

    let frames = if channels > 0 {
        samples.len() / channels
    } else {
        0
    };

    if frames == 0 || channels == 0 {
        return Err("WAV文件无有效音频数据".to_string());
    }

    // 更新 output 缓冲区
    // 注意：AudioBuffer.data 是非交错存储
    output.channels = channels;
    output.frames = frames;
    output.data.resize(channels * frames, 0.0);

    // 解交错：interleaved [L0,R0,L1,R1,...] → planar [L0,L1,...,R0,R1,...]
    for (i, sample) in samples.iter().enumerate() {
        let ch = i % channels;
        let frame = i / channels;
        output.data[ch * frames + frame] = *sample as f64;
    }

    Ok(())
}

/// 从 --help 输出解析参数列表
///
/// 简单启发式：查找 `--param-name` 模式，推断参数名。
/// 无法获取 min/max/default 等详细信息，使用默认范围 [0, 100]。
fn parse_help_for_params(help_text: &str) -> Vec<ParamInfo> {
    let mut params = Vec::new();
    let mut seen = std::collections::HashSet::new();

    for line in help_text.lines() {
        let line = line.trim();
        for part in line.split_whitespace() {
            if let Some(flag) = part.strip_prefix("--") {
                // 过滤掉已知的非参数 flag
                if flag.starts_with("help")
                    || flag.starts_with("version")
                    || flag.starts_with("verbose")
                    || flag.starts_with("input")
                    || flag.starts_with("output")
                    || flag.starts_with("sample-rate")
                    || flag.contains('=')
                {
                    continue;
                }

                // 规范化 flag 名
                let flag = flag.trim_end_matches(',');
                let param_id = flag.replace('-', "_");

                if !seen.insert(param_id.clone()) {
                    continue; // 已存在
                }

                // 默认范围 [0, 100]
                params.push(ParamInfo::new(
                    &param_id,
                    flag,
                    0.0,
                    100.0,
                    50.0,
                    "",
                ));
            }
        }
    }

    params
}

// ── 单元测试 ──────────────────────────────────────────────────────────────

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_infer_plugin_info() {
        // 标准格式
        let path = Path::new("/tmp/AudioFX/VC-EQ/VC-EQ-CLI-Standalone");
        let (id, name) = infer_plugin_info(path);
        assert_eq!(id, "vc-eq");
        assert_eq!(name, "VC-EQ");

        // 多段名称
        let path = Path::new("/tmp/AudioFX/VC-DynamicEQ/VC-DynamicEQ-CLI-Standalone");
        let (id, name) = infer_plugin_info(path);
        assert_eq!(id, "vc-dynamiceq");
        assert_eq!(name, "VC-DynamicEQ");

        // 非标准格式回退
        let path = Path::new("/usr/local/bin/my-effect");
        let (id, name) = infer_plugin_info(path);
        assert_eq!(id, "my-effect");
        assert_eq!(name, "my-effect");
    }

    #[test]
    fn test_builtin_params_coverage() {
        // 确保所有20个已知插件都有参数定义
        assert!(BUILTIN_PLUGINS.len() >= 20, "应有至少20个插件的参数定义");

        for def in BUILTIN_PLUGINS {
            assert!(!def.params.is_empty(), "插件 {} 应有参数定义", def.plugin_id);
        }
    }

    #[test]
    fn test_builtin_param_values_match() {
        // 确保内置参数表的 default 值在 [min, max] 范围内
        for def in BUILTIN_PLUGINS {
            for p in def.params {
                assert!(
                    p.default >= p.min && p.default <= p.max,
                    "插件 {} 参数 {} default={} 不在 [{}, {}] 范围内",
                    def.plugin_id, p.id, p.default, p.min, p.max
                );
            }
        }
    }

    #[test]
    fn test_find_cli_flag() {
        // 测试CLI flag查找
        assert_eq!(
            find_cli_flag_for_param("vc-eq", "peak_freq"),
            Some("--peak-freq".to_string())
        );
        assert_eq!(
            find_cli_flag_for_param("vc-reverb", "room"),
            Some("--room".to_string())
        );
        assert_eq!(
            find_cli_flag_for_param("vc-eq", "nonexistent"),
            None
        );
    }

    #[test]
    fn test_param_set_and_clamp() {
        let mut adapter = VcPluginAdapter {
            id: "vc-eq".to_string(),
            name: "VC-EQ".to_string(),
            binary_path: PathBuf::from("/tmp/fake"),
            params: get_builtin_params("vc-eq"),
            param_values: HashMap::new(),
            sample_rate: 44100.0,
            buffer_size: 1024,
            initialized: true,
        };
        // 初始化默认值
        for p in &adapter.params {
            adapter.param_values.insert(p.id.clone(), p.value);
        }

        // 正常设置
        adapter.set_param("peak_gain", 6.0).unwrap();
        assert_eq!(adapter.param_values["peak_gain"], 6.0);

        // 超出范围 → clamp
        adapter.set_param("peak_gain", 100.0).unwrap();
        assert_eq!(adapter.param_values["peak_gain"], 24.0); // max is 24.0

        // 不存在的参数
        assert!(adapter.set_param("nonexistent", 0.0).is_err());
    }

    #[test]
    fn test_parse_help() {
        let help = "\
Usage: VC-EQ-CLI-Standalone [OPTIONS] input.wav output.wav

Options:
  --low-cut FREQ     Low cut frequency (Hz)
  --high-cut FREQ    High cut frequency (Hz)
  --peak-gain GAIN   Peak gain (dB)
";
        let params = parse_help_for_params(help);
        assert!(!params.is_empty());
        let ids: Vec<&str> = params.iter().map(|p| p.id.as_str()).collect();
        assert!(ids.contains(&"low_cut"), "应发现 low_cut");
        assert!(ids.contains(&"high_cut"), "应发现 high_cut");
        assert!(ids.contains(&"peak_gain"), "应发现 peak_gain");
    }

    #[test]
    fn test_adapter_passthrough_when_uninitialized() {
        let mut adapter = VcPluginAdapter {
            id: "vc-test".to_string(),
            name: "测试".to_string(),
            binary_path: PathBuf::from("/nonexistent"),
            params: vec![],
            param_values: HashMap::new(),
            sample_rate: 44100.0,
            buffer_size: 256,
            initialized: false,
        };

        // 未初始化时应该直通
        let input = AudioBuffer::new(2, 256);
        let mut output = AudioBuffer::new(2, 256);
        adapter.process(&input, &mut output);

        for i in 0..input.data.len() {
            assert!((output.data[i] - input.data[i]).abs() < 1e-10);
        }
    }

    #[test]
    fn test_all_known_plugin_ids() {
        let ids = all_known_plugin_ids();
        assert!(ids.len() >= 20);
        assert!(ids.contains(&"vc-eq"));
        assert!(ids.contains(&"vc-reverb"));
        assert!(ids.contains(&"vc-harmonizer"));
    }
}
