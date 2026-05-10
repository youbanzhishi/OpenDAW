//! JSFX文本解析器
//!
//! 将JSFX源码解析为AST。支持EEL2核心语法子集。
//! EEL2特点：大小写不敏感、变量无需声明、分号结尾、三目运算符
//!
//! 增强功能：
//! - 字符串字面量（"..."）
//! - $常量（$pi, $e, $phi）
//! - #预处理器指令（#define, #ifdef, #ifndef, #else, #endif, #undef）
//! - 数组括号访问（memory[0]）
//! - 复合赋值（+=, -=, *=, /=, ^=, %=）
//! - if/else多行语法
//! - loop(count, body) 语法

use crate::ast::*;
use crate::error::JsfxError;

/// JSFX解析器
pub struct JsfxParser;

/// 简化的token类型
#[derive(Debug, Clone, PartialEq)]
enum Token {
    Number(f64),
    Ident(String),
    StringLit(String),
    Op(String),
    LParen,
    RParen,
    LBracket,
    RBracket,
    Comma,
    Question,
    Colon,
    Dollar,  // $ prefix
}

impl JsfxParser {
    /// 解析JSFX文本为AST
    pub fn parse(source: &str) -> Result<JsfxProgram, JsfxError> {
        // 第一步：预处理（处理#define, #ifdef等）
        let processed = Self::preprocess(source)?;

        let mut program = JsfxProgram::default();
        let mut current_section: Option<String> = None;
        let mut current_lines: Vec<String> = Vec::new();

        let lines: Vec<&str> = processed.lines().collect();
        let mut line_idx = 0;

        while line_idx < lines.len() {
            let line = lines[line_idx].trim();

            // 跳过空行和纯注释
            if line.is_empty() || line.starts_with("//") {
                line_idx += 1;
                continue;
            }

            // 解析头部字段
            if let Some(rest) = line.strip_prefix("desc:") {
                Self::flush_section(&mut program, &current_section, &current_lines)?;
                current_section = None;
                current_lines.clear();
                program.desc = rest.trim().to_string();
                line_idx += 1;
                continue;
            }

            if let Some(rest) = line.strip_prefix("slider") {
                if let Some(slider) = Self::parse_slider_line(rest, line_idx + 1)? {
                    program.sliders.push(slider);
                }
                line_idx += 1;
                continue;
            }

            if let Some(rest) = line.strip_prefix("in_pin:") {
                program.in_pins.push(rest.trim().to_string());
                line_idx += 1;
                continue;
            }

            if let Some(rest) = line.strip_prefix("out_pin:") {
                program.out_pins.push(rest.trim().to_string());
                line_idx += 1;
                continue;
            }

            if line.starts_with("tags:") {
                program.tags = line[5..].trim().split_whitespace()
                    .map(|s| s.to_string()).collect();
                line_idx += 1;
                continue;
            }

            // 检测section标记
            if line.starts_with('@') {
                Self::flush_section(&mut program, &current_section, &current_lines)?;
                current_lines.clear();
                let section_name = line[1..].trim().to_lowercase();
                current_section = Some(section_name);
                line_idx += 1;
                continue;
            }

            // 普通代码行
            current_lines.push(line.to_string());
            line_idx += 1;
        }

        Self::flush_section(&mut program, &current_section, &current_lines)?;
        Ok(program)
    }

    /// 预处理器：处理 #define, #ifdef, #ifndef, #else, #endif, #undef
    fn preprocess(source: &str) -> Result<String, JsfxError> {
        let mut defines: std::collections::HashMap<String, String> = std::collections::HashMap::new();
        let mut result = String::new();
        let mut cond_stack: Vec<(bool, bool)> = Vec::new(); // (is_active, has_been_true)

        for line in source.lines() {
            let trimmed = line.trim();

            // 预处理器指令
            if trimmed.starts_with('#') {
                let directive = trimmed[1..].trim();
                let lower = directive.to_lowercase();

                if lower.starts_with("define ") {
                    let rest = directive[7..].trim();
                    let mut parts = rest.splitn(2, |c: char| c.is_whitespace());
                    if let Some(name) = parts.next() {
                        let value = parts.next().unwrap_or("").trim().to_string();
                        defines.insert(name.to_string(), value);
                    }
                    continue;
                }

                if lower.starts_with("undef ") {
                    let name = directive[6..].trim();
                    defines.remove(name);
                    continue;
                }

                if lower.starts_with("ifdef ") {
                    let name = directive[6..].trim();
                    let is_defined = defines.contains_key(name);
                    cond_stack.push((is_defined, is_defined));
                    continue;
                }

                if lower.starts_with("ifndef ") {
                    let name = directive[7..].trim();
                    let is_defined = defines.contains_key(name);
                    cond_stack.push((!is_defined, !is_defined));
                    continue;
                }

                if lower.starts_with("else") {
                    if let Some((was_active, has_been_true)) = cond_stack.last_mut() {
                        *was_active = !*has_been_true;
                        *has_been_true = true;
                    }
                    continue;
                }

                if lower.starts_with("endif") {
                    cond_stack.pop();
                    continue;
                }

                // 未知预处理器指令，跳过
                continue;
            }

            // 检查是否在条件块内
            let is_active = cond_stack.iter().all(|(active, _)| *active);

            if is_active {
                // 替换 #define 的值
                let mut processed_line = line.to_string();
                for (name, value) in &defines {
                    processed_line = processed_line.replace(name, value);
                }
                result.push_str(&processed_line);
                result.push('\n');
            }
        }

        Ok(result)
    }

    /// 将收集的行刷入对应section
    fn flush_section(
        program: &mut JsfxProgram,
        section: &Option<String>,
        lines: &[String],
    ) -> Result<(), JsfxError> {
        if lines.is_empty() {
            return Ok(());
        }

        // 分离函数定义和普通代码
        let mut code_lines: Vec<String> = Vec::new();
        let mut i = 0;
        while i < lines.len() {
            let line = lines[i].trim();
            let line_lower = line.to_lowercase();
            if line_lower.starts_with("function ") {
                // 解析函数定义
                let (func_name, func_params) = Self::parse_function_header(line, i + 1)?;
                let is_local = func_name.contains('.');
                let mut body_lines = Vec::new();
                i += 1;
                while i < lines.len() {
                    let l = lines[i].trim();
                    if l.to_lowercase().starts_with("function ") {
                        break;
                    }
                    body_lines.push(l.to_string());
                    i += 1;
                }
                let body = Self::parse_statement_block(&body_lines)?;
                program.functions.push(FunctionDef {
                    name: func_name,
                    params: func_params,
                    body,
                    is_local,
                });
                continue;
            }
            code_lines.push(lines[i].clone());
            i += 1;
        }

        let block = Self::parse_statement_block(&code_lines)?;

        match section {
            Some(s) if s == "init" => program.init_block = Some(block),
            Some(s) if s == "slider" => program.slider_block = Some(block),
            Some(s) if s == "block" => program.block_block = Some(block),
            Some(s) if s == "sample" => program.sample_block = Some(block),
            Some(s) if s == "gfx" => program.gfx_block = Some(block),
            Some(s) if s == "serialize" => program.serialize_block = Some(block),
            _ => {}
        }

        Ok(())
    }

    /// 解析slider行
    fn parse_slider_line(rest: &str, line_num: usize) -> Result<Option<SliderDef>, JsfxError> {
        let rest = rest.trim();
        let (index_str, remainder) = if let Some(pos) = rest.find(':') {
            (&rest[..pos], &rest[pos + 1..])
        } else {
            return Ok(None);
        };

        let index: usize = match index_str.trim().parse() {
            Ok(v) => v,
            Err(_) => return Ok(None),
        };

        if index == 0 || index > 256 {
            return Err(JsfxError::parse(line_num, format!("slider索引超出范围: {}", index)));
        }

        let lt_pos = match remainder.find('<') {
            Some(p) => p,
            None => {
                let default: f64 = remainder.trim().parse().unwrap_or(0.0);
                return Ok(Some(SliderDef {
                    index,
                    name: None,
                    default,
                    min: 0.0,
                    max: 1.0,
                    step: 0.001,
                }));
            }
        };

        let default: f64 = remainder[..lt_pos].trim().parse().unwrap_or(0.0);

        let gt_pos = match remainder[lt_pos..].find('>') {
            Some(p) => lt_pos + p,
            None => return Err(JsfxError::parse(line_num, "slider范围定义缺少 >")),
        };

        let range_str = &remainder[lt_pos + 1..gt_pos];
        let range_parts: Vec<&str> = range_str.split(',').collect();

        let min: f64 = range_parts.first().and_then(|s| s.trim().parse().ok()).unwrap_or(0.0);
        let max: f64 = range_parts.get(1).and_then(|s| s.trim().parse().ok()).unwrap_or(1.0);
        let step: f64 = range_parts.get(2).and_then(|s| s.trim().parse().ok()).unwrap_or(0.001);

        let name = if remainder.len() > gt_pos + 1 {
            let n = remainder[gt_pos + 1..].trim();
            if n.is_empty() { None } else { Some(n.to_string()) }
        } else {
            None
        };

        Ok(Some(SliderDef { index, name, default, min, max, step }))
    }

    /// 解析函数头
    fn parse_function_header(line: &str, line_num: usize) -> Result<(String, Vec<String>), JsfxError> {
        let line = line.trim();
        let after_fn = &line[8..].trim_start();

        let paren_pos = match after_fn.find('(') {
            Some(p) => p,
            None => return Err(JsfxError::parse(line_num, "函数定义缺少 (")),
        };

        let name = after_fn[..paren_pos].trim().to_lowercase();
        let close_pos = match after_fn.find(')') {
            Some(p) => p,
            None => return Err(JsfxError::parse(line_num, "函数定义缺少 )")),
        };

        let params_str = &after_fn[paren_pos + 1..close_pos];
        let params: Vec<String> = if params_str.trim().is_empty() {
            Vec::new()
        } else {
            params_str.split(',')
                .map(|p| p.trim().to_lowercase())
                .collect()
        };

        Ok((name, params))
    }

    /// 解析语句块
    fn parse_statement_block(lines: &[String]) -> Result<StatementBlock, JsfxError> {
        let mut statements = Vec::new();
        let mut i = 0;

        while i < lines.len() {
            let line = lines[i].trim();

            if line.is_empty() || line.starts_with("//") {
                i += 1;
                continue;
            }

            // 检测if/else多行块
            if line.to_lowercase().starts_with("if ") || line.to_lowercase().starts_with("if(") {
                let (stmt, advance) = Self::parse_if_statement(lines, i)?;
                statements.push(stmt);
                i += advance;
                continue;
            }

            // 检测while循环
            if line.to_lowercase().starts_with("while ") || line.to_lowercase().starts_with("while(") {
                let (stmt, advance) = Self::parse_while_statement(lines, i)?;
                statements.push(stmt);
                i += advance;
                continue;
            }

            // 检测loop
            if line.to_lowercase().starts_with("loop(") || line.to_lowercase().starts_with("loop (") {
                let (stmt, advance) = Self::parse_loop_statement(lines, i)?;
                statements.push(stmt);
                i += advance;
                continue;
            }

            // 检测function（不应在块内出现，但容错）
            if line.to_lowercase().starts_with("function ") {
                i += 1;
                continue;
            }

            // 普通语句行
            if let Some(stmt) = Self::parse_single_line(line, i + 1)? {
                statements.push(stmt);
            }
            i += 1;
        }

        Ok(statements)
    }

    /// 解析if语句（支持单行和多行）
    fn parse_if_statement(lines: &[String], offset: usize) -> Result<(Statement, usize), JsfxError> {
        let line = Self::strip_comment(lines[offset].trim());
        let lower = line.to_lowercase();

        // 找到条件部分
        let cond_start = if lower.starts_with("if ") { 3 } else { 2 }; // "if " or "if("
        let cond_str = &line[cond_start..].trim();

        // 尝试解析为单行if: if (cond) stmt;
        // 或多行if: if (cond) ( ... ) else ( ... )

        let (cond, then_part, else_part, advance) = if cond_str.starts_with('(') {
            // 查找匹配的右括号
            if let Some(end) = Self::find_matching_paren(cond_str, 0) {
                let cond_expr_str = &cond_str[1..end];
                let after_cond = cond_str[end + 1..].trim();
                let cond_expr = Self::parse_expression(cond_expr_str, offset + 1)?;

                // 检查后面是否有多行块
                if after_cond.starts_with('(') {
                    // 多行 then 块
                    let (then_stmts, else_stmts, adv) = Self::parse_if_multiline(cond_str, end + 1, lines, offset)?;
                    (cond_expr, then_stmts, else_stmts, adv)
                } else if !after_cond.is_empty() {
                    // 单行then
                    let then_stmts = Self::parse_statement_block(&[after_cond.to_string()])?;
                    (cond_expr, then_stmts, None, 1)
                } else {
                    // then块在下一行
                    let mut then_lines = Vec::new();
                    let mut adv = 1;
                    let mut has_else = false;
                    let mut else_lines = Vec::new();

                    while offset + adv < lines.len() {
                        let next = lines[offset + adv].trim();
                        if next.to_lowercase().starts_with("else") {
                            has_else = true;
                            adv += 1;
                            while offset + adv < lines.len() {
                                let el = lines[offset + adv].trim();
                                if el.to_lowercase().starts_with("if ") ||
                                   el.to_lowercase().starts_with("while ") ||
                                   el.to_lowercase().starts_with("loop(") ||
                                   el.is_empty() && adv > offset + 1 {
                                    break;
                                }
                                if el.is_empty() { adv += 1; continue; }
                                else_lines.push(el.to_string());
                                adv += 1;
                            }
                            break;
                        }
                        if next.to_lowercase().starts_with("if ") ||
                           next.to_lowercase().starts_with("while ") ||
                           next.to_lowercase().starts_with("loop(") ||
                           next.starts_with('@') {
                            break;
                        }
                        if next.is_empty() && then_lines.is_empty() { adv += 1; continue; }
                        if next.is_empty() { break; }
                        then_lines.push(next.to_string());
                        adv += 1;
                    }

                    let then_block = Self::parse_statement_block(&then_lines)?;
                    let else_block = if else_lines.is_empty() { None } else { Some(Self::parse_statement_block(&else_lines)?) };
                    (cond_expr, then_block, else_block, adv)
                }
            } else {
                // 无匹配括号，尝试简单解析
                let cond_expr = Self::parse_expression(cond_str, offset + 1)?;
                (cond_expr, Vec::new(), None, 1)
            }
        } else {
            // 无括号条件
            let cond_expr = Self::parse_expression(cond_str, offset + 1)?;
            (cond_expr, Vec::new(), None, 1)
        };

        Ok((Statement::If(cond, then_part, else_part), advance))
    }

    /// 解析多行if的then/else块
    fn parse_if_multiline(
        remaining: &str,
        start: usize,
        _lines: &[String],
        _offset: usize,
    ) -> Result<(StatementBlock, Option<StatementBlock>, usize), JsfxError> {
        let after = remaining[start..].trim();

        if after.starts_with('(') {
            if let Some(end) = Self::find_matching_paren(after, 0) {
                let then_str = &after[1..end];
                let then_lines: Vec<String> = then_str.lines()
                    .map(|l| l.trim().to_string())
                    .filter(|l| !l.is_empty())
                    .collect();
                let then_block = Self::parse_statement_block(&then_lines)?;

                let after_then = after[end + 1..].trim();
                if after_then.to_lowercase().starts_with("else") {
                    let else_part = after_then[4..].trim();
                    if else_part.starts_with('(') {
                        if let Some(else_end) = Self::find_matching_paren(else_part, 0) {
                            let else_str = &else_part[1..else_end];
                            let else_lines: Vec<String> = else_str.lines()
                                .map(|l| l.trim().to_string())
                                .filter(|l| !l.is_empty())
                                .collect();
                            let else_block = Self::parse_statement_block(&else_lines)?;
                            return Ok((then_block, Some(else_block), 1));
                        }
                    }
                    // else 后面是单行
                    let else_lines = vec![else_part.to_string()];
                    let else_block = Self::parse_statement_block(&else_lines)?;
                    return Ok((then_block, Some(else_block), 1));
                }

                return Ok((then_block, None, 1));
            }
        }

        Ok((Vec::new(), None, 1))
    }

    /// 解析while语句
    fn parse_while_statement(lines: &[String], offset: usize) -> Result<(Statement, usize), JsfxError> {
        let line = Self::strip_comment(lines[offset].trim());
        let lower = line.to_lowercase();

        let cond_start = if lower.starts_with("while ") { 6 } else { 5 };
        let cond_str = &line[cond_start..].trim();

        let (cond, body, advance) = if cond_str.starts_with('(') {
            if let Some(end) = Self::find_matching_paren(cond_str, 0) {
                let cond_expr = Self::parse_expression(&cond_str[1..end], offset + 1)?;
                let after = cond_str[end + 1..].trim();

                if after.starts_with('(') {
                    // 多行while体
                    if let Some(body_end) = Self::find_matching_paren(after, 0) {
                        let body_str = &after[1..body_end];
                        let body_lines: Vec<String> = body_str.lines()
                            .map(|l| l.trim().to_string())
                            .filter(|l| !l.is_empty())
                            .collect();
                        let body = Self::parse_statement_block(&body_lines)?;
                        (cond_expr, body, 1)
                    } else {
                        (cond_expr, Vec::new(), 1)
                    }
                } else if !after.is_empty() {
                    let body = Self::parse_statement_block(&[after.to_string()])?;
                    (cond_expr, body, 1)
                } else {
                    // body在下一行
                    let mut body_lines = Vec::new();
                    let mut adv = 1;
                    while offset + adv < lines.len() {
                        let next = lines[offset + adv].trim();
                        if next.is_empty() || next.starts_with('@') { break; }
                        body_lines.push(next.to_string());
                        adv += 1;
                    }
                    let body = Self::parse_statement_block(&body_lines)?;
                    (cond_expr, body, adv)
                }
            } else {
                let cond_expr = Self::parse_expression(cond_str, offset + 1)?;
                (cond_expr, Vec::new(), 1)
            }
        } else {
            let cond_expr = Self::parse_expression(cond_str, offset + 1)?;
            (cond_expr, Vec::new(), 1)
        };

        Ok((Statement::While(cond, body), advance))
    }

    /// 解析loop语句
    fn parse_loop_statement(lines: &[String], offset: usize) -> Result<(Statement, usize), JsfxError> {
        let line = Self::strip_comment(lines[offset].trim());

        let paren_start = line.find('(').ok_or_else(|| JsfxError::parse(offset + 1, "loop缺少("))?;
        let paren_end = Self::find_matching_paren(&line, paren_start).ok_or_else(|| JsfxError::parse(offset + 1, "loop缺少)"))?;

        let inner = &line[paren_start + 1..paren_end];

        // loop(count, body) 格式
        let comma_pos = inner.find(',').ok_or_else(|| JsfxError::parse(offset + 1, "loop缺少逗号分隔count和body"))?;

        let count_expr_str = inner[..comma_pos].trim();
        let after_paren = inner[comma_pos + 1..].trim();

        let count_expr = Self::parse_expression(count_expr_str, offset + 1)?;

        let mut body_lines = Vec::new();

        if !after_paren.is_empty() {
            body_lines.push(after_paren.to_string());
        }

        let advance = if body_lines.is_empty() && offset + 1 < lines.len() {
            let next = Self::strip_comment(lines[offset + 1].trim());
            if !next.is_empty() && !next.starts_with('@') {
                body_lines.push(next.to_string());
                2
            } else {
                1
            }
        } else {
            1
        };

        let body = Self::parse_statement_block(&body_lines)?;
        Ok((Statement::Loop(count_expr, body), advance))
    }

    /// 解析单行语句
    fn parse_single_line(line: &str, line_num: usize) -> Result<Option<Statement>, JsfxError> {
        let line = Self::strip_comment(line.trim());
        if line.is_empty() {
            return Ok(None);
        }

        // 检测if单行语句: if (cond) stmt;
        let lower = line.to_lowercase();
        if lower.starts_with("if ") || lower.starts_with("if(") {
            // 简单单行if
            let cond_start = if lower.starts_with("if ") { 3 } else { 2 };
            let rest = &line[cond_start..];

            // 解析条件
            let (cond, after_cond) = if rest.starts_with('(') {
                if let Some(end) = Self::find_matching_paren(rest, 0) {
                    let cond_expr = Self::parse_expression(&rest[1..end], line_num)?;
                    (cond_expr, rest[end + 1..].trim().to_string())
                } else {
                    let cond_expr = Self::parse_expression(rest, line_num)?;
                    (cond_expr, String::new())
                }
            } else {
                // 无括号的条件 + 三目风格
                let cond_expr = Self::parse_expression(rest, line_num)?;
                (cond_expr, String::new())
            };

            if !after_cond.is_empty() {
                let then_block = Self::parse_statement_block(&[after_cond])?;
                return Ok(Some(Statement::If(cond, then_block, None)));
            }
            return Ok(Some(Statement::If(cond, Vec::new(), None)));
        }

        // 尝试解析赋值语句
        if let Some(stmt) = Self::try_parse_assignment(line, line_num)? {
            return Ok(Some(stmt));
        }

        // 尝试解析表达式语句
        let expr = Self::parse_expression(line, line_num)?;
        Ok(Some(Statement::ExprStatement(expr)))
    }

    /// 尝试解析赋值语句
    fn try_parse_assignment(line: &str, line_num: usize) -> Result<Option<Statement>, JsfxError> {
        let tokens = Self::tokenize(line);

        if tokens.is_empty() {
            return Ok(None);
        }

        // 查找赋值运算符
        let assign_pos = tokens.iter().position(|t| matches!(t,
            Token::Op(s) if s == "=" || s == "+=" || s == "-=" || s == "*=" || s == "/=" || s == "^=" || s == "%="
        ));

        if let Some(pos) = assign_pos {
            if pos == 0 { return Ok(None); }

            let op_str = match &tokens[pos] {
                Token::Op(s) => s.clone(),
                _ => return Ok(None),
            };

            // 获取目标
            let target = &tokens[pos - 1];

            match target {
                Token::Ident(name) => {
                    let name_lower = name.to_lowercase();

                    // 检查是否为数组赋值: name[idx] = expr;
                    if pos + 1 < tokens.len() && matches!(tokens[pos - 1 + 1], Token::LBracket) {
                        // 不太对，需要回看
                    }

                    // 检查 name 后面是否跟着 [
                    // 回看tokens[0..pos]，看是否为 name[idx] 形式
                    if pos >= 2 && matches!(tokens[pos - 2], Token::LBracket) {
                        // 这不是简单的赋值，跳过
                    }

                    // 检查是否为 spl(idx) 赋值
                    if name_lower == "spl" && pos >= 2 {
                        // spl(ch) = expr — 在tokens中回看
                    }

                    // 解析右侧表达式
                    let rhs_tokens = &tokens[pos + 1..];
                    let rhs_expr = if rhs_tokens.is_empty() {
                        Expr::Number(0.0)
                    } else {
                        let mut rhs_pos = 0;
                        Self::parse_expr_from_tokens(rhs_tokens, &mut rhs_pos, line_num)?
                    };

                    if op_str == "=" {
                        return Ok(Some(Statement::Assign(name_lower, rhs_expr)));
                    }

                    let assign_op = match op_str.as_str() {
                        "+=" => AssignOp::Add,
                        "-=" => AssignOp::Sub,
                        "*=" => AssignOp::Mul,
                        "/=" => AssignOp::Div,
                        "^=" => AssignOp::Pow,
                        "%=" => AssignOp::Mod,
                        _ => return Ok(None),
                    };

                    return Ok(Some(Statement::OpAssign(name_lower, assign_op, rhs_expr)));
                }
                _ => {}
            }
        }

        // 检查数组赋值: memory[idx] = expr; 或 name[idx] = expr;
        // 或 spl(idx) = expr;
        // 这些需要更复杂的token分析

        // 尝试数组赋值
        if tokens.len() >= 4 {
            if let Token::Ident(name) = &tokens[0] {
                let name_lower = name.to_lowercase();

                // memory[idx] = expr;
                if matches!(tokens[1], Token::LBracket) {
                    if let Some(rbracket_pos) = tokens[2..].iter().position(|t| matches!(t, Token::RBracket)) {
                        let rb_pos = rbracket_pos + 2;
                        if rb_pos + 1 < tokens.len() && matches!(&tokens[rb_pos + 1], Token::Op(s) if s == "=") {
                            let idx_tokens = &tokens[2..rb_pos];
                            let mut idx_pos = 0;
                            let idx_expr = Self::parse_expr_from_tokens(idx_tokens, &mut idx_pos, line_num)?;

                            let val_tokens = &tokens[rb_pos + 2..];
                            let mut val_pos = 0;
                            let val_expr = Self::parse_expr_from_tokens(val_tokens, &mut val_pos, line_num)?;

                            if name_lower == "spl" {
                                return Ok(Some(Statement::SplAssign(idx_expr, val_expr)));
                            }
                            return Ok(Some(Statement::ArrayAssign(name_lower, idx_expr, val_expr)));
                        }
                    }
                }

                // spl(ch) = expr; 形式
                if name_lower == "spl" && matches!(tokens[1], Token::LParen) {
                    if let Some(rparen_pos) = tokens[2..].iter().position(|t| matches!(t, Token::RParen)) {
                        let rp_pos = rparen_pos + 2;
                        if rp_pos + 1 < tokens.len() {
                            if let Token::Op(s) = &tokens[rp_pos + 1] {
                                if s == "=" {
                                    let ch_tokens = &tokens[2..rp_pos];
                                    let mut ch_pos = 0;
                                    let ch_expr = Self::parse_expr_from_tokens(ch_tokens, &mut ch_pos, line_num)?;

                                    let val_tokens = &tokens[rp_pos + 2..];
                                    let mut val_pos = 0;
                                    let val_expr = Self::parse_expr_from_tokens(val_tokens, &mut val_pos, line_num)?;

                                    return Ok(Some(Statement::SplAssign(ch_expr, val_expr)));
                                }
                            }
                        }
                    }
                }
            }
        }

        Ok(None)
    }

    /// 去除行尾注释
    fn strip_comment(line: &str) -> &str {
        // 简化处理：不在字符串内的 // 视为注释
        let mut in_string = false;
        let chars: Vec<char> = line.chars().collect();
        let mut i = 0;
        while i + 1 < chars.len() {
            if chars[i] == '"' && (i == 0 || chars[i-1] != '\\') {
                in_string = !in_string;
            }
            if !in_string && chars[i] == '/' && chars[i + 1] == '/' {
                return &line[..i];
            }
            i += 1;
        }
        line
    }

    /// 找匹配的括号
    fn find_matching_paren(s: &str, start: usize) -> Option<usize> {
        let chars: Vec<char> = s.chars().collect();
        if start >= chars.len() || chars[start] != '(' { return None; }

        let mut depth = 0;
        let mut in_string = false;
        for i in start..chars.len() {
            if chars[i] == '"' && (i == 0 || chars[i-1] != '\\') {
                in_string = !in_string;
            }
            if in_string { continue; }

            match chars[i] {
                '(' => depth += 1,
                ')' => {
                    depth -= 1;
                    if depth == 0 { return Some(i); }
                }
                _ => {}
            }
        }
        None
    }

    /// 解析表达式
    pub fn parse_expression(code: &str, line_num: usize) -> Result<Expr, JsfxError> {
        let tokens = Self::tokenize(code);
        let mut pos = 0;
        Self::parse_expr_from_tokens(&tokens, &mut pos, line_num)
    }

    /// 词法分析：将代码字符串转换为token列表
    fn tokenize(code: &str) -> Vec<Token> {
        let mut tokens = Vec::new();
        let chars: Vec<char> = code.chars().collect();
        let mut i = 0;

        while i < chars.len() {
            let c = chars[i];

            // 跳过空白
            if c.is_whitespace() {
                i += 1;
                continue;
            }

            // 字符串字面量
            if c == '"' {
                let mut s = String::new();
                i += 1;
                while i < chars.len() && chars[i] != '"' {
                    if chars[i] == '\\' && i + 1 < chars.len() {
                        match chars[i + 1] {
                            'n' => s.push('\n'),
                            't' => s.push('\t'),
                            '\\' => s.push('\\'),
                            '"' => s.push('"'),
                            _ => { s.push(chars[i]); s.push(chars[i + 1]); }
                        }
                        i += 2;
                    } else {
                        s.push(chars[i]);
                        i += 1;
                    }
                }
                if i < chars.len() { i += 1; } // 跳过结尾"
                tokens.push(Token::StringLit(s));
                continue;
            }

            // $常量前缀
            if c == '$' {
                i += 1;
                let mut name = String::new();
                while i < chars.len() && (chars[i].is_alphanumeric() || chars[i] == '_') {
                    name.push(chars[i]);
                    i += 1;
                }
                // $pi, $e, $phi 等作为DollarConst解析
                tokens.push(Token::Dollar);
                tokens.push(Token::Ident(name));
                continue;
            }

            // 数字字面量
            if c.is_ascii_digit() || (c == '.' && i + 1 < chars.len() && chars[i + 1].is_ascii_digit()) {
                let mut num = String::new();
                let mut has_dot = false;
                let mut has_e = false;

                while i < chars.len() {
                    if chars[i].is_ascii_digit() {
                        num.push(chars[i]);
                        i += 1;
                    } else if chars[i] == '.' && !has_dot && !has_e {
                        num.push('.');
                        has_dot = true;
                        i += 1;
                    } else if (chars[i] == 'e' || chars[i] == 'E') && !has_e {
                        num.push(chars[i]);
                        has_e = true;
                        i += 1;
                        if i < chars.len() && (chars[i] == '+' || chars[i] == '-') {
                            num.push(chars[i]);
                            i += 1;
                        }
                    } else if chars[i] == 'x' && num == "0" {
                        // 十六进制 0x...
                        num.push(chars[i]);
                        i += 1;
                        while i < chars.len() && chars[i].is_ascii_hexdigit() {
                            num.push(chars[i]);
                            i += 1;
                        }
                        break;
                    } else {
                        break;
                    }
                }

                let value = if num.starts_with("0x") || num.starts_with("0X") {
                    u64::from_str_radix(&num[2..], 16).unwrap_or(0) as f64
                } else {
                    num.parse().unwrap_or(0.0)
                };
                tokens.push(Token::Number(value));
                continue;
            }

            // 标识符
            if c.is_alphabetic() || c == '_' {
                let mut name = String::new();
                while i < chars.len() && (chars[i].is_alphanumeric() || chars[i] == '_') {
                    name.push(chars[i]);
                    i += 1;
                }
                tokens.push(Token::Ident(name.to_lowercase()));
                continue;
            }

            // 单字符token
            match c {
                '(' => { tokens.push(Token::LParen); i += 1; continue; }
                ')' => { tokens.push(Token::RParen); i += 1; continue; }
                '[' => { tokens.push(Token::LBracket); i += 1; continue; }
                ']' => { tokens.push(Token::RBracket); i += 1; continue; }
                ',' => { tokens.push(Token::Comma); i += 1; continue; }
                '?' => { tokens.push(Token::Question); i += 1; continue; }
                ':' => { tokens.push(Token::Colon); i += 1; continue; }
                _ => {}
            }

            // 多字符运算符
            if i + 1 < chars.len() {
                let two = &code[i..i + 2];
                match two {
                    "==" | "!=" | "<=" | ">=" | "&&" | "||" | "+=" | "-=" | "*=" | "/=" | "^=" | "%=" => {
                        tokens.push(Token::Op(two.to_string()));
                        i += 2;
                        continue;
                    }
                    _ => {}
                }
            }

            // 单字符运算符
            match c {
                '+' | '-' | '*' | '/' | '%' | '^' | '<' | '>' | '!' | '=' | '&' | '|' | '~' => {
                    tokens.push(Token::Op(c.to_string()));
                    i += 1;
                    continue;
                }
                _ => {
                    // 跳过未知字符
                    i += 1;
                }
            }
        }

        tokens
    }

    /// 从token列表解析表达式
    fn parse_expr_from_tokens(tokens: &[Token], pos: &mut usize, line_num: usize) -> Result<Expr, JsfxError> {
        Self::parse_ternary_tokens(tokens, pos, line_num)
    }

    /// 解析三目运算
    fn parse_ternary_tokens(tokens: &[Token], pos: &mut usize, line_num: usize) -> Result<Expr, JsfxError> {
        let cond = Self::parse_or_tokens(tokens, pos, line_num)?;

        if *pos < tokens.len() && matches!(tokens[*pos], Token::Question) {
            *pos += 1;
            let true_expr = Self::parse_ternary_tokens(tokens, pos, line_num)?;

            if *pos < tokens.len() && matches!(tokens[*pos], Token::Colon) {
                *pos += 1;
            }

            let false_expr = Self::parse_ternary_tokens(tokens, pos, line_num)?;
            Ok(Expr::Ternary(Box::new(cond), Box::new(true_expr), Box::new(false_expr)))
        } else {
            Ok(cond)
        }
    }

    /// 解析 ||
    fn parse_or_tokens(tokens: &[Token], pos: &mut usize, line_num: usize) -> Result<Expr, JsfxError> {
        let mut left = Self::parse_and_tokens(tokens, pos, line_num)?;

        while *pos < tokens.len() && matches!(tokens[*pos], Token::Op(ref s) if s == "||") {
            *pos += 1;
            let right = Self::parse_and_tokens(tokens, pos, line_num)?;
            left = Expr::BinaryOp(BinOp::Or, Box::new(left), Box::new(right));
        }

        Ok(left)
    }

    /// 解析 &&
    fn parse_and_tokens(tokens: &[Token], pos: &mut usize, line_num: usize) -> Result<Expr, JsfxError> {
        let mut left = Self::parse_bitwise_or_tokens(tokens, pos, line_num)?;

        while *pos < tokens.len() && matches!(tokens[*pos], Token::Op(ref s) if s == "&&") {
            *pos += 1;
            let right = Self::parse_bitwise_or_tokens(tokens, pos, line_num)?;
            left = Expr::BinaryOp(BinOp::And, Box::new(left), Box::new(right));
        }

        Ok(left)
    }

    /// 解析 | (按位或)
    fn parse_bitwise_or_tokens(tokens: &[Token], pos: &mut usize, line_num: usize) -> Result<Expr, JsfxError> {
        let mut left = Self::parse_bitwise_and_tokens(tokens, pos, line_num)?;

        while *pos < tokens.len() && matches!(tokens[*pos], Token::Op(ref s) if s == "|") {
            *pos += 1;
            let right = Self::parse_bitwise_and_tokens(tokens, pos, line_num)?;
            left = Expr::BinaryOp(BinOp::BitOr, Box::new(left), Box::new(right));
        }

        Ok(left)
    }

    /// 解析 & (按位与)
    fn parse_bitwise_and_tokens(tokens: &[Token], pos: &mut usize, line_num: usize) -> Result<Expr, JsfxError> {
        let mut left = Self::parse_comparison_tokens(tokens, pos, line_num)?;

        while *pos < tokens.len() && matches!(tokens[*pos], Token::Op(ref s) if s == "&") {
            *pos += 1;
            let right = Self::parse_comparison_tokens(tokens, pos, line_num)?;
            left = Expr::BinaryOp(BinOp::BitAnd, Box::new(left), Box::new(right));
        }

        Ok(left)
    }

    /// 解析比较运算
    fn parse_comparison_tokens(tokens: &[Token], pos: &mut usize, line_num: usize) -> Result<Expr, JsfxError> {
        let mut left = Self::parse_addition_tokens(tokens, pos, line_num)?;

        while *pos < tokens.len() {
            let op = match &tokens[*pos] {
                Token::Op(s) => match s.as_str() {
                    "==" => Some(BinOp::Eq),
                    "!=" => Some(BinOp::Ne),
                    "<=" => Some(BinOp::Le),
                    ">=" => Some(BinOp::Ge),
                    "<" => Some(BinOp::Lt),
                    ">" => Some(BinOp::Gt),
                    _ => None,
                },
                _ => None,
            };

            if let Some(op) = op {
                *pos += 1;
                let right = Self::parse_addition_tokens(tokens, pos, line_num)?;
                left = Expr::BinaryOp(op, Box::new(left), Box::new(right));
            } else {
                break;
            }
        }

        Ok(left)
    }

    /// 解析加减
    fn parse_addition_tokens(tokens: &[Token], pos: &mut usize, line_num: usize) -> Result<Expr, JsfxError> {
        let mut left = Self::parse_multiplication_tokens(tokens, pos, line_num)?;

        while *pos < tokens.len() {
            let op = match &tokens[*pos] {
                Token::Op(s) => match s.as_str() {
                    "+" => Some(BinOp::Add),
                    "-" => Some(BinOp::Sub),
                    _ => None,
                },
                _ => None,
            };

            if let Some(op) = op {
                *pos += 1;
                let right = Self::parse_multiplication_tokens(tokens, pos, line_num)?;
                left = Expr::BinaryOp(op, Box::new(left), Box::new(right));
            } else {
                break;
            }
        }

        Ok(left)
    }

    /// 解析乘除取模
    fn parse_multiplication_tokens(tokens: &[Token], pos: &mut usize, line_num: usize) -> Result<Expr, JsfxError> {
        let mut left = Self::parse_power_tokens(tokens, pos, line_num)?;

        while *pos < tokens.len() {
            let op = match &tokens[*pos] {
                Token::Op(s) => match s.as_str() {
                    "*" => Some(BinOp::Mul),
                    "/" => Some(BinOp::Div),
                    "%" => Some(BinOp::Mod),
                    _ => None,
                },
                _ => None,
            };

            if let Some(op) = op {
                *pos += 1;
                let right = Self::parse_power_tokens(tokens, pos, line_num)?;
                left = Expr::BinaryOp(op, Box::new(left), Box::new(right));
            } else {
                break;
            }
        }

        Ok(left)
    }

    /// 解析幂运算
    fn parse_power_tokens(tokens: &[Token], pos: &mut usize, line_num: usize) -> Result<Expr, JsfxError> {
        let left = Self::parse_unary_tokens(tokens, pos, line_num)?;

        if *pos < tokens.len() && matches!(tokens[*pos], Token::Op(ref s) if s == "^") {
            *pos += 1;
            let right = Self::parse_power_tokens(tokens, pos, line_num)?; // 右结合
            Ok(Expr::BinaryOp(BinOp::Pow, Box::new(left), Box::new(right)))
        } else {
            Ok(left)
        }
    }

    /// 解析一元运算
    fn parse_unary_tokens(tokens: &[Token], pos: &mut usize, line_num: usize) -> Result<Expr, JsfxError> {
        if *pos < tokens.len() {
            match &tokens[*pos] {
                Token::Op(s) if s == "-" => {
                    *pos += 1;
                    let operand = Self::parse_unary_tokens(tokens, pos, line_num)?;
                    return Ok(Expr::UnaryOp(UnaryOp::Neg, Box::new(operand)));
                }
                Token::Op(s) if s == "!" => {
                    *pos += 1;
                    let operand = Self::parse_unary_tokens(tokens, pos, line_num)?;
                    return Ok(Expr::UnaryOp(UnaryOp::Not, Box::new(operand)));
                }
                Token::Op(s) if s == "~" => {
                    *pos += 1;
                    let operand = Self::parse_unary_tokens(tokens, pos, line_num)?;
                    return Ok(Expr::UnaryOp(UnaryOp::BitNot, Box::new(operand)));
                }
                _ => {}
            }
        }

        Self::parse_primary_tokens(tokens, pos, line_num)
    }

    /// 解析基本表达式
    fn parse_primary_tokens(tokens: &[Token], pos: &mut usize, line_num: usize) -> Result<Expr, JsfxError> {
        if *pos >= tokens.len() {
            return Ok(Expr::Number(0.0));
        }

        match &tokens[*pos] {
            Token::Number(n) => {
                let val = *n;
                *pos += 1;
                Ok(Expr::Number(val))
            }

            Token::StringLit(s) => {
                let val = s.clone();
                *pos += 1;
                Ok(Expr::StringLit(val))
            }

            Token::Dollar => {
                *pos += 1; // 跳过 $
                if *pos < tokens.len() {
                    if let Token::Ident(name) = &tokens[*pos] {
                        let name = name.clone();
                        *pos += 1;
                        return Ok(Expr::DollarConst(name));
                    }
                }
                Ok(Expr::Number(0.0))
            }

            Token::Ident(name) => {
                let name = name.clone();
                *pos += 1;

                // 检查是否为函数调用: name(
                if *pos < tokens.len() && matches!(tokens[*pos], Token::LParen) {
                    *pos += 1; // 跳过 (
                    let mut args = Vec::new();

                    // 解析参数列表
                    if *pos < tokens.len() && !matches!(tokens[*pos], Token::RParen) {
                        args.push(Self::parse_expr_from_tokens(tokens, pos, line_num)?);
                        while *pos < tokens.len() && matches!(tokens[*pos], Token::Comma) {
                            *pos += 1; // 跳过 ,
                            args.push(Self::parse_expr_from_tokens(tokens, pos, line_num)?);
                        }
                    }

                    if *pos < tokens.len() && matches!(tokens[*pos], Token::RParen) {
                        *pos += 1; // 跳过 )
                    }

                    // 特殊处理：spl(ch)
                    if name == "spl" {
                        if let Some(Expr::Number(ch)) = args.first() {
                            let ch = *ch as usize;
                            return Ok(Expr::SplAccess(Box::new(Expr::Number(ch as f64))));
                        }
                        return Ok(Expr::SplAccess(Box::new(args.into_iter().next().unwrap_or(Expr::Number(0.0)))));
                    }

                    Ok(Expr::FunctionCall(name, args))
                }
                // 检查是否为数组访问: name[
                else if *pos < tokens.len() && matches!(tokens[*pos], Token::LBracket) {
                    *pos += 1; // 跳过 [
                    let idx = Self::parse_expr_from_tokens(tokens, pos, line_num)?;

                    if *pos < tokens.len() && matches!(tokens[*pos], Token::RBracket) {
                        *pos += 1; // 跳过 ]
                    }

                    Ok(Expr::ArrayAccess(name, Box::new(idx)))
                }
                else {
                    Ok(Expr::Variable(name))
                }
            }

            Token::LParen => {
                *pos += 1; // 跳过 (
                let expr = Self::parse_expr_from_tokens(tokens, pos, line_num)?;
                if *pos < tokens.len() && matches!(tokens[*pos], Token::RParen) {
                    *pos += 1; // 跳过 )
                }
                Ok(expr)
            }

            _ => {
                let desc = format!("{:?}", tokens[*pos]);
                Err(JsfxError::parse(line_num, format!("无法解析表达式token: {}", desc)))
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_parse_gain() {
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
        assert_eq!(program.desc, "Simple Gain");
        assert_eq!(program.sliders.len(), 1);
        assert!(program.slider_block.is_some());
        assert!(program.sample_block.is_some());
    }

    #[test]
    fn test_parse_slider() {
        let slider = JsfxParser::parse_slider_line("1:5<0,10,1>slider name", 1).unwrap().unwrap();
        assert_eq!(slider.index, 1);
        assert_eq!(slider.default, 5.0);
        assert_eq!(slider.name, Some("slider name".to_string()));
    }

    #[test]
    fn test_parse_expression() {
        let expr = JsfxParser::parse_expression("2^(slider1/6)", 1).unwrap();
        match expr {
            Expr::BinaryOp(BinOp::Pow, _, _) => {},
            _ => panic!("期望幂运算"),
        }
    }

    #[test]
    fn test_parse_ternary() {
        let expr = JsfxParser::parse_expression("x > 0 ? x : -x", 1).unwrap();
        match expr {
            Expr::Ternary(_, _, _) => {},
            _ => panic!("期望三目运算"),
        }
    }

    #[test]
    fn test_parse_dollar_const() {
        let expr = JsfxParser::parse_expression("$pi", 1).unwrap();
        match expr {
            Expr::DollarConst(name) => assert_eq!(name, "pi"),
            _ => panic!("期望$常量"),
        }
    }

    #[test]
    fn test_parse_string_literal() {
        let expr = JsfxParser::parse_expression("\"hello\"", 1).unwrap();
        match expr {
            Expr::StringLit(s) => assert_eq!(s, "hello"),
            _ => panic!("期望字符串字面量"),
        }
    }

    #[test]
    fn test_parse_preprocessor() {
        let source = r#"
#define GAIN_FACTOR 2.0
desc:Preprocessor Test

@sample
spl0 = spl0 * GAIN_FACTOR;
"#;
        let program = JsfxParser::parse(source).unwrap();
        assert_eq!(program.desc, "Preprocessor Test");
        // GAIN_FACTOR 应该被替换为 2.0
        assert!(program.sample_block.is_some());
    }

    #[test]
    fn test_parse_sections() {
        let source = r#"
desc:All Sections
slider1:0<-12,12,0.1>Gain

@init
x = 0;

@slider
gain = 2^(slider1/6);

@block
blockcount = 0;

@sample
spl0 *= gain;
spl1 *= gain;

@gfx
gfx_clear(0);
"#;
        let program = JsfxParser::parse(source).unwrap();
        assert!(program.init_block.is_some());
        assert!(program.slider_block.is_some());
        assert!(program.block_block.is_some());
        assert!(program.sample_block.is_some());
        assert!(program.gfx_block.is_some());
    }

    #[test]
    fn test_parse_hex_literal() {
        let expr = JsfxParser::parse_expression("0xFF", 1).unwrap();
        match expr {
            Expr::Number(n) => assert_eq!(n, 255.0),
            _ => panic!("期望数字"),
        }
    }

    #[test]
    fn test_parse_compound_assign() {
        let source = r#"
desc:Compound Test

@sample
x = 10;
x += 5;
x *= 2;
spl0 = x;
"#;
        let program = JsfxParser::parse(source).unwrap();
        assert!(program.sample_block.is_some());
        let block = program.sample_block.unwrap();
        assert!(block.len() >= 4);
    }

    #[test]
    fn test_parse_memory_bracket_access() {
        let source = r#"
desc:Memory Bracket Test

@init
memory[0] = 1.0;
memory[1] = 2.0;

@sample
spl0 = memory[0];
"#;
        let program = JsfxParser::parse(source).unwrap();
        assert!(program.init_block.is_some());
        assert!(program.sample_block.is_some());
    }
}
