//! 渲染子命令

use crate::output::OutputFormat;
use clap::Subcommand;

#[derive(Subcommand)]
pub enum RenderAction {
    /// 离线渲染项目
    Render {
        /// 项目文件路径
        project: String,
        /// 输出文件路径
        #[arg(long)]
        output: Option<String>,
        /// 格式 (wav/flac/mp3)
        #[arg(long, default_value = "wav")]
        format: String,
        /// 起始拍
        #[arg(long)]
        start: Option<f64>,
        /// 结束拍
        #[arg(long)]
        end: Option<f64>,
    },
}

#[derive(Debug, serde::Serialize)]
struct RenderResult {
    action: String,
    project: String,
    output: Option<String>,
    status: String,
}

pub fn run(action: RenderAction, format: &OutputFormat) -> Result<(), Box<dyn std::error::Error>> {
    match action {
        RenderAction::Render {
            project,
            output,
            format: fmt,
            start,
            end,
        } => {
            let result = RenderResult {
                action: "render".into(),
                project: project.clone(),
                output: output.clone(),
                status: format!("rendering as {}", fmt).into(),
            };
            format.print(&result);

            if start.is_some() || end.is_some() {
                format.print_success(&format!(
                    "Rendering {} (range: {} - {})",
                    project,
                    start
                        .map(|s| s.to_string())
                        .unwrap_or_else(|| "start".into()),
                    end.map(|e| e.to_string()).unwrap_or_else(|| "end".into()),
                ));
            } else {
                format.print_success(&format!("Rendering project: {}", project));
            }
        }
    }
    Ok(())
}
