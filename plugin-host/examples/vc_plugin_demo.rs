//! VC-Plugin 适配器演示
//!
//! 演示如何：
//!   1. 从 plugin_id 创建适配器（自动搜索二进制）
//!   2. 扫描目录发现所有可用插件
//!   3. 初始化插件并处理一段 sine wave
//!
//! # 运行
//!
//! ```bash
//! # 设置插件目录（可选，默认 $VC_AUDIOFX_DIR 或 /tmp/AudioFX）
//! export VC_AUDIOFX_DIR=/path/to/AudioFX
//!
//! cargo run -p plugin-host --example vc_plugin_demo
//! ```

use opendaw_extension::{AudioBuffer, VcPlugin};
use plugin_host::VcPluginAdapter;
use std::f64::consts::PI;
use std::path::Path;

fn main() {
    // 初始化日志
    env_logger::Builder::from_env(env_logger::Env::default().default_filter_or("info")).init();

    println!("╔══════════════════════════════════════════════╗");
    println!("║  OpenDAW VC-Plugin 适配器演示               ║");
    println!("╚══════════════════════════════════════════════╝");
    println!();

    // ── 1. 展示已知插件列表 ──────────────────────────────────────────
    let known_ids = plugin_host::all_known_plugin_ids();
    println!("📋 内置参数注册表包含 {} 个插件定义:", known_ids.len());
    for id in &known_ids {
        println!("   - {}", id);
    }
    println!();

    // ── 2. 扫描目录发现所有VC插件 ──────────────────────────────────
    let plugin_dir = std::env::var("VC_AUDIOFX_DIR")
        .map(|s| std::path::PathBuf::from(s))
        .unwrap_or_else(|_| std::path::PathBuf::from("/tmp/AudioFX"));

    println!("📂 扫描插件目录: {}", plugin_dir.display());
    match VcPluginAdapter::scan_directory(&plugin_dir) {
        Ok(plugins) => {
            if plugins.is_empty() {
                println!("   ⚠️  未发现任何VC插件");
                println!(
                    "   提示: 设置 VC_AUDIOFX_DIR 环境变量指向包含 VC-*-CLI-Standalone 的目录"
                );
            } else {
                println!("   ✅ 发现 {} 个VC插件:", plugins.len());
                for p in &plugins {
                    println!(
                        "      - {} ({}) → {}",
                        p.plugin_name(),
                        p.plugin_id(),
                        p.binary_path().display()
                    );
                }
            }
        }
        Err(e) => {
            println!("   ❌ 扫描失败: {}", e);
            println!("   这可能是因为插件目录不存在");
        }
    }
    println!();

    // ── 3. 从 plugin_id 创建适配器 ─────────────────────────────────
    println!("🔌 尝试加载 VC-EQ 插件...");
    let mut eq_plugin = match VcPluginAdapter::from_plugin_id("vc-eq") {
        Ok(adapter) => {
            println!(
                "   ✅ 找到: {} → {}",
                adapter.plugin_name(),
                adapter.binary_path().display()
            );
            adapter
        }
        Err(e) => {
            println!("   ❌ 未找到 VC-EQ: {}", e);
            println!();
            println!("   💡 演示模式：展示参数系统但无法进行实际处理");
            println!("      安装VC插件后即可进行实际音频处理");
            demo_param_system();
            return;
        }
    };

    // ── 4. 初始化插件 ─────────────────────────────────────────────
    println!();
    println!("⚙️  初始化插件 (sample_rate=44100, buffer_size=1024)...");
    if let Err(e) = eq_plugin.init(44100.0, 1024) {
        println!("   ❌ 初始化失败: {}", e);
        return;
    }
    println!("   ✅ 初始化成功");

    // ── 5. 展示参数 ────────────────────────────────────────────────
    println!();
    println!("🎛️  参数列表:");
    let params = eq_plugin.get_params();
    for p in &params {
        println!("   - {} ({}) = {} {}", p.id, p.name, p.value, p.unit);
    }

    // 设置 EQ 参数
    if eq_plugin.set_param("peak_freq", 2000.0).is_ok() {
        println!("   → 设置 peak_freq = 2000 Hz");
    }
    if eq_plugin.set_param("peak_gain", 3.0).is_ok() {
        println!("   → 设置 peak_gain = 3 dB");
    }

    // ── 6. 生成 sine wave 并处理 ──────────────────────────────────
    println!();
    println!("🎵 生成 440Hz sine wave (1024帧, 立体声)...");
    let sample_rate = 44100.0;
    let frames = 1024;
    let mut input = AudioBuffer::new(2, frames);

    // 生成 440Hz sine wave（左声道）
    let freq = 440.0f64;
    for frame in 0..frames {
        let t = frame as f64 / sample_rate;
        let sample = (2.0 * PI * freq * t).sin() * 0.5;
        input.set_sample(0, frame, sample); // 左声道
        input.set_sample(1, frame, sample); // 右声道
    }
    println!("   ✅ 已生成 {} 帧 sine wave", frames);

    // 处理
    println!("   🔄 通过 VC-EQ 处理中...");
    let mut output = AudioBuffer::new(2, frames);
    eq_plugin.process(&input, &mut output);

    // 计算输出 RMS
    let rms: f64 = output.data.iter().map(|s| s * s).sum::<f64>() / output.data.len() as f64;
    let rms_db = 20.0 * rms.sqrt().log10();
    println!("   ✅ 处理完成！输出 RMS: {:.2} dB", rms_db);

    // ── 7. 销毁插件 ────────────────────────────────────────────────
    eq_plugin.destroy();
    println!();
    println!("🏁 插件已销毁，演示结束");
}

/// 演示参数系统（无需真实插件）
fn demo_param_system() {
    println!();
    println!("── 参数系统演示 ──");

    use opendaw_extension::{ParamInfo, PluginType};

    // 展示 VC-EQ 的参数定义
    let eq_params = vec![
        ParamInfo::new("low_cut", "Low Cut", 20.0, 20000.0, 20.0, "Hz"),
        ParamInfo::new("high_cut", "High Cut", 20.0, 20000.0, 20000.0, "Hz"),
        ParamInfo::new("peak_freq", "Peak Frequency", 20.0, 20000.0, 1000.0, "Hz"),
        ParamInfo::new("peak_gain", "Peak Gain", -24.0, 24.0, 0.0, "dB"),
    ];

    println!("VC-EQ 参数列表:");
    for p in &eq_params {
        println!("  {} [{}-{}] = {} {}", p.id, p.min, p.max, p.value, p.unit);
    }

    // 展示插件类型
    println!();
    println!("插件类型:");
    println!("  Effect      = {:?}", PluginType::Effect);
    println!("  Instrument  = {:?}", PluginType::Instrument);
    println!("  Analyzer    = {:?}", PluginType::Analyzer);
    println!("  MidiProcessor = {:?}", PluginType::MidiProcessor);

    // 展示所有已知插件
    let all_ids = plugin_host::all_known_plugin_ids();
    println!();
    println!("内置参数注册表包含 {} 个插件定义", all_ids.len());
}
