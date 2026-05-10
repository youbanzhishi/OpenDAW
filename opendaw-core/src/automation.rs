//! 自动化曲线编辑器 — 参数自动化系统
//!
//! - AutomationLane: 自动化轨道
//! - AutomationPoint: 控制点 + 曲线类型
//! - AutomationEnvelope: 包络线插值
//! - ParameterAutomation: 参数与自动化的绑定

use std::collections::HashMap;

use serde::{Deserialize, Serialize};

/// 曲线类型 — 控制点之间的插值方式
#[derive(Debug, Clone, Copy, PartialEq, Serialize, Deserialize)]
pub enum CurveType {
    /// 线性插值
    Linear,
    /// 指数插值（适合音量等对数参数）
    Exponential,
    /// 阶梯式（无插值，适合开关参数）
    Step,
    /// 正弦曲线（平滑过渡）
    Sine,
}

impl CurveType {
    /// 在两个值之间进行插值
    pub fn interpolate(&self, t: f64, from: f64, to: f64) -> f64 {
        match self {
            CurveType::Linear => from + (to - from) * t,
            CurveType::Exponential => {
                if from <= 0.0 || to <= 0.0 {
                    // 零值时退化为线性
                    from + (to - from) * t
                } else {
                    from * (to / from).powf(t)
                }
            }
            CurveType::Step => {
                if t < 1.0 {
                    from
                } else {
                    to
                }
            }
            CurveType::Sine => {
                // 正弦平滑过渡
                let sine_t = (t * std::f64::consts::PI * 0.5).sin();
                from + (to - from) * sine_t
            }
        }
    }
}

/// 自动化控制点
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AutomationPoint {
    /// 时间位置（拍）
    pub beat: f64,
    /// 参数值 (0.0 - 1.0 归一化)
    pub value: f64,
    /// 到下一个点的曲线类型
    pub curve_type: CurveType,
}

impl AutomationPoint {
    /// 创建新的控制点
    pub fn new(beat: f64, value: f64, curve_type: CurveType) -> Self {
        Self {
            beat,
            value: value.clamp(0.0, 1.0),
            curve_type,
        }
    }

    /// 创建线性控制点
    pub fn linear(beat: f64, value: f64) -> Self {
        Self::new(beat, value, CurveType::Linear)
    }

    /// 创建指数控制点
    pub fn exponential(beat: f64, value: f64) -> Self {
        Self::new(beat, value, CurveType::Exponential)
    }

    /// 创建阶梯控制点
    pub fn step(beat: f64, value: f64) -> Self {
        Self::new(beat, value, CurveType::Step)
    }

    /// 创建正弦控制点
    pub fn sine(beat: f64, value: f64) -> Self {
        Self::new(beat, value, CurveType::Sine)
    }
}

/// 自动化包络线 — 控制点集合 + 插值
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AutomationEnvelope {
    /// 控制点列表（按beat排序）
    points: Vec<AutomationPoint>,
    /// 默认值（无控制点时使用）
    default_value: f64,
}

impl AutomationEnvelope {
    /// 创建新的包络线
    pub fn new(default_value: f64) -> Self {
        Self {
            points: Vec::new(),
            default_value: default_value.clamp(0.0, 1.0),
        }
    }

    /// 添加控制点
    pub fn add_point(&mut self, point: AutomationPoint) {
        // 找到插入位置以保持排序
        let pos = self
            .points
            .iter()
            .position(|p| p.beat > point.beat)
            .unwrap_or(self.points.len());
        self.points.insert(pos, point);
    }

    /// 移除指定beat位置的控制点
    pub fn remove_point_at(&mut self, beat: f64) -> Option<AutomationPoint> {
        let pos = self
            .points
            .iter()
            .position(|p| (p.beat - beat).abs() < 1e-10)?;
        Some(self.points.remove(pos))
    }

    /// 移除指定索引的控制点
    pub fn remove_point(&mut self, index: usize) -> Option<AutomationPoint> {
        if index < self.points.len() {
            Some(self.points.remove(index))
        } else {
            None
        }
    }

    /// 获取指定beat的插值
    pub fn value_at(&self, beat: f64) -> f64 {
        if self.points.is_empty() {
            return self.default_value;
        }

        if beat <= self.points[0].beat {
            return self.points[0].value;
        }

        if beat >= self.points[self.points.len() - 1].beat {
            return self.points[self.points.len() - 1].value;
        }

        // 找到包含beat的两个控制点
        for i in 0..self.points.len() - 1 {
            let p0 = &self.points[i];
            let p1 = &self.points[i + 1];

            if beat >= p0.beat && beat < p1.beat {
                let t = if (p1.beat - p0.beat).abs() < 1e-10 {
                    0.0
                } else {
                    (beat - p0.beat) / (p1.beat - p0.beat)
                };
                return p0.curve_type.interpolate(t, p0.value, p1.value);
            }
        }

        self.default_value
    }

    /// 获取指定范围内的采样值
    pub fn sample_range(&self, start_beat: f64, end_beat: f64, steps: usize) -> Vec<f64> {
        if steps == 0 {
            return Vec::new();
        }
        let step_size = if steps > 1 {
            (end_beat - start_beat) / (steps - 1) as f64
        } else {
            0.0
        };
        (0..steps)
            .map(|i| self.value_at(start_beat + step_size * i as f64))
            .collect()
    }

    /// 控制点数量
    pub fn point_count(&self) -> usize {
        self.points.len()
    }

    /// 获取所有控制点
    pub fn points(&self) -> &[AutomationPoint] {
        &self.points
    }

    /// 获取控制点可变引用
    pub fn points_mut(&mut self) -> &mut Vec<AutomationPoint> {
        &mut self.points
    }

    /// 清空所有控制点
    pub fn clear(&mut self) {
        self.points.clear();
    }

    /// 包络线范围（起止beat）
    pub fn range(&self) -> Option<(f64, f64)> {
        if self.points.is_empty() {
            return None;
        }
        Some((
            self.points.first().unwrap().beat,
            self.points.last().unwrap().beat,
        ))
    }

    /// 最大值
    pub fn max_value(&self) -> f64 {
        self.points
            .iter()
            .map(|p| p.value)
            .fold(self.default_value, f64::max)
    }

    /// 最小值
    pub fn min_value(&self) -> f64 {
        self.points
            .iter()
            .map(|p| p.value)
            .fold(self.default_value, f64::min)
    }
}

impl Default for AutomationEnvelope {
    fn default() -> Self {
        Self::new(0.5)
    }
}

/// 自动化轨道 — 绑定到特定参数的包络线
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AutomationLane {
    /// 唯一ID
    pub id: String,
    /// 轨道名称
    pub name: String,
    /// 绑定的轨道索引
    pub track_index: usize,
    /// 绑定的参数名
    pub param_name: String,
    /// 包络线
    pub envelope: AutomationEnvelope,
    /// 是否启用
    pub enabled: bool,
    /// 是否处于写入模式（录音自动化）
    pub write_mode: bool,
    /// 是否处于读取模式（回放自动化）
    pub read_mode: bool,
    /// 颜色（UI用，0xRRGGBB）
    pub color: u32,
}

impl AutomationLane {
    /// 创建新的自动化轨道
    pub fn new(id: &str, name: &str, track_index: usize, param_name: &str) -> Self {
        Self {
            id: id.to_string(),
            name: name.to_string(),
            track_index,
            param_name: param_name.to_string(),
            envelope: AutomationEnvelope::new(0.5),
            enabled: true,
            write_mode: false,
            read_mode: true,
            color: 0x00AAFF,
        }
    }

    /// 获取指定beat的参数值
    pub fn value_at(&self, beat: f64) -> f64 {
        if !self.enabled || !self.read_mode {
            return self.envelope.default_value;
        }
        self.envelope.value_at(beat)
    }

    /// 写入自动化数据点（写入模式下）
    pub fn write_point(&mut self, beat: f64, value: f64, curve_type: CurveType) {
        if self.write_mode {
            self.envelope
                .add_point(AutomationPoint::new(beat, value, curve_type));
        }
    }

    /// 添加控制点（无论写入模式）
    pub fn add_point(&mut self, point: AutomationPoint) {
        self.envelope.add_point(point);
    }

    /// 采样指定范围
    pub fn sample_range(&self, start_beat: f64, end_beat: f64, steps: usize) -> Vec<f64> {
        if !self.enabled {
            return vec![self.envelope.default_value; steps];
        }
        self.envelope.sample_range(start_beat, end_beat, steps)
    }
}

/// 参数自动化绑定 — 管理参数与自动化轨道的映射
pub struct ParameterAutomation {
    /// 自动化轨道列表
    lanes: HashMap<String, AutomationLane>,
    /// 参数到自动化轨道的映射：(track_index, param_name) → lane_id
    param_map: HashMap<(usize, String), String>,
}

impl ParameterAutomation {
    /// 创建新的参数自动化系统
    pub fn new() -> Self {
        Self {
            lanes: HashMap::new(),
            param_map: HashMap::new(),
        }
    }

    /// 添加自动化轨道
    pub fn add_lane(&mut self, lane: AutomationLane) {
        let key = (lane.track_index, lane.param_name.clone());
        self.param_map.insert(key, lane.id.clone());
        self.lanes.insert(lane.id.clone(), lane);
    }

    /// 移除自动化轨道
    pub fn remove_lane(&mut self, id: &str) -> Option<AutomationLane> {
        if let Some(lane) = self.lanes.remove(id) {
            let key = (lane.track_index, lane.param_name.clone());
            self.param_map.remove(&key);
            Some(lane)
        } else {
            None
        }
    }

    /// 获取自动化轨道
    pub fn get_lane(&self, id: &str) -> Option<&AutomationLane> {
        self.lanes.get(id)
    }

    /// 获取自动化轨道可变引用
    pub fn get_lane_mut(&mut self, id: &str) -> Option<&mut AutomationLane> {
        self.lanes.get_mut(id)
    }

    /// 根据参数获取自动化值
    pub fn get_value(&self, track_index: usize, param_name: &str, beat: f64) -> Option<f64> {
        let key = (track_index, param_name.to_string());
        if let Some(lane_id) = self.param_map.get(&key) {
            self.lanes.get(lane_id).map(|lane| lane.value_at(beat))
        } else {
            None
        }
    }

    /// 获取参数绑定的自动化轨道ID
    pub fn get_lane_for_param(&self, track_index: usize, param_name: &str) -> Option<&str> {
        let key = (track_index, param_name.to_string());
        self.param_map.get(&key).map(|s| s.as_str())
    }

    /// 获取指定轨道的所有自动化轨道
    pub fn get_lanes_for_track(&self, track_index: usize) -> Vec<&AutomationLane> {
        self.lanes
            .values()
            .filter(|l| l.track_index == track_index)
            .collect()
    }

    /// 自动化轨道数量
    pub fn lane_count(&self) -> usize {
        self.lanes.len()
    }

    /// 是否有参数绑定
    pub fn has_automation(&self, track_index: usize, param_name: &str) -> bool {
        let key = (track_index, param_name.to_string());
        self.param_map.contains_key(&key)
    }

    /// 为参数创建默认的自动化轨道
    pub fn create_automation_for_param(
        &mut self,
        track_index: usize,
        param_name: &str,
        default_value: f64,
    ) -> String {
        let lane_id = format!("auto_{}_{}", track_index, param_name);
        let lane_name = format!("{} - {}", track_index, param_name);

        let mut lane = AutomationLane::new(&lane_id, &lane_name, track_index, param_name);
        lane.envelope = AutomationEnvelope::new(default_value);

        self.add_lane(lane);
        lane_id
    }

    /// 列出所有自动化描述
    pub fn describe(&self) -> Vec<String> {
        self.lanes
            .values()
            .map(|l| {
                format!(
                    "Lane '{}' (Track {} / {}): {} points, {}",
                    l.name,
                    l.track_index,
                    l.param_name,
                    l.envelope.point_count(),
                    if l.enabled { "ON" } else { "OFF" }
                )
            })
            .collect()
    }
}

impl Default for ParameterAutomation {
    fn default() -> Self {
        Self::new()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_curve_type_linear() {
        let result = CurveType::Linear.interpolate(0.5, 0.0, 1.0);
        assert!((result - 0.5).abs() < 1e-10);

        let result = CurveType::Linear.interpolate(0.25, 0.0, 1.0);
        assert!((result - 0.25).abs() < 1e-10);
    }

    #[test]
    fn test_curve_type_exponential() {
        let result = CurveType::Exponential.interpolate(0.5, 1.0, 100.0);
        assert!(
            result > 1.0 && result < 100.0,
            "Midpoint of exponential should be between 1 and 100, got {}",
            result
        );
    }

    #[test]
    fn test_curve_type_step() {
        let result = CurveType::Step.interpolate(0.5, 0.0, 1.0);
        assert!((result - 0.0).abs() < 1e-10);

        let result = CurveType::Step.interpolate(1.0, 0.0, 1.0);
        assert!((result - 1.0).abs() < 1e-10);
    }

    #[test]
    fn test_curve_type_sine() {
        let result = CurveType::Sine.interpolate(0.5, 0.0, 1.0);
        // sin(π/4) ≈ 0.707
        assert!(
            (result - 0.7071).abs() < 0.01,
            "Sine midpoint should be ~0.707, got {}",
            result
        );

        let result_start = CurveType::Sine.interpolate(0.0, 0.0, 1.0);
        assert!((result_start - 0.0).abs() < 1e-10);

        let result_end = CurveType::Sine.interpolate(1.0, 0.0, 1.0);
        assert!((result_end - 1.0).abs() < 1e-10);
    }

    #[test]
    fn test_automation_point() {
        let point = AutomationPoint::linear(4.0, 0.75);
        assert!((point.beat - 4.0).abs() < 1e-10);
        assert!((point.value - 0.75).abs() < 1e-10);
        assert_eq!(point.curve_type, CurveType::Linear);
    }

    #[test]
    fn test_envelope_basic() {
        let mut env = AutomationEnvelope::new(0.5);
        assert_eq!(env.point_count(), 0);

        env.add_point(AutomationPoint::linear(0.0, 0.0));
        env.add_point(AutomationPoint::linear(4.0, 1.0));
        assert_eq!(env.point_count(), 2);

        // 在beat=2处应该插值为0.5
        let val = env.value_at(2.0);
        assert!(
            (val - 0.5).abs() < 1e-10,
            "Value at beat 2 should be 0.5, got {}",
            val
        );
    }

    #[test]
    fn test_envelope_empty() {
        let env = AutomationEnvelope::new(0.7);
        assert!((env.value_at(0.0) - 0.7).abs() < 1e-10);
        assert!((env.value_at(100.0) - 0.7).abs() < 1e-10);
    }

    #[test]
    fn test_envelope_before_first_point() {
        let mut env = AutomationEnvelope::new(0.5);
        env.add_point(AutomationPoint::linear(4.0, 0.8));
        let val = env.value_at(2.0);
        assert!(
            (val - 0.8).abs() < 1e-10,
            "Before first point should use first point value"
        );
    }

    #[test]
    fn test_envelope_after_last_point() {
        let mut env = AutomationEnvelope::new(0.5);
        env.add_point(AutomationPoint::linear(4.0, 0.8));
        let val = env.value_at(10.0);
        assert!(
            (val - 0.8).abs() < 1e-10,
            "After last point should use last point value"
        );
    }

    #[test]
    fn test_envelope_step_curve() {
        let mut env = AutomationEnvelope::new(0.0);
        env.add_point(AutomationPoint::step(0.0, 0.0));
        env.add_point(AutomationPoint::step(4.0, 1.0));

        // 在beat 0-3.99应该是0
        assert!((env.value_at(1.0) - 0.0).abs() < 1e-10);
        assert!((env.value_at(3.0) - 0.0).abs() < 1e-10);
        // 在beat 4.0应该是1
        assert!((env.value_at(4.0) - 1.0).abs() < 1e-10);
    }

    #[test]
    fn test_envelope_sample_range() {
        let mut env = AutomationEnvelope::new(0.0);
        env.add_point(AutomationPoint::linear(0.0, 0.0));
        env.add_point(AutomationPoint::linear(10.0, 1.0));

        let samples = env.sample_range(0.0, 10.0, 11);
        assert_eq!(samples.len(), 11);
        assert!((samples[0] - 0.0).abs() < 1e-10);
        assert!((samples[10] - 1.0).abs() < 1e-10);
        assert!((samples[5] - 0.5).abs() < 1e-10);
    }

    #[test]
    fn test_envelope_remove_point() {
        let mut env = AutomationEnvelope::new(0.5);
        env.add_point(AutomationPoint::linear(0.0, 0.0));
        env.add_point(AutomationPoint::linear(4.0, 1.0));

        env.remove_point_at(0.0);
        assert_eq!(env.point_count(), 1);
    }

    #[test]
    fn test_envelope_range() {
        let mut env = AutomationEnvelope::new(0.5);
        assert!(env.range().is_none());

        env.add_point(AutomationPoint::linear(2.0, 0.5));
        env.add_point(AutomationPoint::linear(8.0, 0.8));

        let (start, end) = env.range().unwrap();
        assert!((start - 2.0).abs() < 1e-10);
        assert!((end - 8.0).abs() < 1e-10);
    }

    #[test]
    fn test_envelope_min_max() {
        let mut env = AutomationEnvelope::new(0.5);
        env.add_point(AutomationPoint::linear(0.0, 0.2));
        env.add_point(AutomationPoint::linear(4.0, 0.9));
        env.add_point(AutomationPoint::linear(8.0, 0.3));

        assert!((env.min_value() - 0.2).abs() < 1e-10);
        assert!((env.max_value() - 0.9).abs() < 1e-10);
    }

    #[test]
    fn test_automation_lane() {
        let mut lane = AutomationLane::new("auto_0_volume", "Volume", 0, "volume");
        lane.add_point(AutomationPoint::linear(0.0, 0.5));
        lane.add_point(AutomationPoint::linear(4.0, 1.0));

        let val = lane.value_at(2.0);
        assert!((val - 0.75).abs() < 1e-10);
    }

    #[test]
    fn test_automation_lane_disabled() {
        let mut lane = AutomationLane::new("auto_0_volume", "Volume", 0, "volume");
        lane.add_point(AutomationPoint::linear(0.0, 0.5));
        lane.enabled = false;

        let val = lane.value_at(2.0);
        assert!(
            (val - 0.5).abs() < 1e-10,
            "Disabled lane should return default value"
        );
    }

    #[test]
    fn test_automation_lane_write_mode() {
        let mut lane = AutomationLane::new("auto_0_volume", "Volume", 0, "volume");
        lane.write_mode = true;
        lane.write_point(2.0, 0.8, CurveType::Linear);
        assert_eq!(lane.envelope.point_count(), 1);

        lane.write_mode = false;
        lane.write_point(4.0, 1.0, CurveType::Linear);
        assert_eq!(
            lane.envelope.point_count(),
            1,
            "Should not write when write_mode is off"
        );
    }

    #[test]
    fn test_parameter_automation() {
        let mut pa = ParameterAutomation::new();
        let mut lane = AutomationLane::new("auto_0_volume", "Volume", 0, "volume");
        lane.add_point(AutomationPoint::linear(0.0, 0.5));
        lane.add_point(AutomationPoint::linear(4.0, 1.0));
        pa.add_lane(lane);

        let val = pa.get_value(0, "volume", 2.0);
        assert!(val.is_some());
        assert!((val.unwrap() - 0.75).abs() < 1e-10);

        assert!(!pa.has_automation(1, "volume"));
        assert!(pa.has_automation(0, "volume"));
    }

    #[test]
    fn test_parameter_automation_create() {
        let mut pa = ParameterAutomation::new();
        let _lane_id = pa.create_automation_for_param(0, "volume", 0.7);

        assert!(pa.has_automation(0, "volume"));
        let val = pa.get_value(0, "volume", 0.0);
        assert!(val.is_some());
        assert!((val.unwrap() - 0.7).abs() < 1e-10);
    }

    #[test]
    fn test_parameter_automation_lanes_for_track() {
        let mut pa = ParameterAutomation::new();
        pa.create_automation_for_param(0, "volume", 0.5);
        pa.create_automation_for_param(0, "pan", 0.0);
        pa.create_automation_for_param(1, "volume", 0.8);

        let track0_lanes = pa.get_lanes_for_track(0);
        assert_eq!(track0_lanes.len(), 2);

        let track1_lanes = pa.get_lanes_for_track(1);
        assert_eq!(track1_lanes.len(), 1);
    }

    #[test]
    fn test_parameter_automation_describe() {
        let mut pa = ParameterAutomation::new();
        pa.create_automation_for_param(0, "volume", 0.5);
        pa.create_automation_for_param(0, "pan", 0.0);

        let descriptions = pa.describe();
        assert_eq!(descriptions.len(), 2);
    }

    #[test]
    fn test_multi_point_envelope() {
        let mut env = AutomationEnvelope::new(0.0);
        env.add_point(AutomationPoint::linear(0.0, 0.0));
        env.add_point(AutomationPoint::linear(2.0, 0.5));
        env.add_point(AutomationPoint::linear(4.0, 1.0));
        env.add_point(AutomationPoint::linear(6.0, 0.5));
        env.add_point(AutomationPoint::linear(8.0, 0.0));

        assert!((env.value_at(1.0) - 0.25).abs() < 1e-10);
        assert!((env.value_at(3.0) - 0.75).abs() < 1e-10);
        assert!((env.value_at(5.0) - 0.75).abs() < 1e-10);
        assert!((env.value_at(7.0) - 0.25).abs() < 1e-10);
    }
}
