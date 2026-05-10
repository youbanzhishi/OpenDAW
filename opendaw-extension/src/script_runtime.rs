//! Script Runtime — 脚本扩展接口
//!
//! 第二根柱子：支持 Python/Lua/JavaScript 脚本扩展
//! 脚本可通过注册的API访问DAW全部能力

use std::path::Path;

use crate::error::ScriptError;
use crate::types::ScriptValue;

/// 脚本引擎trait — 不同语言实现此接口即可接入
///
/// 内置桥接：Python(PyO3)、Lua(mlua)、JS(boa/v8)
/// 第三方可实现自定义引擎
pub trait ScriptEngine: Send + Sync {
    /// 脚本语言标识（如 "python", "lua", "javascript"）
    fn lang(&self) -> &str;

    /// 引擎版本
    fn engine_version(&self) -> &str {
        "unknown"
    }

    /// 执行一段脚本代码，返回结果
    fn eval(&mut self, code: &str) -> Result<ScriptValue, ScriptError>;

    /// 调用脚本中定义的函数
    fn call_function(
        &mut self,
        name: &str,
        args: &[ScriptValue],
    ) -> Result<ScriptValue, ScriptError>;

    /// 从文件加载脚本
    fn load_script(&mut self, path: &Path) -> Result<(), ScriptError>;

    /// 注册Rust侧的API供脚本调用
    /// name: 脚本中使用的函数名
    /// func: Rust闭包实现
    fn register_api(
        &mut self,
        name: &str,
        func: Box<dyn Fn(&[ScriptValue]) -> Result<ScriptValue, ScriptError> + Send + Sync>,
    );

    /// 检查脚本中是否存在指定函数
    fn has_function(&self, name: &str) -> bool;

    /// 重置引擎状态
    fn reset(&mut self) -> Result<(), ScriptError>;
}

/// 内置的简单脚本引擎 — 用于测试和演示
/// 只支持基本数学运算和变量赋值
pub struct SimpleScriptEngine {
    variables: std::collections::HashMap<String, ScriptValue>,
    functions: std::collections::HashMap<
        String,
        Box<dyn Fn(&[ScriptValue]) -> Result<ScriptValue, ScriptError> + Send + Sync>,
    >,
    loaded_scripts: Vec<String>,
}

impl SimpleScriptEngine {
    pub fn new() -> Self {
        Self {
            variables: std::collections::HashMap::new(),
            functions: std::collections::HashMap::new(),
            loaded_scripts: Vec::new(),
        }
    }
}

impl Default for SimpleScriptEngine {
    fn default() -> Self {
        Self::new()
    }
}

impl ScriptEngine for SimpleScriptEngine {
    fn lang(&self) -> &str {
        "simple"
    }

    fn engine_version(&self) -> &str {
        "0.1.0"
    }

    fn eval(&mut self, code: &str) -> Result<ScriptValue, ScriptError> {
        let trimmed = code.trim();

        // 简单赋值: x = 42 或 x = 3.14 或 x = "hello"
        if let Some(eq_pos) = trimmed.find('=') {
            let var_name = trimmed[..eq_pos].trim().to_string();
            let value_str = trimmed[eq_pos + 1..].trim();

            let value = if value_str.starts_with('"') && value_str.ends_with('"') {
                ScriptValue::Str(value_str[1..value_str.len() - 1].to_string())
            } else if let Ok(i) = value_str.parse::<i64>() {
                ScriptValue::Int(i)
            } else if let Ok(f) = value_str.parse::<f64>() {
                ScriptValue::Float(f)
            } else if value_str == "true" {
                ScriptValue::Bool(true)
            } else if value_str == "false" {
                ScriptValue::Bool(false)
            } else if value_str == "null" {
                ScriptValue::Null
            } else {
                return Err(ScriptError::SyntaxError(format!(
                    "无法解析值: {}",
                    value_str
                )));
            };

            self.variables.insert(var_name, value.clone());
            return Ok(value);
        }

        // 查找变量
        if let Some(val) = self.variables.get(trimmed) {
            return Ok(val.clone());
        }

        Err(ScriptError::SyntaxError(format!("无法执行: {}", trimmed)))
    }

    fn call_function(
        &mut self,
        name: &str,
        args: &[ScriptValue],
    ) -> Result<ScriptValue, ScriptError> {
        if let Some(func) = self.functions.get(name) {
            func(args)
        } else {
            Err(ScriptError::FunctionNotFound(name.to_string()))
        }
    }

    fn load_script(&mut self, path: &Path) -> Result<(), ScriptError> {
        let content =
            std::fs::read_to_string(path).map_err(|e| ScriptError::LoadFailed(format!("{}", e)))?;
        // 逐行执行
        for line in content.lines() {
            let line = line.trim();
            if line.is_empty() || line.starts_with('#') {
                continue;
            }
            self.eval(line)?;
        }
        self.loaded_scripts.push(path.display().to_string());
        Ok(())
    }

    fn register_api(
        &mut self,
        name: &str,
        func: Box<dyn Fn(&[ScriptValue]) -> Result<ScriptValue, ScriptError> + Send + Sync>,
    ) {
        self.functions.insert(name.to_string(), func);
    }

    fn has_function(&self, name: &str) -> bool {
        self.functions.contains_key(name)
    }

    fn reset(&mut self) -> Result<(), ScriptError> {
        self.variables.clear();
        self.loaded_scripts.clear();
        // 不清除注册的API函数，它们是持久化的
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_simple_engine_eval() {
        let mut engine = SimpleScriptEngine::new();

        // 整数赋值
        let result = engine.eval("x = 42").unwrap();
        assert_eq!(result.as_float(), Some(42.0));

        // 浮点赋值
        let result = engine.eval("y = 3.14").unwrap();
        assert_eq!(result.as_float(), Some(3.14));

        // 变量查找
        let result = engine.eval("x").unwrap();
        assert_eq!(result.as_float(), Some(42.0));
    }

    #[test]
    fn test_simple_engine_register_api() {
        let mut engine = SimpleScriptEngine::new();
        engine.register_api(
            "add",
            Box::new(|args| {
                if args.len() != 2 {
                    return Err(ScriptError::ArgCountMismatch {
                        expected: 2,
                        actual: args.len(),
                    });
                }
                let a = args[0]
                    .as_float()
                    .ok_or(ScriptError::TypeError("参数1不是数字".into()))?;
                let b = args[1]
                    .as_float()
                    .ok_or(ScriptError::TypeError("参数2不是数字".into()))?;
                Ok(ScriptValue::Float(a + b))
            }),
        );

        let result = engine
            .call_function("add", &[ScriptValue::Float(1.0), ScriptValue::Float(2.0)])
            .unwrap();
        assert_eq!(result.as_float(), Some(3.0));
    }
}
