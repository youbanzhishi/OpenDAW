//! Sidechain路由 — 从一个轨道路由音频到另一个轨道的效果器
//!
//! 典型应用：压缩器侧链（kick→bass compressor）
//! - SidechainRouter: 管理侧链连接
//! - SidechainBus: 专用侧链总线，支持多个发送源

use std::collections::HashMap;

use serde::{Deserialize, Serialize};

/// 侧链连接 — 从源轨道到目标效果器参数的映射
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SidechainLink {
    /// 唯一ID
    pub id: String,
    /// 源轨道索引
    pub source_track: usize,
    /// 源声道选择
    pub source_channel: SidechainSource,
    /// 目标轨道索引
    pub target_track: usize,
    /// 目标效果器参数名（如 "compressor_gain"）
    pub target_param: String,
    /// 发送量 (0.0 - 1.0)
    pub send_amount: f64,
    /// 是否启用
    pub enabled: bool,
}

/// 侧链源声道选择
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum SidechainSource {
    /// 左声道
    Left,
    /// 右声道
    Right,
    /// 立体声混合（单声道缩混）
    Mix,
    /// 仅低频（通过简单滤波）
    LowPass,
}

impl SidechainSource {
    /// 从立体声帧中提取侧链信号
    pub fn extract(&self, left: f32, right: f32) -> f32 {
        match self {
            SidechainSource::Left => left,
            SidechainSource::Right => right,
            SidechainSource::Mix => (left + right) * 0.5,
            SidechainSource::LowPass => {
                // 简化的低频提取：取左右均值
                // 实际实现应使用真正的低通滤波器
                (left + right) * 0.25
            }
        }
    }
}

/// 侧链总线 — 汇聚多个发送源的侧链信号
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SidechainBus {
    /// 总线名称
    pub name: String,
    /// 发送源列表
    pub sources: Vec<SidechainBusSource>,
    /// 汇聚后的侧链信号缓冲区
    #[serde(skip)]
    pub buffer: SidechainBuffer,
    /// 是否启用
    pub enabled: bool,
}

/// 侧链总线发送源
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SidechainBusSource {
    /// 源轨道索引
    pub track_index: usize,
    /// 源声道选择
    pub channel: SidechainSource,
    /// 发送量
    pub send_amount: f64,
    /// 是否启用
    pub enabled: bool,
}

/// 侧链信号缓冲区
#[derive(Debug, Clone)]
pub struct SidechainBuffer {
    /// 侧链信号数据（单声道）
    pub data: Vec<f32>,
    /// 采样率
    pub sample_rate: f64,
}

impl SidechainBuffer {
    /// 创建新的侧链缓冲区
    pub fn new(frames: usize, sample_rate: f64) -> Self {
        Self {
            data: vec![0.0; frames],
            sample_rate,
        }
    }

    /// 清空缓冲区
    pub fn clear(&mut self) {
        for sample in &mut self.data {
            *sample = 0.0;
        }
    }

    /// 获取帧数
    pub fn frames(&self) -> usize {
        self.data.len()
    }

    /// 获取指定位置的采样
    pub fn get(&self, index: usize) -> f32 {
        self.data.get(index).copied().unwrap_or(0.0)
    }

    /// 设置指定位置的采样
    pub fn set(&mut self, index: usize, value: f32) {
        if index < self.data.len() {
            self.data[index] = value;
        }
    }

    /// 累加采样值（用于混合多个源）
    pub fn add(&mut self, index: usize, value: f32) {
        if index < self.data.len() {
            self.data[index] += value;
        }
    }

    /// 调整缓冲区大小
    pub fn resize(&mut self, frames: usize) {
        self.data.resize(frames, 0.0);
    }

    /// 计算RMS电平
    pub fn rms(&self) -> f32 {
        if self.data.is_empty() {
            return 0.0;
        }
        let sum: f32 = self.data.iter().map(|s| s * s).sum();
        (sum / self.data.len() as f32).sqrt()
    }

    /// 计算峰值电平
    pub fn peak(&self) -> f32 {
        self.data.iter().map(|s| s.abs()).fold(0.0f32, f32::max)
    }
}

impl Default for SidechainBuffer {
    fn default() -> Self {
        Self::new(256, 44100.0)
    }
}

impl SidechainBus {
    /// 创建新的侧链总线
    pub fn new(name: &str, frames: usize, sample_rate: f64) -> Self {
        Self {
            name: name.to_string(),
            sources: Vec::new(),
            buffer: SidechainBuffer::new(frames, sample_rate),
            enabled: true,
        }
    }

    /// 添加发送源
    pub fn add_source(&mut self, track_index: usize, channel: SidechainSource, send_amount: f64) {
        self.sources.push(SidechainBusSource {
            track_index,
            channel,
            send_amount,
            enabled: true,
        });
    }

    /// 移除发送源
    pub fn remove_source(&mut self, index: usize) {
        if index < self.sources.len() {
            self.sources.remove(index);
        }
    }

    /// 处理音频 — 从各源轨道提取侧链信号并混合
    pub fn process(&mut self, track_buffers: &[(usize, &[[f32; 2]])]) {
        self.buffer.clear();

        let frames = self.buffer.frames();
        for source in &self.sources {
            if !source.enabled {
                continue;
            }

            // 找到对应轨道的缓冲区
            for &(track_idx, buffer) in track_buffers {
                if track_idx == source.track_index {
                    let process_frames = frames.min(buffer.len());
                    for i in 0..process_frames {
                        let signal = source.channel.extract(buffer[i][0], buffer[i][1]);
                        self.buffer.add(i, signal * source.send_amount as f32);
                    }
                    break;
                }
            }
        }
    }
}

/// 侧链路由器 — 管理所有侧链连接
pub struct SidechainRouter {
    /// 侧链连接列表
    links: HashMap<String, SidechainLink>,
    /// 侧链总线列表
    buses: Vec<SidechainBus>,
    /// 连接到总线的映射：link_id → bus_index
    link_to_bus: HashMap<String, usize>,
}

impl SidechainRouter {
    /// 创建新的侧链路由器
    pub fn new() -> Self {
        Self {
            links: HashMap::new(),
            buses: Vec::new(),
            link_to_bus: HashMap::new(),
        }
    }

    /// 添加侧链连接
    pub fn add_link(&mut self, link: SidechainLink) {
        self.links.insert(link.id.clone(), link);
    }

    /// 移除侧链连接
    pub fn remove_link(&mut self, id: &str) -> Option<SidechainLink> {
        self.link_to_bus.remove(id);
        self.links.remove(id)
    }

    /// 获取侧链连接
    pub fn get_link(&self, id: &str) -> Option<&SidechainLink> {
        self.links.get(id)
    }

    /// 获取侧链连接可变引用
    pub fn get_link_mut(&mut self, id: &str) -> Option<&mut SidechainLink> {
        self.links.get_mut(id)
    }

    /// 添加侧链总线
    pub fn add_bus(&mut self, bus: SidechainBus) -> usize {
        let index = self.buses.len();
        self.buses.push(bus);
        index
    }

    /// 获取侧链总线
    pub fn get_bus(&self, index: usize) -> Option<&SidechainBus> {
        self.buses.get(index)
    }

    /// 获取侧链总线可变引用
    pub fn get_bus_mut(&mut self, index: usize) -> Option<&mut SidechainBus> {
        self.buses.get_mut(index)
    }

    /// 将侧链连接绑定到总线
    pub fn link_to_bus(&mut self, link_id: &str, bus_index: usize) {
        self.link_to_bus.insert(link_id.to_string(), bus_index);
    }

    /// 获取目标轨道的所有侧链源
    pub fn get_sources_for_target(&self, target_track: usize) -> Vec<&SidechainLink> {
        self.links
            .values()
            .filter(|l| l.target_track == target_track && l.enabled)
            .collect()
    }

    /// 获取源轨道的所有侧链目标
    pub fn get_targets_for_source(&self, source_track: usize) -> Vec<&SidechainLink> {
        self.links
            .values()
            .filter(|l| l.source_track == source_track && l.enabled)
            .collect()
    }

    /// 创建典型的压缩器侧链（kick→bass compressor）
    pub fn create_kick_bass_sidechain(
        &mut self,
        kick_track: usize,
        bass_track: usize,
        send_amount: f64,
    ) -> String {
        let link_id = format!("sc_{}_{}", kick_track, bass_track);
        let link = SidechainLink {
            id: link_id.clone(),
            source_track: kick_track,
            source_channel: SidechainSource::Mix,
            target_track: bass_track,
            target_param: "compressor_sidechain".to_string(),
            send_amount,
            enabled: true,
        };
        self.add_link(link);
        link_id
    }

    /// 启用/禁用侧链连接
    pub fn set_link_enabled(&mut self, id: &str, enabled: bool) {
        if let Some(link) = self.links.get_mut(id) {
            link.enabled = enabled;
        }
    }

    /// 连接数量
    pub fn link_count(&self) -> usize {
        self.links.len()
    }

    /// 总线数量
    pub fn bus_count(&self) -> usize {
        self.buses.len()
    }

    /// 列出所有连接的描述
    pub fn describe_links(&self) -> Vec<String> {
        self.links
            .values()
            .map(|l| {
                format!(
                    "Track {} → Track {} (param: {}, amount: {:.2}, {})",
                    l.source_track,
                    l.target_track,
                    l.target_param,
                    l.send_amount,
                    if l.enabled { "ON" } else { "OFF" }
                )
            })
            .collect()
    }
}

impl Default for SidechainRouter {
    fn default() -> Self {
        Self::new()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_sidechain_source_extract() {
        let left = 0.8f32;
        let right = 0.4f32;

        assert!((SidechainSource::Left.extract(left, right) - 0.8).abs() < 1e-6);
        assert!((SidechainSource::Right.extract(left, right) - 0.4).abs() < 1e-6);
        assert!((SidechainSource::Mix.extract(left, right) - 0.6).abs() < 1e-6);
    }

    #[test]
    fn test_sidechain_buffer() {
        let mut buf = SidechainBuffer::new(256, 44100.0);
        assert_eq!(buf.frames(), 256);

        buf.set(0, 0.5);
        buf.set(1, -0.3);
        assert!((buf.get(0) - 0.5).abs() < 1e-6);
        assert!((buf.get(1) - (-0.3)).abs() < 1e-6);

        buf.add(0, 0.3);
        assert!((buf.get(0) - 0.8).abs() < 1e-6);

        buf.clear();
        assert!((buf.get(0)).abs() < 1e-6);
    }

    #[test]
    fn test_sidechain_buffer_rms() {
        let mut buf = SidechainBuffer::new(4, 44100.0);
        buf.set(0, 1.0);
        buf.set(1, 0.0);
        buf.set(2, -1.0);
        buf.set(3, 0.0);
        let rms = buf.rms();
        assert!((rms - 0.7071).abs() < 0.01, "RMS should be ~0.707, got {}", rms);
    }

    #[test]
    fn test_sidechain_buffer_peak() {
        let mut buf = SidechainBuffer::new(4, 44100.0);
        buf.set(0, 0.3);
        buf.set(1, -0.8);
        buf.set(2, 0.5);
        buf.set(3, 0.1);
        assert!((buf.peak() - 0.8).abs() < 1e-6);
    }

    #[test]
    fn test_sidechain_bus() {
        let mut bus = SidechainBus::new("Kick→Bass", 256, 44100.0);
        bus.add_source(0, SidechainSource::Mix, 1.0);
        bus.add_source(1, SidechainSource::Left, 0.5);

        assert_eq!(bus.sources.len(), 2);
        assert!(bus.enabled);
    }

    #[test]
    fn test_sidechain_bus_process() {
        let mut bus = SidechainBus::new("Kick→Bass", 4, 44100.0);
        bus.add_source(0, SidechainSource::Mix, 1.0);

        // 模拟源轨道音频
        let kick_buffer: [[f32; 2]; 4] = [[0.5, 0.5], [0.8, 0.8], [0.3, 0.3], [0.0, 0.0]];
        let track_buffers: [(usize, &[[f32; 2]]); 1] = [(0, &kick_buffer)];

        bus.process(&track_buffers);

        // 验证侧链信号
        assert!((bus.buffer.get(0) - 0.5).abs() < 1e-6);
        assert!((bus.buffer.get(1) - 0.8).abs() < 1e-6);
    }

    #[test]
    fn test_sidechain_router() {
        let mut router = SidechainRouter::new();

        let link = SidechainLink {
            id: "sc_0_1".to_string(),
            source_track: 0,
            source_channel: SidechainSource::Mix,
            target_track: 1,
            target_param: "compressor_sidechain".to_string(),
            send_amount: 1.0,
            enabled: true,
        };
        router.add_link(link);
        assert_eq!(router.link_count(), 1);

        let sources = router.get_sources_for_target(1);
        assert_eq!(sources.len(), 1);
        assert_eq!(sources[0].source_track, 0);
    }

    #[test]
    fn test_kick_bass_sidechain() {
        let mut router = SidechainRouter::new();
        let link_id = router.create_kick_bass_sidechain(0, 1, 0.8);

        assert_eq!(router.link_count(), 1);
        let link = router.get_link(&link_id).unwrap();
        assert_eq!(link.source_track, 0);
        assert_eq!(link.target_track, 1);
        assert!((link.send_amount - 0.8).abs() < 1e-10);
    }

    #[test]
    fn test_sidechain_link_enable_disable() {
        let mut router = SidechainRouter::new();
        let link_id = router.create_kick_bass_sidechain(0, 1, 1.0);

        router.set_link_enabled(&link_id, false);
        let sources = router.get_sources_for_target(1);
        assert!(sources.is_empty(), "Disabled link should not appear");

        router.set_link_enabled(&link_id, true);
        let sources = router.get_sources_for_target(1);
        assert_eq!(sources.len(), 1);
    }

    #[test]
    fn test_describe_links() {
        let mut router = SidechainRouter::new();
        router.create_kick_bass_sidechain(0, 1, 0.75);
        router.create_kick_bass_sidechain(2, 3, 1.0);

        let descriptions = router.describe_links();
        assert_eq!(descriptions.len(), 2);
        assert!(descriptions[0].contains("0 → 1"));
        assert!(descriptions[1].contains("2 → 3"));
    }
}
