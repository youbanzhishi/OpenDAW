//! 交互式REPL模式

use std::io::{self, Write};

/// REPL命令
#[derive(Debug)]
pub enum ReplCommand {
    Help,
    Quit,
    Status,
    Unknown(String),
}

impl ReplCommand {
    pub fn parse(input: &str) -> Self {
        match input.trim() {
            "help" | "h" | "?" => ReplCommand::Help,
            "quit" | "q" | "exit" => ReplCommand::Quit,
            "status" | "info" => ReplCommand::Status,
            other => ReplCommand::Unknown(other.into()),
        }
    }
}

/// 启动交互式REPL
pub fn run() -> Result<(), Box<dyn std::error::Error>> {
    println!("OpenDAW Interactive Shell v0.31.0");
    println!("Type 'help' for available commands, 'quit' to exit.");
    println!();

    loop {
        print!("opendaw> ");
        io::stdout().flush()?;

        let mut input = String::new();
        io::stdin().read_line(&mut input)?;

        let command = ReplCommand::parse(&input);
        match command {
            ReplCommand::Help => {
                println!("Available commands:");
                println!("  help, h, ?    Show this help");
                println!("  quit, q, exit Exit the shell");
                println!("  status, info  Show current status");
                println!();
                println!("Project commands: new, open, save, export, import");
                println!("Mix commands: automix, suggest, analyze");
                println!("Render commands: render");
                println!("Plugin commands: list, install, search");
                println!("Transcribe commands: transcribe");
            }
            ReplCommand::Quit => {
                println!("Goodbye!");
                break;
            }
            ReplCommand::Status => {
                println!("OpenDAW Shell Status:");
                println!("  Version: 0.31.0");
                println!("  No project loaded");
                println!("  Engine: idle");
            }
            ReplCommand::Unknown(cmd) => {
                println!("Unknown command: '{}'. Type 'help' for available commands.", cmd);
            }
        }
    }

    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_parse_help() {
        assert!(matches!(ReplCommand::parse("help"), ReplCommand::Help));
        assert!(matches!(ReplCommand::parse("h"), ReplCommand::Help));
        assert!(matches!(ReplCommand::parse("?"), ReplCommand::Help));
    }

    #[test]
    fn test_parse_quit() {
        assert!(matches!(ReplCommand::parse("quit"), ReplCommand::Quit));
        assert!(matches!(ReplCommand::parse("q"), ReplCommand::Quit));
        assert!(matches!(ReplCommand::parse("exit"), ReplCommand::Quit));
    }

    #[test]
    fn test_parse_status() {
        assert!(matches!(ReplCommand::parse("status"), ReplCommand::Status));
        assert!(matches!(ReplCommand::parse("info"), ReplCommand::Status));
    }

    #[test]
    fn test_parse_unknown() {
        assert!(matches!(ReplCommand::parse("foo"), ReplCommand::Unknown(_)));
    }

    #[test]
    fn test_parse_whitespace() {
        assert!(matches!(ReplCommand::parse("  help  "), ReplCommand::Help));
    }
}
