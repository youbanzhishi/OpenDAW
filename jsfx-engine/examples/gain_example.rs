//! 简单 Gain 效果器示例
//!
//! 验证目标：
//! 1. @slider 块执行 slider1 -> gain 转换
//! 2. @sample 块执行 spl0 *= gain; spl1 *= gain;
//! 3. 0dB 时输出等于输入

use jsfx_engine::{vm::AudioBuffer, JsfxParser, JsfxVm};

fn main() {
    let source = r#"
desc:Simple Gain (dB)
slider1:0<-150,150,0.1>Gain (dB)

@slider
gain = 2^(slider1/6);

@sample
spl0 *= gain;
spl1 *= gain;
"#;

    println!("=== JSFX Gain 效果器测试 ===\n");

    // 解析
    let program = JsfxParser::parse(source).expect("解析失败");
    println!("✓ 解析成功: {}", program.desc);
    println!("  Slider: {:?}", program.sliders);

    // 创建 VM
    let mut vm = JsfxVm::new();
    vm.load(&program).expect("加载失败");
    vm.init(44100.0);

    // 测试 1: 0dB (gain = 1.0)
    vm.update_slider(1, 0.0);
    let (out0, out1) = vm.process_sample(1.0, 0.5);
    println!("\n测试 1: 0dB (gain = 2^(0/6) = 1.0)");
    println!("  输入: (1.0, 0.5)");
    println!("  输出: ({:.4}, {:.4})", out0, out1);
    assert!((out0 - 1.0).abs() < 0.001, "0dB时out0应≈1.0");
    assert!((out1 - 0.5).abs() < 0.001, "0dB时out1应≈0.5");
    println!("  ✓ 通过");

    // 测试 2: +6dB (gain = 2.0)
    vm.update_slider(1, 6.0);
    let (out0, out1) = vm.process_sample(1.0, 0.5);
    println!("\n测试 2: +6dB (gain = 2^(6/6) = 2.0)");
    println!("  输入: (1.0, 0.5)");
    println!("  输出: ({:.4}, {:.4})", out0, out1);
    assert!((out0 - 2.0).abs() < 0.001, "+6dB时out0应≈2.0");
    assert!((out1 - 1.0).abs() < 0.001, "+6dB时out1应≈1.0");
    println!("  ✓ 通过");

    // 测试 3: -6dB (gain = 0.5)
    vm.update_slider(1, -6.0);
    let (out0, out1) = vm.process_sample(1.0, 0.5);
    println!("\n测试 3: -6dB (gain = 2^(-6/6) = 0.5)");
    println!("  输入: (1.0, 0.5)");
    println!("  输出: ({:.4}, {:.4})", out0, out1);
    assert!((out0 - 0.5).abs() < 0.001, "-6dB时out0应≈0.5");
    assert!((out1 - 0.25).abs() < 0.001, "-6dB时out1应≈0.25");
    println!("  ✓ 通过");

    // 测试 4: 缓冲区处理
    println!("\n测试 4: 缓冲区处理");
    let mut input = AudioBuffer::new(2, 4);
    let mut output = AudioBuffer::new(2, 4);
    input.set_sample(0, 0, 1.0);
    input.set_sample(0, 1, 0.5);
    input.set_sample(0, 2, 0.25);
    input.set_sample(0, 3, 0.125);
    vm.update_slider(1, 6.0); // +6dB
    vm.process_buffer(&input, &mut output);
    println!("  +6dB 增益后的输出:");
    for i in 0..4 {
        println!("    帧{}: L={:.4}", i, output.sample(0, i));
    }
    assert!((output.sample(0, 0) - 2.0).abs() < 0.001);
    println!("  ✓ 通过");

    println!("\n=== 全部测试通过! ===");
}
