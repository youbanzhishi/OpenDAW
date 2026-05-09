//! JSFX文本解析器
//!
//! 将JSFX源码解析为AST。支持EEL2核心语法子集。
//! EEL2特点：大小写不敏感、变量无需声明、分号结尾、三目运算符

use crate::ast::*;
use crate::error::JsfxError;

/// JSFX解析器
pub struct JsfxParser;


/// 简化的token类型
#[derive(Debug, Clone, PartialEq)]
enum Token {
    Number(f64),
    Ident(String),
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
        let mut program = JsfxProgram::default();
        let mut current_section: Option<String> = None;
        let mut current_lines: Vec<String> = Vec::new();

        let lines: Vec<&str> = source.lines().collect();
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
            if line.to_lowercase().starts_with("function ") {
                // 解析函数定义
                let (func_name, func_params) = Self::parse_function_header(line, i + 1)?;
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

            let (stmt, advance) = Self::parse_one_statement(lines, i)?;
            statements.push(stmt);
            i += advance;
        }

        Ok(statements)
    }

    /// 解析一条语句
    fn parse_one_statement(lines: &[String], offset: usize) -> Result<(Statement, usize), JsfxError> {
        let line = lines[offset].trim();
        let code = Self::strip_comment(line);

        if code.is_empty() {
            return Ok((Statement::ExprStatement(Expr::Number(0.0)), 1));
        }

        let code_lower = code.to_lowercase();

        if code_lower.starts_with("if ") || code_lower.starts_with("if(") {
            return Self::parse_if_statement(lines, offset);
        }

        if code_lower.starts_with("while ") || code_lower.starts_with("while(") {
            return Self::parse_while_statement(lines, offset);
        }

        if code_lower.starts_with("loop(") || code_lower.starts_with("loop ") {
            return Self::parse_loop_statement(lines, offset);
        }

        let stmt = Self::parse_simple_statement(&code, offset + 1)?;
        Ok((stmt, 1))
    }

    /// 去掉行尾注释
    fn strip_comment(line: &str) -> String {
        let chars: Vec<char> = line.chars().collect();
        let mut result = String::new();
        let mut i = 0;
        while i < chars.len() {
            if i + 1 < chars.len() && chars[i] == '/' && chars[i + 1] == '/' {
                break;
            }
            result.push(chars[i]);
            i += 1;
        }
        result.trim().to_string()
    }

    /// 解析if语句
    fn parse_if_statement(lines: &[String], offset: usize) -> Result<(Statement, usize), JsfxError> {
        let line = Self::strip_comment(lines[offset].trim());
        let line_lower = line.to_lowercase();

        let cond_start = if line_lower.starts_with("if(") { 2 } else { 3 };
        let (condition, body_start) = Self::extract_paren_or_expr(&line[cond_start..]);

        let cond_expr = Self::parse_expression(&condition, offset + 1)?;

        let mut then_lines = Vec::new();
        let mut else_lines = Vec::new();
        let mut in_else = false;
        let mut lines_consumed = 1;

        if !body_start.is_empty() {
            if body_start.trim().to_lowercase().starts_with("else") {
                let else_code = body_start.trim()[4..].trim();
                if !else_code.is_empty() {
                    else_lines.push(else_code.to_string());
                }
                in_else = true;
            } else {
                then_lines.push(body_start.to_string());
            }
        }

        let mut i = offset + 1;
        while i < lines.len() {
            let l = Self::strip_comment(lines[i].trim());
            if l.is_empty() {
                i += 1;
                lines_consumed += 1;
                continue;
            }

            let l_lower = l.to_lowercase();
            if l_lower == "else" || l_lower.starts_with("else ") || l_lower.starts_with("else(") {
                in_else = true;
                let else_rest = l[4..].trim();
                if !else_rest.is_empty() {
                    else_lines.push(else_rest.to_string());
                }
                i += 1;
                lines_consumed += 1;
                continue;
            }

            if l.starts_with('@') || l.to_lowercase().starts_with("function ") {
                break;
            }

            if in_else {
                else_lines.push(l.to_string());
                i += 1;
                lines_consumed += 1;
                break;
            } else {
                then_lines.push(l.to_string());
                i += 1;
                lines_consumed += 1;
                if i < lines.len() {
                    let next = Self::strip_comment(lines[i].trim());
                    if !next.to_lowercase().starts_with("else") {
                        break;
                    }
                } else {
                    break;
                }
            }
        }

        let then_block = Self::parse_statement_block(&then_lines)?;
        let else_block = if else_lines.is_empty() {
            None
        } else {
            Some(Self::parse_statement_block(&else_lines)?)
        };

        Ok((Statement::If(cond_expr, then_block, else_block), lines_consumed))
    }

    /// 解析while语句
    fn parse_while_statement(lines: &[String], offset: usize) -> Result<(Statement, usize), JsfxError> {
        let line = Self::strip_comment(lines[offset].trim());
        let line_lower = line.to_lowercase();

        let cond_start = if line_lower.starts_with("while(") { 5 } else { 6 };
        let (condition, body_start) = Self::extract_paren_or_expr(&line[cond_start..]);

        let cond_expr = Self::parse_expression(&condition, offset + 1)?;

        let mut body_lines = Vec::new();
        if !body_start.is_empty() {
            // 单行情况: while(cond, body_statement)
            body_lines.push(body_start.to_string());
        }

        if body_lines.is_empty() && offset + 1 < lines.len() {
            let next = Self::strip_comment(lines[offset + 1].trim());
            if !next.is_empty() && !next.starts_with('@') {
                body_lines.push(next.to_string());
            }
        }
        
        let body = Self::parse_statement_block(&body_lines)?;
        Ok((Statement::While(cond_expr, body), 1 + if body_start.is_empty() && !body_lines.is_empty() { 1 } else { 0 }))
    }

    /// 解析loop语句
    fn parse_loop_statement(lines: &[String], offset: usize) -> Result<(Statement, usize), JsfxError> {
        let line = Self::strip_comment(lines[offset].trim());

        // 找第一个 (
        let paren_start = line.find('(').ok_or_else(|| JsfxError::parse(offset + 1, "loop缺少("))?;
        
        // 找对应的 )
        let paren_end = Self::find_matching_paren(&line, paren_start).ok_or_else(|| JsfxError::parse(offset + 1, "loop缺少)"))?;

        let inner = &line[paren_start + 1..paren_end];
        
        // 在 inner 中找逗号来分隔 count 和 body
        let comma_pos = inner.find(',').ok_or_else(|| JsfxError::parse(offset + 1, "loop缺少逗号分隔count和body"))?;
        
        let count_expr_str = inner[..comma_pos].trim();
        let after_paren = inner[comma_pos + 1..].trim();
        
        let count_expr = Self::parse_expression(count_expr_str, offset + 1)?;
        
        let mut body_lines = Vec::new();
        
        if !after_paren.is_empty() {
            // 单行情况: loop(5, sum += 1;)
            body_lines.push(after_paren.to_string());
        }
        
        // 检查下一行（可能是多行 loop）
        if offset + 1 < lines.len() {
            let next = Self::strip_comment(lines[offset + 1].trim());
            if !next.is_empty() && !next.starts_with('@') && body_lines.is_empty() {
                body_lines.push(next.to_string());
            }
        }
        
        let body = Self::parse_statement_block(&body_lines)?;
        Ok((Statement::Loop(count_expr, body), 1 + if after_paren.is_empty() && !body_lines.is_empty() { 1 } else { 0 }))
    }
    /// 解析loop语句
    fn extract_paren_or_expr(s: &str) -> (String, String) {
        let s = s.trim();
        if s.starts_with('(') {
            if let Some(end) = Self::find_matching_paren(s, 0) {
                let inner = s[1..end].to_string();
                let rest = s[end + 1..].trim().to_string();
                return (inner, rest);
            }
        }
        (s.to_string(), String::new())
    }

    /// 找到匹配的右括号
    fn find_matching_paren(s: &str, start: usize) -> Option<usize> {
        let chars: Vec<char> = s.chars().collect();
        if chars.get(start) != Some(&'(') { return None; }
        let mut depth = 0;
        for i in start..chars.len() {
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

    /// 解析简单语句
    fn parse_simple_statement(code: &str, line_num: usize) -> Result<Statement, JsfxError> {
        let code = code.trim();
        if code.is_empty() {
            return Ok(Statement::ExprStatement(Expr::Number(0.0)));
        }

        // 去掉尾部分号
        let code = code.trim_end_matches(';').trim();

        // 检测spl(ch) = ...
        let code_lower = code.to_lowercase();
        if code_lower.starts_with("spl(") {
            if let Some(eq_pos) = Self::find_assignment_eq(code) {
                let spl_expr_str = &code[..eq_pos].trim();
                let val_str = &code[eq_pos + 1..].trim();
                let spl_ch = Self::parse_expression(&spl_expr_str[3..], line_num)?;
                let val = Self::parse_expression(val_str, line_num)?;
                return Ok(Statement::SplAssign(spl_ch, val));
            }
        }

        // 检测arr[idx] = ... 或 arr[idx] += ...
        if let Some(bracket_pos) = code.find('[') {
            if let Some(eq_pos) = code[bracket_pos..].find('=') {
                let real_eq = bracket_pos + eq_pos;
                if !code[real_eq..].starts_with("==") {
                    let arr_name = code[..bracket_pos].trim().to_lowercase();
                    let close_bracket = Self::find_matching_bracket(code, bracket_pos)
                        .ok_or_else(|| JsfxError::parse(line_num, "缺少 ]"))?;
                    let idx_expr = Self::parse_expression(&code[bracket_pos + 1..close_bracket], line_num)?;
                    let val_str = &code[real_eq + 1..].trim();
                    let val = Self::parse_expression(val_str, line_num)?;
                    return Ok(Statement::ArrayAssign(arr_name, idx_expr, val));
                }
            }
        }

        // 检测复合赋值
        for (op_str, op) in [("+=", AssignOp::Add), ("-=", AssignOp::Sub), ("*=", AssignOp::Mul), ("/=", AssignOp::Div)] {
            if let Some(pos) = code.find(op_str) {
                let var_name = code[..pos].trim().to_lowercase();
                if Self::is_valid_var_name(&var_name) {
                    let val_str = &code[pos + op_str.len()..].trim();
                    let val = Self::parse_expression(val_str, line_num)?;
                    return Ok(Statement::OpAssign(var_name, op, val));
                }
            }
        }

        // 检测简单赋值
        if let Some(eq_pos) = Self::find_assignment_eq(code) {
            let var_name = code[..eq_pos].trim().to_lowercase();
            if Self::is_valid_var_name(&var_name) {
                let val_str = &code[eq_pos + 1..].trim();
                let val = Self::parse_expression(val_str, line_num)?;
                return Ok(Statement::Assign(var_name, val));
            }
        }

        // 表达式语句
        let expr = Self::parse_expression(code, line_num)?;
        Ok(Statement::ExprStatement(expr))
    }

    /// 找到赋值等号的位置（排除==、!=、<=、>=中的等号）
    fn find_assignment_eq(code: &str) -> Option<usize> {
        let chars: Vec<char> = code.chars().collect();
        let mut i = 0;
        while i < chars.len() {
            if chars[i] == '=' {
                // 跳过 == 
                if i + 1 < chars.len() && chars[i + 1] == '=' {
                    i += 2;
                    continue;
                }
                // 跳过 !=, <=, >= 中的 =
                if i > 0 && (chars[i - 1] == '!' || chars[i - 1] == '<' || chars[i - 1] == '>') {
                    i += 1;
                    continue;
                }
                return Some(i);
            }
            i += 1;
        }
        None
    }

    /// 是否有效变量名
    fn is_valid_var_name(name: &str) -> bool {
        if name.is_empty() { return false; }
        let chars: Vec<char> = name.chars().collect();
        if !chars[0].is_alphabetic() && chars[0] != '_' && chars[0] != '$' {
            return false;
        }
        for &c in &chars[1..] {
            if !c.is_alphanumeric() && c != '_' && c != '$' && c != '.' {
                return false;
            }
        }
        true
    }

    /// 找匹配右方括号
    fn find_matching_bracket(s: &str, start: usize) -> Option<usize> {
        let chars: Vec<char> = s.chars().collect();
        if chars.get(start) != Some(&'[') { return None; }
        let mut depth = 0;
        for i in start..chars.len() {
            match chars[i] {
                '[' => depth += 1,
                ']' => {
                    depth -= 1;
                    if depth == 0 { return Some(i); }
                }
                _ => {}
            }
        }
        None
    }

    // ========== 表达式解析（基于token化，更健壮） ==========

    /// 解析表达式
    fn parse_expression(code: &str, line_num: usize) -> Result<Expr, JsfxError> {
        let code = code.trim();
        if code.is_empty() {
            return Ok(Expr::Number(0.0));
        }

        // 使用简化的递归下降解析器
        let tokens = Self::tokenize(code);
        let mut pos = 0;
        let expr = Self::parse_expr_from_tokens(&tokens, &mut pos, line_num)?;

        // 确保所有token都被消费（除非是多余的分隔符）
        Ok(expr)
    }


    /// 将代码字符串token化
    fn tokenize(code: &str) -> Vec<Token> {
        let chars: Vec<char> = code.chars().collect();
        let mut tokens = Vec::new();
        let mut i = 0;

        while i < chars.len() {
            let c = chars[i];

            // 跳过空白
            if c.is_whitespace() {
                i += 1;
                continue;
            }

            // 数字
            if c.is_ascii_digit() || (c == '.' && i + 1 < chars.len() && chars[i + 1].is_ascii_digit()) {
                let start = i;
                let mut has_dot = false;
                while i < chars.len() && (chars[i].is_ascii_digit() || (chars[i] == '.' && !has_dot)) {
                    if chars[i] == '.' { has_dot = true; }
                    i += 1;
                }
                // 检查十六进制
                if chars[start] == '0' && i > start + 1 && (chars[start + 1] == 'x' || chars[start + 1] == 'X') {
                    while i < chars.len() && (chars[i].is_ascii_hexdigit()) { i += 1; }
                    let hex_str = &code[start + 2..i];
                    if let Ok(val) = i64::from_str_radix(hex_str, 16) {
                        tokens.push(Token::Number(val as f64));
                    }
                } else {
                    let num_str = &code[start..i];
                    if let Ok(val) = num_str.parse::<f64>() {
                        tokens.push(Token::Number(val));
                    }
                }
                continue;
            }

            // 标识符（变量名）
            if c.is_alphabetic() || c == '_' {
                let start = i;
                while i < chars.len() && (chars[i].is_alphanumeric() || chars[i] == '_') {
                    i += 1;
                }
                // 允许点号后继续（如 _lp0）
                let ident = &code[start..i];
                tokens.push(Token::Ident(ident.to_lowercase()));
                continue;
            }

            // $ 开头的标识符（如 $pi, $e）
            if c == '$' {
                i += 1;
                let start = i;
                while i < chars.len() && (chars[i].is_alphanumeric() || chars[i] == '_') {
                    i += 1;
                }
                let ident = &code[start..i];
                let full_name = format!("${}", ident.to_lowercase());
                // 转换为常量
                match full_name.as_str() {
                    "$pi" => tokens.push(Token::Number(std::f64::consts::PI)),
                    "$e" => tokens.push(Token::Number(std::f64::consts::E)),
                    "$phi" => tokens.push(Token::Number(1.618033988749895)),
                    _ => tokens.push(Token::Ident(full_name)),
                }
                continue;
            }

            // 运算符
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
                    "==" | "!=" | "<=" | ">=" | "&&" | "||" | "+=" | "-=" | "*=" | "/=" => {
                        tokens.push(Token::Op(two.to_string()));
                        i += 2;
                        continue;
                    }
                    _ => {}
                }
            }

            // 单字符运算符
            match c {
                '+' | '-' | '*' | '/' | '%' | '^' | '<' | '>' | '!' => {
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
        let mut left = Self::parse_comparison_tokens(tokens, pos, line_num)?;

        while *pos < tokens.len() && matches!(tokens[*pos], Token::Op(ref s) if s == "&&") {
            *pos += 1;
            let right = Self::parse_comparison_tokens(tokens, pos, line_num)?;
            left = Expr::BinaryOp(BinOp::And, Box::new(left), Box::new(right));
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
    fn test_parse_addition() {
        let expr = JsfxParser::parse_expression("x + y", 1).unwrap();
        match expr {
            Expr::BinaryOp(BinOp::Add, _, _) => {},
            _ => panic!("期望加法"),
        }
    }

    #[test]
    fn test_parse_multiplication_chain() {
        let expr = JsfxParser::parse_expression("2 * $pi * freq / srate", 1).unwrap();
        match expr {
            Expr::BinaryOp(BinOp::Div, _, _) => {}, // 顶层是 /
            _ => panic!("期望除法"),
        }
    }
}
