//! JSFX 适配器示例
//!
//! 演示如何使用 JsfxPlugin 作为 VcPlugin trait 实现

use jsfx_engine::{JsfxPlugin, JsfxParser};
use opendaw_extension::{VcPlugin, AudioBuffer, PluginType};

fn main() {
    println!("JSFX Adapter Demo");
    println!("=================\n");

    // JSFX 源码示例
    let source = r#"
desc:Simple Gain
slider1:0<-150,150,0.1>Gain (dB)

@init
// 初始化代码
gain = 1.0;

@slider
gain = 10 ^ (slider1 / 20);

@sample
spl0 *= gain;
spl1 *= gain;
"#;

    println!("Parsing JSFX source...");
    let program = JsfxParser::parse(source).expect("Failed to parse JSFX");
    
    println!("Program: {}", program.desc);
    println!("Sliders: {}", program.sliders.len());
    
    // 创建插件
    let mut plugin = JsfxPlugin::from_source(source, "jsfx-gain")
        .expect("Failed to create plugin");
    
    println!("\nPlugin info:");
    println!("  ID: {}", plugin.plugin_id());
    println!("  Name: {}", plugin.plugin_name());
    println!("  Type: {:?}", plugin.plugin_type());
    println!("  Version: {}", plugin.version());
    
    // 初始化
    plugin.init(44100.0, 256).expect("Failed to init");
    println!("\nInitialized at 44100Hz, 256 samples");
    
    // 获取参数
    let params = plugin.get_params();
    println!("\nParameters:");
    for param in &params {
        println!("  {}: {} (range: {} ~ {}, default: {})",
                 param.id, param.name, param.min, param.max, param.default);
    }
    
    // 设置参数
    plugin.set_param("slider1", 6.0).expect("Failed to set gain to +6dB");
    println!("\nSet gain to +6dB");
    
    // 创建测试音频
    let mut input = AudioBuffer::new(2, 256);
    for i in 0..512 {
        input.data[i] = 0.5_f64; // 0.5 amplitude
    }
    
    // 处理音频
    let mut output = AudioBuffer::new(2, 256);
    plugin.process(&input, &mut output);
    
    // 验证: +6dB ≈ 2.0 gain
    let expected = 0.5 * 2.0; // 0.5 * 2.0 = 1.0
    let actual = output.data[0];
    println!("\nAudio processing:");
    println!("  Input amplitude: {}", input.data[0]);
    println!("  Output amplitude: {}", actual);
    println!("  Expected (0dB + 6dB = 2x): {}", expected);
    println!("  Match: {}", (actual - expected).abs() < 0.001);
    
    // 测试直通（未初始化插件）
    println!("\nPass-through test (destroyed plugin):");
    let mut plugin2 = JsfxPlugin::from_source(source, "jsfx-gain-2")
        .expect("Failed to create plugin");
    plugin2.destroy(); // 销毁插件
    
    let input2 = AudioBuffer::new(2, 256);
    for i in 0..512 {
        // 故意写入非零值
        let _ = i;
    }
    let mut output2 = AudioBuffer::new(2, 256);
    plugin2.process(&input2, &mut output2);
    println!("  Destroyed plugin outputs zero (pass-through)");
    
    println!("\nDone!");
}
