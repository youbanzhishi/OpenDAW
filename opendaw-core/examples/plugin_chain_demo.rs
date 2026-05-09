//! PluginChain 示例
//!
//! 演示如何使用 PluginChain 处理音频：
//! 1. 添加 VC-CLI 插件到信号链
//! 2. 处理音频缓冲区
//! 3. 在 extension (f64) 和 engine (f32) 之间转换

use opendaw_core::{
    PluginChain, ExtAudioBuffer, EngineAudioBuffer,
    ext_to_engine, engine_to_ext,
};

/// 简单的增益插件（测试用）
struct GainPlugin {
    gain: f64,
}

impl opendaw_extension::VcPlugin for GainPlugin {
    fn plugin_id(&self) -> &str { "demo-gain" }
    fn plugin_name(&self) -> &str { "Demo Gain" }
    fn plugin_type(&self) -> opendaw_extension::PluginType { 
        opendaw_extension::PluginType::Effect 
    }
    fn version(&self) -> &str { "1.0.0" }
    
    fn init(&mut self, _sr: f64, _bs: usize) -> Result<(), opendaw_extension::PluginError> {
        Ok(())
    }
    
    fn process(&mut self, input: &ExtAudioBuffer, output: &mut ExtAudioBuffer) {
        for (i, &sample) in input.data.iter().enumerate() {
            output.data[i] = sample * self.gain;
        }
    }
    
    fn get_params(&self) -> Vec<opendaw_extension::ParamInfo> {
        vec![opendaw_extension::ParamInfo::new(
            "gain", "Gain", -60.0, 60.0, 0.0, "dB"
        )]
    }
    
    fn set_param(&mut self, id: &str, value: f64) -> Result<(), opendaw_extension::PluginError> {
        if id == "gain" {
            self.gain = 10f64.powf(value / 20.0); // dB to linear
            Ok(())
        } else {
            Err(opendaw_extension::PluginError::ParamNotFound(id.to_string()))
        }
    }
    
    fn get_param(&self, id: &str) -> Option<f64> {
        if id == "gain" {
            Some(20.0 * self.gain.log10())
        } else {
            None
        }
    }
    
    fn destroy(&mut self) {}
}

fn main() {
    println!("PluginChain Demo");
    println!("===============\n");

    // 创建信号链
    let mut chain = PluginChain::new(2, 256);
    
    // 添加增益插件
    chain.push(Box::new(GainPlugin { gain: 1.0 }));
    
    // 创建输入缓冲区 (f64)
    let mut input = ExtAudioBuffer::new(2, 256);
    for i in 0..512 {
        input.data[i] = (i as f64) * 0.001; // 0.001, 0.002, ...
    }
    
    // 处理
    let mut output = ExtAudioBuffer::new(2, 256);
    chain.process(&input, &mut output);
    
    println!("Extension buffer (f64):");
    println!("  Input[0]: {:.6}", input.data[0]);
    println!("  Output[0]: {:.6}", output.data[0]);
    
    // 演示 f32 缓冲区处理
    let mut chain2 = PluginChain::new(2, 256);
    chain2.push(Box::new(GainPlugin { gain: 2.0 }));
    
    let mut engine_input = EngineAudioBuffer::new(2, 256, 44100.0);
    for i in 0..512 {
        engine_input.as_mut_slice()[i] = (i as f32) * 0.001;
    }
    
    let mut engine_output = EngineAudioBuffer::new(2, 256, 44100.0);
    chain2.process_engine(&engine_input, &mut engine_output);
    
    println!("\nEngine buffer (f32):");
    println!("  Input[0]: {:.6}", engine_input.as_slice()[0]);
    println!("  Output[0]: {:.6}", engine_output.as_slice()[0]);
    
    // 演示桥接转换
    println!("\nBridge conversion:");
    let mut ext_buf = ExtAudioBuffer::new(2, 100);
    for i in 0..200 {
        ext_buf.data[i] = (i as f64) * 0.1;
    }
    
    let mut eng_buf = EngineAudioBuffer::new(2, 100, 44100.0);
    ext_to_engine(&ext_buf, &mut eng_buf);
    
    let mut ext_buf2 = ExtAudioBuffer::new(2, 100);
    engine_to_ext(&eng_buf, &mut ext_buf2);
    
    println!("  ext[0]: {:.6} -> eng[0]: {:.6} -> ext[0]: {:.6}",
             ext_buf.data[0], eng_buf.as_slice()[0], ext_buf2.data[0]);
    
    // 列出链中插件
    println!("\nChain plugins:");
    for info in chain.list_plugins() {
        println!("  [{}] {} ({}) - {}", 
                 info.index, info.name, info.id, 
                 if info.enabled { "enabled" } else { "disabled" });
    }
    
    println!("\nDone!");
}
