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

// 公共接口重导出
pub use error::JsfxError;
pub use parser::JsfxParser;
pub use vm::JsfxVm;
pub use adapter::{JsfxPlugin, VcPlugin, PluginType, ParamInfo, PluginError};
