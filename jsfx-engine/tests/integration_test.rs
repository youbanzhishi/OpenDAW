//! 集成测试 — 加载JSFX文件并验证处理结果
//!
//! 覆盖：
//! - 基本增益效果
//! - 低通滤波器
//! - 延迟效果
//! - 混响效果
//! - 参数均衡器
//! - 三目运算符
//! - if/else语句
//! - 数学内置函数
//! - Plugin适配器
//! - 变量运算
//! - slider参数范围
//! - 预处理器
//! - $常量
//! - 内存操作
//! - 用户函数
//! - 多区段执行

use jsfx_engine::parser::JsfxParser;
use jsfx_engine::vm::JsfxVm;
use jsfx_engine::AudioBuffer;
use jsfx_engine::JsfxPlugin;
use jsfx_engine::VcPlugin;
use jsfx_engine::loader::{load_jsfx_source, JsfxMeta};
use std::path::Path;

// ==================== 文件加载测试 ====================

/// 测试加载gain.jsfx
#[test]
fn test_load_gain_jsfx() {
    let path = Path::new("tests/gain.jsfx");
    if !path.exists() {
        eprintln!("跳过: tests/gain.jsfx 不存在");
        return;
    }
    let source = std::fs::read_to_string(path).unwrap();
    let program = JsfxParser::parse(&source).unwrap();
    assert_eq!(program.desc, "Simple Gain");
    assert_eq!(program.sliders.len(), 1);
}

/// 测试加载reverb.jsfx
#[test]
fn test_load_reverb_jsfx() {
    let path = Path::new("tests/reverb.jsfx");
    if !path.exists() {
        eprintln!("跳过: tests/reverb.jsfx 不存在");
        return;
    }
    let source = std::fs::read_to_string(path).unwrap();
    let program = JsfxParser::parse(&source).unwrap();
    assert_eq!(program.desc, "Simple Reverb (Comb Filter)");
    assert!(program.init_block.is_some());
    assert!(program.sample_block.is_some());
}

/// 测试加载eq.jsfx
#[test]
fn test_load_eq_jsfx() {
    let path = Path::new("tests/eq.jsfx");
    if !path.exists() {
        eprintln!("跳过: tests/eq.jsfx 不存在");
        return;
    }
    let source = std::fs::read_to_string(path).unwrap();
    let program = JsfxParser::parse(&source).unwrap();
    assert_eq!(program.desc, "Parametric EQ");
    assert_eq!(program.sliders.len(), 3);
}

// ==================== 增益效果测试 ====================

/// 测试增益效果
#[test]
fn test_gain_effect() {
    let source = r#"
desc:Simple Gain
slider1:0<-150,150,0.1>Gain (dB)

@slider
gain = 2^(slider1/6);

@sample
spl0 *= gain;
spl1 *= gain;
"#;
    let program = JsfxParser::parse(source).unwrap();
    let mut vm = JsfxVm::new();
    vm.load(&program).unwrap();
    vm.init(44100.0);

    // 0dB = gain 1.0
    vm.update_slider(1, 0.0);
    let (out0, out1) = vm.process_sample(0.8, 0.6);
    assert!((out0 - 0.8).abs() < 0.01, "0dB: 期望0.8, 得到{}", out0);
    assert!((out1 - 0.6).abs() < 0.01, "0dB: 期望0.6, 得到{}", out1);

    // +6dB = gain 2.0
    vm.update_slider(1, 6.0);
    let (out0, out1) = vm.process_sample(0.5, 0.5);
    assert!((out0 - 1.0).abs() < 0.01, "+6dB: 期望1.0, 得到{}", out0);
    assert!((out1 - 1.0).abs() < 0.01, "+6dB: 期望1.0, 得到{}", out1);

    // -6dB = gain 0.5
    vm.update_slider(1, -6.0);
    let (out0, out1) = vm.process_sample(1.0, 1.0);
    assert!((out0 - 0.5).abs() < 0.01, "-6dB: 期望0.5, 得到{}", out0);
    assert!((out1 - 0.5).abs() < 0.01, "-6dB: 期望0.5, 得到{}", out1);
}

// ==================== 低通滤波器测试 ====================

/// 测试低通滤波器
#[test]
fn test_lowpass_filter() {
    let source = r#"
desc:Simple Lowpass Filter
slider1:1000<20,20000,1>Cutoff (Hz)

@init
_lp0 = 0;
_lp1 = 0;

@slider
freq = slider1;

@sample
k = exp(-2 * $pi * freq / srate);
_lp0 = spl0 * (1-k) + _lp0 * k;
spl0 = _lp0;
_lp1 = spl1 * (1-k) + _lp1 * k;
spl1 = _lp1;
"#;
    let program = JsfxParser::parse(source).unwrap();
    assert_eq!(program.desc, "Simple Lowpass Filter");
    assert_eq!(program.sliders.len(), 1);

    let mut vm = JsfxVm::new();
    vm.load(&program).unwrap();
    vm.init(44100.0);

    // 低通滤波器应该能运行不崩溃
    for _ in 0..100 {
        let (out0, out1) = vm.process_sample(1.0, 1.0);
        assert!(out0.is_finite(), "输出应为有限值");
        assert!(out1.is_finite(), "输出应为有限值");
    }

    // 经过足够采样后，DC输入的输出应接近输入
    // 低通对DC（0Hz）应该几乎直通
}

// ==================== 延迟效果测试 ====================

/// 测试延迟效果
#[test]
fn test_delay_effect() {
    let source = r#"
desc:Simple Delay
slider1:200<1,2000,1>Delay (ms)
slider2:0.5<0,1,0.01>Feedback

@init
delay_pos = 0;
delay_len = srate * 2;
memory(0, delay_len);

@sample
rdpos = delay_pos - (slider1/1000 * srate);
rdpos < 0 ? rdpos += delay_len;
d = mem_get(rdpos);
spl0 = spl0 + d;
spl1 = spl1 + d;
mem_set(delay_pos, spl0 * slider2);
delay_pos += 1;
delay_pos >= delay_len ? delay_pos = 0;
"#;
    let program = JsfxParser::parse(source).unwrap();
    assert_eq!(program.desc, "Simple Delay");

    let mut vm = JsfxVm::new();
    vm.load(&program).unwrap();
    vm.init(44100.0);

    // 延迟效果器应该能运行不崩溃
    for _ in 0..1000 {
        let (out0, out1) = vm.process_sample(0.5, 0.5);
        assert!(out0.is_finite(), "输出应为有限值");
        assert!(out1.is_finite(), "输出应为有限值");
    }
}

// ==================== 混响效果测试 ====================

/// 测试混响效果（Comb滤波器）
#[test]
fn test_reverb_effect() {
    let source = r#"
desc:Simple Reverb (Comb Filter)
slider1:0.5<0,1,0.01>Wet/Dry
slider2:0.6<0,0.99,0.01>Feedback
slider3:50<10,200,1>Delay (ms)

@init
comb_pos = 0;
comb_len = srate;
memory(0, comb_len);

@sample
rdpos = comb_pos - (slider3/1000 * srate);
rdpos < 0 ? rdpos += comb_len;
d = mem_get(rdpos);
wet = slider1;
dry = 1 - slider1;
mem_set(comb_pos, spl0 + d * slider2);
spl0 = spl0 * dry + d * wet;
spl1 = spl1 * dry + d * wet;
comb_pos += 1;
comb_pos >= comb_len ? comb_pos = 0;
"#;
    let program = JsfxParser::parse(source).unwrap();
    assert_eq!(program.desc, "Simple Reverb (Comb Filter)");

    let mut vm = JsfxVm::new();
    vm.load(&program).unwrap();
    vm.init(44100.0);

    // 混响效果器应该能运行不崩溃
    for _ in 0..5000 {
        let (out0, out1) = vm.process_sample(0.5, 0.5);
        assert!(out0.is_finite(), "输出应为有限值");
        assert!(out1.is_finite(), "输出应为有限值");
    }
}

// ==================== 三目运算符测试 ====================

/// 测试三目运算符
#[test]
fn test_ternary_operator() {
    let source = r#"
desc:Ternary Test

@sample
spl0 = spl0 > 0.5 ? 1.0 : 0.0;
spl1 = spl1 < -0.5 ? -1.0 : spl1;
"#;
    let program = JsfxParser::parse(source).unwrap();
    let mut vm = JsfxVm::new();
    vm.load(&program).unwrap();
    vm.init(44100.0);

    // spl0 > 0.5 → 1.0
    let (out0, _) = vm.process_sample(0.8, 0.0);
    assert!((out0 - 1.0).abs() < 0.01, "期望1.0, 得到{}", out0);

    // spl0 <= 0.5 → 0.0
    let (out0, _) = vm.process_sample(0.3, 0.0);
    assert!((out0 - 0.0).abs() < 0.01, "期望0.0, 得到{}", out0);
}

// ==================== if/else语句测试 ====================

/// 测试if/else语句（使用三目运算符形式）
#[test]
fn test_if_else() {
    let source = r#"
desc:If Else Test

@sample
spl0 > 0 ? spl0 = spl0 * 2 : spl0 = spl0 * -1;
spl1 = spl0;
"#;
    let program = JsfxParser::parse(source).unwrap();
    let mut vm = JsfxVm::new();
    vm.load(&program).unwrap();
    vm.init(44100.0);

    let (out0, _) = vm.process_sample(0.5, 0.0);
    // if spl0 > 0: spl0 * 2 = 1.0
    assert!((out0 - 1.0).abs() < 0.01, "正数: 期望1.0, 得到{}", out0);
}

// ==================== 数学内置函数测试 ====================

/// 测试数学内置函数
#[test]
fn test_builtin_functions() {
    let source = r#"
desc:Builtin Functions Test

@sample
x = sin($pi / 2);
y = cos(0);
spl0 = x;
spl1 = y;
"#;
    let program = JsfxParser::parse(source).unwrap();
    let mut vm = JsfxVm::new();
    vm.load(&program).unwrap();
    vm.init(44100.0);

    let (out0, out1) = vm.process_sample(0.0, 0.0);
    assert!((out0 - 1.0).abs() < 0.01, "sin(π/2) ≈ 1.0, 得到{}", out0);
    assert!((out1 - 1.0).abs() < 0.01, "cos(0) ≈ 1.0, 得到{}", out1);
}

/// 测试更多数学函数
#[test]
fn test_more_builtin_functions() {
    let source = r#"
desc:More Math Functions

@sample
a = abs(-5);
b = sqrt(16);
c = floor(3.7);
d = ceil(3.2);
e = round(3.5);
spl0 = a + b + c + d + e;
spl1 = sign(-10);
"#;
    let program = JsfxParser::parse(source).unwrap();
    let mut vm = JsfxVm::new();
    vm.load(&program).unwrap();
    vm.init(44100.0);

    let (out0, out1) = vm.process_sample(0.0, 0.0);
    // abs(-5)=5 + sqrt(16)=4 + floor(3.7)=3 + ceil(3.2)=4 + round(3.5)=4 = 20
    assert!((out0 - 20.0).abs() < 0.01, "期望20.0, 得到{}", out0);
    assert!((out1 - (-1.0)).abs() < 0.01, "sign(-10) = -1, 得到{}", out1);
}

// ==================== Plugin适配器测试 ====================

/// 测试JsfxPlugin适配器
#[test]
fn test_plugin_adapter() {
    let source = r#"
desc:Plugin Test
slider1:0<-12,12,0.1>Gain (dB)

@slider
gain = 2^(slider1/6);

@sample
spl0 *= gain;
spl1 *= gain;
"#;

    let mut plugin = JsfxPlugin::from_source(source, "test_plugin").unwrap();
    assert_eq!(plugin.plugin_id(), "jsfx-test_plugin");
    assert_eq!(plugin.plugin_name(), "Plugin Test");

    plugin.init(48000.0, 512).unwrap();

    let params = plugin.get_params();
    assert_eq!(params.len(), 1);
    assert_eq!(params[0].id, "slider1");

    // 设置参数
    plugin.set_param("slider1", 0.0).unwrap();
    assert!((plugin.get_param("slider1").unwrap() - 0.0).abs() < 0.001);

    // 处理音频
    let input = AudioBuffer::new(2, 256);
    let mut output = AudioBuffer::new(2, 256);
    plugin.process(&input, &mut output);

    // 静音输入→静音输出
    for i in 0..256 {
        assert!(output.sample(0, i).abs() < 0.001);
    }

    plugin.destroy();
}

// ==================== 变量运算测试 ====================

/// 测试变量赋值和运算
#[test]
fn test_variable_operations() {
    let source = r#"
desc:Variable Test

@init
x = 10;
y = 20;
z = x + y;

@sample
spl0 = z;
spl1 = z * 2;
"#;
    let program = JsfxParser::parse(source).unwrap();
    let mut vm = JsfxVm::new();
    vm.load(&program).unwrap();
    vm.init(44100.0);

    let (out0, out1) = vm.process_sample(0.0, 0.0);
    assert!((out0 - 30.0).abs() < 0.01, "x+y=30, 得到{}", out0);
    assert!((out1 - 60.0).abs() < 0.01, "z*2=60, 得到{}", out1);
}

// ==================== Slider参数范围测试 ====================

/// 测试slider参数范围
#[test]
fn test_slider_ranges() {
    let source = r#"
desc:Slider Test
slider1:50<0,100,1>Volume

@sample
spl0 *= slider1 / 100;
spl1 *= slider1 / 100;
"#;
    let program = JsfxParser::parse(source).unwrap();
    assert_eq!(program.sliders.len(), 1);

    let slider = &program.sliders[0];
    assert_eq!(slider.index, 1);
    assert_eq!(slider.default, 50.0);
    assert_eq!(slider.min, 0.0);
    assert_eq!(slider.max, 100.0);
    assert_eq!(slider.step, 1.0);
}

// ==================== 预处理器测试 ====================

/// 测试预处理器
#[test]
fn test_preprocessor() {
    let source = r#"
#define FACTOR 3.0
desc:Preprocessor Test

@sample
spl0 = spl0 * FACTOR;
spl1 = spl1 * FACTOR;
"#;
    let program = JsfxParser::parse(source).unwrap();
    let mut vm = JsfxVm::new();
    vm.load(&program).unwrap();
    vm.init(44100.0);

    let (out0, out1) = vm.process_sample(1.0, 1.0);
    assert!((out0 - 3.0).abs() < 0.01, "期望3.0, 得到{}", out0);
    assert!((out1 - 3.0).abs() < 0.01, "期望3.0, 得到{}", out1);
}

/// 测试#ifdef条件编译
#[test]
fn test_ifdef() {
    let source = r#"
#define DEBUG
desc:Ifdef Test

#ifdef DEBUG
@sample
spl0 = 1.0;
spl1 = 1.0;
#endif

#ifndef DEBUG
@sample
spl0 = 0.0;
spl1 = 0.0;
#endif
"#;
    let program = JsfxParser::parse(source).unwrap();
    let mut vm = JsfxVm::new();
    vm.load(&program).unwrap();
    vm.init(44100.0);

    let (out0, out1) = vm.process_sample(0.0, 0.0);
    // DEBUG is defined, so spl0=1.0, spl1=1.0
    assert!((out0 - 1.0).abs() < 0.01, "ifdef: 期望1.0, 得到{}", out0);
    assert!((out1 - 1.0).abs() < 0.01, "ifdef: 期望1.0, 得到{}", out1);
}

// ==================== $常量测试 ====================

/// 测试$常量
#[test]
fn test_dollar_constants() {
    let source = r#"
desc:Dollar Constants Test

@sample
spl0 = $pi;
spl1 = $e;
"#;
    let program = JsfxParser::parse(source).unwrap();
    let mut vm = JsfxVm::new();
    vm.load(&program).unwrap();
    vm.init(44100.0);

    let (out0, out1) = vm.process_sample(0.0, 0.0);
    assert!((out0 - std::f64::consts::PI).abs() < 0.01, "期望π, 得到{}", out0);
    assert!((out1 - std::f64::consts::E).abs() < 0.01, "期望e, 得到{}", out1);
}

// ==================== 内存操作测试 ====================

/// 测试内存操作
#[test]
fn test_memory_operations() {
    let source = r#"
desc:Memory Test

@init
memory(0, 100);
mem_set(0, 42.0);
mem_set(1, 3.14);

@sample
spl0 = mem_get(0);
spl1 = mem_get(1);
"#;
    let program = JsfxParser::parse(source).unwrap();
    let mut vm = JsfxVm::new();
    vm.load(&program).unwrap();
    vm.init(44100.0);

    let (out0, out1) = vm.process_sample(0.0, 0.0);
    assert!((out0 - 42.0).abs() < 0.01, "期望42.0, 得到{}", out0);
    assert!((out1 - 3.14).abs() < 0.01, "期望3.14, 得到{}", out1);
}

/// 测试数组括号语法
#[test]
fn test_bracket_memory_syntax() {
    let source = r#"
desc:Bracket Memory Test

@init
memory[0] = 99.0;
memory[1] = 100.0;

@sample
spl0 = memory[0];
spl1 = memory[1];
"#;
    let program = JsfxParser::parse(source).unwrap();
    let mut vm = JsfxVm::new();
    vm.load(&program).unwrap();
    vm.init(44100.0);

    let (out0, out1) = vm.process_sample(0.0, 0.0);
    assert!((out0 - 99.0).abs() < 0.01, "期望99.0, 得到{}", out0);
    assert!((out1 - 100.0).abs() < 0.01, "期望100.0, 得到{}", out1);
}

// ==================== 用户函数测试 ====================

/// 测试用户自定义函数
#[test]
fn test_user_function() {
    let source = r#"
desc:Function Test

function myabs(x)
  x < 0 ? -x : x;

@sample
spl0 = myabs(-5.0);
spl1 = myabs(3.0);
"#;
    let program = JsfxParser::parse(source).unwrap();
    let mut vm = JsfxVm::new();
    vm.load(&program).unwrap();
    vm.init(44100.0);

    let (out0, out1) = vm.process_sample(0.0, 0.0);
    assert!((out0 - 5.0).abs() < 0.01, "期望5.0, 得到{}", out0);
    assert!((out1 - 3.0).abs() < 0.01, "期望3.0, 得到{}", out1);
}

// ==================== 多区段执行测试 ====================

/// 测试多区段执行顺序
#[test]
fn test_section_execution_order() {
    let source = r#"
desc:Section Order Test
slider1:1<0,10,1>Value

@init
x = 100;

@slider
x = x + slider1;

@sample
spl0 = x;
spl1 = x;
"#;
    let program = JsfxParser::parse(source).unwrap();
    let mut vm = JsfxVm::new();
    vm.load(&program).unwrap();
    vm.init(44100.0);

    // @init: x=100, @slider: x=100+1=101
    let (out0, out1) = vm.process_sample(0.0, 0.0);
    assert!((out0 - 101.0).abs() < 0.01, "期望101.0, 得到{}", out0);
}

// ==================== clamp/min/max测试 ====================

/// 测试clamp/min/max内置函数
#[test]
fn test_clamp_min_max() {
    let source = r#"
desc:Clamp Test

@sample
spl0 = clamp(spl0, -0.5, 0.5);
spl1 = min(max(spl1, -0.5), 0.5);
"#;

    let mut plugin = load_jsfx_source(source, "clamp-test").unwrap();
    plugin.init(44100.0, 256).unwrap();

    let mut ext_input = AudioBuffer::new(2, 10);
    ext_input.set_sample(0, 0, 1.0);
    ext_input.set_sample(1, 0, -1.0);

    let mut ext_output = AudioBuffer::new(2, 10);
    plugin.process(&ext_input, &mut ext_output);

    assert!((ext_output.sample(0, 0) - 0.5).abs() < 0.01,
        "clamp应限制到0.5, 得到{}", ext_output.sample(0, 0));
    assert!((ext_output.sample(1, 0) - (-0.5)).abs() < 0.01,
        "min(max())应限制到-0.5, 得到{}", ext_output.sample(1, 0));
}

// ==================== rand函数测试 ====================

/// 测试rand函数
#[test]
fn test_rand_function() {
    let source = r#"
desc:Random Test

@sample
spl0 = rand();
spl1 = rand();
"#;
    let mut plugin = load_jsfx_source(source, "rand-test").unwrap();
    plugin.init(44100.0, 256).unwrap();

    let ext_input = AudioBuffer::new(2, 100);
    let mut ext_output = AudioBuffer::new(2, 100);
    plugin.process(&ext_input, &mut ext_output);

    for i in 0..100 {
        let l = ext_output.sample(0, i);
        let r = ext_output.sample(1, i);
        assert!(l >= 0.0 && l < 1.0, "rand() L应在[0,1), 得到{}", l);
        assert!(r >= 0.0 && r < 1.0, "rand() R应在[0,1), 得到{}", r);
    }
}

// ==================== 音频RMS/Peak验证测试 ====================

/// 测试增益效果的RMS/Peak
#[test]
fn test_gain_rms_peak() {
    let source = r#"
desc:Gain RMS Test
slider1:0<-150,150,0.1>Gain (dB)

@slider
gain = 2^(slider1/6);

@sample
spl0 *= gain;
spl1 *= gain;
"#;

    let mut plugin = load_jsfx_source(source, "gain-rms").unwrap();
    plugin.init(44100.0, 256).unwrap();
    plugin.set_param("slider1", 0.0).unwrap(); // 0dB

    // 生成1kHz正弦波
    let frames = 4410; // 100ms
    let mut ext_input = AudioBuffer::new(2, frames);
    for i in 0..frames {
        let t = i as f64 / 44100.0;
        let sample = 0.5 * (2.0 * std::f64::consts::PI * 1000.0 * t).sin();
        ext_input.set_sample(0, i, sample);
        ext_input.set_sample(1, i, sample);
    }

    let mut ext_output = AudioBuffer::new(2, frames);
    plugin.process(&ext_input, &mut ext_output);

    // 0dB增益，输出RMS应约等于输入RMS
    let in_rms = (0..frames).map(|i| ext_input.sample(0, i).powi(2)).sum::<f64>() / frames as f64;
    let in_rms = in_rms.sqrt();
    let out_rms = (frames/2..frames).map(|i| ext_output.sample(0, i).powi(2)).sum::<f64>() / (frames/2) as f64;
    let out_rms = out_rms.sqrt();
    assert!((out_rms - in_rms).abs() < 0.01,
        "0dB增益: 输出RMS应≈输入RMS, in={:.4}, out={:.4}", in_rms, out_rms);

    // 6dB增益
    plugin.set_param("slider1", 6.0).unwrap();
    let mut ext_output2 = AudioBuffer::new(2, frames);
    plugin.process(&ext_input, &mut ext_output2);
    let out_rms2 = (0..frames).map(|i| ext_output2.sample(0, i).powi(2)).sum::<f64>() / frames as f64;
    let out_rms2 = out_rms2.sqrt();
    assert!((out_rms2 / out_rms - 2.0).abs() < 0.1,
        "6dB增益: 输出应为2倍, ratio={:.2}", out_rms2 / out_rms);
}

// ==================== 元信息测试 ====================

/// 测试JsfxMeta
#[test]
fn test_jsfx_meta() {
    let source = r#"
desc:Meta Test
tags:test audio
slider1:1<0,10,0.1>Value

@init
x = 0;

@sample
spl0 = x;
"#;
    let meta = JsfxMeta::from_source(source, Path::new("test.jsfx")).unwrap();
    assert_eq!(meta.desc, "Meta Test");
    assert_eq!(meta.tags.len(), 2);
    assert!(meta.has_init);
    assert!(meta.has_sample);
    assert!(!meta.has_gfx);
}
