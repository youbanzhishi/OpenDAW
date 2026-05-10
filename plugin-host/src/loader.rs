//! PluginLoader — 工厂模式加载不同格式插件
//!
//! 根据插件格式（VST3/CLAP/VC-CLI/JSFX/LV2）选择对应适配器，
//! 统一创建 `Box<dyn VcPlugin>` 实例。
//!
//! # 架构
//!
//! ```text
//! PluginLoader::load(path) ──► match format ──► Adapter::from_file(path)
//!                              ├── .vst3  → Vst3Adapter
//!                              ├── .clap  → ClapAdapter
//!                              ├── *CLI*  → VcPluginAdapter
//!                              ├── .jsfx  → JsfxAdapter
//!                              └── .lv2   → (预留)
//! ```
//!
//! # 使用
//!
//! ```ignore
//! use plugin_host::loader::PluginLoader;
//!
//! let mut loader = PluginLoader::new();
//! let plugin = loader.load_from_path("/path/to/plugin.vst3")?;
//! let plugin = loader.load_from_path("/path/to/script.jsfx")?;
//!
//! // 或者通过扫描结果加载
//! let plugin = loader.load_from_scanned(&scanned_plugin)?;
//! ```

use std::path::{Path, PathBuf};

use opendaw_extension::{PluginError, VcPlugin};
use crate::scanner::{PluginFormat, ScannedPlugin};
use crate::vc_adapter::VcPluginAdapter;

/// 插件加载器 — 工厂模式
///
/// 根据插件文件路径或格式信息，选择对应的适配器加载插件。
/// 支持自动格式检测和显式格式指定。
pub struct PluginLoader {
    /// VC-CLI 搜索目录列表
    vc_search_dirs: Vec<PathBuf>,
}

impl PluginLoader {
    /// 创建新的插件加载器
    pub fn new() -> Self {
        Self {
            vc_search_dirs: vec![PathBuf::from("/tmp/AudioFX")],
        }
    }

    /// 添加 VC-CLI 搜索目录
    pub fn add_vc_search_dir(&mut self, dir: PathBuf) {
        if !self.vc_search_dirs.contains(&dir) {
            self.vc_search_dirs.push(dir);
        }
    }

    /// 从文件路径自动检测格式并加载
    ///
    /// 根据文件扩展名和文件名特征判断插件格式，
    /// 然后使用对应的适配器加载。
    pub fn load_from_path(&self, path: &Path) -> Result<Box<dyn VcPlugin>, PluginError> {
        let format = Self::detect_format(path)?;
        self.load_with_format(path, &format)
    }

    /// 使用指定格式加载
    pub fn load_with_format(
        &self,
        path: &Path,
        format: &PluginFormat,
    ) -> Result<Box<dyn VcPlugin>, PluginError> {
        match format {
            PluginFormat::Vst3 => {
                #[cfg(feature = "vst3")]
                {
                    let adapter = crate::vst3_adapter::Vst3Adapter::from_file(path)?;
                    Ok(Box::new(adapter))
                }
                #[cfg(not(feature = "vst3"))]
                {
                    Err(PluginError::InitFailed(
                        format!("VST3 支持未启用，请启用 'vst3' feature: {}", path.display())
                    ))
                }
            }
            PluginFormat::Clap => {
                #[cfg(feature = "clap")]
                {
                    let adapter = crate::clap_adapter::ClapAdapter::from_file(path)?;
                    Ok(Box::new(adapter))
                }
                #[cfg(not(feature = "clap"))]
                {
                    Err(PluginError::InitFailed(
                        format!("CLAP 支持未启用，请启用 'clap' feature: {}", path.display())
                    ))
                }
            }
            PluginFormat::VcCli => {
                let adapter = VcPluginAdapter::from_binary(path)?;
                Ok(Box::new(adapter))
            }
            PluginFormat::Jsfx => {
                #[cfg(feature = "jsfx")]
                {
                    use jsfx_engine::JsfxPlugin;
                    let plugin = JsfxPlugin::from_file(path)
                        .map_err(|e| PluginError::InitFailed(format!("JSFX 加载失败: {}", e)))?;
                    Ok(Box::new(plugin))
                }
                #[cfg(not(feature = "jsfx"))]
                {
                    Err(PluginError::InitFailed(
                        format!("JSFX 支持未启用，请启用 'jsfx' feature: {}", path.display())
                    ))
                }
            }
            PluginFormat::Lv2 => {
                Err(PluginError::InitFailed("LV2 格式暂不支持".to_string()))
            }
        }
    }

    /// 从扫描结果加载
    pub fn load_from_scanned(&self, info: &ScannedPlugin) -> Result<Box<dyn VcPlugin>, PluginError> {
        self.load_with_format(&info.path, &info.format)
    }

    /// 从插件ID加载 VC-CLI 插件
    ///
    /// 在 VC 搜索目录中查找匹配的 CLI 二进制。
    pub fn load_vc_by_id(&self, plugin_id: &str) -> Result<Box<dyn VcPlugin>, PluginError> {
        for dir in &self.vc_search_dirs {
            if !dir.exists() {
                continue;
            }

            // 尝试直接匹配: VC-{Name}/VC-{Name}-CLI-Standalone
            let name_part = plugin_id.strip_prefix("vc-").unwrap_or(plugin_id);
            // Handle multi-word: vc-dynamic-eq → VC-DynamicEQ
            let dir_name = format!("VC-{}", Self::to_pascal_case(name_part));
            let binary_name = format!("{}-CLI-Standalone", dir_name);
            let binary_path = dir.join(&dir_name).join(&binary_name);

            if binary_path.exists() {
                let adapter = VcPluginAdapter::from_binary(&binary_path)?;
                return Ok(Box::new(adapter));
            }
        }

        Err(PluginError::ProcessFailed(
            format!("未找到 VC-CLI 插件: {}", plugin_id)
        ))
    }

    /// 自动检测插件格式
    pub fn detect_format(path: &Path) -> Result<PluginFormat, PluginError> {
        if !path.exists() {
            return Err(PluginError::InitFailed(
                format!("文件不存在: {}", path.display())
            ));
        }

        // 优先检查扩展名
        if let Some(ext) = path.extension().and_then(|e| e.to_str()) {
            match ext.to_lowercase().as_str() {
                "vst3" => return Ok(PluginFormat::Vst3),
                "clap" => return Ok(PluginFormat::Clap),
                "jsfx" => return Ok(PluginFormat::Jsfx),
                "lv2" => return Ok(PluginFormat::Lv2),
                _ => {}
            }
        }

        // 检查文件名模式 (VC-CLI)
        let file_name = path.file_name()
            .unwrap_or_default()
            .to_string_lossy();

        if file_name.contains("CLI-Standalone") || file_name.contains("CLI") {
            return Ok(PluginFormat::VcCli);
        }

        // 检查路径中的格式提示
        let path_str = path.to_string_lossy().to_lowercase();
        if path_str.contains(".vst3") {
            return Ok(PluginFormat::Vst3);
        }
        if path_str.contains(".clap") {
            return Ok(PluginFormat::Clap);
        }
        if path_str.contains(".jsfx") {
            return Ok(PluginFormat::Jsfx);
        }

        Err(PluginError::InitFailed(
            format!("无法识别插件格式: {}", path.display())
        ))
    }

    /// 列出所有支持的格式
    pub fn supported_formats() -> Vec<PluginFormat> {
        let mut formats = vec![PluginFormat::VcCli, PluginFormat::Jsfx, PluginFormat::Lv2];
        formats.push(PluginFormat::Vst3);
        formats.push(PluginFormat::Clap);
        formats
    }

    /// 将 kebab-case 转换为 PascalCase
    ///
    /// 例: "dynamic-eq" → "DynamicEQ"
    fn to_pascal_case(s: &str) -> String {
        s.split('-')
            .map(|part| {
                // Two-letter abbreviations should be fully uppercased (e.g., "eq" -> "EQ")
                if part.len() <= 2 {
                    part.to_uppercase()
                } else {
                    let mut chars = part.chars();
                    match chars.next() {
                        None => String::new(),
                        Some(first) => first.to_uppercase().collect::<String>() + chars.as_str(),
                    }
                }
            })
            .collect()
    }
}

impl Default for PluginLoader {
    fn default() -> Self {
        Self::new()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_detect_format_nonexistent() {
        let result = PluginLoader::detect_format(Path::new("/nonexistent/path"));
        assert!(result.is_err());
    }

    #[test]
    fn test_supported_formats() {
        let formats = PluginLoader::supported_formats();
        assert!(formats.contains(&PluginFormat::Vst3));
        assert!(formats.contains(&PluginFormat::Clap));
        assert!(formats.contains(&PluginFormat::VcCli));
        assert!(formats.contains(&PluginFormat::Jsfx));
        assert!(formats.contains(&PluginFormat::Lv2));
    }

    #[test]
    fn test_to_pascal_case() {
        assert_eq!(PluginLoader::to_pascal_case("eq"), "EQ");
        assert_eq!(PluginLoader::to_pascal_case("dynamic-eq"), "DynamicEQ");
        assert_eq!(PluginLoader::to_pascal_case("reverb"), "Reverb");
        assert_eq!(PluginLoader::to_pascal_case("multi-band"), "MultiBand");
    }

    #[test]
    fn test_loader_new() {
        let loader = PluginLoader::new();
        assert_eq!(loader.vc_search_dirs.len(), 1);
    }

    #[test]
    fn test_loader_add_search_dir() {
        let mut loader = PluginLoader::new();
        loader.add_vc_search_dir(PathBuf::from("/custom/dir"));
        assert_eq!(loader.vc_search_dirs.len(), 2);

        // 重复不应添加
        loader.add_vc_search_dir(PathBuf::from("/custom/dir"));
        assert_eq!(loader.vc_search_dirs.len(), 2);
    }

    #[test]
    fn test_load_from_path_nonexistent() {
        let loader = PluginLoader::new();
        let result = loader.load_from_path(Path::new("/nonexistent.vst3"));
        assert!(result.is_err());
    }

    #[test]
    fn test_load_vc_by_id_nonexistent() {
        let loader = PluginLoader::new();
        let result = loader.load_vc_by_id("vc-nonexistent");
        assert!(result.is_err());
    }

    #[test]
    fn test_load_lv2_unsupported() {
        let loader = PluginLoader::new();
        // Create a temp .lv2 dir to test format detection
        let temp_dir = std::env::temp_dir().join("test_lv2_plugin.lv2");
        let _ = std::fs::create_dir_all(&temp_dir);
        let result = loader.load_with_format(&temp_dir, &PluginFormat::Lv2);
        assert!(result.is_err());
        let _ = std::fs::remove_dir_all(&temp_dir);
    }
}
