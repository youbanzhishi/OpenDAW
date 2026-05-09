//! JSFX字节码虚拟机
//!
//! 直接解释执行AST（V1实现，优先正确性）
//! 后续可优化为真正的字节码VM

use crate::ast::*;
use crate::builtins::BuiltinFn;
use crate::error::JsfxError;
use crate::runtime::JsfxRuntime;

/// JSFX虚拟机
pub struct JsfxVm {
    /// 运行时环境
    pub runtime: JsfxRuntime,
    /// JSFX程序
    program: JsfxProgram,
    /// 用户自定义函数（名称 -> (参数列表, 函数体)）
    user_functions: std::collections::HashMap<String, (Vec<String>, StatementBlock)>,
}

/// 音频缓冲区（简化版，避免依赖opendaw-extension）
#[derive(Clone, Debug)]
pub struct AudioBuffer {
    pub channels: usize,
    pub frames: usize,
    pub data: Vec<f64>,
}

impl AudioBuffer {
    pub fn new(channels: usize, frames: usize) -> Self {
        Self {
            channels,
            frames,
            data: vec![0.0; channels * frames],
        }
    }

    pub fn sample(&self, channel: usize, frame: usize) -> f64 {
        self.data[channel * self.frames + frame]
    }

    pub fn set_sample(&mut self, channel: usize, frame: usize, value: f64) {
        if channel < self.channels && frame < self.frames {
            self.data[channel * self.frames + frame] = value;
        }
    }

    pub fn clear(&mut self) {
        self.data.fill(0.0);
    }
}

impl JsfxVm {
    /// 创建新的虚拟机
    pub fn new() -> Self {
        Self {
            runtime: JsfxRuntime::new(),
            program: JsfxProgram::default(),
            user_functions: std::collections::HashMap::new(),
        }
    }

    /// 加载JSFX程序
    pub fn load(&mut self, program: &JsfxProgram) -> Result<(), JsfxError> {
        self.program = program.clone();

        // 初始化slider默认值
        for slider in &program.sliders {
            self.runtime.set_slider(slider.index, slider.default);
        }

        // 注册用户自定义函数
        for func in &program.functions {
            self.user_functions.insert(func.name.clone(), (func.params.clone(), func.body.clone()));
        }

        Ok(())
    }

    /// 执行@init块
    pub fn init(&mut self, sample_rate: f64) {
        self.runtime.init(sample_rate, 256);

        // 初始化slider默认值
        for slider in &self.program.sliders {
            self.runtime.set_slider(slider.index, slider.default);
        }

        // 执行@init — 克隆block避免借用冲突
        if let Some(ref block) = self.program.init_block {
            let block = block.clone();
            let _ = self.execute_block(&block);
        }
    }

    /// 更新slider参数并执行@slider块
    pub fn update_slider(&mut self, index: usize, value: f64) {
        self.runtime.set_slider(index, value);

        // 执行@slider块
        if let Some(ref block) = self.program.slider_block {
            let block = block.clone();
            let _ = self.execute_block(&block);
        }
    }

    /// 处理单个采样点
    pub fn process_sample(&mut self, spl0: f64, spl1: f64) -> (f64, f64) {
        // 设置输入
        self.runtime.spl[0] = spl0;
        self.runtime.spl[1] = spl1;

        // 执行@sample块
        if let Some(ref block) = self.program.sample_block {
            let block = block.clone();
            let _ = self.execute_block(&block);
        }

        // 返回输出
        (self.runtime.spl[0], self.runtime.spl[1])
    }

    /// 处理整个缓冲区
    pub fn process_buffer(&mut self, input: &AudioBuffer, output: &mut AudioBuffer) {
        let frames = input.frames.min(output.frames);
        let channels = input.channels.min(output.channels).min(2);

        // 执行@block（每个buffer一次）
        if let Some(ref block) = self.program.block_block {
            let block = block.clone();
            let _ = self.execute_block(&block);
        }

        // 逐采样处理
        for frame in 0..frames {
            let spl0 = if channels > 0 { input.sample(0, frame) } else { 0.0 };
            let spl1 = if channels > 1 { input.sample(1, frame) } else { spl0 };

            let (out0, out1) = self.process_sample(spl0, spl1);

            if channels > 0 { output.set_sample(0, frame, out0); }
            if channels > 1 { output.set_sample(1, frame, out1); }

            self.runtime.sample_index += 1;
            self.runtime.play_position += 1.0;
        }
    }

    /// 执行语句块
    fn execute_block(&mut self, block: &[Statement]) -> Result<f64, JsfxError> {
        let mut last_val = 0.0;
        for stmt in block {
            last_val = self.execute_statement(stmt)?;
        }
        Ok(last_val)
    }

    /// 执行单条语句
    fn execute_statement(&mut self, stmt: &Statement) -> Result<f64, JsfxError> {
        match stmt {
            Statement::Assign(name, expr) => {
                let val = self.eval_expr(expr)?;
                self.runtime.set_var(name, val);
                Ok(val)
            }

            Statement::OpAssign(name, op, expr) => {
                let current = self.runtime.get_var(name);
                let rhs = self.eval_expr(expr)?;
                let val = match op {
                    AssignOp::Add => current + rhs,
                    AssignOp::Sub => current - rhs,
                    AssignOp::Mul => current * rhs,
                    AssignOp::Div => {
                        if rhs == 0.0 { return Err(JsfxError::DivisionByZero); }
                        current / rhs
                    }
                };
                self.runtime.set_var(name, val);
                Ok(val)
            }

            Statement::ArrayAssign(arr_name, idx_expr, val_expr) => {
                let idx = self.eval_expr(idx_expr)? as usize;
                let val = self.eval_expr(val_expr)?;
                if arr_name == "memory" || arr_name == "mem" {
                    self.runtime.mem_set(idx, val);
                } else {
                    // 其他数组变量用memory空间
                    self.runtime.mem_set(idx, val);
                }
                Ok(val)
            }

            Statement::SplAssign(ch_expr, val_expr) => {
                let ch = self.eval_expr(ch_expr)? as usize;
                let val = self.eval_expr(val_expr)?;
                self.runtime.set_spl(ch, val);
                Ok(val)
            }

            Statement::If(cond, then_block, else_block) => {
                let cond_val = self.eval_expr(cond)?;
                if cond_val != 0.0 {
                    self.execute_block(then_block)
                } else if let Some(else_block) = else_block {
                    self.execute_block(else_block)
                } else {
                    Ok(0.0)
                }
            }

            Statement::While(cond, body) => {
                let mut last_val = 0.0;
                let mut iterations = 0;
                const MAX_ITERATIONS: usize = 1000000;
                while self.eval_expr(cond)? != 0.0 && iterations < MAX_ITERATIONS {
                    last_val = self.execute_block(body)?;
                    iterations += 1;
                }
                Ok(last_val)
            }

            Statement::Loop(count_expr, body) => {
                let count = self.eval_expr(count_expr)? as usize;
                let mut last_val = 0.0;
                let max = count.min(1000000);
                for _ in 0..max {
                    last_val = self.execute_block(body)?;
                }
                Ok(last_val)
            }

            Statement::ExprStatement(expr) => {
                self.eval_expr(expr)
            }
        }
    }

    /// 求值表达式
    fn eval_expr(&mut self, expr: &Expr) -> Result<f64, JsfxError> {
        match expr {
            Expr::Number(n) => Ok(*n),

            Expr::Variable(name) => Ok(self.runtime.get_var(name)),

            Expr::BinaryOp(op, left, right) => {
                let l = self.eval_expr(left)?;
                let r = self.eval_expr(right)?;
                Ok(match op {
                    BinOp::Add => l + r,
                    BinOp::Sub => l - r,
                    BinOp::Mul => l * r,
                    BinOp::Div => {
                        if r == 0.0 { return Err(JsfxError::DivisionByZero); }
                        l / r
                    }
                    BinOp::Mod => {
                        if r == 0.0 { return Err(JsfxError::DivisionByZero); }
                        l % r
                    }
                    BinOp::Pow => l.powf(r),
                    BinOp::Lt => if l < r { 1.0 } else { 0.0 },
                    BinOp::Gt => if l > r { 1.0 } else { 0.0 },
                    BinOp::Le => if l <= r { 1.0 } else { 0.0 },
                    BinOp::Ge => if l >= r { 1.0 } else { 0.0 },
                    BinOp::Eq => if (l - r).abs() < f64::EPSILON { 1.0 } else { 0.0 },
                    BinOp::Ne => if (l - r).abs() >= f64::EPSILON { 1.0 } else { 0.0 },
                    BinOp::And => if l != 0.0 && r != 0.0 { 1.0 } else { 0.0 },
                    BinOp::Or => if l != 0.0 || r != 0.0 { 1.0 } else { 0.0 },
                })
            }

            Expr::UnaryOp(op, operand) => {
                let v = self.eval_expr(operand)?;
                Ok(match op {
                    UnaryOp::Neg => -v,
                    UnaryOp::Not => if v == 0.0 { 1.0 } else { 0.0 },
                })
            }

            Expr::Ternary(cond, true_expr, false_expr) => {
                let cond_val = self.eval_expr(cond)?;
                if cond_val != 0.0 {
                    self.eval_expr(true_expr)
                } else {
                    self.eval_expr(false_expr)
                }
            }

            Expr::FunctionCall(name, args) => {
                // 先求值所有参数
                let mut arg_vals = Vec::new();
                for arg in args {
                    arg_vals.push(self.eval_expr(arg)?);
                }

                // 检查是否为内置函数
                if let Some(builtin) = BuiltinFn::from_name(name) {
                    // 内存操作需要特殊处理
                    match builtin {
                        BuiltinFn::MemGet => {
                            let idx = arg_vals.first().copied().unwrap_or(0.0) as usize;
                            return Ok(self.runtime.mem_get(idx));
                        }
                        BuiltinFn::MemSet => {
                            let idx = arg_vals.first().copied().unwrap_or(0.0) as usize;
                            let val = arg_vals.get(1).copied().unwrap_or(0.0);
                            self.runtime.mem_set(idx, val);
                            return Ok(val);
                        }
                        BuiltinFn::MemCpy => {
                            let dest = arg_vals.first().copied().unwrap_or(0.0) as usize;
                            let src = arg_vals.get(1).copied().unwrap_or(0.0) as usize;
                            let len = arg_vals.get(2).copied().unwrap_or(0.0) as usize;
                            if src + len <= self.runtime.memory.len() && dest + len <= self.runtime.memory.len() {
                                let tmp: Vec<f64> = self.runtime.memory[src..src + len].to_vec();
                                self.runtime.memory[dest..dest + len].copy_from_slice(&tmp);
                            }
                            return Ok(0.0);
                        }
                        _ => {
                            let (min_args, max_args) = builtin.arg_count();
                            if arg_vals.len() < min_args || arg_vals.len() > max_args {
                                return Err(JsfxError::ArgCountMismatch {
                                    func: name.clone(),
                                    expected: min_args,
                                    actual: arg_vals.len(),
                                });
                            }
                            return Ok(builtin.call(&arg_vals));
                        }
                    }
                }

                // 特殊函数：memory(start, size) — 分配内存
                if name == "memory" {
                    let start = arg_vals.first().copied().unwrap_or(0.0) as usize;
                    let size = arg_vals.get(1).copied().unwrap_or(0.0) as usize;
                    self.runtime.mem_alloc(start, size);
                    return Ok(start as f64);
                }

                // 检查是否为用户自定义函数 — 克隆函数信息避免借用冲突
                if let Some((params, body)) = self.user_functions.get(name).cloned() {
                    // 保存当前参数值
                    let old_values: Vec<(String, f64)> = params.iter()
                        .map(|p| (p.clone(), self.runtime.get_var(p)))
                        .collect();

                    // 设置参数
                    for (i, param) in params.iter().enumerate() {
                        let val = arg_vals.get(i).copied().unwrap_or(0.0);
                        self.runtime.set_var(param, val);
                    }

                    // 执行函数体
                    let result = self.execute_block(&body);

                    // 恢复参数值
                    for (param, old_val) in old_values {
                        self.runtime.set_var(&param, old_val);
                    }

                    return result;
                }

                Err(JsfxError::UndefinedFunction(name.clone()))
            }

            Expr::ArrayAccess(name, idx_expr) => {
                let idx = self.eval_expr(idx_expr)? as usize;
                if name == "memory" || name == "mem" {
                    Ok(self.runtime.mem_get(idx))
                } else {
                    // 其他数组变量
                    Ok(self.runtime.mem_get(idx))
                }
            }

            Expr::SplAccess(ch_expr) => {
                let ch = self.eval_expr(ch_expr)? as usize;
                Ok(self.runtime.get_spl(ch))
            }
        }
    }
}

impl Default for JsfxVm {
    fn default() -> Self {
        Self::new()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::parser::JsfxParser;

    #[test]
    fn test_vm_gain() {
        let source = r#"
desc:Simple Gain
slider1:0<-150,150,0.1>Gain (dB)

@slider
gain = 2^(slider1/6);

@sample
spl0 *= gain;
spl1 *= gain;
"#;
        let program = JsfxParser::parse(source).unwrap();
        let mut vm = JsfxVm::new();
        vm.load(&program).unwrap();
        vm.init(44100.0);

        // 设置slider为0dB（gain=1.0）
        vm.update_slider(1, 0.0);

        let (out0, out1) = vm.process_sample(1.0, 0.5);
        // 0dB时gain = 2^(0/6) = 1.0
        assert!((out0 - 1.0).abs() < 0.001, "期望out0≈1.0, 实际={}", out0);
        assert!((out1 - 0.5).abs() < 0.001, "期望out1≈0.5, 实际={}", out1);
    }

    #[test]
    fn test_vm_buffer_processing() {
        let source = r#"
desc:Simple Gain
slider1:6<-150,150,0.1>Gain (dB)

@slider
gain = 2^(slider1/6);

@sample
spl0 *= gain;
spl1 *= gain;
"#;
        let program = JsfxParser::parse(source).unwrap();
        let mut vm = JsfxVm::new();
        vm.load(&program).unwrap();
        vm.init(44100.0);

        // 6dB增益: gain = 2^(6/6) = 2.0
        vm.update_slider(1, 6.0);

        let input = AudioBuffer::new(2, 4);
        let mut output = AudioBuffer::new(2, 4);

        // 静音输入，所以输出也应该是0
        vm.process_buffer(&input, &mut output);
        for i in 0..4 {
            assert!(output.sample(0, i).abs() < 0.001);
        }
    }
}
