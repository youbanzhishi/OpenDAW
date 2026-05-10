//! JSFX引擎错误类型
//!
//! 使用自定义错误实现，不依赖外部crate

use std::fmt;

/// JSFX引擎顶层错误
#[derive(Debug)]
pub enum JsfxError {
    /// 解析错误
    ParseError { line: usize, message: String },
    /// 编译错误
    CompileError(String),
    /// 运行时错误
    RuntimeError(String),
    /// 未定义变量
    UndefinedVariable(String),
    /// 未定义函数
    UndefinedFunction(String),
    /// 参数数量不匹配
    ArgCountMismatch {
        func: String,
        expected: usize,
        actual: usize,
    },
    /// 除零错误
    DivisionByZero,
    /// 内存越界
    MemoryOutOfBounds { index: usize, size: usize },
    /// IO错误
    Io(std::io::Error),
}

impl fmt::Display for JsfxError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            JsfxError::ParseError { line, message } => {
                write!(f, "解析错误 行{}: {}", line, message)
            }
            JsfxError::CompileError(msg) => write!(f, "编译错误: {}", msg),
            JsfxError::RuntimeError(msg) => write!(f, "运行时错误: {}", msg),
            JsfxError::UndefinedVariable(name) => write!(f, "未定义变量: {}", name),
            JsfxError::UndefinedFunction(name) => write!(f, "未定义函数: {}", name),
            JsfxError::ArgCountMismatch {
                func,
                expected,
                actual,
            } => {
                write!(
                    f,
                    "参数数量不匹配: 函数{}期望{}个参数, 实际{}个",
                    func, expected, actual
                )
            }
            JsfxError::DivisionByZero => write!(f, "除零错误"),
            JsfxError::MemoryOutOfBounds { index, size } => {
                write!(f, "内存越界: 索引{}, 大小{}", index, size)
            }
            JsfxError::Io(e) => write!(f, "IO错误: {}", e),
        }
    }
}

impl std::error::Error for JsfxError {
    fn source(&self) -> Option<&(dyn std::error::Error + 'static)> {
        match self {
            JsfxError::Io(e) => Some(e),
            _ => None,
        }
    }
}

impl From<std::io::Error> for JsfxError {
    fn from(e: std::io::Error) -> Self {
        JsfxError::Io(e)
    }
}

impl JsfxError {
    /// 创建解析错误的便捷方法
    pub fn parse(line: usize, msg: impl Into<String>) -> Self {
        JsfxError::ParseError {
            line,
            message: msg.into(),
        }
    }
}
