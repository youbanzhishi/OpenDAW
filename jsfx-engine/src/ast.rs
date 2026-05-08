//! 抽象语法树 — EEL2语言核心子集
//!
//! 支持的语法：
//! - 数字字面量、变量引用
//! - 二元运算: +, -, *, /, ^, %, 比较运算
//! - 复合赋值: +=, -=, *=, /=
//! - 一元运算: -, !
//! - 三目运算: condition ? a : b
//! - 函数调用: sin(x), max(a, b)等
//! - 数组访问: memory[index]
//! - if/else语句
//! - while循环
//! - loop(count)循环
//! - 函数定义
//! - 变量赋值

/// JSFX完整程序
#[derive(Debug, Clone)]
pub struct JsfxProgram {
    /// 插件描述（desc:行）
    pub desc: String,
    /// 标签列表
    pub tags: Vec<String>,
    /// Slider参数定义
    pub sliders: Vec<SliderDef>,
    /// 输入引脚名
    pub in_pins: Vec<String>,
    /// 输出引脚名
    pub out_pins: Vec<String>,
    /// @init块
    pub init_block: Option<StatementBlock>,
    /// @slider块
    pub slider_block: Option<StatementBlock>,
    /// @block块
    pub block_block: Option<StatementBlock>,
    /// @sample块（核心）
    pub sample_block: Option<StatementBlock>,
    /// @gfx块（暂不实现执行）
    pub gfx_block: Option<StatementBlock>,
    /// 用户自定义函数
    pub functions: Vec<FunctionDef>,
}

impl Default for JsfxProgram {
    fn default() -> Self {
        Self {
            desc: String::new(),
            tags: Vec::new(),
            sliders: Vec::new(),
            in_pins: Vec::new(),
            out_pins: Vec::new(),
            init_block: None,
            slider_block: None,
            block_block: None,
            sample_block: None,
            gfx_block: None,
            functions: Vec::new(),
        }
    }
}

/// Slider参数定义
#[derive(Debug, Clone)]
pub struct SliderDef {
    /// 序号 1-256
    pub index: usize,
    /// 参数名称
    pub name: Option<String>,
    /// 默认值
    pub default: f64,
    /// 最小值
    pub min: f64,
    /// 最大值
    pub max: f64,
    /// 步长
    pub step: f64,
}

/// 语句块
pub type StatementBlock = Vec<Statement>;

/// 二元运算符
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum BinOp {
    Add,       // +
    Sub,       // -
    Mul,       // *
    Div,       // /
    Mod,       // %
    Pow,       // ^
    Lt,        // <
    Gt,        // >
    Le,        // <=
    Ge,        // >=
    Eq,        // ==
    Ne,        // !=
    And,       // &&
    Or,        // ||
}

/// 一元运算符
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum UnaryOp {
    Neg,  // -
    Not,  // !
}

/// 复合赋值运算符
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum AssignOp {
    Add,  // +=
    Sub,  // -=
    Mul,  // *=
    Div,  // /=
}

/// 表达式
#[derive(Debug, Clone)]
pub enum Expr {
    /// 数字字面量
    Number(f64),
    /// 变量引用（名称已转小写，EEL2大小写不敏感）
    Variable(String),
    /// 二元运算
    BinaryOp(BinOp, Box<Expr>, Box<Expr>),
    /// 一元运算
    UnaryOp(UnaryOp, Box<Expr>),
    /// 函数调用
    FunctionCall(String, Vec<Expr>),
    /// 数组访问 memory[index] 或变量[index]
    ArrayAccess(String, Box<Expr>),
    /// 三目运算 condition ? a : b
    Ternary(Box<Expr>, Box<Expr>, Box<Expr>),
    /// spl(ch) 多通道访问
    SplAccess(Box<Expr>),
}

/// 语句
#[derive(Debug, Clone)]
pub enum Statement {
    /// 变量赋值 x = expr;
    Assign(String, Expr),
    /// 复合赋值 x += expr; x *= expr; 等
    OpAssign(String, AssignOp, Expr),
    /// 数组元素赋值 arr[idx] = expr;
    ArrayAssign(String, Expr, Expr),
    /// spl通道赋值 spl(ch) = expr;
    SplAssign(Expr, Expr),
    /// if语句
    If(Expr, StatementBlock, Option<StatementBlock>),
    /// while循环
    While(Expr, StatementBlock),
    /// loop(count)循环
    Loop(Expr, StatementBlock),
    /// 表达式语句（函数调用等）
    ExprStatement(Expr),
}

/// 用户自定义函数
#[derive(Debug, Clone)]
pub struct FunctionDef {
    pub name: String,
    pub params: Vec<String>,
    pub body: StatementBlock,
}
