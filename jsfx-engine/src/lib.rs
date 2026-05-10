//! JSFX引擎 — 兼容Reaper自定义效果器的EEL2脚本解释器
//!
//! JSFX是Reaper DAW的独家脚本效果器格式，基于纯文本EEL2语言。
//! 本crate实现了JSFX核心子集的解释器，使OpenDAW能直接运行Reaper的JSFX脚本，
//! 继承Reaper的自定义效果器生态。
//!
//! # 核心架构
//!
//! - **parser** — JSFX文本→AST解析器，支持EEL2核心语法
//! - **ast** — 抽象语法树定义
//! - **vm** — 虚拟机，AST直接解释执行（V1）
//! - **runtime** — 运行时环境（变量、内存、spl通道、slider参数）
//! - **builtins** — 内置函数（sin/cos/log/min/max等60+函数）
//! - **adapter** — VcPlugin trait适配，集成到OpenDAW扩展系统
//! - **compiler** — 字节码编译器（预留，V2性能优化）
//!
//! # 支持的EEL2语法子集
//!
//! - 数字字面量、变量引用（大小写不敏感）
//! - 二元运算: +, -, *, /, ^, %, <, >, <=, >=, ==, !=, &&, ||
//! - 复合赋值: +=, -=, *=, /=
//! - 一元运算: -, !
//! - 三目运算: condition ? a : b
//! - 函数调用: sin(x), max(a, b), mem_set(idx, val)等
//! - 数组访问: memory[index]
//! - if/else语句
//! - while循环
//! - loop(count)循环
//! - 函数定义: function name(params) ...
//!
//! # 特殊变量
//!
//! - `spl0`, `spl1` — 左右声道当前采样值
//! - `slider1`~`slider256` — 参数值
//! - `srate` — 采样率
//! - `samplesblock` — 当前block大小
//! - `spl(ch)` — 多通道访问
//! - `$pi`, `$e`, `$phi` — 数学常量
//!
//! # 使用示例
//!
//! ```rust
//! use jsfx_engine::parser::JsfxParser;
//! use jsfx_engine::vm::JsfxVm;
//!
//! let source = r#"
//! desc:Simple Gain
//! slider1:0<-150,150,0.1>Gain (dB)
//!
//! @slider
//! gain = 2^(slider1/6);
//!
//! @sample
//! spl0 *= gain;
//! spl1 *= gain;
//! "#;
//!
//! let program = JsfxParser::parse(source).unwrap();
//! let mut vm = JsfxVm::new();
//! vm.load(&program).unwrap();
//! vm.init(44100.0);
//!
//! // 处理单个采样
//! let (out_l, out_r) = vm.process_sample(1.0, 0.5);
//! ```

pub mod error;
pub mod ast;
pub mod parser;
pub mod builtins;
pub mod runtime;
pub mod vm;
pub mod compiler;
pub mod adapter;
pub mod loader;

// 公共接口重导出
pub use error::JsfxError;
pub use parser::JsfxParser;
pub use vm::JsfxVm;
pub use adapter::JsfxPlugin;
pub use loader::{load_jsfx_file, load_jsfx_source, scan_jsfx_directory, JsfxMeta};

// 从opendaw-extension重导出统一类型（消除重复定义）
pub use opendaw_extension::{VcPlugin, PluginType, ParamInfo, PluginError, AudioBuffer};

#[cfg(test)]
mod integration_tests {
    //! 端到端集成测试：JSFX → PluginChain → 音频输出
    
    use super::*;

    /// 测试加载gain.jsfx并验证增益效果
    #[test]
    fn test_gain_jsfx_e2e() {
        let source = r#"
desc:Simple Gain
slider1:6<-150,150,0.1>Gain (dB)

@slider
gain = 2^(slider1/6);

@sample
spl0 *= gain;
spl1 *= gain;
"#;

        let mut plugin = load_jsfx_source(source, "gain-test").unwrap();
        plugin.init(44100.0, 256).unwrap();

        // 创建输入缓冲区：1kHz正弦波，振幅0.5
        let channels = 2;
        let frames = 441; // 10ms @ 44100Hz
        let mut ext_input = AudioBuffer::new(channels, frames);
        
        for i in 0..frames {
            let t = i as f64 / 44100.0;
            let sample = 0.5 * (2.0 * std::f64::consts::PI * 1000.0 * t).sin();
            ext_input.set_sample(0, i, sample);
            ext_input.set_sample(1, i, sample);
        }

        let mut ext_output = AudioBuffer::new(channels, frames);
        plugin.process(&ext_input, &mut ext_output);

        // 6dB增益: gain = 2^(6/6) = 2.0
        // 检查峰值是否正确（正弦波峰值应该是 0.5 * 2.0 = 1.0）
        let tolerance = 0.01;
        
        // 找到输出峰值
        let peak_l = (0..frames)
            .map(|i| ext_output.sample(0, i).abs())
            .fold(0.0f64, |a, b| a.max(b));
        
        assert!(
            (peak_l - 1.0).abs() < tolerance,
            "期望峰值≈1.0, 实际峰值={:.4}", peak_l
        );
        
        // 验证所有采样都被正确处理（非零值应该被增益）
        for i in 0..frames {
            let in_l = ext_input.sample(0, i);
            let out_l = ext_output.sample(0, i);
            let expected = in_l * 2.0; // 6dB = 2x
            
            assert!(
                (out_l - expected).abs() < tolerance,
                "帧{} L: 期望{:.4}, 实际{:.4}", i, expected, out_l
            );
        }
    }

    /// 测试加载包含@init块的JSFX
    #[test]
    fn test_jsfx_with_init_block() {
        let source = r#"
desc:Gain with Init
slider1:3<-150,150,0.1>Gain (dB)

@init
  // 初始化内部状态
  state = 0;
  multiplier = 1.0;

@slider
  // 更新增益系数
  multiplier = 2^(slider1/6);

@sample
  // 使用内部状态处理
  state = spl0 * multiplier;
  spl0 = state;
  spl1 = spl1 * multiplier;
"#;

        let mut plugin = load_jsfx_source(source, "init-test").unwrap();
        plugin.init(44100.0, 256).unwrap();

        // 3dB增益: gain = 2^(3/6) = 2^(0.5) ≈ 1.414
        let mut ext_input = AudioBuffer::new(2, 100);
        for i in 0..100 {
            ext_input.set_sample(0, i, 0.3);
            ext_input.set_sample(1, i, 0.4);
        }

        let mut ext_output = AudioBuffer::new(2, 100);
        plugin.process(&ext_input, &mut ext_output);

        let expected = 0.3 * 2.0_f64.powf(0.5);
        for i in 0..100 {
            let out_l = ext_output.sample(0, i);
            assert!(
                (out_l - expected).abs() < 0.001,
                "帧{} L: 期望{:.4}, 实际{:.4}", i, expected, out_l
            );
        }
    }

    /// 测试slider参数动态更新
    #[test]
    fn test_jsfx_slider_update() {
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

        let mut ext_input = AudioBuffer::new(2, 10);
        ext_input.set_sample(0, 0, 1.0);
        ext_input.set_sample(1, 0, 1.0);

        // 初始0dB增益
        let mut ext_output = AudioBuffer::new(2, 10);
        plugin.process(&ext_input, &mut ext_output);
        assert!((ext_output.sample(0, 0) - 1.0).abs() < 0.001);

        // 更新为6dB增益
        plugin.set_param("slider1", 6.0).unwrap();
        
        let mut ext_output2 = AudioBuffer::new(2, 10);
        plugin.process(&ext_input, &mut ext_output2);
        // 6dB = 2x
        assert!((ext_output2.sample(0, 0) - 2.0).abs() < 0.001);
    }

    /// 测试立体声处理
    #[test]
    fn test_jsfx_stereo_processing() {
        let source = r#"
desc:Stereo Gain
slider1:0<-150,150,0.1>Gain (dB)

@slider
gain = 2^(slider1/6);

@sample
spl0 *= gain;
spl1 *= gain * 0.8;  // 右声道略低
"#;

        let mut plugin = load_jsfx_source(source, "stereo").unwrap();
        plugin.init(44100.0, 256).unwrap();

        let mut ext_input = AudioBuffer::new(2, 10);
        ext_input.set_sample(0, 0, 1.0);
        ext_input.set_sample(1, 0, 1.0);

        let mut ext_output = AudioBuffer::new(2, 10);
        plugin.process(&ext_input, &mut ext_output);

        // 0dB增益 = 1.0
        assert!((ext_output.sample(0, 0) - 1.0).abs() < 0.001);
        // 右声道0.8倍
        assert!((ext_output.sample(1, 0) - 0.8).abs() < 0.001);
    }

    /// 测试get_params接口
    #[test]
    fn test_jsfx_get_params() {
        let source = r#"
desc:Param Test
slider1:50<0,100,1>Param1
slider2:0.5<0,1,0.01>Param2
slider3:0<-150,150,0.1>Gain (dB)

@sample
spl0 *= 2^(slider3/6);
spl1 *= 2^(slider3/6);
"#;

        let plugin = load_jsfx_source(source, "param-test").unwrap();
        let params = plugin.get_params();
        
        assert_eq!(params.len(), 3);
        assert_eq!(params[0].id, "slider1");
        assert_eq!(params[1].id, "slider2");
        assert_eq!(params[2].id, "slider3");
        
        // 检查范围
        assert_eq!(params[2].min, -150.0);
        assert_eq!(params[2].max, 150.0);
        assert_eq!(params[2].default, 0.0);
    }

    /// 测试loader模块
    #[test]
    fn test_loader_parse_source() {
        let source = r#"
desc:Test Gain
slider1:0<-150,150,0.1>Gain (dB)

@slider
gain = 2^(slider1/6);

@sample
spl0 *= gain;
spl1 *= gain;
"#;
        let plugin = load_jsfx_source(source, "test-gain").unwrap();
        assert_eq!(plugin.plugin_name(), "Test Gain");
    }

    /// 测试loader元信息解析
    #[test]
    fn test_jsfx_meta_parsing() {
        let source = r#"
desc:Meta Test
tags:test utility audio
slider1:1<0,10,0.1>Test

@sample
spl0 = spl0 * slider1;
"#;
        let program = super::parser::JsfxParser::parse(source).unwrap();
        
        assert_eq!(program.desc, "Meta Test");
        assert_eq!(program.tags.len(), 3);
        assert_eq!(program.sliders.len(), 1);
        assert!(program.sample_block.is_some());
    }
}
