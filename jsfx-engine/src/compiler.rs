//! EEL2→字节码编译器（预留）
//!
//! 当前V1版本使用AST直接解释执行（见vm.rs）。
//! 此模块为未来性能优化预留，将AST编译为字节码后由更轻量的VM执行。
//! 字节码VM可减少递归和HashMap查找，大幅提升@sample路径的执行效率。

use crate::ast::*;
use crate::error::JsfxError;

/// 字节码操作码（预留）
#[derive(Debug, Clone)]
pub enum OpCode {
    /// 从变量槽加载
    LoadVar(usize),
    /// 存储到变量槽
    StoreVar(usize),
    /// 加载常量
    LoadConst(f64),
    /// 加载spl[N]
    LoadSpl(usize),
    /// 存储spl[N]
    StoreSpl(usize),
    /// 加载slider[N]
    LoadSlider(usize),
    /// 加载内存[index]
    LoadMem,
    /// 存储内存[index]
    StoreMem,
    /// 算术运算
    Add,
    Sub,
    Mul,
    Div,
    Mod,
    Pow,
    /// 取负
    Neg,
    /// 逻辑非
    Not,
    /// 比较运算（返回0.0或1.0）
    CmpLt,
    CmpGt,
    CmpLe,
    CmpGe,
    CmpEq,
    CmpNe,
    /// 逻辑与/或
    LogicalAnd,
    LogicalOr,
    /// 无条件跳转
    Jump(usize),
    /// 条件跳转（栈顶为0时跳转）
    JumpIfZero(usize),
    /// 调用内置函数
    CallBuiltin(usize),
    /// 调用用户函数
    CallUser(usize),
    /// 返回
    Return,
    /// 空操作
    Nop,
}

/// 编译器（预留）
pub struct Compiler {
    /// 变量名→槽位映射
    var_slots: std::collections::HashMap<String, usize>,
    /// 常量池
    constants: Vec<f64>,
    /// 输出字节码
    code: Vec<OpCode>,
}

impl Compiler {
    /// 创建新编译器
    pub fn new() -> Self {
        Self {
            var_slots: std::collections::HashMap::new(),
            constants: Vec::new(),
            code: Vec::new(),
        }
    }

    /// 编译语句块为字节码（预留接口）
    pub fn compile_block(&mut self, _block: &[Statement]) -> Result<Vec<OpCode>, JsfxError> {
        // TODO: 实现AST到字节码的编译
        Ok(Vec::new())
    }

    /// 编译表达式为字节码（预留接口）
    pub fn compile_expr(&mut self, _expr: &Expr) -> Result<Vec<OpCode>, JsfxError> {
        // TODO: 实现表达式到字节码的编译
        Ok(Vec::new())
    }
}

impl Default for Compiler {
    fn default() -> Self {
        Self::new()
    }
}
