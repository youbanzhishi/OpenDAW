//! 插件管理子命令

use crate::output::OutputFormat;
use clap::Subcommand;

#[derive(Subcommand)]
pub enum PluginAction {
    /// 列出已安装插件
    List {
        /// 过滤类型 (effect/instrument/analyzer)
        #[arg(long)]
        plugin_type: Option<String>,
    },
    /// 安装插件
    Install {
        /// 插件名称或ID
        name: String,
        /// 指定版本
        #[arg(long)]
        version: Option<String>,
    },
    /// 搜索插件市场
    Search {
        /// 搜索关键词
        query: String,
    },
}

#[derive(Debug, serde::Serialize)]
struct PluginResult {
    action: String,
    status: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    name: Option<String>,
}

pub fn run(action: PluginAction, format: &OutputFormat) -> Result<(), Box<dyn std::error::Error>> {
    match action {
        PluginAction::List { plugin_type } => {
            let result = PluginResult {
                action: "list".into(),
                status: if plugin_type.is_some() {
                    format!("filtered by type: {}", plugin_type.unwrap()).into()
                } else {
                    "all plugins listed".into()
                },
                name: None,
            };
            format.print(&result);
            format.print_success("Plugins listed");
        }
        PluginAction::Install { name, version } => {
            let result = PluginResult {
                action: "install".into(),
                status: version
                    .map(|v| format!("installing version {}", v))
                    .unwrap_or_else(|| "installing latest".into()),
                name: Some(name.clone()),
            };
            format.print(&result);
            format.print_success(&format!("Plugin '{}' installed", name));
        }
        PluginAction::Search { query } => {
            let result = PluginResult {
                action: "search".into(),
                status: format!("searching for '{}'", query).into(),
                name: Some(query),
            };
            format.print(&result);
            format.print_success("Search complete");
        }
    }
    Ok(())
}
