//! JSFX示例：加载并运行JSFX脚本
//!
//! 演示如何使用jsfx-engine加载JSFX效果器并处理音频数据

use jsfx_engine::parser::JsfxParser;
use jsfx_engine::vm::{AudioBuffer as VmAudioBuffer, JsfxVm};
use jsfx_engine::AudioBuffer;

fn main() {
    println!("=== JSFX引擎示例 ===\n");

    // 示例1: 简单增益
    println!("--- 示例1: 简单增益 ---");
    let gain_source = r#"
desc:Simple Gain
slider1:0<-150,150,0.1>Gain (dB)

@slider
gain = 2^(slider1/6);

@sample
spl0 *= gain;
spl1 *= gain;
"#;

    match JsfxParser::parse(gain_source) {
        Ok(program) => {
            println!("解析成功: {}", program.desc);
            println!("Slider参数: {}个", program.sliders.len());
            for s in &program.sliders {
                println!(
                    "  slider{}: {} (默认={}, 范围={}~{}, 步长={})",
                    s.index,
                    s.name.as_deref().unwrap_or("未命名"),
                    s.default,
                    s.min,
                    s.max,
                    s.step
                );
            }

            let mut vm = JsfxVm::new();
            vm.load(&program).unwrap();
            vm.init(44100.0);

            // 0dB增益
            vm.update_slider(1, 0.0);
            let (out0, out1) = vm.process_sample(1.0, 0.5);
            println!("0dB增益: 输入(1.0, 0.5) → 输出({:.4}, {:.4})", out0, out1);

            // +6dB增益
            vm.update_slider(1, 6.0);
            let (out0, out1) = vm.process_sample(1.0, 0.5);
            println!("+6dB增益: 输入(1.0, 0.5) → 输出({:.4}, {:.4})", out0, out1);

            // -6dB增益
            vm.update_slider(1, -6.0);
            let (out0, out1) = vm.process_sample(1.0, 0.5);
            println!("-6dB增益: 输入(1.0, 0.5) → 输出({:.4}, {:.4})", out0, out1);
        }
        Err(e) => println!("解析失败: {}", e),
    }

    println!();

    // 示例2: 缓冲区处理
    println!("--- 示例2: 缓冲区处理 ---");
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
    vm.update_slider(1, 0.0); // 0dB

    // 创建输入缓冲区（440Hz正弦波）
    let frames = 256;
    let mut input = VmAudioBuffer::new(2, frames);
    for i in 0..frames {
        let t = i as f64 / 44100.0;
        let sample = (2.0 * std::f64::consts::PI * 440.0 * t).sin() * 0.5;
        input.set_sample(0, i, sample);
        input.set_sample(1, i, sample);
    }

    let mut output = VmAudioBuffer::new(2, frames);
    vm.process_buffer(&input, &mut output);

    println!("处理了 {} 帧", frames);
    println!(
        "输出前4个采样: [{:.4}, {:.4}, {:.4}, {:.4}]",
        output.sample(0, 0),
        output.sample(0, 1),
        output.sample(0, 2),
        output.sample(0, 3)
    );

    println!();

    // 示例3: 使用JsfxPlugin适配器
    println!("--- 示例3: JsfxPlugin适配器 ---");
    use jsfx_engine::JsfxPlugin;
    use jsfx_engine::VcPlugin;

    match JsfxPlugin::from_source(gain_source, "demo_gain") {
        Ok(mut plugin) => {
            println!(
                "插件加载成功: {} (id={})",
                plugin.plugin_name(),
                plugin.plugin_id()
            );
            plugin.init(44100.0, 256).unwrap();

            let params = plugin.get_params();
            println!("参数列表:");
            for p in &params {
                println!(
                    "  {} ({}): 范围={}~{}, 默认={}",
                    p.id, p.name, p.min, p.max, p.default
                );
            }

            plugin.set_param("slider1", 6.0).unwrap();
            let val = plugin.get_param("slider1");
            println!("设置slider1=6.0, 当前值={:?}", val);

            let input = AudioBuffer::new(2, 4);
            let mut output = AudioBuffer::new(2, 4);
            plugin.process(&input, &mut output);
            println!("音频处理完成");
        }
        Err(e) => println!("插件加载失败: {}", e),
    }

    println!("\n=== 示例完成 ===");
}
