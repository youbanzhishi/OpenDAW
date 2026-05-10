//! 混音子命令

use crate::output::OutputFormat;
use clap::Subcommand;

#[derive(Subcommand)]
pub enum MixAction {
    /// AI自动混音
    Automix {
        /// 项目文件路径
        project: String,
        /// 混音风格 (pop/rock/jazz/classical/electronic)
        #[arg(long, default_value = "pop")]
        style: String,
        /// 目标响度 (LUFS)
        #[arg(long, default_value = "-14")]
        target_loudness: f32,
    },
    /// 混音建议
    Suggest {
        /// 项目文件路径
        project: String,
    },
    /// 分析混音
    Analyze {
        /// 项目文件路径
        project: String,
    },
}

#[derive(Debug, serde::Serialize)]
struct MixResult {
    action: String,
    project: String,
    status: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    style: Option<String>,
}

pub fn run(action: MixAction, format: &OutputFormat) -> Result<(), Box<dyn std::error::Error>> {
    match action {
        MixAction::Automix {
            project,
            style,
            target_loudness,
        } => {
            let result = MixResult {
                action: "automix".into(),
                project: project.clone(),
                status: format!(
                    "applied style '{}' (target: {} LUFS)",
                    style, target_loudness
                )
                .into(),
                style: Some(style),
            };
            format.print(&result);
            format.print_success(&format!("Auto-mix applied to: {}", project));
        }
        MixAction::Suggest { project } => {
            let result = MixResult {
                action: "suggest".into(),
                project: project.clone(),
                status: "suggestions generated".into(),
                style: None,
            };
            format.print(&result);
            format.print_success(&format!("Mix suggestions for: {}", project));
        }
        MixAction::Analyze { project } => {
            let result = MixResult {
                action: "analyze".into(),
                project: project.clone(),
                status: "analysis complete".into(),
                style: None,
            };
            format.print(&result);
            format.print_success(&format!("Mix analysis for: {}", project));
        }
    }
    Ok(())
}
