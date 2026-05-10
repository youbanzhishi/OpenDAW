//! 项目格式升级 — YAML↔JSON↔Binary 互转
//!
//! 支持三种序列化格式：
//! - YAML: 人类可读，适合版本控制和手动编辑
//! - JSON: 通用交换格式，适合Web/API集成
//! - Binary: 高性能紧凑格式，适合大项目和实时加载

use std::path::Path;

use serde::{Deserialize, Serialize};

use crate::project::{Project, ProjectConfig, ProjectError};

/// 项目序列化格式
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum ProjectFormat {
    /// YAML格式 — 人类可读，适合版本控制
    Yaml,
    /// JSON格式 — 通用交换格式
    Json,
    /// Binary格式 (bincode) — 高性能紧凑格式
    Binary,
}

impl ProjectFormat {
    /// 根据文件扩展名自动检测格式
    pub fn from_extension(path: &Path) -> Option<Self> {
        match path.extension().and_then(|e| e.to_str()) {
            Some("yaml") | Some("yml") => Some(ProjectFormat::Yaml),
            Some("json") => Some(ProjectFormat::Json),
            Some("daw" | "bin" | "binary") => Some(ProjectFormat::Binary),
            _ => None,
        }
    }

    /// 获取格式的默认文件扩展名
    pub fn default_extension(&self) -> &'static str {
        match self {
            ProjectFormat::Yaml => "yaml",
            ProjectFormat::Json => "json",
            ProjectFormat::Binary => "daw",
        }
    }

    /// 格式的描述名称
    pub fn name(&self) -> &'static str {
        match self {
            ProjectFormat::Yaml => "YAML",
            ProjectFormat::Json => "JSON",
            ProjectFormat::Binary => "Binary",
        }
    }
}

/// 项目序列化器 trait
pub trait ProjectSerializer {
    /// 序列化项目配置到字节数据
    fn serialize(config: &ProjectConfig) -> Result<Vec<u8>, ProjectFormatError>;

    /// 从字节数据反序列化项目配置
    fn deserialize(data: &[u8]) -> Result<ProjectConfig, ProjectFormatError>;

    /// 保存项目配置到文件
    fn save(config: &ProjectConfig, path: &Path) -> Result<(), ProjectFormatError> {
        let data = Self::serialize(config)?;
        std::fs::write(path, data)
            .map_err(|e| ProjectFormatError::IoError(format!("写入文件失败: {}", e)))?;
        Ok(())
    }

    /// 从文件加载项目配置
    fn load(path: &Path) -> Result<ProjectConfig, ProjectFormatError> {
        let data = std::fs::read(path)
            .map_err(|e| ProjectFormatError::IoError(format!("读取文件失败: {}", e)))?;
        Self::deserialize(&data)
    }
}

/// YAML序列化器
pub struct YamlSerializer;

impl ProjectSerializer for YamlSerializer {
    fn serialize(config: &ProjectConfig) -> Result<Vec<u8>, ProjectFormatError> {
        let yaml = serde_yaml::to_string(config)
            .map_err(|e| ProjectFormatError::SerializeError(format!("YAML序列化失败: {}", e)))?;
        Ok(yaml.into_bytes())
    }

    fn deserialize(data: &[u8]) -> Result<ProjectConfig, ProjectFormatError> {
        let yaml_str = std::str::from_utf8(data)
            .map_err(|e| ProjectFormatError::ParseError(format!("无效UTF-8: {}", e)))?;
        serde_yaml::from_str(yaml_str)
            .map_err(|e| ProjectFormatError::ParseError(format!("YAML解析失败: {}", e)))
    }
}

/// JSON序列化器
pub struct JsonSerializer;

impl ProjectSerializer for JsonSerializer {
    fn serialize(config: &ProjectConfig) -> Result<Vec<u8>, ProjectFormatError> {
        serde_json::to_vec_pretty(config)
            .map_err(|e| ProjectFormatError::SerializeError(format!("JSON序列化失败: {}", e)))
    }

    fn deserialize(data: &[u8]) -> Result<ProjectConfig, ProjectFormatError> {
        serde_json::from_slice(data)
            .map_err(|e| ProjectFormatError::ParseError(format!("JSON解析失败: {}", e)))
    }
}

/// Binary序列化器 (bincode)
pub struct BinarySerializer;

impl ProjectSerializer for BinarySerializer {
    fn serialize(config: &ProjectConfig) -> Result<Vec<u8>, ProjectFormatError> {
        bincode::serialize(config)
            .map_err(|e| ProjectFormatError::SerializeError(format!("Binary序列化失败: {}", e)))
    }

    fn deserialize(data: &[u8]) -> Result<ProjectConfig, ProjectFormatError> {
        bincode::deserialize(data)
            .map_err(|e| ProjectFormatError::ParseError(format!("Binary解析失败: {}", e)))
    }
}

/// 格式转换器 — 在不同格式间互转
pub struct FormatConverter;

impl FormatConverter {
    /// 将一种格式的数据转换为另一种格式
    pub fn convert(
        data: &[u8],
        from: ProjectFormat,
        to: ProjectFormat,
    ) -> Result<Vec<u8>, ProjectFormatError> {
        if from == to {
            return Ok(data.to_vec());
        }

        // 先反序列化为 ProjectConfig
        let config = match from {
            ProjectFormat::Yaml => YamlSerializer::deserialize(data)?,
            ProjectFormat::Json => JsonSerializer::deserialize(data)?,
            ProjectFormat::Binary => BinarySerializer::deserialize(data)?,
        };

        // 再序列化为目标格式
        match to {
            ProjectFormat::Yaml => YamlSerializer::serialize(&config),
            ProjectFormat::Json => JsonSerializer::serialize(&config),
            ProjectFormat::Binary => BinarySerializer::serialize(&config),
        }
    }

    /// 文件格式转换
    pub fn convert_file(source: &Path, target: &Path) -> Result<ProjectConfig, ProjectFormatError> {
        let from_format = ProjectFormat::from_extension(source).ok_or_else(|| {
            ProjectFormatError::FormatError(format!("无法识别源文件格式: {:?}", source.extension()))
        })?;
        let to_format = ProjectFormat::from_extension(target).ok_or_else(|| {
            ProjectFormatError::FormatError(format!(
                "无法识别目标文件格式: {:?}",
                target.extension()
            ))
        })?;

        let data = std::fs::read(source)
            .map_err(|e| ProjectFormatError::IoError(format!("读取源文件失败: {}", e)))?;

        let converted = Self::convert(&data, from_format, to_format)?;

        std::fs::write(target, &converted)
            .map_err(|e| ProjectFormatError::IoError(format!("写入目标文件失败: {}", e)))?;

        // 返回解析后的配置
        match to_format {
            ProjectFormat::Yaml => YamlSerializer::deserialize(&converted),
            ProjectFormat::Json => JsonSerializer::deserialize(&converted),
            ProjectFormat::Binary => BinarySerializer::deserialize(&converted),
        }
    }
}

/// 自动格式检测的项目加载器
pub struct ProjectLoader;

impl ProjectLoader {
    /// 自动检测格式并加载项目
    pub fn load_auto(path: &Path) -> Result<Project, ProjectFormatError> {
        let format = ProjectFormat::from_extension(path).ok_or_else(|| {
            ProjectFormatError::FormatError(format!("无法识别文件格式: {:?}", path.extension()))
        })?;

        let config = match format {
            ProjectFormat::Yaml => YamlSerializer::load(path)?,
            ProjectFormat::Json => JsonSerializer::load(path)?,
            ProjectFormat::Binary => BinarySerializer::load(path)?,
        };

        let mut project = Project::from_config(&config);
        project.path = Some(path.display().to_string());
        Ok(project)
    }

    /// 以指定格式保存项目
    pub fn save_as(
        project: &Project,
        path: &Path,
        format: ProjectFormat,
    ) -> Result<(), ProjectFormatError> {
        let config = project.to_config();
        match format {
            ProjectFormat::Yaml => YamlSerializer::save(&config, path),
            ProjectFormat::Json => JsonSerializer::save(&config, path),
            ProjectFormat::Binary => BinarySerializer::save(&config, path),
        }
    }
}

/// 项目格式错误
#[derive(Debug, thiserror::Error)]
pub enum ProjectFormatError {
    #[error("IO错误: {0}")]
    IoError(String),
    #[error("解析错误: {0}")]
    ParseError(String),
    #[error("序列化错误: {0}")]
    SerializeError(String),
    #[error("格式错误: {0}")]
    FormatError(String),
}

impl From<ProjectError> for ProjectFormatError {
    fn from(e: ProjectError) -> Self {
        match e {
            ProjectError::IoError(s) => ProjectFormatError::IoError(s),
            ProjectError::ParseError(s) => ProjectFormatError::ParseError(s),
            ProjectError::SerializeError(s) => ProjectFormatError::SerializeError(s),
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::project::TrackConfig;

    fn test_config() -> ProjectConfig {
        ProjectConfig {
            name: "格式测试".into(),
            sample_rate: 44100.0,
            buffer_size: 256,
            tracks: vec![TrackConfig {
                name: "鼓组".into(),
                channels: 2,
                volume: 0.8,
                pan: 0.0,
                muted: false,
                plugins: vec!["vc-compressor".into()],
            }],
            master_volume: 1.0,
        }
    }

    #[test]
    fn test_format_detection() {
        assert_eq!(
            ProjectFormat::from_extension(Path::new("test.yaml")),
            Some(ProjectFormat::Yaml)
        );
        assert_eq!(
            ProjectFormat::from_extension(Path::new("test.yml")),
            Some(ProjectFormat::Yaml)
        );
        assert_eq!(
            ProjectFormat::from_extension(Path::new("test.json")),
            Some(ProjectFormat::Json)
        );
        assert_eq!(
            ProjectFormat::from_extension(Path::new("test.daw")),
            Some(ProjectFormat::Binary)
        );
        assert_eq!(ProjectFormat::from_extension(Path::new("test.txt")), None);
    }

    #[test]
    fn test_yaml_roundtrip() {
        let config = test_config();
        let data = YamlSerializer::serialize(&config).unwrap();
        let loaded = YamlSerializer::deserialize(&data).unwrap();
        assert_eq!(loaded.name, config.name);
        assert_eq!(loaded.sample_rate, config.sample_rate);
        assert_eq!(loaded.tracks.len(), config.tracks.len());
    }

    #[test]
    fn test_json_roundtrip() {
        let config = test_config();
        let data = JsonSerializer::serialize(&config).unwrap();
        let loaded = JsonSerializer::deserialize(&data).unwrap();
        assert_eq!(loaded.name, config.name);
        assert_eq!(loaded.tracks.len(), config.tracks.len());
    }

    #[test]
    fn test_binary_roundtrip() {
        let config = test_config();
        let data = BinarySerializer::serialize(&config).unwrap();
        let loaded = BinarySerializer::deserialize(&data).unwrap();
        assert_eq!(loaded.name, config.name);
        assert_eq!(loaded.tracks.len(), config.tracks.len());
    }

    #[test]
    fn test_format_converter_yaml_to_json() {
        let config = test_config();
        let yaml_data = YamlSerializer::serialize(&config).unwrap();
        let json_data =
            FormatConverter::convert(&yaml_data, ProjectFormat::Yaml, ProjectFormat::Json).unwrap();
        let loaded = JsonSerializer::deserialize(&json_data).unwrap();
        assert_eq!(loaded.name, config.name);
    }

    #[test]
    fn test_format_converter_json_to_binary() {
        let config = test_config();
        let json_data = JsonSerializer::serialize(&config).unwrap();
        let binary_data =
            FormatConverter::convert(&json_data, ProjectFormat::Json, ProjectFormat::Binary)
                .unwrap();
        let loaded = BinarySerializer::deserialize(&binary_data).unwrap();
        assert_eq!(loaded.name, config.name);
    }

    #[test]
    fn test_format_converter_yaml_to_binary_to_json() {
        let config = test_config();
        let yaml_data = YamlSerializer::serialize(&config).unwrap();
        let binary_data =
            FormatConverter::convert(&yaml_data, ProjectFormat::Yaml, ProjectFormat::Binary)
                .unwrap();
        let json_data =
            FormatConverter::convert(&binary_data, ProjectFormat::Binary, ProjectFormat::Json)
                .unwrap();
        let loaded = JsonSerializer::deserialize(&json_data).unwrap();
        assert_eq!(loaded.name, config.name);
        assert_eq!(loaded.sample_rate, config.sample_rate);
    }

    #[test]
    fn test_binary_is_smaller() {
        let config = test_config();
        let yaml_size = YamlSerializer::serialize(&config).unwrap().len();
        let json_size = JsonSerializer::serialize(&config).unwrap().len();
        let binary_size = BinarySerializer::serialize(&config).unwrap().len();
        // Binary格式应比文本格式更紧凑
        assert!(
            binary_size < yaml_size,
            "Binary({}) should be < YAML({})",
            binary_size,
            yaml_size
        );
        assert!(
            binary_size < json_size,
            "Binary({}) should be < JSON({})",
            binary_size,
            json_size
        );
    }

    #[test]
    fn test_save_load_yaml() {
        let config = test_config();
        let tmp = std::env::temp_dir().join("test_format_save.yaml");
        YamlSerializer::save(&config, &tmp).unwrap();
        let loaded = YamlSerializer::load(&tmp).unwrap();
        assert_eq!(loaded.name, config.name);
        let _ = std::fs::remove_file(&tmp);
    }

    #[test]
    fn test_save_load_json() {
        let config = test_config();
        let tmp = std::env::temp_dir().join("test_format_save.json");
        JsonSerializer::save(&config, &tmp).unwrap();
        let loaded = JsonSerializer::load(&tmp).unwrap();
        assert_eq!(loaded.name, config.name);
        let _ = std::fs::remove_file(&tmp);
    }

    #[test]
    fn test_save_load_binary() {
        let config = test_config();
        let tmp = std::env::temp_dir().join("test_format_save.daw");
        BinarySerializer::save(&config, &tmp).unwrap();
        let loaded = BinarySerializer::load(&tmp).unwrap();
        assert_eq!(loaded.name, config.name);
        let _ = std::fs::remove_file(&tmp);
    }
}
