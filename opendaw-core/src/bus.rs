//! 多级Bus — 音频总线系统 (Track→Bus→Master层级)
//!
//! - Bus: 音频总线，支持多种类型
//! - BusRouter: 灵活的路由拓扑
//! - 预置模板：2-bus, 5-bus

use std::collections::HashMap;

use serde::{Deserialize, Serialize};

/// 总线类型（扩展版，包含Sidechain）
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum BusType {
    /// 音频总线 — 通用音频路由
    Audio,
    /// MIDI总线 — MIDI信号路由
    Midi,
    /// 辅助发送总线 — 效果器发送
    Aux,
    /// 侧链总线 — 侧链信号路由
    Sidechain,
    /// 主输出总线
    Master,
    /// 编组总线
    Group,
}

impl BusType {
    /// 类型描述
    pub fn name(&self) -> &'static str {
        match self {
            BusType::Audio => "Audio",
            BusType::Midi => "MIDI",
            BusType::Aux => "Aux",
            BusType::Sidechain => "Sidechain",
            BusType::Master => "Master",
            BusType::Group => "Group",
        }
    }
}

/// 总线配置
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct BusConfig {
    /// 总线名称
    pub name: String,
    /// 总线类型
    pub bus_type: BusType,
    /// 声道数
    pub channels: usize,
    /// 默认音量
    pub volume: f64,
    /// 默认声像
    pub pan: f64,
    /// 是否静音
    pub muted: bool,
    /// 是否独奏
    pub solo: bool,
}

/// 总线 — 音频路由节点
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Bus {
    /// 唯一ID
    pub id: String,
    /// 总线名称
    pub name: String,
    /// 总线类型
    pub bus_type: BusType,
    /// 声道数
    pub channels: usize,
    /// 音量 (0.0 - 2.0)
    pub volume: f64,
    /// 声像 (-1.0 - 1.0)
    pub pan: f64,
    /// 是否静音
    pub muted: bool,
    /// 是否独奏
    pub solo: bool,
    /// 输入增益
    pub input_gain: f64,
    /// 发送列表：目标总线ID → 发送量
    pub sends: HashMap<String, f64>,
    /// 效果器插件链
    pub plugin_chain: Vec<String>,
    /// 信号电平（左/右）
    #[serde(skip)]
    pub level: (f32, f32),
}

impl Bus {
    /// 创建新的总线
    pub fn new(id: &str, name: &str, bus_type: BusType, channels: usize) -> Self {
        Self {
            id: id.to_string(),
            name: name.to_string(),
            bus_type,
            channels,
            volume: 1.0,
            pan: 0.0,
            muted: false,
            solo: false,
            input_gain: 1.0,
            sends: HashMap::new(),
            plugin_chain: Vec::new(),
            level: (0.0, 0.0),
        }
    }

    /// 创建主输出总线
    pub fn master(id: &str) -> Self {
        Self::new(id, "Master", BusType::Master, 2)
    }

    /// 创建辅助总线
    pub fn aux(id: &str, name: &str) -> Self {
        Self::new(id, name, BusType::Aux, 2)
    }

    /// 创建编组总线
    pub fn group(id: &str, name: &str) -> Self {
        Self::new(id, name, BusType::Group, 2)
    }

    /// 添加发送
    pub fn add_send(&mut self, target_bus_id: &str, amount: f64) {
        self.sends.insert(target_bus_id.to_string(), amount);
    }

    /// 移除发送
    pub fn remove_send(&mut self, target_bus_id: &str) {
        self.sends.remove(target_bus_id);
    }

    /// 设置发送量
    pub fn set_send_amount(&mut self, target_bus_id: &str, amount: f64) {
        if let Some(send) = self.sends.get_mut(target_bus_id) {
            *send = amount;
        }
    }

    /// 添加效果器到链
    pub fn add_plugin(&mut self, plugin_name: &str) {
        self.plugin_chain.push(plugin_name.to_string());
    }

    /// 移除效果器
    pub fn remove_plugin(&mut self, index: usize) {
        if index < self.plugin_chain.len() {
            self.plugin_chain.remove(index);
        }
    }

    /// 更新信号电平
    pub fn update_level(&mut self, left: f32, right: f32) {
        self.level = (left, right);
    }

    /// 从配置创建
    pub fn from_config(id: &str, config: &BusConfig) -> Self {
        Self {
            id: id.to_string(),
            name: config.name.clone(),
            bus_type: config.bus_type,
            channels: config.channels,
            volume: config.volume,
            pan: config.pan,
            muted: config.muted,
            solo: config.solo,
            input_gain: 1.0,
            sends: HashMap::new(),
            plugin_chain: Vec::new(),
            level: (0.0, 0.0),
        }
    }
}

/// 路由连接 — 从源到目标的信号路径
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RouteConnection {
    /// 源ID（轨道或总线）
    pub source_id: String,
    /// 目标ID（总线）
    pub target_id: String,
    /// 路由增益
    pub gain: f64,
    /// 是否启用
    pub enabled: bool,
}

/// 总线路由器 — 管理灵活的路由拓扑
pub struct BusRouter {
    /// 所有总线
    buses: HashMap<String, Bus>,
    /// 路由连接
    routes: Vec<RouteConnection>,
    /// 延迟补偿表（总线ID → 延迟样本数）
    latency_compensation: HashMap<String, usize>,
}

impl BusRouter {
    /// 创建新的总线路由器
    pub fn new() -> Self {
        let mut router = Self {
            buses: HashMap::new(),
            routes: Vec::new(),
            latency_compensation: HashMap::new(),
        };
        // 默认创建Master总线
        let master = Bus::master("master");
        router.buses.insert("master".to_string(), master);
        router
    }

    /// 添加总线
    pub fn add_bus(&mut self, bus: Bus) {
        self.buses.insert(bus.id.clone(), bus);
    }

    /// 移除总线
    pub fn remove_bus(&mut self, id: &str) -> Option<Bus> {
        // 同时移除相关路由
        self.routes
            .retain(|r| r.source_id != id && r.target_id != id);
        self.buses.remove(id)
    }

    /// 获取总线
    pub fn get_bus(&self, id: &str) -> Option<&Bus> {
        self.buses.get(id)
    }

    /// 获取总线可变引用
    pub fn get_bus_mut(&mut self, id: &str) -> Option<&mut Bus> {
        self.buses.get_mut(id)
    }

    /// 添加路由连接
    pub fn add_route(&mut self, source_id: &str, target_id: &str, gain: f64) {
        // 检查是否已存在
        let exists = self
            .routes
            .iter()
            .any(|r| r.source_id == source_id && r.target_id == target_id);
        if !exists {
            self.routes.push(RouteConnection {
                source_id: source_id.to_string(),
                target_id: target_id.to_string(),
                gain,
                enabled: true,
            });
        }
    }

    /// 移除路由连接
    pub fn remove_route(&mut self, source_id: &str, target_id: &str) {
        self.routes
            .retain(|r| !(r.source_id == source_id && r.target_id == target_id));
    }

    /// 设置路由增益
    pub fn set_route_gain(&mut self, source_id: &str, target_id: &str, gain: f64) {
        if let Some(route) = self
            .routes
            .iter_mut()
            .find(|r| r.source_id == source_id && r.target_id == target_id)
        {
            route.gain = gain;
        }
    }

    /// 启用/禁用路由
    pub fn set_route_enabled(&mut self, source_id: &str, target_id: &str, enabled: bool) {
        if let Some(route) = self
            .routes
            .iter_mut()
            .find(|r| r.source_id == source_id && r.target_id == target_id)
        {
            route.enabled = enabled;
        }
    }

    /// 获取指定总线的所有输入源
    pub fn get_inputs(&self, target_id: &str) -> Vec<&RouteConnection> {
        self.routes
            .iter()
            .filter(|r| r.target_id == target_id && r.enabled)
            .collect()
    }

    /// 获取指定总线的所有输出目标
    pub fn get_outputs(&self, source_id: &str) -> Vec<&RouteConnection> {
        self.routes
            .iter()
            .filter(|r| r.source_id == source_id && r.enabled)
            .collect()
    }

    /// 设置延迟补偿
    pub fn set_latency_compensation(&mut self, bus_id: &str, samples: usize) {
        self.latency_compensation
            .insert(bus_id.to_string(), samples);
    }

    /// 获取延迟补偿
    pub fn get_latency_compensation(&self, bus_id: &str) -> usize {
        self.latency_compensation.get(bus_id).copied().unwrap_or(0)
    }

    /// 获取总线的完整信号链路（从轨道到Master的路径）
    pub fn get_signal_chain(&self, source_id: &str) -> Vec<String> {
        let mut chain = vec![source_id.to_string()];
        let mut current = source_id;

        // 最多遍历20层防止循环
        for _ in 0..20 {
            let outputs = self.get_outputs(current);
            if outputs.is_empty() {
                break;
            }
            // 取第一个启用的输出
            if let Some(route) = outputs.first() {
                chain.push(route.target_id.clone());
                current = &route.target_id;
            } else {
                break;
            }
        }

        chain
    }

    /// 总线数量
    pub fn bus_count(&self) -> usize {
        self.buses.len()
    }

    /// 路由数量
    pub fn route_count(&self) -> usize {
        self.routes.len()
    }

    /// 列出所有总线
    pub fn list_buses(&self) -> Vec<(&str, &BusType, &str)> {
        self.buses
            .values()
            .map(|b| (b.id.as_str(), &b.bus_type, b.name.as_str()))
            .collect()
    }

    /// 检测路由循环
    pub fn detect_cycle(&self) -> Option<Vec<String>> {
        // 简单的DFS循环检测
        for bus_id in self.buses.keys() {
            let mut visited = Vec::new();
            if self.dfs_cycle(bus_id, &mut visited) {
                return Some(visited);
            }
        }
        None
    }

    fn dfs_cycle(&self, current: &str, path: &mut Vec<String>) -> bool {
        if path.contains(&current.to_string()) {
            path.push(current.to_string());
            return true;
        }
        path.push(current.to_string());

        for route in self.get_outputs(current) {
            if self.dfs_cycle(&route.target_id, path) {
                return true;
            }
        }

        path.pop();
        false
    }
}

impl Default for BusRouter {
    fn default() -> Self {
        Self::new()
    }
}

// ========================================================================
// 预置模板
// ========================================================================

/// 总线模板
pub struct BusTemplate;

impl BusTemplate {
    /// 2-bus模板：单混响 + 单延迟
    pub fn two_bus() -> BusRouter {
        let mut router = BusRouter::new();

        // 混响总线
        let reverb_bus = Bus::aux("aux_reverb", "Reverb");
        router.add_bus(reverb_bus);

        // 延迟总线
        let delay_bus = Bus::aux("aux_delay", "Delay");
        router.add_bus(delay_bus);

        // Aux → Master
        router.add_route("aux_reverb", "master", 1.0);
        router.add_route("aux_delay", "master", 1.0);

        router
    }

    /// 5-bus模板：标准混音模板
    pub fn five_bus() -> BusRouter {
        let mut router = BusRouter::new();

        // 编组总线
        let drums_group = Bus::group("group_drums", "Drums");
        router.add_bus(drums_group);

        let instruments_group = Bus::group("group_instruments", "Instruments");
        router.add_bus(instruments_group);

        let vocals_group = Bus::group("group_vocals", "Vocals");
        router.add_bus(vocals_group);

        // 效果器总线
        let reverb_bus = Bus::aux("aux_reverb", "Reverb");
        router.add_bus(reverb_bus);

        let delay_bus = Bus::aux("aux_delay", "Delay");
        router.add_bus(delay_bus);

        // 编组 → Master
        router.add_route("group_drums", "master", 1.0);
        router.add_route("group_instruments", "master", 1.0);
        router.add_route("group_vocals", "master", 1.0);

        // 效果器 → Master
        router.add_route("aux_reverb", "master", 1.0);
        router.add_route("aux_delay", "master", 1.0);

        router
    }

    /// 自定义模板：根据配置创建
    pub fn custom(groups: &[(&str, &str)], auxes: &[(&str, &str)]) -> BusRouter {
        let mut router = BusRouter::new();

        for (id, name) in groups {
            let bus = Bus::group(id, name);
            router.add_bus(bus);
            router.add_route(id, "master", 1.0);
        }

        for (id, name) in auxes {
            let bus = Bus::aux(id, name);
            router.add_bus(bus);
            router.add_route(id, "master", 1.0);
        }

        router
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_bus_creation() {
        let bus = Bus::new("bus_1", "Vocals Bus", BusType::Audio, 2);
        assert_eq!(bus.id, "bus_1");
        assert_eq!(bus.name, "Vocals Bus");
        assert_eq!(bus.bus_type, BusType::Audio);
        assert!((bus.volume - 1.0).abs() < 1e-10);
        assert!(!bus.muted);
    }

    #[test]
    fn test_bus_master() {
        let bus = Bus::master("master");
        assert_eq!(bus.bus_type, BusType::Master);
        assert_eq!(bus.channels, 2);
    }

    #[test]
    fn test_bus_sends() {
        let mut bus = Bus::new("track_1", "Track 1", BusType::Audio, 2);
        bus.add_send("aux_reverb", 0.5);
        bus.add_send("aux_delay", 0.3);

        assert_eq!(bus.sends.len(), 2);
        assert!((bus.sends["aux_reverb"] - 0.5).abs() < 1e-10);

        bus.set_send_amount("aux_reverb", 0.7);
        assert!((bus.sends["aux_reverb"] - 0.7).abs() < 1e-10);

        bus.remove_send("aux_delay");
        assert_eq!(bus.sends.len(), 1);
    }

    #[test]
    fn test_bus_plugins() {
        let mut bus = Bus::new("bus_1", "Vocals", BusType::Audio, 2);
        bus.add_plugin("vc-eq");
        bus.add_plugin("vc-compressor");
        bus.add_plugin("vc-reverb");

        assert_eq!(bus.plugin_chain.len(), 3);

        bus.remove_plugin(1);
        assert_eq!(bus.plugin_chain.len(), 2);
        assert_eq!(bus.plugin_chain[1], "vc-reverb");
    }

    #[test]
    fn test_bus_router_basic() {
        let mut router = BusRouter::new();

        let aux = Bus::aux("aux_reverb", "Reverb");
        router.add_bus(aux);

        router.add_route("track_0", "aux_reverb", 0.5);
        router.add_route("aux_reverb", "master", 1.0);

        assert_eq!(router.bus_count(), 2); // master + aux_reverb
        assert_eq!(router.route_count(), 2);
    }

    #[test]
    fn test_bus_router_signal_chain() {
        let mut router = BusRouter::new();

        let group = Bus::group("group_drums", "Drums");
        router.add_bus(group);

        router.add_route("track_0", "group_drums", 1.0);
        router.add_route("group_drums", "master", 1.0);

        let chain = router.get_signal_chain("track_0");
        assert_eq!(chain, vec!["track_0", "group_drums", "master"]);
    }

    #[test]
    fn test_bus_router_inputs_outputs() {
        let mut router = BusRouter::new();

        let aux = Bus::aux("aux_reverb", "Reverb");
        router.add_bus(aux);

        router.add_route("track_0", "aux_reverb", 0.5);
        router.add_route("track_1", "aux_reverb", 0.7);
        router.add_route("aux_reverb", "master", 1.0);

        let inputs = router.get_inputs("aux_reverb");
        assert_eq!(inputs.len(), 2);

        let outputs = router.get_outputs("aux_reverb");
        assert_eq!(outputs.len(), 1);
    }

    #[test]
    fn test_bus_router_latency() {
        let mut router = BusRouter::new();
        router.set_latency_compensation("bus_1", 512);
        assert_eq!(router.get_latency_compensation("bus_1"), 512);
        assert_eq!(router.get_latency_compensation("nonexistent"), 0);
    }

    #[test]
    fn test_template_two_bus() {
        let router = BusTemplate::two_bus();
        assert_eq!(router.bus_count(), 3); // master + reverb + delay
        assert!(router.get_bus("aux_reverb").is_some());
        assert!(router.get_bus("aux_delay").is_some());
        assert!(router.get_bus("master").is_some());
    }

    #[test]
    fn test_template_five_bus() {
        let router = BusTemplate::five_bus();
        assert_eq!(router.bus_count(), 6); // master + 3 groups + 2 aux
        assert!(router.get_bus("group_drums").is_some());
        assert!(router.get_bus("group_instruments").is_some());
        assert!(router.get_bus("group_vocals").is_some());
    }

    #[test]
    fn test_template_custom() {
        let router = BusTemplate::custom(
            &[("group_drums", "Drums"), ("group_bass", "Bass")],
            &[("aux_reverb", "Reverb")],
        );
        assert_eq!(router.bus_count(), 4); // master + 2 groups + 1 aux
    }

    #[test]
    fn test_bus_level_update() {
        let mut bus = Bus::new("bus_1", "Test", BusType::Audio, 2);
        bus.update_level(0.5, 0.7);
        assert!((bus.level.0 - 0.5).abs() < 1e-6);
        assert!((bus.level.1 - 0.7).abs() < 1e-6);
    }

    #[test]
    fn test_bus_from_config() {
        let config = BusConfig {
            name: "Reverb".into(),
            bus_type: BusType::Aux,
            channels: 2,
            volume: 0.8,
            pan: 0.0,
            muted: false,
            solo: false,
        };
        let bus = Bus::from_config("aux_reverb", &config);
        assert_eq!(bus.name, "Reverb");
        assert_eq!(bus.bus_type, BusType::Aux);
        assert!((bus.volume - 0.8).abs() < 1e-10);
    }

    #[test]
    fn test_remove_bus_cleans_routes() {
        let mut router = BusRouter::new();
        let aux = Bus::aux("aux_test", "Test");
        router.add_bus(aux);
        router.add_route("track_0", "aux_test", 0.5);
        router.add_route("aux_test", "master", 1.0);

        assert_eq!(router.route_count(), 2);

        router.remove_bus("aux_test");
        assert_eq!(router.route_count(), 0);
    }
}
