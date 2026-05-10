//! JSFX文件加载器
//!
//! 提供从文件或源码字符串加载JSFX插件的功能
//! 支持批量扫描和元信息快速提取

use std::fs;
use std::io;
use std::path::Path;

use crate::adapter::JsfxPlugin;
use crate::ast::{JsfxProgram, SliderDef};
use crate::error::JsfxError;
use crate::parser::JsfxParser;
use crate::VcPlugin;

/// 加载JSFX文件
///
/// # Arguments
/// * `path` - .jsfx文件路径
///
/// # Returns
/// * 成功返回JsfxPlugin实例
/// * 失败返回JsfxError
pub fn load_jsfx_file(path: &Path) -> Result<JsfxPlugin, JsfxError> {
    if !path.exists() {
        return Err(JsfxError::Io(io::Error::new(
            io::ErrorKind::NotFound,
            format!("JSFX文件不存在: {:?}", path),
        )));
    }

    let source = fs::read_to_string(path).map_err(|e| JsfxError::Io(e))?;

    let name = path
        .file_stem()
        .and_then(|s| s.to_str())
        .unwrap_or("unknown")
        .to_string();

    load_jsfx_source(&source, &name)
}

/// 从源码字符串加载JSFX
///
/// # Arguments
/// * `source` - JSFX源码内容
/// * `name` - 插件名称（用于错误报告）
///
/// # Returns
/// * 成功返回JsfxPlugin实例
/// * 失败返回JsfxError
pub fn load_jsfx_source(source: &str, name: &str) -> Result<JsfxPlugin, JsfxError> {
    JsfxPlugin::from_source(source, name)
}

/// 扫描目录下所有JSFX文件
///
/// # Arguments
/// * `dir` - 要扫描的目录路径
///
/// # Returns
/// * 成功返回JsfxPlugin实例Vec
pub fn scan_jsfx_directory(dir: &Path) -> Result<Vec<JsfxPlugin>, JsfxError> {
    JsfxPlugin::scan_directory(dir)
}

/// 解析JSFX源码并返回程序结构（不创建Plugin）
///
/// 适用于只需要检查源码结构而不创建完整插件的场景
pub fn parse_jsfx_source(source: &str) -> Result<JsfxProgram, JsfxError> {
    JsfxParser::parse(source)
}

/// 验证JSFX文件是否有效
pub fn validate_jsfx_file(path: &Path) -> Result<String, JsfxError> {
    let plugin = load_jsfx_file(path)?;
    Ok(plugin.plugin_name().to_string())
}

/// 获取JSFX文件元信息（不完整加载）
///
/// 适用于批量扫描场景，比完整加载更高效
pub struct JsfxMeta {
    /// 插件描述
    pub desc: String,
    /// 标签列表
    pub tags: Vec<String>,
    /// Slider参数定义
    pub sliders: Vec<SliderDef>,
    /// 文件路径
    pub path: std::path::PathBuf,
    /// 是否有@init块
    pub has_init: bool,
    /// 是否有@sample块
    pub has_sample: bool,
    /// 是否有@block块
    pub has_block: bool,
    /// 是否有@gfx块
    pub has_gfx: bool,
    /// 是否有@serialize块
    pub has_serialize: bool,
    /// 是否有@slider块
    pub has_slider: bool,
    /// 用户自定义函数数量
    pub function_count: usize,
}

impl JsfxMeta {
    /// 从文件加载元信息（快速扫描）
    pub fn from_file(path: &Path) -> Option<Self> {
        let source = fs::read_to_string(path).ok()?;
        let program = JsfxParser::parse(&source).ok()?;

        Some(Self {
            desc: program.desc,
            tags: program.tags,
            sliders: program.sliders,
            path: path.to_path_buf(),
            has_init: program.init_block.is_some(),
            has_sample: program.sample_block.is_some(),
            has_block: program.block_block.is_some(),
            has_gfx: program.gfx_block.is_some(),
            has_serialize: program.serialize_block.is_some(),
            has_slider: program.slider_block.is_some(),
            function_count: program.functions.len(),
        })
    }

    /// 从源码加载元信息
    pub fn from_source(source: &str, path: &Path) -> Option<Self> {
        let program = JsfxParser::parse(source).ok()?;

        Some(Self {
            desc: program.desc,
            tags: program.tags,
            sliders: program.sliders,
            path: path.to_path_buf(),
            has_init: program.init_block.is_some(),
            has_sample: program.sample_block.is_some(),
            has_block: program.block_block.is_some(),
            has_gfx: program.gfx_block.is_some(),
            has_serialize: program.serialize_block.is_some(),
            has_slider: program.slider_block.is_some(),
            function_count: program.functions.len(),
        })
    }
}

/// 扫描目录并收集所有JSFX元信息
pub fn scan_jsfx_directory_meta(dir: &Path) -> Vec<JsfxMeta> {
    let mut metas = Vec::new();

    if !dir.exists() {
        return metas;
    }

    if let Ok(entries) = fs::read_dir(dir) {
        for entry in entries.flatten() {
            let path = entry.path();
            if path.extension().and_then(|e| e.to_str()) == Some("jsfx") {
                if let Some(meta) = JsfxMeta::from_file(&path) {
                    metas.push(meta);
                }
            }
        }
    }

    metas
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_load_source() {
        let source = r#"
desc:Test Gain
slider1:0<-150,150,0.1>Gain (dB)

@slider
gain = 2^(slider1/6);

@sample
spl0 *= gain;
spl1 *= gain;
"#;
        let plugin = load_jsfx_source(source, "test-gain").unwrap();
        assert_eq!(plugin.plugin_name(), "Test Gain");
    }

    #[test]
    fn test_parse_source() {
        let source = r#"
desc:Test Plugin
slider1:1<0,10,0.1>Test

@sample
spl0 = spl0 * slider1;
"#;
        let program = parse_jsfx_source(source).unwrap();
        assert_eq!(program.desc, "Test Plugin");
        assert_eq!(program.sliders.len(), 1);
        assert!(program.sample_block.is_some());
    }

    #[test]
    fn test_meta_from_source() {
        let source = r#"
desc:Meta Test
tags:test audio
slider1:1<0,10,0.1>Value

@init
x = 0;

@sample
spl0 = x;
"#;
        let meta = JsfxMeta::from_source(source, Path::new("test.jsfx")).unwrap();
        assert_eq!(meta.desc, "Meta Test");
        assert_eq!(meta.tags.len(), 2);
        assert!(meta.has_init);
        assert!(meta.has_sample);
        assert!(!meta.has_gfx);
        assert!(!meta.has_serialize);
        assert!(!meta.has_slider);
    }
}
