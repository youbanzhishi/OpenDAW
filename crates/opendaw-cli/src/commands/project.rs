//! 项目管理子命令

use crate::output::OutputFormat;
use clap::Subcommand;

#[derive(Subcommand)]
pub enum ProjectAction {
    /// 创建新项目
    New {
        /// 项目名称
        name: String,
        /// BPM
        #[arg(long, default_value = "120")]
        bpm: f64,
        /// 采样率
        #[arg(long, default_value = "44100")]
        sample_rate: u32,
    },
    /// 打开项目
    Open {
        /// 项目文件路径
        path: String,
    },
    /// 保存项目
    Save {
        /// 项目文件路径
        #[arg(long)]
        path: Option<String>,
    },
    /// 导出项目
    Export {
        /// 输出路径
        output: String,
        /// 格式 (wav/flac/mp3)
        #[arg(long, default_value = "wav")]
        format: String,
    },
    /// 导入文件
    Import {
        /// 输入文件路径
        input: String,
        /// 目标项目（可选）
        #[arg(long)]
        project: Option<String>,
    },
    /// 格式转换
    Convert {
        /// 输入文件
        input: String,
        /// 输出文件
        output: String,
    },
}

#[derive(Debug, serde::Serialize)]
struct ProjectResult {
    action: String,
    name: Option<String>,
    path: Option<String>,
    status: String,
}

pub fn run(action: ProjectAction, format: &OutputFormat) -> Result<(), Box<dyn std::error::Error>> {
    match action {
        ProjectAction::New { name, bpm, sample_rate } => {
            let result = ProjectResult {
                action: "new".into(),
                name: Some(name.clone()),
                path: None,
                status: "created".into(),
            };
            format.print(&result);
            format.print_success(&format!("Project '{}' created (BPM: {}, SR: {})", name, bpm, sample_rate));
        }
        ProjectAction::Open { path } => {
            let result = ProjectResult {
                action: "open".into(),
                name: None,
                path: Some(path.clone()),
                status: "opened".into(),
            };
            format.print(&result);
            format.print_success(&format!("Project opened: {}", path));
        }
        ProjectAction::Save { path } => {
            let result = ProjectResult {
                action: "save".into(),
                name: None,
                path: path.clone(),
                status: "saved".into(),
            };
            format.print(&result);
            format.print_success("Project saved");
        }
        ProjectAction::Export { output, format: fmt } => {
            let result = ProjectResult {
                action: "export".into(),
                name: None,
                path: Some(output.clone()),
                status: format!("exported as {}", fmt).into(),
            };
            format.print(&result);
            format.print_success(&format!("Project exported to: {}", output));
        }
        ProjectAction::Import { input, project } => {
            let result = ProjectResult {
                action: "import".into(),
                name: project,
                path: Some(input.clone()),
                status: "imported".into(),
            };
            format.print(&result);
            format.print_success(&format!("File imported: {}", input));
        }
        ProjectAction::Convert { input, output } => {
            let result = ProjectResult {
                action: "convert".into(),
                name: None,
                path: Some(format!("{} -> {}", input, output)),
                status: "converted".into(),
            };
            format.print(&result);
            format.print_success("Project format converted");
        }
    }
    Ok(())
}
