//! # 技巧包 (.omx.zip) — 跨DAW可移植技巧打包与分享
//!
//! .omx = OpenDAW Music eXchange，一个zip包包含：
//! - manifest.yaml：包元数据
//! - templates/：.omt.yaml 技巧模板文件
//! - profiles/：.omp.yaml 风格画像文件
//! - presets/：DAW特定参数映射（Ableton/Reaper/Logic/FL等）
//! - README.md：人类可读描述
//!
//! 核心设计：
//! - TechniquePackage：包数据结构
//! - DAW参数映射：将抽象ProcessingStep映射到具体DAW操作
//! - 导入导出：打包/解包 .omx.zip

use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::io::{Read, Write};

// ─── 错误类型 ──────────────────────────────────────────────

#[derive(Debug, thiserror::Error)]
pub enum PackageError {
    #[error("IO error: {0}")]
    Io(#[from] std::io::Error),
    #[error("YAML error: {0}")]
    Yaml(#[from] serde_yaml::Error),
    #[error("Zip error: {0}")]
    Zip(#[from] zip::result::ZipError),
    #[error("Invalid package: {0}")]
    Invalid(String),
    #[error("DAW mapping not found: {0}")]
    MappingNotFound(String),
}

// ─── DAW标识 ──────────────────────────────────────────────

/// 支持的目标DAW
#[derive(Debug, Clone, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum DAW {
    Ableton,
    Reaper,
    Logic,
    FLStudio,
    ProTools,
    Cubase,
    StudioOne,
    Bitwig,
    OpenDAW,
    /// 自定义DAW（用于扩展）
    Custom(String),
}

impl DAW {
    pub fn id(&self) -> &str {
        match self {
            DAW::Ableton => "ableton",
            DAW::Reaper => "reaper",
            DAW::Logic => "logic",
            DAW::FLStudio => "flstudio",
            DAW::ProTools => "protools",
            DAW::Cubase => "cubase",
            DAW::StudioOne => "studioone",
            DAW::Bitwig => "bitwig",
            DAW::OpenDAW => "opendaw",
            DAW::Custom(name) => name,
        }
    }

    pub fn display_name(&self) -> &str {
        match self {
            DAW::Ableton => "Ableton Live",
            DAW::Reaper => "REAPER",
            DAW::Logic => "Logic Pro",
            DAW::FLStudio => "FL Studio",
            DAW::ProTools => "Pro Tools",
            DAW::Cubase => "Cubase",
            DAW::StudioOne => "Studio One",
            DAW::Bitwig => "Bitwig Studio",
            DAW::OpenDAW => "OpenDAW",
            DAW::Custom(name) => name,
        }
    }

    /// 该DAW支持的效果器类型映射
    pub fn supported_effect_types(&self) -> &[&str] {
        match self {
            DAW::Reaper => &["JS", "VST2", "VST3", "AU", "CLAP"],
            DAW::Ableton => &["VST2", "VST3", "AU", "AUv3", "Built-in"],
            DAW::Logic => &["AU", "AUv3"],
            DAW::FLStudio => &["VST2", "VST3"],
            DAW::OpenDAW => &["VST3", "CLAP", "Built-in"],
            _ => &["VST2", "VST3"],
        }
    }
}

// ─── 参数映射 ──────────────────────────────────────────────

/// DAW特定参数名映射
/// 将OpenDAW抽象参数名映射到具体DAW的参数名/ID
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DAWParamMap {
    /// 目标DAW
    pub daw: DAW,
    /// 效果器名称映射：OpenDAW名 → DAW名
    pub effect_name_map: HashMap<String, String>,
    /// 参数名映射：(效果器, OpenDAW参数) → DAW参数
    pub param_name_map: HashMap<String, String>,
    /// 默认值覆盖：参数 → DAW特定默认值
    pub default_overrides: HashMap<String, f64>,
    /// DAW特定备注
    pub notes: String,
}

/// DAW预设：一组完整的参数映射 + 效果器链
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DAWPreset {
    /// 预设ID
    pub id: String,
    /// 目标DAW
    pub daw: DAW,
    /// 预设名称
    pub name: String,
    /// 描述
    pub description: String,
    /// 效果器链（DAW特定格式）
    pub chain: Vec<DAWEffectInstance>,
    /// 参数映射
    pub param_map: DAWParamMap,
}

/// DAW中的效果器实例
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DAWEffectInstance {
    /// 效果器在DAW中的标识名
    pub daw_plugin_name: String,
    /// 插件格式 (VST3/AU/JS等)
    pub format: String,
    /// 参数值：参数名 → 值
    pub params: HashMap<String, f64>,
    /// 是否旁通
    pub bypassed: bool,
}

// ─── 包清单 ──────────────────────────────────────────────

/// .omx.zip包清单
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PackageManifest {
    /// 格式版本
    pub version: String,
    /// 包ID（唯一标识）
    pub id: String,
    /// 包名称
    pub name: String,
    /// 描述
    pub description: String,
    /// 作者
    pub author: String,
    /// 标签
    pub tags: Vec<String>,
    /// 许可证
    pub license: String,
    /// 来源DAW
    pub source_daw: DAW,
    /// 支持的目标DAW列表
    pub target_daws: Vec<DAW>,
    /// 包含的模板文件列表
    pub templates: Vec<String>,
    /// 包含的风格画像文件列表
    pub profiles: Vec<String>,
    /// 包含的DAW预设列表
    pub presets: Vec<String>,
    /// 创建时间
    pub created_at: String,
    /// 更新时间
    pub updated_at: String,
}

impl PackageManifest {
    pub fn new(id: impl Into<String>, name: impl Into<String>, author: impl Into<String>) -> Self {
        Self {
            version: "1.0.0".to_string(),
            id: id.into(),
            name: name.into(),
            description: String::new(),
            author: author.into(),
            tags: Vec::new(),
            license: "MIT".to_string(),
            source_daw: DAW::OpenDAW,
            target_daws: vec![DAW::Ableton, DAW::Reaper, DAW::Logic],
            templates: Vec::new(),
            profiles: Vec::new(),
            presets: Vec::new(),
            created_at: chrono::Utc::now().to_rfc3339(),
            updated_at: chrono::Utc::now().to_rfc3339(),
        }
    }
}

// ─── 技巧包 ──────────────────────────────────────────────

/// .omx.zip技巧包完整数据结构
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TechniquePackage {
    /// 包清单
    pub manifest: PackageManifest,
    /// 技巧模板内容（文件名 → YAML内容）
    pub templates: HashMap<String, String>,
    /// 风格画像内容（文件名 → YAML内容）
    pub profiles: HashMap<String, String>,
    /// DAW预设
    pub presets: Vec<DAWPreset>,
    /// 人类可读描述
    pub readme: String,
}

impl TechniquePackage {
    /// 创建新的技巧包
    pub fn new(id: impl Into<String>, name: impl Into<String>, author: impl Into<String>) -> Self {
        Self {
            manifest: PackageManifest::new(id, name, author),
            templates: HashMap::new(),
            profiles: HashMap::new(),
            presets: Vec::new(),
            readme: String::new(),
        }
    }

    /// 添加模板
    pub fn add_template(&mut self, filename: impl Into<String>, content: impl Into<String>) {
        let fname = filename.into();
        if !fname.ends_with(".omt.yaml") {
            return;
        }
        self.templates.insert(fname.clone(), content.into());
        if !self.manifest.templates.contains(&fname) {
            self.manifest.templates.push(fname);
        }
    }

    /// 添加风格画像
    pub fn add_profile(&mut self, filename: impl Into<String>, content: impl Into<String>) {
        let fname = filename.into();
        if !fname.ends_with(".omp.yaml") {
            return;
        }
        self.profiles.insert(fname.clone(), content.into());
        if !self.manifest.profiles.contains(&fname) {
            self.manifest.profiles.push(fname);
        }
    }

    /// 添加DAW预设
    pub fn add_preset(&mut self, preset: DAWPreset) {
        if !self.manifest.target_daws.contains(&preset.daw) {
            self.manifest.target_daws.push(preset.daw.clone());
        }
        self.manifest.presets.push(preset.id.clone());
        self.presets.push(preset);
    }

    /// 导出为 .omx.zip 字节流
    pub fn to_omx_bytes(&self) -> Result<Vec<u8>, PackageError> {
        let mut buf = Vec::new();
        {
            let mut zip = zip::ZipWriter::new(std::io::Cursor::new(&mut buf));
            let options = zip::write::SimpleFileOptions::default()
                .compression_method(zip::CompressionMethod::Deflated);

            // manifest.yaml
            let manifest_yaml = serde_yaml::to_string(&self.manifest)?;
            zip.start_file("manifest.yaml", options)?;
            zip.write_all(manifest_yaml.as_bytes())?;

            // templates/
            for (fname, content) in &self.templates {
                zip.start_file(format!("templates/{fname}"), options)?;
                zip.write_all(content.as_bytes())?;
            }

            // profiles/
            for (fname, content) in &self.profiles {
                zip.start_file(format!("profiles/{fname}"), options)?;
                zip.write_all(content.as_bytes())?;
            }

            // presets/
            for preset in &self.presets {
                let preset_yaml = serde_yaml::to_string(preset)?;
                zip.start_file(format!("presets/{}.yaml", preset.id), options)?;
                zip.write_all(preset_yaml.as_bytes())?;
            }

            // README.md
            zip.start_file("README.md", options)?;
            zip.write_all(self.readme.as_bytes())?;

            zip.finish()?;
        }
        Ok(buf)
    }

    /// 从 .omx.zip 字节流导入
    pub fn from_omx_bytes(data: &[u8]) -> Result<Self, PackageError> {
        let reader = std::io::Cursor::new(data);
        let mut zip = zip::ZipArchive::new(reader)?;

        // Read manifest
        let manifest: PackageManifest = {
            let mut file = zip
                .by_name("manifest.yaml")
                .map_err(|e| PackageError::Invalid(format!("manifest.yaml not found: {e}")))?;
            let mut content = String::new();
            file.read_to_string(&mut content)?;
            serde_yaml::from_str(&content)?
        };

        let mut pkg = Self {
            manifest,
            templates: HashMap::new(),
            profiles: HashMap::new(),
            presets: Vec::new(),
            readme: String::new(),
        };

        for i in 0..zip.len() {
            let mut file = zip.by_index(i)?;
            let name = file.name().to_string();
            let mut content = String::new();
            file.read_to_string(&mut content)?;

            if name.starts_with("templates/") && name.ends_with(".omt.yaml") {
                let fname = name.trim_start_matches("templates/").to_string();
                pkg.templates.insert(fname.clone(), content);
            } else if name.starts_with("profiles/") && name.ends_with(".omp.yaml") {
                let fname = name.trim_start_matches("profiles/").to_string();
                pkg.profiles.insert(fname.clone(), content);
            } else if name.starts_with("presets/") && name.ends_with(".yaml") {
                let preset: DAWPreset = serde_yaml::from_str(&content)?;
                pkg.presets.push(preset);
            } else if name == "README.md" {
                pkg.readme = content;
            }
        }

        Ok(pkg)
    }

    /// 获取指定DAW的预设
    pub fn get_preset_for_daw(&self, daw: &DAW) -> Option<&DAWPreset> {
        self.presets.iter().find(|p| &p.daw == daw)
    }

    /// 列出所有支持的DAW
    pub fn supported_daws(&self) -> Vec<&DAW> {
        self.presets.iter().map(|p| &p.daw).collect()
    }
}

// ─── 跨DAW参数映射器 ─────────────────────────────────────

/// 将OpenDAW抽象参数映射到具体DAW参数
pub struct DAWMapper;

impl DAWMapper {
    /// 内置效果器名映射表
    const BUILTIN_MAP: &'static [(&'static str, &'static [(&'static str, &'static str)])] = &[
        (
            "EQ",
            &[
                ("Ableton", "EQ Eight"),
                ("Reaper", "ReaEQ"),
                ("Logic", "Channel EQ"),
                ("FLStudio", "Fruity Parametric EQ 2"),
                ("OpenDAW", "VC-EQ"),
            ],
        ),
        (
            "Compressor",
            &[
                ("Ableton", "Compressor"),
                ("Reaper", "ReaComp"),
                ("Logic", "Compressor"),
                ("FLStudio", "Fruity Compressor"),
                ("OpenDAW", "VC-Comp"),
            ],
        ),
        (
            "Reverb",
            &[
                ("Ableton", "Reverb"),
                ("Reaper", "ReaVerbate"),
                ("Logic", "Space Designer"),
                ("FLStudio", "Fruity Reeverb 2"),
                ("OpenDAW", "VC-Reverb"),
            ],
        ),
        (
            "Delay",
            &[
                ("Ableton", "Simple Delay"),
                ("Reaper", "ReaDelay"),
                ("Logic", "Delay Designer"),
                ("FLStudio", "Fruity Delay 3"),
                ("OpenDAW", "VC-Delay"),
            ],
        ),
        (
            "DeEsser",
            &[
                ("Ableton", "Dynamic Tube"),
                ("Reaper", "ReaXComp"),
                ("Logic", "De-Esser"),
                ("FLStudio", "Fruity Limiter"),
                ("OpenDAW", "VC-DeEsser"),
            ],
        ),
        (
            "Limiter",
            &[
                ("Ableton", "Limiter"),
                ("Reaper", "ReaLimit"),
                ("Logic", "Limiter"),
                ("FLStudio", "Fruity Limiter"),
                ("OpenDAW", "VC-Limiter"),
            ],
        ),
    ];

    /// 将抽象效果器名映射到DAW特定名
    pub fn map_effect_name(effect_type: &str, daw: &DAW) -> String {
        let daw_id = daw.id();
        for (builtin_type, mappings) in Self::BUILTIN_MAP {
            if effect_type.eq_ignore_ascii_case(builtin_type) {
                for (daw_name, plugin_name) in *mappings {
                    if daw_id == *daw_name {
                        return plugin_name.to_string();
                    }
                }
            }
        }
        // 没有内置映射，返回原名
        effect_type.to_string()
    }

    /// 生成DAW预设模板
    pub fn generate_preset_template(
        effect_type: &str,
        daw: DAW,
        abstract_params: &HashMap<String, f64>,
    ) -> DAWPreset {
        let daw_plugin = Self::map_effect_name(effect_type, &daw);
        let daw_id = daw.id();

        DAWPreset {
            id: format!("{daw_id}_{effect_type}_preset"),
            daw: daw.clone(),
            name: format!("{} {} preset", daw.display_name(), effect_type),
            description: format!(
                "Auto-mapped {effect_type} preset for {}",
                daw.display_name()
            ),
            chain: vec![DAWEffectInstance {
                daw_plugin_name: daw_plugin,
                format: daw
                    .supported_effect_types()
                    .first()
                    .unwrap_or(&"VST3")
                    .to_string(),
                params: abstract_params.clone(),
                bypassed: false,
            }],
            param_map: DAWParamMap {
                daw,
                effect_name_map: [(effect_type.to_string(), daw_plugin.clone())]
                    .into_iter()
                    .collect(),
                param_name_map: HashMap::new(),
                default_overrides: HashMap::new(),
                notes: String::new(),
            },
        }
    }
}

// ─── 单元测试 ──────────────────────────────────────────────

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_daw_effect_name_mapping() {
        assert_eq!(DAWMapper::map_effect_name("EQ", &DAW::Ableton), "EQ Eight");
        assert_eq!(DAWMapper::map_effect_name("EQ", &DAW::Reaper), "ReaEQ");
        assert_eq!(
            DAWMapper::map_effect_name("Compressor", &DAW::Logic),
            "Compressor"
        );
        assert_eq!(
            DAWMapper::map_effect_name("Reverb", &DAW::OpenDAW),
            "VC-Reverb"
        );
        assert_eq!(
            DAWMapper::map_effect_name("UnknownFX", &DAW::Ableton),
            "UnknownFX"
        );
    }

    #[test]
    fn test_package_create_and_add() {
        let mut pkg = TechniquePackage::new("test-pkg", "Test Package", "test-author");
        pkg.add_template("vocal-chain.omt.yaml", "test: template");
        pkg.add_profile("my-style.omp.yaml", "test: profile");

        assert_eq!(pkg.templates.len(), 1);
        assert_eq!(pkg.profiles.len(), 1);
        assert!(pkg
            .manifest
            .templates
            .contains(&"vocal-chain.omt.yaml".to_string()));
        assert!(pkg
            .manifest
            .profiles
            .contains(&"my-style.omp.yaml".to_string()));
    }

    #[test]
    fn test_package_rejects_invalid_extensions() {
        let mut pkg = TechniquePackage::new("test", "Test", "author");
        pkg.add_template("invalid.txt", "content"); // should be ignored
        pkg.add_profile("invalid.yaml", "content"); // should be ignored
        assert!(pkg.templates.is_empty());
        assert!(pkg.profiles.is_empty());
    }

    #[test]
    fn test_daw_preset_template() {
        let mut params = HashMap::new();
        params.insert("threshold_db".to_string(), -12.0);
        params.insert("ratio".to_string(), 4.0);

        let preset = DAWMapper::generate_preset_template("Compressor", DAW::Reaper, &params);
        assert_eq!(preset.daw, DAW::Reaper);
        assert_eq!(preset.chain[0].daw_plugin_name, "ReaComp");
        assert_eq!(preset.chain[0].params.get("threshold_db"), Some(&-12.0));
    }

    #[test]
    fn test_manifest_creation() {
        let m = PackageManifest::new("pkg-1", "My Package", "Author");
        assert_eq!(m.version, "1.0.0");
        assert_eq!(m.license, "MIT");
        assert!(m.target_daws.contains(&DAW::Ableton));
    }

    #[test]
    fn test_daw_supported_types() {
        assert!(DAW::Reaper.supported_effect_types().contains(&"VST3"));
        assert!(DAW::Logic.supported_effect_types().contains(&"AU"));
        assert!(DAW::OpenDAW.supported_effect_types().contains(&"CLAP"));
    }
}
