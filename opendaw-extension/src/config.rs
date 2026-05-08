//! 配置解析 — opendaw-extensions.yaml
//!
//! 从YAML文件加载扩展配置，创建对应的注册表

use std::path::Path;

use serde::{Deserialize, Serialize};

use crate::error::ExtensionError;

/// 扩展配置顶层结构
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ExtensionConfig {
    pub extensions: Extensions,
}

/// 扩展集合
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Extensions {
    #[serde(default)]
    pub plugins: Vec<PluginConfig>,
    #[serde(default)]
    pub scripts: Vec<ScriptConfig>,
    #[serde(default)]
    pub models: Vec<ModelConfig>,
    #[serde(default)]
    pub hooks: Vec<HookConfig>,
}

/// 插件配置
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PluginConfig {
    pub id: String,
    #[serde(rename = "type")]
    pub plugin_type: String,
    pub path: String,
}

/// 脚本配置
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ScriptConfig {
    pub id: String,
    pub lang: String,
    pub path: String,
    #[serde(default)]
    pub hooks: Vec<String>,
}

/// 模型配置
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ModelConfig {
    pub id: String,
    pub backend: String,
    #[serde(default)]
    pub path: Option<String>,
    #[serde(default)]
    pub endpoint: Option<String>,
    #[serde(default)]
    pub tasks: Vec<String>,
}

/// 钩子配置
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct HookConfig {
    pub event: String,
    pub handler: String,
    #[serde(default)]
    pub priority: i32,
}

impl ExtensionConfig {
    /// 从YAML文件加载配置
    pub fn from_file(path: &Path) -> Result<Self, ExtensionError> {
        let content = std::fs::read_to_string(path)
            .map_err(|e| ExtensionError::ConfigParse(format!("读取文件失败: {}", e)))?;
        Self::from_str(&content)
    }

    /// 从YAML字符串解析配置
    pub fn from_str(yaml: &str) -> Result<Self, ExtensionError> {
        serde_yaml::from_str(yaml)
            .map_err(|e| ExtensionError::ConfigParse(format!("YAML解析失败: {}", e)))
    }

    /// 生成示例配置
    pub fn example() -> Self {
        Self {
            extensions: Extensions {
                plugins: vec![
                    PluginConfig {
                        id: "vc-eq".into(),
                        plugin_type: "vc-plugin".into(),
                        path: "~/.opendaw/plugins/vc-eq/".into(),
                    },
                ],
                scripts: vec![
                    ScriptConfig {
                        id: "auto-save".into(),
                        lang: "python".into(),
                        path: "~/scripts/auto_save.py".into(),
                        hooks: vec!["render_finish".into()],
                    },
                ],
                models: vec![
                    ModelConfig {
                        id: "smart-mixer-v2".into(),
                        backend: "local".into(),
                        path: Some("~/.opendaw/models/mixer_v2.onnx".into()),
                        endpoint: None,
                        tasks: vec!["auto_mix".into()],
                    },
                ],
                hooks: vec![
                    HookConfig {
                        event: "render_start".into(),
                        handler: "scripts.auto-save.on_render_start".into(),
                        priority: 10,
                    },
                ],
            },
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_parse_config() {
        let yaml = r#"
extensions:
  plugins:
    - id: vc-eq
      type: vc-plugin
      path: ~/.opendaw/plugins/vc-eq/
  scripts:
    - id: auto-save
      lang: python
      path: ~/scripts/auto_save.py
      hooks:
        - render_finish
  models:
    - id: smart-mixer-v2
      backend: local
      path: ~/.opendaw/models/mixer_v2.onnx
      tasks:
        - auto_mix
  hooks:
    - event: render_start
      handler: scripts.auto-save.on_render_start
      priority: 10
"#;
        let config = ExtensionConfig::from_str(yaml).unwrap();
        assert_eq!(config.extensions.plugins.len(), 1);
        assert_eq!(config.extensions.plugins[0].id, "vc-eq");
        assert_eq!(config.extensions.scripts[0].hooks, vec!["render_finish"]);
        assert_eq!(config.extensions.models[0].tasks, vec!["auto_mix"]);
        assert_eq!(config.extensions.hooks[0].priority, 10);
    }

    #[test]
    fn test_example_config() {
        let config = ExtensionConfig::example();
        assert!(!config.extensions.plugins.is_empty());
        assert!(!config.extensions.scripts.is_empty());
        assert!(!config.extensions.models.is_empty());
        assert!(!config.extensions.hooks.is_empty());
    }
}
