//! 统一插件扫描器 — 发现和加载 VST3/CLAP/VC-CLI/JSFX 插件
//!
//! `PluginScanner` 负责在系统标准路径和用户指定路径中
//! 搜索所有支持格式的插件，并返回扫描结果。
//! `ScannedPlugin` 记录插件的元信息，可用于后续加载。
//!
//! # 支持的插件格式
//!
//! | 格式     | 扩展名/标识      | 说明                          |
//! |----------|------------------|-------------------------------|
//! | VST3     | .vst3            | Steinberg VST3 标准           |
//! | CLAP     | .clap            | CLAP 开放插件标准             |
//! | VC-CLI   | (可执行文件)      | OpenDAW VC-Plugin CLI 协议    |
//! | JSFX     | .jsfx            | Reaper JSFX EEL2 脚本         |
//! | LV2      | .lv2             | LV2 开放标准（预留）          |

use std::path::{Path, PathBuf};

use opendaw_extension::PluginError;

// 有条件地导入适配器
#[cfg(feature = "clap")]
use crate::clap_adapter::ClapAdapter;
use crate::vc_adapter::VcPluginAdapter;
#[cfg(feature = "vst3")]
use crate::vst3_adapter::Vst3Adapter;

use opendaw_extension::VcPlugin;

// ── 插件格式枚举 ────────────────────────────────────────────────────────

/// 插件格式
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum PluginFormat {
    /// Steinberg VST3
    Vst3,
    /// CLAP 开放标准
    Clap,
    /// OpenDAW VC-Plugin CLI
    VcCli,
    /// Reaper JSFX EEL2 脚本
    Jsfx,
    /// LV2 开放标准（预留）
    Lv2,
}

impl std::fmt::Display for PluginFormat {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            PluginFormat::Vst3 => write!(f, "VST3"),
            PluginFormat::Clap => write!(f, "CLAP"),
            PluginFormat::VcCli => write!(f, "VC-CLI"),
            PluginFormat::Jsfx => write!(f, "JSFX"),
            PluginFormat::Lv2 => write!(f, "LV2"),
        }
    }
}

// ── 扫描结果 ─────────────────────────────────────────────────────────────

/// 扫描到的插件信息
#[derive(Clone, Debug)]
pub struct ScannedPlugin {
    /// 插件唯一标识
    pub id: String,
    /// 插件名称
    pub name: String,
    /// 插件格式
    pub format: PluginFormat,
    /// 插件文件路径（对于 JSFX 是 .jsfx 文件路径，对于 VC-CLI 是目录路径）
    pub path: PathBuf,
}

impl ScannedPlugin {
    /// 创建新的扫描结果
    pub fn new(id: &str, name: &str, format: PluginFormat, path: PathBuf) -> Self {
        Self {
            id: id.to_string(),
            name: name.to_string(),
            format,
            path,
        }
    }
}

// ── 扫描统计 ─────────────────────────────────────────────────────────────

/// 扫描统计信息
#[derive(Clone, Debug, Default)]
pub struct ScanStats {
    /// 扫描的目录数
    pub directories_scanned: usize,
    /// 发现的插件数
    pub plugins_found: usize,
    /// 失败的插件数
    pub plugins_failed: usize,
    /// 各格式的发现数
    pub by_format: std::collections::HashMap<String, usize>,
}

impl std::fmt::Display for ScanStats {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(
            f,
            "扫描完成: {} 目录, {} 插件发现, {} 失败",
            self.directories_scanned, self.plugins_found, self.plugins_failed
        )
    }
}

// ── 插件扫描器 ───────────────────────────────────────────────────────────

/// 统一插件扫描器
///
/// 在系统标准路径和用户指定路径中搜索所有支持格式的插件。
///
/// # 使用方法
///
/// ```ignore
/// use plugin_host::scanner::PluginScanner;
///
/// let mut scanner = PluginScanner::new();
/// scanner.add_standard_paths();
/// scanner.add_path(PathBuf::from("/my/custom/plugins"));
///
/// let results = scanner.scan().unwrap();
/// for plugin in &results.0 {
///     println!("{} [{}]: {}", plugin.name, plugin.format, plugin.path.display());
/// }
/// ```
pub struct PluginScanner {
    /// 搜索路径列表
    search_paths: Vec<PathBuf>,
    /// 是否启用 JSFX 扫描
    include_jsfx: bool,
}

impl PluginScanner {
    /// 创建新的插件扫描器
    pub fn new() -> Self {
        Self {
            search_paths: Vec::new(),
            include_jsfx: true,
        }
    }

    /// 创建新的插件扫描器（可配置 JSFX）
    pub fn new_with_jsfx(include_jsfx: bool) -> Self {
        Self {
            search_paths: Vec::new(),
            include_jsfx,
        }
    }

    /// 添加搜索路径
    pub fn add_path(&mut self, path: PathBuf) {
        if !self.search_paths.contains(&path) {
            self.search_paths.push(path);
        }
    }

    /// 启用/禁用 JSFX 扫描
    pub fn set_jsfx_scan(&mut self, enabled: bool) {
        self.include_jsfx = enabled;
    }

    /// 添加标准系统插件路径
    ///
    /// 自动检测操作系统并添加对应的 VST3 和 CLAP 标准路径。
    pub fn add_standard_paths(&mut self) {
        let home = std::env::var("HOME")
            .or_else(|_| std::env::var("USERPROFILE"))
            .ok();

        #[cfg(target_os = "macos")]
        {
            // macOS VST3 标准路径
            self.add_path(PathBuf::from("/Library/Audio/Plug-Ins/VST3"));
            if let Some(ref h) = home {
                self.add_path(PathBuf::from(h).join("Library/Audio/Plug-Ins/VST3"));
            }

            // macOS CLAP 标准路径
            self.add_path(PathBuf::from("/Library/Audio/Plug-Ins/CLAP"));
            if let Some(ref h) = home {
                self.add_path(PathBuf::from(h).join("Library/Audio/Plug-Ins/CLAP"));
            }

            // macOS JSFX 路径
            if let Some(ref h) = home {
                self.add_path(PathBuf::from(h).join("Library/Application Support/REAPER/Effects"));
            }
        }

        #[cfg(target_os = "linux")]
        {
            // Linux VST3 标准路径
            self.add_path(PathBuf::from("/usr/lib/vst3"));
            self.add_path(PathBuf::from("/usr/local/lib/vst3"));
            if let Some(ref h) = home {
                self.add_path(PathBuf::from(h).join(".vst3"));
            }

            // Linux CLAP 标准路径
            self.add_path(PathBuf::from("/usr/lib/clap"));
            self.add_path(PathBuf::from("/usr/local/lib/clap"));
            if let Some(ref h) = home {
                self.add_path(PathBuf::from(h).join(".clap"));
            }

            // Linux JSFX 路径
            if let Some(ref h) = home {
                self.add_path(PathBuf::from(h).join(".REAPER/Effects"));
            }
        }

        #[cfg(target_os = "windows")]
        {
            // Windows VST3 标准路径
            self.add_path(PathBuf::from("C:\\Program Files\\Common Files\\VST3"));
            self.add_path(PathBuf::from("C:\\Program Files (x86)\\Common Files\\VST3"));

            // Windows CLAP 标准路径
            self.add_path(PathBuf::from("C:\\Program Files\\Common Files\\CLAP"));

            // 用户路径
            if let Ok(local_app_data) = std::env::var("LOCALAPPDATA") {
                self.add_path(PathBuf::from(local_app_data).join("Programs\\Common\\VST3"));
            }

            // Windows JSFX 路径
            if let Ok(app_data) = std::env::var("APPDATA") {
                self.add_path(PathBuf::from(app_data).join("REAPER\\Effects"));
            }
        }

        // VC-CLI 插件搜索路径
        if let Ok(vc_dir) = std::env::var("VC_AUDIOFX_DIR") {
            self.add_path(PathBuf::from(vc_dir));
        }
        self.add_path(PathBuf::from("/tmp/AudioFX"));

        // JSFX 默认搜索路径
        self.add_path(PathBuf::from("/tmp/OpenDAW/jsfx-engine/tests"));
        self.add_path(PathBuf::from("."));
    }

    /// 扫描所有路径，返回发现的插件列表
    ///
    /// 依次扫描每个搜索路径，收集所有可识别的插件信息。
    /// 失败的插件会被记录到日志但不会中断扫描。
    pub fn scan(&self) -> Result<(Vec<ScannedPlugin>, ScanStats), PluginError> {
        let mut results = Vec::new();
        let mut stats = ScanStats::default();

        for dir in &self.search_paths {
            stats.directories_scanned += 1;

            if !dir.exists() {
                continue;
            }

            // 扫描 VST3 插件
            #[cfg(feature = "vst3")]
            {
                match Vst3Adapter::scan_directory(dir) {
                    Ok(adapters) => {
                        let count = adapters.len();
                        for adapter in adapters {
                            results.push(ScannedPlugin::new(
                                adapter.plugin_id(),
                                adapter.plugin_name(),
                                PluginFormat::Vst3,
                                adapter.path().to_path_buf(),
                            ));
                        }
                        *stats.by_format.entry("VST3".to_string()).or_insert(0) += count;
                        stats.plugins_found += count;
                    }
                    Err(e) => {
                        log::warn!("VST3 扫描失败 {}: {}", dir.display(), e);
                        stats.plugins_failed += 1;
                    }
                }
            }

            // 扫描 CLAP 插件
            #[cfg(feature = "clap")]
            {
                match ClapAdapter::scan_directory(dir) {
                    Ok(adapters) => {
                        let count = adapters.len();
                        for adapter in adapters {
                            results.push(ScannedPlugin::new(
                                adapter.plugin_id(),
                                adapter.plugin_name(),
                                PluginFormat::Clap,
                                adapter.path().to_path_buf(),
                            ));
                        }
                        *stats.by_format.entry("CLAP".to_string()).or_insert(0) += count;
                        stats.plugins_found += count;
                    }
                    Err(e) => {
                        log::warn!("CLAP 扫描失败 {}: {}", dir.display(), e);
                        stats.plugins_failed += 1;
                    }
                }
            }

            // 扫描 VC-CLI 插件（始终可用）
            Self::scan_vc_cli_directory(dir, &mut results, &mut stats);

            // 扫描 JSFX 插件
            if self.include_jsfx {
                Self::scan_jsfx_directory(dir, &mut results, &mut stats);
            }

            // 扫描 VST3 文件（非 feature 门控的文件发现）
            #[cfg(not(feature = "vst3"))]
            {
                Self::scan_vst3_files(dir, &mut results, &mut stats);
            }

            // 扫描 CLAP 文件（非 feature 门控的文件发现）
            #[cfg(not(feature = "clap"))]
            {
                Self::scan_clap_files(dir, &mut results, &mut stats);
            }
        }

        log::info!("{}", stats);
        Ok((results, stats))
    }

    /// 加载指定插件为 VcPlugin 实例
    ///
    /// 根据插件格式选择对应的适配器进行加载。
    /// 返回的 `Box<dyn VcPlugin>` 可直接传给 `PluginHost::load_plugin()`。
    pub fn load(&self, info: &ScannedPlugin) -> Result<Box<dyn VcPlugin>, PluginError> {
        match info.format {
            PluginFormat::Vst3 => {
                #[cfg(feature = "vst3")]
                {
                    let adapter = Vst3Adapter::from_file(&info.path)?;
                    Ok(Box::new(adapter))
                }
                #[cfg(not(feature = "vst3"))]
                {
                    Err(PluginError::InitFailed(format!(
                        "VST3 支持未启用，请启用 'vst3' feature: {}",
                        info.path.display()
                    )))
                }
            }
            PluginFormat::Clap => {
                #[cfg(feature = "clap")]
                {
                    let adapter = ClapAdapter::from_file(&info.path)?;
                    Ok(Box::new(adapter))
                }
                #[cfg(not(feature = "clap"))]
                {
                    Err(PluginError::InitFailed(format!(
                        "CLAP 支持未启用，请启用 'clap' feature: {}",
                        info.path.display()
                    )))
                }
            }
            PluginFormat::VcCli => {
                let adapter = VcPluginAdapter::from_binary(&info.path)?;
                Ok(Box::new(adapter))
            }
            PluginFormat::Jsfx => {
                // 动态加载 jsfx-engine
                #[cfg(feature = "jsfx")]
                {
                    use jsfx_engine::JsfxPlugin;
                    let plugin = JsfxPlugin::from_file(&info.path)
                        .map_err(|e| PluginError::InitFailed(format!("JSFX 加载失败: {}", e)))?;
                    Ok(Box::new(plugin))
                }
                #[cfg(not(feature = "jsfx"))]
                {
                    Err(PluginError::InitFailed(format!(
                        "JSFX 支持未启用，请启用 'jsfx' feature: {}",
                        info.path.display()
                    )))
                }
            }
            PluginFormat::Lv2 => Err(PluginError::InitFailed("LV2 格式暂不支持".to_string())),
        }
    }

    /// 获取搜索路径列表
    pub fn search_paths(&self) -> &[PathBuf] {
        &self.search_paths
    }

    // ── 内部方法 ──────────────────────────────────────────────────────

    /// 扫描 VC-CLI 插件目录
    fn scan_vc_cli_directory(dir: &Path, results: &mut Vec<ScannedPlugin>, stats: &mut ScanStats) {
        if !dir.exists() {
            return;
        }

        let entries = match std::fs::read_dir(dir) {
            Ok(e) => e,
            Err(_) => return,
        };

        for entry in entries.flatten() {
            let path = entry.path();
            if !path.is_dir() {
                continue;
            }

            // 查找 CLI-Standalone 二进制
            let dir_name = path
                .file_name()
                .map(|n| n.to_string_lossy().to_string())
                .unwrap_or_default();

            // VC-CLI 插件目录通常名为 VC-XXX 或符合 CLI-Standalone 模式
            if dir_name.starts_with("VC-") {
                let binary_name = format!("{}-CLI-Standalone", dir_name);
                let binary_path = path.join(&binary_name);

                if binary_path.exists() {
                    let id = dir_name.to_lowercase().replace(' ', "-");
                    results.push(ScannedPlugin::new(
                        &id,
                        &dir_name,
                        PluginFormat::VcCli,
                        path,
                    ));
                    *stats.by_format.entry("VC-CLI".to_string()).or_insert(0) += 1;
                    stats.plugins_found += 1;
                }
            }
        }
    }

    /// 扫描 JSFX 目录
    fn scan_jsfx_directory(dir: &Path, results: &mut Vec<ScannedPlugin>, stats: &mut ScanStats) {
        if !dir.exists() {
            return;
        }

        let entries = match std::fs::read_dir(dir) {
            Ok(e) => e,
            Err(_) => return,
        };

        for entry in entries.flatten() {
            let path = entry.path();

            // 检查是否是 .jsfx 文件
            if path.is_file() {
                if let Some(ext) = path.extension() {
                    if ext == "jsfx" {
                        let name = path
                            .file_stem()
                            .map(|s| s.to_string_lossy().to_string())
                            .unwrap_or_default();
                        let id = format!("jsfx-{}", name.to_lowercase().replace(' ', "-"));

                        results.push(ScannedPlugin::new(&id, &name, PluginFormat::Jsfx, path));
                        *stats.by_format.entry("JSFX".to_string()).or_insert(0) += 1;
                        stats.plugins_found += 1;
                    }
                }
            }
        }
    }

    /// 扫描 VST3 文件（轻量级文件发现，不加载动态库）
    ///
    /// 当 vst3 feature 未启用时，仅发现 .vst3 文件/目录，
    /// 不尝试加载插件。
    #[cfg(not(feature = "vst3"))]
    fn scan_vst3_files(dir: &Path, results: &mut Vec<ScannedPlugin>, stats: &mut ScanStats) {
        if !dir.exists() {
            return;
        }

        let entries = match std::fs::read_dir(dir) {
            Ok(e) => e,
            Err(_) => return,
        };

        for entry in entries.flatten() {
            let path = entry.path();
            let is_vst3 = path.extension().map(|e| e == "vst3").unwrap_or(false);

            if is_vst3 {
                let name = path
                    .file_stem()
                    .map(|s| s.to_string_lossy().to_string())
                    .unwrap_or_default();
                let id = name.to_lowercase().replace(' ', "-");

                results.push(ScannedPlugin::new(&id, &name, PluginFormat::Vst3, path));
                *stats.by_format.entry("VST3".to_string()).or_insert(0) += 1;
                stats.plugins_found += 1;
            }
        }
    }

    /// 扫描 CLAP 文件（轻量级文件发现，不加载动态库）
    ///
    /// 当 clap feature 未启用时，仅发现 .clap 文件/目录，
    /// 不尝试加载插件。
    #[cfg(not(feature = "clap"))]
    fn scan_clap_files(dir: &Path, results: &mut Vec<ScannedPlugin>, stats: &mut ScanStats) {
        if !dir.exists() {
            return;
        }

        let entries = match std::fs::read_dir(dir) {
            Ok(e) => e,
            Err(_) => return,
        };

        for entry in entries.flatten() {
            let path = entry.path();
            let is_clap = path.extension().map(|e| e == "clap").unwrap_or(false);

            if is_clap {
                let name = path
                    .file_stem()
                    .map(|s| s.to_string_lossy().to_string())
                    .unwrap_or_default();
                let id = name.to_lowercase().replace(' ', "-");

                results.push(ScannedPlugin::new(&id, &name, PluginFormat::Clap, path));
                *stats.by_format.entry("CLAP".to_string()).or_insert(0) += 1;
                stats.plugins_found += 1;
            }
        }
    }
}

impl Default for PluginScanner {
    fn default() -> Self {
        Self::new()
    }
}

// ── 单元测试 ─────────────────────────────────────────────────────────────

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_scanner_new() {
        let scanner = PluginScanner::new();
        assert!(scanner.search_paths().is_empty());
        assert!(scanner.include_jsfx);
    }

    #[test]
    fn test_scanner_add_path() {
        let mut scanner = PluginScanner::new();
        scanner.add_path(PathBuf::from("/test/path"));
        assert_eq!(scanner.search_paths().len(), 1);

        // 重复路径不应添加
        scanner.add_path(PathBuf::from("/test/path"));
        assert_eq!(scanner.search_paths().len(), 1);
    }

    #[test]
    fn test_scanner_jsfx_toggle() {
        let mut scanner = PluginScanner::new();
        assert!(scanner.include_jsfx);

        scanner.set_jsfx_scan(false);
        assert!(!scanner.include_jsfx);

        scanner.set_jsfx_scan(true);
        assert!(scanner.include_jsfx);
    }

    #[test]
    fn test_scanned_plugin_creation() {
        let plugin = ScannedPlugin::new(
            "surge",
            "Surge",
            PluginFormat::Vst3,
            PathBuf::from("/usr/lib/vst3/Surge.vst3"),
        );
        assert_eq!(plugin.id, "surge");
        assert_eq!(plugin.name, "Surge");
        assert_eq!(plugin.format, PluginFormat::Vst3);
    }

    #[test]
    fn test_scanned_plugin_jsfx() {
        let plugin = ScannedPlugin::new(
            "jsfx-my-effect",
            "My Effect",
            PluginFormat::Jsfx,
            PathBuf::from("/path/to/effect.jsfx"),
        );
        assert_eq!(plugin.id, "jsfx-my-effect");
        assert_eq!(plugin.format, PluginFormat::Jsfx);
    }

    #[test]
    fn test_plugin_format_display() {
        assert_eq!(format!("{}", PluginFormat::Vst3), "VST3");
        assert_eq!(format!("{}", PluginFormat::Clap), "CLAP");
        assert_eq!(format!("{}", PluginFormat::VcCli), "VC-CLI");
        assert_eq!(format!("{}", PluginFormat::Jsfx), "JSFX");
        assert_eq!(format!("{}", PluginFormat::Lv2), "LV2");
    }

    #[test]
    fn test_scan_stats_display() {
        let mut stats = ScanStats::default();
        stats.directories_scanned = 5;
        stats.plugins_found = 10;
        stats.plugins_failed = 1;
        let s = format!("{}", stats);
        assert!(s.contains("5 目录"));
        assert!(s.contains("10 插件"));
        assert!(s.contains("1 失败"));
    }

    #[test]
    fn test_scan_nonexistent_directory() {
        let scanner = PluginScanner::new();
        let (results, stats) = scanner.scan().unwrap();
        assert!(results.is_empty());
        assert_eq!(stats.plugins_found, 0);
    }

    #[test]
    fn test_load_without_feature() {
        let scanner = PluginScanner::new();
        let plugin = ScannedPlugin::new(
            "test",
            "Test",
            PluginFormat::Vst3,
            PathBuf::from("/tmp/test.vst3"),
        );

        // 无 vst3 feature 时应返回错误
        #[cfg(not(feature = "vst3"))]
        {
            let result = scanner.load(&plugin);
            assert!(result.is_err());
        }

        let clap_plugin = ScannedPlugin::new(
            "test",
            "Test",
            PluginFormat::Clap,
            PathBuf::from("/tmp/test.clap"),
        );

        // 无 clap feature 时应返回错误
        #[cfg(not(feature = "clap"))]
        {
            let result = scanner.load(&clap_plugin);
            assert!(result.is_err());
        }
    }

    #[test]
    fn test_load_lv2_unsupported() {
        let scanner = PluginScanner::new();
        let plugin = ScannedPlugin::new(
            "test",
            "Test",
            PluginFormat::Lv2,
            PathBuf::from("/tmp/test.lv2"),
        );
        let result = scanner.load(&plugin);
        assert!(result.is_err());
    }
}
