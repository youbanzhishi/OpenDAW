//! 导入注册表 — 统一的导入/导出管理
//!
//! - ImportRegistry: 统一的导入管理器
//! - 自动检测文件格式（扩展名+magic bytes）
//! - ExportRegistry: 统一的导出管理器

use std::collections::HashMap;
use std::path::Path;

use serde::{Deserialize, Serialize};

pub mod reaper;
pub mod ableton;

use reaper::{ReaperProjectParser, ReaperProject, ReaperParseError, ReaperToProject};
use ableton::{AbletonProjectParser, AbletonProject, AbletonParseError, AbletonToProject};

use crate::project::ProjectConfig;

// ── 文件格式检测 ──────────────────────────────────────────

/// 支持的导入格式
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum ImportFormat {
    /// Reaper RPP
    ReaperRpp,
    /// Ableton ALS
    AbletonAls,
    /// OpenDAW YAML
    OpenDawYaml,
    /// OpenDAW JSON
    OpenDawJson,
    /// Standard MIDI File
    MidiFile,
    /// 未知格式
    Unknown,
}

impl std::fmt::Display for ImportFormat {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            ImportFormat::ReaperRpp => write!(f, "Reaper RPP"),
            ImportFormat::AbletonAls => write!(f, "Ableton ALS"),
            ImportFormat::OpenDawYaml => write!(f, "OpenDAW YAML"),
            ImportFormat::OpenDawJson => write!(f, "OpenDAW JSON"),
            ImportFormat::MidiFile => write!(f, "Standard MIDI"),
            ImportFormat::Unknown => write!(f, "Unknown"),
        }
    }
}

/// 支持的导出格式
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum ExportFormat {
    /// Standard MIDI File Format 0
    MidiFormat0,
    /// Standard MIDI File Format 1
    MidiFormat1,
    /// OpenDAW YAML
    OpenDawYaml,
    /// OpenDAW JSON
    OpenDawJson,
    /// OpenDAW Binary
    OpenDawBinary,
}

impl std::fmt::Display for ExportFormat {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            ExportFormat::MidiFormat0 => write!(f, "MIDI Format 0"),
            ExportFormat::MidiFormat1 => write!(f, "MIDI Format 1"),
            ExportFormat::OpenDawYaml => write!(f, "OpenDAW YAML"),
            ExportFormat::OpenDawJson => write!(f, "OpenDAW JSON"),
            ExportFormat::OpenDawBinary => write!(f, "OpenDAW Binary"),
        }
    }
}

/// 导入错误
#[derive(Debug, thiserror::Error)]
pub enum ImportError {
    #[error("Reaper解析错误: {0}")]
    Reaper(#[from] ReaperParseError),
    #[error("Ableton解析错误: {0}")]
    Ableton(#[from] AbletonParseError),
    #[error("不支持的格式: {0}")]
    UnsupportedFormat(String),
    #[error("IO错误: {0}")]
    Io(#[from] std::io::Error),
    #[error("格式检测失败: {0}")]
    DetectionFailed(String),
}

/// 导出错误
#[derive(Debug, thiserror::Error)]
pub enum ExportError {
    #[error("不支持的导出格式: {0}")]
    UnsupportedFormat(String),
    #[error("IO错误: {0}")]
    Io(#[from] std::io::Error),
    #[error("序列化错误: {0}")]
    Serialization(String),
    #[error("MIDI导出错误: {0}")]
    MidiExport(String),
}

// ── 格式检测器 ────────────────────────────────────────────

/// 文件格式检测器
pub struct FormatDetector;

impl FormatDetector {
    /// 通过文件扩展名检测格式
    pub fn detect_by_extension(path: &Path) -> ImportFormat {
        match path
            .extension()
            .and_then(|e| e.to_str())
            .map(|e| e.to_lowercase())
            .as_deref()
        {
            Some("rpp") => ImportFormat::ReaperRpp,
            Some("als") => ImportFormat::AbletonAls,
            Some("yaml") | Some("yml") => ImportFormat::OpenDawYaml,
            Some("json") => ImportFormat::OpenDawJson,
            Some("mid") | Some("midi") => ImportFormat::MidiFile,
            _ => ImportFormat::Unknown,
        }
    }

    /// 通过magic bytes检测格式
    pub fn detect_by_magic(data: &[u8]) -> ImportFormat {
        if data.len() < 4 {
            return ImportFormat::Unknown;
        }

        // gzip magic (ALS是gzip压缩的XML)
        if data[0] == 0x1f && data[1] == 0x8b {
            return ImportFormat::AbletonAls;
        }

        // XML声明 (ALS解压后或RPP)
        if data.starts_with(b"<?xml") || data.starts_with(b"<Ableton") {
            // 检查是Ableton还是Reaper
            let content = String::from_utf8_lossy(data);
            if content.contains("<Ableton") {
                return ImportFormat::AbletonAls;
            }
            if content.contains("REAPER") || content.contains("<TRACK") {
                return ImportFormat::ReaperRpp;
            }
            return ImportFormat::Unknown;
        }

        // MIDI文件头 "MThd"
        if data[0] == 0x4d && data[1] == 0x54 && data[2] == 0x68 && data[3] == 0x64 {
            return ImportFormat::MidiFile;
        }

        // RPP文件通常不以XML开头
        let content = String::from_utf8_lossy(data);
        if content.contains("REAPER") || content.contains("bpm") {
            return ImportFormat::ReaperRpp;
        }

        ImportFormat::Unknown
    }

    /// 综合检测文件格式
    pub fn detect(path: &Path) -> Result<ImportFormat, ImportError> {
        // 首先尝试扩展名
        let ext_format = Self::detect_by_extension(path);
        if ext_format != ImportFormat::Unknown {
            return Ok(ext_format);
        }

        // 然后尝试magic bytes
        let data = std::fs::read(path)?;
        let magic_format = Self::detect_by_magic(&data);
        if magic_format != ImportFormat::Unknown {
            return Ok(magic_format);
        }

        Err(ImportError::DetectionFailed(format!(
            "无法检测文件格式: {}",
            path.display()
        )))
    }
}

// ── 导入注册表 ────────────────────────────────────────────

/// 导入结果
#[derive(Debug, Clone)]
pub enum ImportResult {
    /// Reaper项目
    Reaper(ReaperProject),
    /// Ableton项目
    Ableton(AbletonProject),
    /// OpenDAW项目配置
    OpenDaw(ProjectConfig),
}

/// 导入注册表 — 统一的导入管理器
pub struct ImportRegistry {
    /// 支持的格式映射
    format_handlers: HashMap<ImportFormat, String>,
}

impl ImportRegistry {
    /// 创建新的导入注册表
    pub fn new() -> Self {
        let mut handlers = HashMap::new();
        handlers.insert(ImportFormat::ReaperRpp, "reaper".to_string());
        handlers.insert(ImportFormat::AbletonAls, "ableton".to_string());
        handlers.insert(ImportFormat::OpenDawYaml, "opendaw_yaml".to_string());
        handlers.insert(ImportFormat::OpenDawJson, "opendaw_json".to_string());
        handlers.insert(ImportFormat::MidiFile, "midi".to_string());

        Self {
            format_handlers: handlers,
        }
    }

    /// 导入文件
    pub fn import(&self, path: &Path) -> Result<ImportResult, ImportError> {
        let format = FormatDetector::detect(path)?;

        match format {
            ImportFormat::ReaperRpp => {
                let parser = ReaperProjectParser::new();
                let project = parser.parse_file(path)?;
                Ok(ImportResult::Reaper(project))
            }
            ImportFormat::AbletonAls => {
                let parser = AbletonProjectParser::new();
                let project = parser.parse_file(path)?;
                Ok(ImportResult::Ableton(project))
            }
            ImportFormat::OpenDawYaml | ImportFormat::OpenDawJson => {
                // 使用已有的项目格式加载器
                let content = std::fs::read_to_string(path)?;
                let config: ProjectConfig = if format == ImportFormat::OpenDawYaml {
                    serde_yaml::from_str(&content)
                        .map_err(|e| ImportError::UnsupportedFormat(e.to_string()))?
                } else {
                    serde_json::from_str(&content)
                        .map_err(|e| ImportError::UnsupportedFormat(e.to_string()))?
                };
                Ok(ImportResult::OpenDaw(config))
            }
            ImportFormat::MidiFile => {
                Err(ImportError::UnsupportedFormat(
                    "MIDI导入暂未实现，请使用MIDI导出".to_string(),
                ))
            }
            ImportFormat::Unknown => {
                Err(ImportError::UnsupportedFormat("未知文件格式".to_string()))
            }
        }
    }

    /// 导入文件并转换为OpenDAW项目配置
    pub fn import_as_project(&self, path: &Path) -> Result<ProjectConfig, ImportError> {
        let result = self.import(path)?;

        match result {
            ImportResult::Reaper(reaper) => {
                let converter = ReaperToProject::new();
                Ok(converter.convert(&reaper))
            }
            ImportResult::Ableton(ableton) => {
                let converter = AbletonToProject::new();
                Ok(converter.convert(&ableton))
            }
            ImportResult::OpenDaw(config) => Ok(config),
        }
    }

    /// 列出支持的格式
    pub fn supported_formats(&self) -> Vec<ImportFormat> {
        let mut formats: Vec<ImportFormat> = self.format_handlers.keys().copied().collect();
        formats.sort_by(|a, b| a.to_string().cmp(&b.to_string()));
        formats
    }

    /// 检查格式是否支持
    pub fn is_supported(&self, format: ImportFormat) -> bool {
        self.format_handlers.contains_key(&format)
    }

    /// 获取格式的处理程序名称
    pub fn get_handler(&self, format: ImportFormat) -> Option<&str> {
        self.format_handlers.get(&format).map(|s| s.as_str())
    }
}

impl Default for ImportRegistry {
    fn default() -> Self {
        Self::new()
    }
}

// ── 导出注册表 ────────────────────────────────────────────

/// 导出注册表 — 统一的导出管理器
pub struct ExportRegistry {
    /// 支持的格式
    format_handlers: HashMap<ExportFormat, String>,
}

impl ExportRegistry {
    /// 创建新的导出注册表
    pub fn new() -> Self {
        let mut handlers = HashMap::new();
        handlers.insert(ExportFormat::MidiFormat0, "midi_f0".to_string());
        handlers.insert(ExportFormat::MidiFormat1, "midi_f1".to_string());
        handlers.insert(ExportFormat::OpenDawYaml, "opendaw_yaml".to_string());
        handlers.insert(ExportFormat::OpenDawJson, "opendaw_json".to_string());
        handlers.insert(ExportFormat::OpenDawBinary, "opendaw_binary".to_string());

        Self {
            format_handlers: handlers,
        }
    }

    /// 导出为指定格式
    pub fn export(
        &self,
        config: &ProjectConfig,
        format: ExportFormat,
        path: &Path,
    ) -> Result<(), ExportError> {
        match format {
            ExportFormat::OpenDawYaml => {
                let content = serde_yaml::to_string(config)
                    .map_err(|e| ExportError::Serialization(e.to_string()))?;
                std::fs::write(path, content)?;
                Ok(())
            }
            ExportFormat::OpenDawJson => {
                let content = serde_json::to_string_pretty(config)
                    .map_err(|e| ExportError::Serialization(e.to_string()))?;
                std::fs::write(path, content)?;
                Ok(())
            }
            ExportFormat::MidiFormat0 | ExportFormat::MidiFormat1 => {
                // MIDI导出由midi_export模块处理
                Err(ExportError::MidiExport(
                    "请使用MidiExporter直接导出MIDI文件".to_string(),
                ))
            }
            ExportFormat::OpenDawBinary => {
                let content = bincode::serialize(config)
                    .map_err(|e| ExportError::Serialization(e.to_string()))?;
                std::fs::write(path, content)?;
                Ok(())
            }
        }
    }

    /// 列出支持的格式
    pub fn supported_formats(&self) -> Vec<ExportFormat> {
        let mut formats: Vec<ExportFormat> = self.format_handlers.keys().copied().collect();
        formats.sort_by(|a, b| a.to_string().cmp(&b.to_string()));
        formats
    }

    /// 检查格式是否支持
    pub fn is_supported(&self, format: ExportFormat) -> bool {
        self.format_handlers.contains_key(&format)
    }
}

impl Default for ExportRegistry {
    fn default() -> Self {
        Self::new()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_format_detector_extension() {
        use std::path::PathBuf;
        assert_eq!(
            FormatDetector::detect_by_extension(&PathBuf::from("test.rpp")),
            ImportFormat::ReaperRpp
        );
        assert_eq!(
            FormatDetector::detect_by_extension(&PathBuf::from("test.als")),
            ImportFormat::AbletonAls
        );
        assert_eq!(
            FormatDetector::detect_by_extension(&PathBuf::from("test.yaml")),
            ImportFormat::OpenDawYaml
        );
        assert_eq!(
            FormatDetector::detect_by_extension(&PathBuf::from("test.json")),
            ImportFormat::OpenDawJson
        );
        assert_eq!(
            FormatDetector::detect_by_extension(&PathBuf::from("test.mid")),
            ImportFormat::MidiFile
        );
        assert_eq!(
            FormatDetector::detect_by_extension(&PathBuf::from("test.unknown")),
            ImportFormat::Unknown
        );
    }

    #[test]
    fn test_format_detector_magic_gzip() {
        let gzip_data = vec![0x1f, 0x8b, 0x08, 0x00];
        assert_eq!(
            FormatDetector::detect_by_magic(&gzip_data),
            ImportFormat::AbletonAls
        );
    }

    #[test]
    fn test_format_detector_magic_midi() {
        let midi_data = vec![0x4d, 0x54, 0x68, 0x64, 0x00, 0x00];
        assert_eq!(
            FormatDetector::detect_by_magic(&midi_data),
            ImportFormat::MidiFile
        );
    }

    #[test]
    fn test_format_detector_magic_ableton_xml() {
        let xml_data = b"<?xml version=\"1.0\"?><Ableton></Ableton>";
        assert_eq!(
            FormatDetector::detect_by_magic(xml_data),
            ImportFormat::AbletonAls
        );
    }

    #[test]
    fn test_import_registry_supported_formats() {
        let registry = ImportRegistry::new();
        let formats = registry.supported_formats();
        assert!(formats.contains(&ImportFormat::ReaperRpp));
        assert!(formats.contains(&ImportFormat::AbletonAls));
    }

    #[test]
    fn test_import_registry_is_supported() {
        let registry = ImportRegistry::new();
        assert!(registry.is_supported(ImportFormat::ReaperRpp));
        assert!(registry.is_supported(ImportFormat::AbletonAls));
        assert!(!registry.is_supported(ImportFormat::Unknown));
    }

    #[test]
    fn test_export_registry_supported_formats() {
        let registry = ExportRegistry::new();
        let formats = registry.supported_formats();
        assert!(formats.contains(&ExportFormat::MidiFormat0));
        assert!(formats.contains(&ExportFormat::MidiFormat1));
        assert!(formats.contains(&ExportFormat::OpenDawYaml));
    }

    #[test]
    fn test_export_format_display() {
        assert_eq!(format!("{}", ExportFormat::MidiFormat0), "MIDI Format 0");
        assert_eq!(format!("{}", ExportFormat::MidiFormat1), "MIDI Format 1");
    }

    #[test]
    fn test_import_format_display() {
        assert_eq!(format!("{}", ImportFormat::ReaperRpp), "Reaper RPP");
        assert_eq!(format!("{}", ImportFormat::AbletonAls), "Ableton ALS");
    }
}
