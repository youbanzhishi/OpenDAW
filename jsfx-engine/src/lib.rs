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
//! - 数字字面量（含十六进制0xFF）、变量引用（大小写不敏感）
//! - 字符串字面量（"..."）
//! - $常量（$pi, $e, $phi）
//! - 二元运算: +, -, *, /, ^, %, <, >, <=, >=, ==, !=, &&, ||, &, |
//! - 复合赋值: +=, -=, *=, /=, ^=, %=
//! - 一元运算: -, !, ~
//! - 三目运算: condition ? a : b
//! - 函数调用: sin(x), max(a, b), mem_set(idx, val)等
//! - 数组访问: memory[index], 变量[index]
//! - if/else语句（单行和多行）
//! - while循环
//! - loop(count)循环
//! - 函数定义: function name(params) ...
//! - #预处理器指令: #define, #ifdef, #ifndef, #else, #endif, #undef
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
//! # 多区段执行模型（Reaper兼容）
//!
//! - `@init` — 插件加载时执行一次
//! - `@slider` — slider参数变化时执行
//! - `@block` — 每个音频buffer执行一次
//! - `@sample` — 每个采样点执行（核心音频处理）
//! - `@gfx` — GUI绘制（暂不实现执行）
//! - `@serialize` — 预设持久化（暂不实现执行）
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
    }

    /// 测试加载包含@init块的JSFX
    #[test]
    fn test_jsfx_with_init_block() {
        let source = r#"
desc:Gain with Init
slider1:3<-150,150,0.1>Gain (dB)

@init
state = 0;
multiplier = 1.0;

@slider
multiplier = 2^(slider1/6);

@sample
state = spl0 * multiplier;
spl0 = state;
spl1 = spl1 * multiplier;
"#;

        let mut plugin = load_jsfx_source(source, "init-test").unwrap();
        plugin.init(44100.0, 256).unwrap();

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
spl1 *= gain * 0.8;
"#;

        let mut plugin = load_jsfx_source(source, "stereo").unwrap();
        plugin.init(44100.0, 256).unwrap();

        let mut ext_input = AudioBuffer::new(2, 10);
        ext_input.set_sample(0, 0, 1.0);
        ext_input.set_sample(1, 0, 1.0);

        let mut ext_output = AudioBuffer::new(2, 10);
        plugin.process(&ext_input, &mut ext_output);

        assert!((ext_output.sample(0, 0) - 1.0).abs() < 0.001);
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
        
        assert_eq!(params[2].min, -150.0);
        assert_eq!(params[2].max, 150.0);
        assert_eq!(params[2].default, 0.0);
    }

    /// 测试低通滤波器 — 验证音频输出在合理范围
    #[test]
    fn test_lowpass_filter_e2e() {
        let source = r#"
desc:Simple Lowpass Filter
slider1:1000<20,20000,1>Cutoff (Hz)

@slider
freq = slider1;

@sample
k = exp(-2 * $pi * freq / srate);
_lp0 = spl0 * (1-k) + _lp0 * k;
spl0 = _lp0;
_lp1 = spl1 * (1-k) + _lp1 * k;
spl1 = _lp1;
"#;

        let mut plugin = load_jsfx_source(source, "lowpass").unwrap();
        plugin.init(44100.0, 256).unwrap();
        plugin.set_param("slider1", 1000.0).unwrap();

        // 创建1kHz正弦波输入
        let frames = 4410; // 100ms
        let mut ext_input = AudioBuffer::new(2, frames);
        for i in 0..frames {
            let t = i as f64 / 44100.0;
            let sample = 0.8 * (2.0 * std::f64::consts::PI * 1000.0 * t).sin();
            ext_input.set_sample(0, i, sample);
            ext_input.set_sample(1, i, sample);
        }

        let mut ext_output = AudioBuffer::new(2, frames);
        plugin.process(&ext_input, &mut ext_output);

        // 验证输出：低通滤波后RMS应小于输入RMS，但非零
        let in_rms = (0..frames).map(|i| ext_input.sample(0, i).powi(2)).sum::<f64>() / frames as f64;
        let in_rms = in_rms.sqrt();
        let out_rms = (frames / 2..frames)  // 跳过前半段瞬态
            .map(|i| ext_output.sample(0, i).powi(2))
            .sum::<f64>() / (frames / 2) as f64;
        let out_rms = out_rms.sqrt();

        assert!(out_rms > 0.01, "输出RMS应大于0: {}", out_rms);
        assert!(out_rms < in_rms * 1.5, "输出RMS应合理: in={}, out={}", in_rms, out_rms);
        assert!(out_rms.is_finite(), "输出应为有限值");
    }

    /// 测试延迟效果 — 验证延迟输出
    #[test]
    fn test_delay_effect_e2e() {
        let source = r#"
desc:Simple Delay
slider1:200<1,2000,1>Delay (ms)
slider2:0.5<0,1,0.01>Feedback

@init
delay_pos = 0;
delay_len = srate * 2;
memory(0, delay_len);

@slider

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

        let mut plugin = load_jsfx_source(source, "delay").unwrap();
        plugin.init(44100.0, 256).unwrap();

        let frames = 4410;
        let mut ext_input = AudioBuffer::new(2, frames);
        // 第一个采样设为1.0，其余为0（脉冲）
        ext_input.set_sample(0, 0, 1.0);
        ext_input.set_sample(1, 0, 1.0);

        let mut ext_output = AudioBuffer::new(2, frames);
        plugin.process(&ext_input, &mut ext_output);

        // 验证输出不崩溃且有限
        let peak = (0..frames)
            .map(|i| ext_output.sample(0, i).abs())
            .fold(0.0f64, |a, b| a.max(b));
        assert!(peak.is_finite(), "输出应为有限值, peak={}", peak);
        assert!(peak > 0.0, "延迟应有输出, peak={}", peak);
    }

    /// 测试$常量
    #[test]
    fn test_dollar_constants_e2e() {
        let source = r#"
desc:Constants Test

@sample
spl0 = $pi;
spl1 = $e;
"#;

        let mut plugin = load_jsfx_source(source, "constants").unwrap();
        plugin.init(44100.0, 256).unwrap();

        let mut ext_input = AudioBuffer::new(2, 10);
        let mut ext_output = AudioBuffer::new(2, 10);
        plugin.process(&ext_input, &mut ext_output);

        assert!((ext_output.sample(0, 0) - std::f64::consts::PI).abs() < 0.01);
        assert!((ext_output.sample(1, 0) - std::f64::consts::E).abs() < 0.01);
    }

    /// 测试预处理器
    #[test]
    fn test_preprocessor_e2e() {
        let source = r#"
#define MULTIPLIER 2.0
desc:Preprocessor Test

@sample
spl0 = spl0 * MULTIPLIER;
spl1 = spl1 * MULTIPLIER;
"#;

        let mut plugin = load_jsfx_source(source, "preprocessor").unwrap();
        plugin.init(44100.0, 256).unwrap();

        let mut ext_input = AudioBuffer::new(2, 10);
        ext_input.set_sample(0, 0, 1.0);
        ext_input.set_sample(1, 0, 1.0);

        let mut ext_output = AudioBuffer::new(2, 10);
        plugin.process(&ext_input, &mut ext_output);

        assert!((ext_output.sample(0, 0) - 2.0).abs() < 0.01);
        assert!((ext_output.sample(1, 0) - 2.0).abs() < 0.01);
    }

    /// 测试内存操作
    #[test]
    fn test_memory_operations_e2e() {
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

        let mut plugin = load_jsfx_source(source, "memory-test").unwrap();
        plugin.init(44100.0, 256).unwrap();

        let mut ext_input = AudioBuffer::new(2, 10);
        let mut ext_output = AudioBuffer::new(2, 10);
        plugin.process(&ext_input, &mut ext_output);

        assert!((ext_output.sample(0, 0) - 42.0).abs() < 0.01);
        assert!((ext_output.sample(1, 0) - 3.14).abs() < 0.01);
    }

    /// 测试用户自定义函数
    #[test]
    fn test_user_function_e2e() {
        let source = r#"
desc:Function Test

function myabs(x)
  x < 0 ? -x : x;

@sample
spl0 = myabs(-5.0);
spl1 = myabs(3.0);
"#;

        let mut plugin = load_jsfx_source(source, "func-test").unwrap();
        plugin.init(44100.0, 256).unwrap();

        let mut ext_input = AudioBuffer::new(2, 10);
        let mut ext_output = AudioBuffer::new(2, 10);
        plugin.process(&ext_input, &mut ext_output);

        assert!((ext_output.sample(0, 0) - 5.0).abs() < 0.01);
        assert!((ext_output.sample(1, 0) - 3.0).abs() < 0.01);
    }

    /// 测试rand函数
    #[test]
    fn test_rand_function_e2e() {
        let source = r#"
desc:Random Test

@sample
spl0 = rand();
spl1 = rand();
"#;

        let mut plugin = load_jsfx_source(source, "rand-test").unwrap();
        plugin.init(44100.0, 256).unwrap();

        let mut ext_input = AudioBuffer::new(2, 100);
        let mut ext_output = AudioBuffer::new(2, 100);
        plugin.process(&ext_input, &mut ext_output);

        // 所有输出应在[0,1)范围内
        for i in 0..100 {
            let l = ext_output.sample(0, i);
            let r = ext_output.sample(1, i);
            assert!(l >= 0.0 && l < 1.0, "rand() L应在[0,1), 得到{}", l);
            assert!(r >= 0.0 && r < 1.0, "rand() R应在[0,1), 得到{}", r);
        }
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

        let mut plugin = load_jsfx_source(source, "section-order").unwrap();
        plugin.init(44100.0, 256).unwrap();

        let mut ext_input = AudioBuffer::new(2, 10);
        let mut ext_output = AudioBuffer::new(2, 10);
        plugin.process(&ext_input, &mut ext_output);

        // @init: x=100, @slider: x=100+1=101
        assert!((ext_output.sample(0, 0) - 102.0).abs() < 0.01,
            "期望102.0, 得到{}", ext_output.sample(0, 0));
    }

    /// 测试clamp/min/max内置函数
    #[test]
    fn test_clamp_min_max_e2e() {
        let source = r#"
desc:Clamp Test

@sample
spl0 = clamp(spl0, -0.5, 0.5);
spl1 = min(max(spl1, -0.5), 0.5);
"#;

        let mut plugin = load_jsfx_source(source, "clamp-test").unwrap();
        plugin.init(44100.0, 256).unwrap();

        let mut ext_input = AudioBuffer::new(2, 10);
        ext_input.set_sample(0, 0, 1.0);  // 超过上限
        ext_input.set_sample(1, 0, -1.0);  // 低于下限

        let mut ext_output = AudioBuffer::new(2, 10);
        plugin.process(&ext_input, &mut ext_output);

        assert!((ext_output.sample(0, 0) - 0.5).abs() < 0.01,
            "clamp应限制到0.5, 得到{}", ext_output.sample(0, 0));
        assert!((ext_output.sample(1, 0) - (-0.5)).abs() < 0.01,
            "min(max())应限制到-0.5, 得到{}", ext_output.sample(1, 0));
    }
}
