//! 统一参数系统 — 自动化、预设

use std::collections::HashMap;
use opendaw_extension::ParamInfo;

/// 参数管理器 — 统一管理所有插件参数
pub struct ParamManager {
    /// 参数ID -> (插件ID, 参数信息)
    params: HashMap<String, (String, ParamInfo)>,
    /// 自动化点：参数ID -> [(时间(秒), 值)]
    automation: HashMap<String, Vec<(f64, f64)>>,
}

impl ParamManager {
    pub fn new() -> Self {
        Self {
            params: HashMap::new(),
            automation: HashMap::new(),
        }
    }

    /// 注册参数
    pub fn register(&mut self, plugin_id: &str, param: ParamInfo) {
        let key = format!("{}:{}", plugin_id, param.id);
        self.params.insert(key, (plugin_id.to_string(), param));
    }

    /// 批量注册插件的所有参数
    pub fn register_plugin_params(&mut self, plugin_id: &str, params: Vec<ParamInfo>) {
        for param in params {
            self.register(plugin_id, param);
        }
    }

    /// 获取参数值
    pub fn get_param(&self, plugin_id: &str, param_id: &str) -> Option<f64> {
        let key = format!("{}:{}", plugin_id, param_id);
        self.params.get(&key).map(|(_, p)| p.value)
    }

    /// 设置参数值
    pub fn set_param(&mut self, plugin_id: &str, param_id: &str, value: f64) -> Option<f64> {
        let key = format!("{}:{}", plugin_id, param_id);
        if let Some((_, param)) = self.params.get_mut(&key) {
            let clamped = param.clamp_value(value);
            param.value = clamped;
            Some(clamped)
        } else {
            None
        }
    }

    /// 添加自动化点
    pub fn add_automation_point(&mut self, plugin_id: &str, param_id: &str, time: f64, value: f64) {
        let key = format!("{}:{}", plugin_id, param_id);
        let points = self.automation.entry(key).or_default();
        points.push((time, value));
        // 按时间排序
        points.sort_by(|a, b| a.0.partial_cmp(&b.0).unwrap());
    }

    /// 获取指定时间的自动化值（线性插值）
    pub fn get_automation_value(&self, plugin_id: &str, param_id: &str, time: f64) -> Option<f64> {
        let key = format!("{}:{}", plugin_id, param_id);
        let points = self.automation.get(&key)?;

        if points.is_empty() {
            return None;
        }

        // 在第一个点之前
        if time <= points[0].0 {
            return Some(points[0].1);
        }

        // 在最后一个点之后
        if time >= points[points.len() - 1].0 {
            return Some(points[points.len() - 1].1);
        }

        // 线性插值
        for i in 0..points.len() - 1 {
            let (t0, v0) = points[i];
            let (t1, v1) = points[i + 1];
            if time >= t0 && time <= t1 {
                let ratio = (time - t0) / (t1 - t0);
                return Some(v0 + (v1 - v0) * ratio);
            }
        }

        None
    }

    /// 列出所有参数
    pub fn list_params(&self) -> Vec<(String, String, f64)> {
        self.params
            .iter()
            .map(|(_key, (plugin_id, param))| {
                (plugin_id.clone(), param.id.clone(), param.value)
            })
            .collect()
    }

    /// 列出指定插件的所有参数
    pub fn list_plugin_params(&self, plugin_id: &str) -> Vec<ParamInfo> {
        self.params
            .iter()
            .filter(|(_, (pid, _))| pid == plugin_id)
            .map(|(_, (_, p))| p.clone())
            .collect()
    }

    /// 清除指定参数的自动化
    pub fn clear_automation(&mut self, plugin_id: &str, param_id: &str) {
        let key = format!("{}:{}", plugin_id, param_id);
        self.automation.remove(&key);
    }

    /// 参数总数
    pub fn len(&self) -> usize {
        self.params.len()
    }

    pub fn is_empty(&self) -> bool {
        self.params.is_empty()
    }
}

impl Default for ParamManager {
    fn default() -> Self {
        Self::new()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_param_manager() {
        let mut pm = ParamManager::new();
        let param = ParamInfo::new("gain", "增益", 0.0, 10.0, 1.0, "x");
        pm.register("gain-plugin", param);

        assert_eq!(pm.get_param("gain-plugin", "gain"), Some(1.0));
        pm.set_param("gain-plugin", "gain", 5.0);
        assert_eq!(pm.get_param("gain-plugin", "gain"), Some(5.0));
    }

    #[test]
    fn test_automation() {
        let mut pm = ParamManager::new();
        let param = ParamInfo::new("gain", "增益", 0.0, 10.0, 1.0, "x");
        pm.register("plugin", param);

        pm.add_automation_point("plugin", "gain", 0.0, 0.0);
        pm.add_automation_point("plugin", "gain", 1.0, 10.0);

        // t=0.5 应该是5.0（线性插值）
        assert!((pm.get_automation_value("plugin", "gain", 0.5).unwrap() - 5.0).abs() < 0.001);
        // t=0.25 应该是2.5
        assert!((pm.get_automation_value("plugin", "gain", 0.25).unwrap() - 2.5).abs() < 0.001);
    }
}
