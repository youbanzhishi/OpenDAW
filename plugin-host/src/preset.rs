//! 预设管理 — 加载/保存/导入/导出

use std::collections::HashMap;
use std::path::Path;

use serde::{Deserialize, Serialize};

/// 预设数据
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct Preset {
    /// 预设名称
    pub name: String,
    /// 插件ID
    pub plugin_id: String,
    /// 参数值映射
    pub params: HashMap<String, f64>,
    /// 预设标签
    pub tags: Vec<String>,
}

impl Preset {
    /// 创建新预设
    pub fn new(name: &str, plugin_id: &str) -> Self {
        Self {
            name: name.to_string(),
            plugin_id: plugin_id.to_string(),
            params: HashMap::new(),
            tags: Vec::new(),
        }
    }

    /// 设置参数
    pub fn set_param(&mut self, id: &str, value: f64) {
        self.params.insert(id.to_string(), value);
    }

    /// 获取参数
    pub fn get_param(&self, id: &str) -> Option<f64> {
        self.params.get(id).copied()
    }

    /// 添加标签
    pub fn add_tag(&mut self, tag: &str) {
        if !self.tags.contains(&tag.to_string()) {
            self.tags.push(tag.to_string());
        }
    }
}

/// 预设管理器
pub struct PresetManager {
    /// 插件ID -> 预设列表
    presets: HashMap<String, Vec<Preset>>,
}

impl PresetManager {
    pub fn new() -> Self {
        Self {
            presets: HashMap::new(),
        }
    }

    /// 保存预设
    pub fn save(&mut self, preset: Preset) {
        self.presets
            .entry(preset.plugin_id.clone())
            .or_default()
            .push(preset);
    }

    /// 加载预设（按名称查找）
    pub fn load(&self, plugin_id: &str, preset_name: &str) -> Option<&Preset> {
        self.presets
            .get(plugin_id)?
            .iter()
            .find(|p| p.name == preset_name)
    }

    /// 删除预设
    pub fn delete(&mut self, plugin_id: &str, preset_name: &str) -> bool {
        if let Some(presets) = self.presets.get_mut(plugin_id) {
            let before = presets.len();
            presets.retain(|p| p.name != preset_name);
            presets.len() < before
        } else {
            false
        }
    }

    /// 列出指定插件的所有预设
    pub fn list_presets(&self, plugin_id: &str) -> Vec<String> {
        self.presets
            .get(plugin_id)
            .map(|ps| ps.iter().map(|p| p.name.clone()).collect())
            .unwrap_or_default()
    }

    /// 导出预设为JSON
    pub fn export_json(&self, plugin_id: &str, preset_name: &str) -> Option<String> {
        let preset = self.load(plugin_id, preset_name)?;
        serde_json::to_string_pretty(preset).ok()
    }

    /// 从JSON导入预设
    pub fn import_json(&mut self, json: &str) -> Result<(), String> {
        let preset: Preset =
            serde_json::from_str(json).map_err(|e| format!("JSON解析失败: {}", e))?;
        self.save(preset);
        Ok(())
    }

    /// 保存所有预设到文件
    pub fn save_to_file(&self, path: &Path) -> Result<(), std::io::Error> {
        let all_presets: Vec<&Preset> = self.presets.values().flat_map(|v| v.iter()).collect();
        let json = serde_json::to_string_pretty(&all_presets)?;
        std::fs::write(path, json)
    }

    /// 从文件加载预设
    pub fn load_from_file(&mut self, path: &Path) -> Result<(), String> {
        let content = std::fs::read_to_string(path).map_err(|e| format!("读取文件失败: {}", e))?;
        let presets: Vec<Preset> =
            serde_json::from_str(&content).map_err(|e| format!("JSON解析失败: {}", e))?;
        for preset in presets {
            self.save(preset);
        }
        Ok(())
    }

    /// 预设总数
    pub fn total_count(&self) -> usize {
        self.presets.values().map(|v| v.len()).sum()
    }
}

impl Default for PresetManager {
    fn default() -> Self {
        Self::new()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_preset_save_load() {
        let mut pm = PresetManager::new();

        let mut preset = Preset::new("温暖", "gain");
        preset.set_param("gain", 0.8);
        preset.add_tag("vocal");

        pm.save(preset);

        let loaded = pm.load("gain", "温暖").unwrap();
        assert_eq!(loaded.get_param("gain"), Some(0.8));
        assert!(loaded.tags.contains(&"vocal".to_string()));
    }

    #[test]
    fn test_preset_export_import() {
        let mut pm = PresetManager::new();
        let mut preset = Preset::new("默认", "eq");
        preset.set_param("low", 1.5);
        preset.set_param("high", 2.0);
        pm.save(preset);

        let json = pm.export_json("eq", "默认").unwrap();
        let mut pm2 = PresetManager::new();
        pm2.import_json(&json).unwrap();

        let loaded = pm2.load("eq", "默认").unwrap();
        assert_eq!(loaded.get_param("low"), Some(1.5));
        assert_eq!(loaded.get_param("high"), Some(2.0));
    }
}
