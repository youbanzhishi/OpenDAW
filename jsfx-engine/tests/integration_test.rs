//! 集成测试 — 加载JSFX文件并验证处理结果

use jsfx_engine::parser::JsfxParser;
use jsfx_engine::vm::{AudioBuffer, JsfxVm};
use jsfx_engine::JsfxPlugin;
use jsfx_engine::VcPlugin;
use std::path::Path;

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
}

/// 测试低通滤波器
#[test]
fn test_lowpass_filter() {
    let source = r#"
desc:Simple Lowpass Filter
slider1:1000<20,20000,1>Cutoff (Hz)
slider2:0.7<0.01,1,0.01>Resonance

@init
freq = 1000;
q = 0.7;

@slider
freq = slider1;
q = slider2;

@sample
k = exp(-2 * $pi * freq / srate);
spl0 = spl0 * (1-k) + _lp0 * k;
_lp0 = spl0;
spl1 = spl1 * (1-k) + _lp1 * k;
_lp1 = spl1;
"#;
    let program = JsfxParser::parse(source).unwrap();
    assert_eq!(program.desc, "Simple Lowpass Filter");
    assert_eq!(program.sliders.len(), 2);

    let mut vm = JsfxVm::new();
    vm.load(&program).unwrap();
    vm.init(44100.0);

    // 低通滤波器应该能运行不崩溃
    for _ in 0..100 {
        let (out0, out1) = vm.process_sample(1.0, 1.0);
        assert!(out0.is_finite(), "输出应为有限值");
        assert!(out1.is_finite(), "输出应为有限值");
    }
}

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

/// 测试if/else语句
#[test]
fn test_if_else() {
    let source = r#"
desc:If Else Test

@sample
if (spl0 > 0) (
    spl0 = spl0 * 2;
) else (
    spl0 = spl0 * -1;
)
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
