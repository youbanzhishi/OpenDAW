//! JSFX端到端测试：加载.jsfx文件 → PluginChain → 输出音频
//!
//! 验证完整的JSFX处理链路

use jsfx_engine::{load_jsfx_source, JsfxPlugin, VcPlugin};
use opendaw_extension::AudioBuffer as ExtAudioBuffer;
use plugin_host::chain::PluginChain;

fn main() {
    println!("=== JSFX端到端测试 ===\n");

    // 测试1: 加载并处理gain.jsfx
    test_gain_plugin();

    // 测试2: PluginChain处理多个JSFX
    test_plugin_chain();

    // 测试3: 动态slider参数更新
    test_slider_update();

    println!("\n所有测试通过! ✅");
}

/// 测试1: 基本的gain JSFX处理
fn test_gain_plugin() {
    println!("[测试1] 基础Gain JSFX处理");

    let source = r#"
desc:Test Gain
slider1:6<-150,150,0.1>Gain (dB)

@slider
gain = 2^(slider1/6);

@sample
spl0 *= gain;
spl1 *= gain;
"#;

    let mut plugin = load_jsfx_source(source, "test-gain").unwrap();
    plugin.init(44100.0, 256).unwrap();

    // 创建测试输入: 振幅0.5的正弦波
    let frames = 441; // 10ms @ 44100Hz
    let mut input = ExtAudioBuffer::new(2, frames);

    for i in 0..frames {
        let t = i as f64 / 44100.0;
        let sample = 0.5 * (2.0 * std::f64::consts::PI * 1000.0 * t).sin();
        input.set_sample(0, i, sample);
        input.set_sample(1, i, sample);
    }

    let mut output = ExtAudioBuffer::new(2, frames);
    plugin.process(&input, &mut output);

    // 验证: 6dB = 2x增益，输出振幅应该是1.0
    let tolerance = 0.01;
    let peak_l = (0..frames)
        .map(|i| output.sample(0, i).abs())
        .fold(0.0f64, |a, b| a.max(b));

    println!("  输入峰值: {:.4}", 0.5);
    println!("  输出峰值: {:.4}", peak_l);
    println!("  期望峰值: {:.4} (6dB增益)", 1.0);

    assert!((peak_l - 1.0).abs() < tolerance, "增益效果不正确");
    println!("  ✅ 通过\n");
}

/// 测试2: PluginChain中多个JSFX串联
fn test_plugin_chain() {
    println!("[测试2] PluginChain多JSFX串联");

    let gain_source = r#"
desc:Gain Stage 1
slider1:6<-150,150,0.1>Gain (dB)

@slider
gain = 2^(slider1/6);

@sample
spl0 *= gain;
spl1 *= gain;
"#;

    let tone_source = r#"
desc:Tone Control
slider1:1<0.1,10,0.1>Brightness

@sample
// 简单的高频提升
spl0 = spl0 * slider1;
spl1 = spl1 * slider1;
"#;

    let mut chain = PluginChain::new(2, 256);

    // 添加两个JSFX插件到链中
    let plugin1 = load_jsfx_source(gain_source, "gain").unwrap();
    let plugin2 = load_jsfx_source(tone_source, "tone").unwrap();

    chain.push(Box::new(plugin1));
    chain.push(Box::new(plugin2));

    // 初始化所有插件
    for i in 0..chain.len() {
        if let Some(plugin) = chain.get_plugin_mut(i) {
            plugin.init(44100.0, 256).unwrap();
        }
    }

    // 创建输入
    let frames = 256;
    let mut input = ExtAudioBuffer::new(2, frames);
    for i in 0..frames {
        input.set_sample(0, i, 0.3);
        input.set_sample(1, i, 0.3);
    }

    // 处理
    let mut output = ExtAudioBuffer::new(2, frames);
    chain.process(&input, &mut output);

    // 验证: gain 6dB * brightness 1 = 2x，0.3 * 2 = 0.6
    let peak = output.sample(0, 0).abs();
    println!("  输入: {:.4}", 0.3);
    println!("  输出: {:.4}", peak);
    println!("  期望: {:.4}", 0.6);

    assert!((peak - 0.6).abs() < 0.001);
    println!("  ✅ 通过\n");
}

/// 测试3: 动态slider参数更新
fn test_slider_update() {
    println!("[测试3] 动态Slider参数更新");

    let source = r#"
desc:Dynamic Gain
slider1:0<-150,150,0.1>Gain (dB)

@slider
gain = 2^(slider1/6);

@sample
spl0 *= gain;
spl1 *= gain;
"#;

    let mut plugin = load_jsfx_source(source, "dynamic-gain").unwrap();
    plugin.init(44100.0, 256).unwrap();

    // 创建输入
    let mut input = ExtAudioBuffer::new(2, 10);
    input.set_sample(0, 0, 1.0);
    input.set_sample(1, 0, 1.0);

    // 测试不同增益值
    let test_cases = vec![
        (0.0, 1.0, "0dB"),
        (6.0, 2.0, "6dB"),
        (-6.0, 0.5, "-6dB"),
        (12.0, 4.0, "12dB"),
    ];

    for (db, expected, label) in test_cases {
        plugin.set_param("slider1", db).unwrap();

        let mut output = ExtAudioBuffer::new(2, 10);
        plugin.process(&input, &mut output);

        let actual = output.sample(0, 0);
        println!("  {}: 期望{:.4}, 实际{:.4}", label, expected, actual);
        assert!((actual - expected).abs() < 0.001);
    }

    println!("  ✅ 通过\n");
}
