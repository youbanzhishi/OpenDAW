//! OpenDAW CLI 入口

mod commands;
mod output;
mod repl;

use clap::{Parser, Subcommand};
use colored::Colorize;

#[derive(Parser)]
#[command(name = "opendaw")]
#[command(about = "OpenDAW — 开源DAW命令行工具")]
#[command(version)]
struct Cli {
    /// 输出格式: json, yaml, table
    #[arg(long, global = true, default_value = "table")]
    format: String,

    #[command(subcommand)]
    command: Commands,
}

#[derive(Subcommand)]
enum Commands {
    /// 项目管理
    Project {
        #[command(subcommand)]
        action: commands::project::ProjectAction,
    },
    /// 离线渲染
    Render {
        #[command(subcommand)]
        action: commands::render::RenderAction,
    },
    /// 混音操作
    Mix {
        #[command(subcommand)]
        action: commands::mix::MixAction,
    },
    /// 插件管理
    Plugin {
        #[command(subcommand)]
        action: commands::plugin::PluginAction,
    },
    /// 音频扒带
    Transcribe {
        #[command(subcommand)]
        action: commands::transcribe::TranscribeAction,
    },
    /// 启动API+WebSocket服务器
    Serve(commands::serve::ServeArgs),
    /// 交互式REPL模式
    Shell,
}

fn main() {
    let cli = Cli::parse();
    let format = output::OutputFormat::from_str(&cli.format);

    let result = match cli.command {
        Commands::Project { action } => commands::project::run(action, &format),
        Commands::Render { action } => commands::render::run(action, &format),
        Commands::Mix { action } => commands::mix::run(action, &format),
        Commands::Plugin { action } => commands::plugin::run(action, &format),
        Commands::Transcribe { action } => commands::transcribe::run(action, &format),
        Commands::Serve(args) => commands::serve::run(args, &format),
        Commands::Shell => repl::run(),
    };

    if let Err(e) = result {
        eprintln!("{}", e.to_string().red());
        std::process::exit(1);
    }
}
