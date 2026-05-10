//! 输出格式化

use colored::Colorize;
use serde::Serialize;

/// 输出格式
#[derive(Clone, Debug, PartialEq)]
pub enum OutputFormat {
    Json,
    Yaml,
    Table,
}

impl OutputFormat {
    pub fn from_str(s: &str) -> Self {
        match s.to_lowercase().as_str() {
            "json" => OutputFormat::Json,
            "yaml" => OutputFormat::Yaml,
            _ => OutputFormat::Table,
        }
    }

    /// 格式化输出
    pub fn format<T: Serialize + std::fmt::Debug>(&self, data: &T) -> String {
        match self {
            OutputFormat::Json => serde_json::to_string_pretty(data).unwrap_or_else(|e| format!("JSON error: {}", e)),
            OutputFormat::Yaml => serde_yaml::to_string(data).unwrap_or_else(|e| format!("YAML error: {}", e)),
            OutputFormat::Table => format!("{:#?}", data),
        }
    }

    /// 打印输出
    pub fn print<T: Serialize + std::fmt::Debug>(&self, data: &T) {
        println!("{}", self.format(data));
    }

    /// 打印成功消息
    pub fn print_success(&self, msg: &str) {
        match self {
            OutputFormat::Json => {
                println!(r#"{{"success": true, "message": "{}"}}"#, msg);
            }
            OutputFormat::Yaml => {
                println!("success: true\nmessage: \"{}\"", msg);
            }
            OutputFormat::Table => {
                println!("{} {}", "✓".green(), msg);
            }
        }
    }

    /// 打印错误消息
    pub fn print_error(&self, msg: &str) {
        match self {
            OutputFormat::Json => {
                println!(r#"{{"success": false, "error": "{}"}}"#, msg);
            }
            OutputFormat::Yaml => {
                println!("success: false\nerror: \"{}\"", msg);
            }
            OutputFormat::Table => {
                println!("{} {}", "✗".red(), msg);
            }
        }
    }
}

/// 简单进度条
pub struct ProgressBar {
    total: usize,
    current: usize,
    width: usize,
}

impl ProgressBar {
    pub fn new(total: usize) -> Self {
        Self {
            total,
            current: 0,
            width: 40,
        }
    }

    pub fn inc(&mut self) {
        self.current += 1;
        self.render();
    }

    pub fn set(&mut self, current: usize) {
        self.current = current;
        self.render();
    }

    fn render(&self) {
        if self.total == 0 {
            return;
        }
        let ratio = self.current as f64 / self.total as f64;
        let filled = (ratio * self.width as f64) as usize;
        let bar: String = "█".repeat(filled) + &"░".repeat(self.width - filled);
        let percent = (ratio * 100.0) as usize;
        eprint!("\r[{}] {}% ({}/{})", bar, percent, self.current, self.total);
        if self.current >= self.total {
            eprintln!();
        }
    }

    pub fn finish(&mut self) {
        self.current = self.total;
        self.render();
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_output_format_from_str() {
        assert_eq!(OutputFormat::from_str("json"), OutputFormat::Json);
        assert_eq!(OutputFormat::from_str("yaml"), OutputFormat::Yaml);
        assert_eq!(OutputFormat::from_str("table"), OutputFormat::Table);
        assert_eq!(OutputFormat::from_str("TABLE"), OutputFormat::Table);
    }

    #[test]
    fn test_format_json() {
        let fmt = OutputFormat::Json;
        let data = vec!["hello", "world"];
        let output = fmt.format(&data);
        assert!(output.contains("hello"));
    }

    #[test]
    fn test_format_yaml() {
        let fmt = OutputFormat::Yaml;
        let data = vec!["hello", "world"];
        let output = fmt.format(&data);
        assert!(output.contains("hello"));
    }

    #[test]
    fn test_format_table() {
        let fmt = OutputFormat::Table;
        let data = vec!["hello"];
        let output = fmt.format(&data);
        assert!(output.contains("hello"));
    }

    #[test]
    fn test_progress_bar_new() {
        let pb = ProgressBar::new(100);
        assert_eq!(pb.total, 100);
        assert_eq!(pb.current, 0);
    }

    #[test]
    fn test_progress_bar_inc() {
        let mut pb = ProgressBar::new(10);
        pb.inc();
        assert_eq!(pb.current, 1);
    }

    #[test]
    fn test_progress_bar_finish() {
        let mut pb = ProgressBar::new(10);
        pb.finish();
        assert_eq!(pb.current, 10);
    }
}
