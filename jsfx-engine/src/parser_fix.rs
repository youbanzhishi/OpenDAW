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
