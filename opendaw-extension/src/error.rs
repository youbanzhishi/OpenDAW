//! 统一错误类型

use thiserror::Error;

/// 扩展注册中心顶层错误
#[derive(Error, Debug)]
pub enum ExtensionError {
    #[error("插件错误: {0}")]
    Plugin(#[from] PluginError),

    #[error("脚本错误: {0}")]
    Script(#[from] ScriptError),

    #[error("模型错误: {0}")]
    Model(#[from] ModelError),

    #[error("钩子错误: {0}")]
    Hook(#[from] HookError),

    #[error("配置解析错误: {0}")]
    ConfigParse(String),

    #[error("扩展未找到: {0}")]
    NotFound(String),

    #[error("扩展已存在: {0}")]
    AlreadyExists(String),

    #[error("IO错误: {0}")]
    Io(#[from] std::io::Error),
}

/// 插件错误
#[derive(Error, Debug)]
pub enum PluginError {
    #[error("插件初始化失败: {0}")]
    InitFailed(String),

    #[error("参数无效: id={id}, value={value}")]
    InvalidParam { id: String, value: f64 },

    #[error("参数未找到: {0}")]
    ParamNotFound(String),

    #[error("处理失败: {0}")]
    ProcessFailed(String),

    #[error("插件已销毁")]
    Destroyed,
}

/// 脚本错误
#[derive(Error, Debug)]
pub enum ScriptError {
    #[error("语法错误: {0}")]
    SyntaxError(String),

    #[error("运行时错误: {0}")]
    RuntimeError(String),

    #[error("函数未找到: {0}")]
    FunctionNotFound(String),

    #[error("类型错误: {0}")]
    TypeError(String),

    #[error("加载失败: {0}")]
    LoadFailed(String),

    #[error("参数数量不匹配: 期望{expected}个, 实际{actual}个")]
    ArgCountMismatch { expected: usize, actual: usize },
}

/// 模型错误
#[derive(Error, Debug)]
pub enum ModelError {
    #[error("模型加载失败: {0}")]
    LoadFailed(String),

    #[error("推理失败: {0}")]
    PredictFailed(String),

    #[error("不支持的任务: {0}")]
    UnsupportedTask(String),

    #[error("输入无效: {0}")]
    InvalidInput(String),

    #[error("后端不可用: {0}")]
    BackendUnavailable(String),
}

/// 钩子错误
#[derive(Error, Debug)]
pub enum HookError {
    #[error("处理器未找到: {0}")]
    HandlerNotFound(String),

    #[error("处理器执行失败: {0}")]
    HandlerFailed(String),

    #[error("事件未注册: {0}")]
    EventNotFound(String),
}
