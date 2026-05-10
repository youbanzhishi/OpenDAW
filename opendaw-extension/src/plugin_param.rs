//! PluginParameter — 统一参数模型
//!
//! 支持 float/int/bool/enum 四种参数类型，
//! 提供统一的参数描述、验证和值转换。
//!
//! # 参数类型
//!
//! | 类型   | 存储     | 适用场景                  |
//! |--------|----------|--------------------------|
//! | Float  | f64      | 增益、频率、混音比等连续量 |
//! | Int    | i64      | 量化步长、延迟线数等       |
//! | Bool   | bool     | 开关、bypass、相位反转     |
//! | Enum   | usize    | 模式选择、滤波器类型等     |
//!
//! # 使用
//!
//! ```ignore
//! use opendaw_extension::plugin_param::{PluginParameter, ParameterValue};
//!
//! let gain = PluginParameter::float("gain", "增益", -60.0, 60.0, 0.0, "dB");
//! let mode = PluginParameter::enum_param("mode", "模式", &["LPF", "HPF", "BPF"], 0);
//! let bypass = PluginParameter::bool_param("bypass", "旁路", false);
//! let voices = PluginParameter::int("voices", "声部数", 1, 64, 8, "");
//! ```

use serde::{Deserialize, Serialize};

/// 参数值 — 统一存储各种类型的参数值
#[derive(Clone, Debug, Serialize, Deserialize)]
pub enum ParameterValue {
    /// 浮点参数（增益、频率等）
    Float(f64),
    /// 整数参数（声部数、量化步长等）
    Int(i64),
    /// 布尔参数（开关、bypass等）
    Bool(bool),
    /// 枚举参数（模式选择，存储索引）
    Enum(usize),
}

impl ParameterValue {
    /// 转换为 f64（用于统一自动化系统）
    pub fn to_f64(&self) -> f64 {
        match self {
            ParameterValue::Float(v) => *v,
            ParameterValue::Int(v) => *v as f64,
            ParameterValue::Bool(v) => {
                if *v {
                    1.0
                } else {
                    0.0
                }
            }
            ParameterValue::Enum(v) => *v as f64,
        }
    }

    /// 从 f64 转换（指定目标类型）
    pub fn from_f64(value: f64, param_type: &ParameterType) -> Self {
        match param_type {
            ParameterType::Float => ParameterValue::Float(value),
            ParameterType::Int => ParameterValue::Int(value.round() as i64),
            ParameterType::Bool => ParameterValue::Bool(value >= 0.5),
            ParameterType::Enum => ParameterValue::Enum(value.round().max(0.0) as usize),
        }
    }

    /// 尝试获取浮点值
    pub fn as_float(&self) -> Option<f64> {
        match self {
            ParameterValue::Float(v) => Some(*v),
            _ => None,
        }
    }

    /// 尝试获取整数值
    pub fn as_int(&self) -> Option<i64> {
        match self {
            ParameterValue::Int(v) => Some(*v),
            _ => None,
        }
    }

    /// 尝试获取布尔值
    pub fn as_bool(&self) -> Option<bool> {
        match self {
            ParameterValue::Bool(v) => Some(*v),
            _ => None,
        }
    }

    /// 尝试获取枚举索引
    pub fn as_enum(&self) -> Option<usize> {
        match self {
            ParameterValue::Enum(v) => Some(*v),
            _ => None,
        }
    }
}

impl std::fmt::Display for ParameterValue {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            ParameterValue::Float(v) => write!(f, "{}", v),
            ParameterValue::Int(v) => write!(f, "{}", v),
            ParameterValue::Bool(v) => write!(f, "{}", v),
            ParameterValue::Enum(v) => write!(f, "{}", v),
        }
    }
}

/// 参数类型
#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub enum ParameterType {
    Float,
    Int,
    Bool,
    Enum,
}

impl std::fmt::Display for ParameterType {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            ParameterType::Float => write!(f, "float"),
            ParameterType::Int => write!(f, "int"),
            ParameterType::Bool => write!(f, "bool"),
            ParameterType::Enum => write!(f, "enum"),
        }
    }
}

/// 统一参数描述 — 扩展 ParamInfo，支持多种参数类型
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct PluginParameter {
    /// 参数唯一ID
    pub id: String,
    /// 人类可读名称
    pub name: String,
    /// 参数类型
    pub param_type: ParameterType,
    /// 当前值
    pub value: ParameterValue,
    /// 默认值
    pub default: ParameterValue,
    /// 浮点最小值（Float/Int/Enum均使用）
    pub min_f64: f64,
    /// 浮点最大值
    pub max_f64: f64,
    /// 步进值（0.0=连续）
    pub step: f64,
    /// 单位
    pub unit: String,
    /// 枚举选项标签（仅 Enum 类型）
    pub enum_labels: Vec<String>,
    /// 参数所属组（用于UI分组）
    pub group: String,
    /// 是否可自动化
    pub automatable: bool,
}

impl PluginParameter {
    // ── 构造函数 ──────────────────────────────────────────────────────

    /// 创建浮点参数
    pub fn float(id: &str, name: &str, min: f64, max: f64, default: f64, unit: &str) -> Self {
        Self {
            id: id.to_string(),
            name: name.to_string(),
            param_type: ParameterType::Float,
            value: ParameterValue::Float(default),
            default: ParameterValue::Float(default),
            min_f64: min,
            max_f64: max,
            step: 0.0,
            unit: unit.to_string(),
            enum_labels: Vec::new(),
            group: String::new(),
            automatable: true,
        }
    }

    /// 创建整数参数
    pub fn int(id: &str, name: &str, min: i64, max: i64, default: i64, unit: &str) -> Self {
        Self {
            id: id.to_string(),
            name: name.to_string(),
            param_type: ParameterType::Int,
            value: ParameterValue::Int(default),
            default: ParameterValue::Int(default),
            min_f64: min as f64,
            max_f64: max as f64,
            step: 1.0,
            unit: unit.to_string(),
            enum_labels: Vec::new(),
            group: String::new(),
            automatable: true,
        }
    }

    /// 创建布尔参数
    pub fn bool_param(id: &str, name: &str, default: bool) -> Self {
        Self {
            id: id.to_string(),
            name: name.to_string(),
            param_type: ParameterType::Bool,
            value: ParameterValue::Bool(default),
            default: ParameterValue::Bool(default),
            min_f64: 0.0,
            max_f64: 1.0,
            step: 1.0,
            unit: String::new(),
            enum_labels: vec!["Off".to_string(), "On".to_string()],
            group: String::new(),
            automatable: true,
        }
    }

    /// 创建枚举参数
    pub fn enum_param(id: &str, name: &str, labels: &[&str], default_index: usize) -> Self {
        let max = if labels.is_empty() {
            0
        } else {
            labels.len() - 1
        };
        let idx = default_index.min(max);
        Self {
            id: id.to_string(),
            name: name.to_string(),
            param_type: ParameterType::Enum,
            value: ParameterValue::Enum(idx),
            default: ParameterValue::Enum(idx),
            min_f64: 0.0,
            max_f64: max as f64,
            step: 1.0,
            unit: String::new(),
            enum_labels: labels.iter().map(|s| s.to_string()).collect(),
            group: String::new(),
            automatable: true,
        }
    }

    // ── Builder 方法 ──────────────────────────────────────────────────

    /// 设置步进值
    pub fn with_step(mut self, step: f64) -> Self {
        self.step = step;
        self
    }

    /// 设置参数组
    pub fn with_group(mut self, group: &str) -> Self {
        self.group = group.to_string();
        self
    }

    /// 设置是否可自动化
    pub fn with_automatable(mut self, auto: bool) -> Self {
        self.automatable = auto;
        self
    }

    // ── 值操作 ────────────────────────────────────────────────────────

    /// 设置值（从 f64 自动转换）
    pub fn set_from_f64(&mut self, value: f64) {
        let clamped = value.clamp(self.min_f64, self.max_f64);
        self.value = ParameterValue::from_f64(clamped, &self.param_type);
    }

    /// 获取值的 f64 表示
    pub fn as_f64(&self) -> f64 {
        self.value.to_f64()
    }

    /// 将值钳位到合法范围
    pub fn clamp_f64(&self, v: f64) -> f64 {
        v.clamp(self.min_f64, self.max_f64)
    }

    /// 重置为默认值
    pub fn reset(&mut self) {
        self.value = self.default.clone();
    }

    /// 判断当前值是否为默认值
    pub fn is_default(&self) -> bool {
        self.value.to_f64() == self.default.to_f64()
    }

    /// 获取归一化值 [0.0, 1.0]
    pub fn normalized(&self) -> f64 {
        let range = self.max_f64 - self.min_f64;
        if range.abs() < f64::EPSILON {
            return 0.0;
        }
        (self.value.to_f64() - self.min_f64) / range
    }

    /// 从归一化值设置
    pub fn set_normalized(&mut self, norm: f64) {
        let norm = norm.clamp(0.0, 1.0);
        let value = self.min_f64 + norm * (self.max_f64 - self.min_f64);
        self.set_from_f64(value);
    }

    /// 获取枚举标签（如果是枚举参数）
    pub fn current_enum_label(&self) -> Option<&str> {
        match &self.value {
            ParameterValue::Enum(idx) => self.enum_labels.get(*idx).map(|s| s.as_str()),
            _ => None,
        }
    }

    /// 获取值的显示字符串
    pub fn display_value(&self) -> String {
        match &self.value {
            ParameterValue::Float(v) => {
                if self.unit.is_empty() {
                    format!("{:.2}", v)
                } else {
                    format!("{:.2} {}", v, self.unit)
                }
            }
            ParameterValue::Int(v) => {
                if self.unit.is_empty() {
                    format!("{}", v)
                } else {
                    format!("{} {}", v, self.unit)
                }
            }
            ParameterValue::Bool(v) => {
                if *v {
                    "On".to_string()
                } else {
                    "Off".to_string()
                }
            }
            ParameterValue::Enum(idx) => self
                .enum_labels
                .get(*idx)
                .cloned()
                .unwrap_or_else(|| format!("[{}]", idx)),
        }
    }

    /// 转换为兼容的 ParamInfo（向下兼容）
    pub fn to_param_info(&self) -> crate::ParamInfo {
        crate::ParamInfo {
            id: self.id.clone(),
            name: self.name.clone(),
            min: self.min_f64,
            max: self.max_f64,
            default: self.default.to_f64(),
            step: self.step,
            value: self.value.to_f64(),
            unit: self.unit.clone(),
        }
    }

    /// 从 ParamInfo 创建 PluginParameter（向上兼容，推断为 Float 类型）
    pub fn from_param_info(info: &crate::ParamInfo) -> Self {
        Self {
            id: info.id.clone(),
            name: info.name.clone(),
            param_type: ParameterType::Float,
            value: ParameterValue::Float(info.value),
            default: ParameterValue::Float(info.default),
            min_f64: info.min,
            max_f64: info.max,
            step: info.step,
            unit: info.unit.clone(),
            enum_labels: Vec::new(),
            group: String::new(),
            automatable: true,
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_float_param() {
        let mut p = PluginParameter::float("gain", "增益", -60.0, 60.0, 0.0, "dB");
        assert_eq!(p.as_f64(), 0.0);
        assert_eq!(p.param_type, ParameterType::Float);

        p.set_from_f64(6.0);
        assert_eq!(p.as_f64(), 6.0);

        // 超出范围 → clamp
        p.set_from_f64(100.0);
        assert_eq!(p.as_f64(), 60.0);

        p.reset();
        assert_eq!(p.as_f64(), 0.0);
    }

    #[test]
    fn test_int_param() {
        let mut p = PluginParameter::int("voices", "声部数", 1, 64, 8, "");
        assert_eq!(p.as_f64(), 8.0);
        assert_eq!(p.value.as_int(), Some(8));

        p.set_from_f64(16.0);
        assert_eq!(p.value.as_int(), Some(16));
    }

    #[test]
    fn test_bool_param() {
        let mut p = PluginParameter::bool_param("bypass", "旁路", false);
        assert_eq!(p.value.as_bool(), Some(false));

        p.set_from_f64(1.0);
        assert_eq!(p.value.as_bool(), Some(true));

        p.set_from_f64(0.3);
        assert_eq!(p.value.as_bool(), Some(false));
    }

    #[test]
    fn test_enum_param() {
        let mut p =
            PluginParameter::enum_param("filter", "滤波器", &["LPF", "HPF", "BPF", "Notch"], 0);
        assert_eq!(p.value.as_enum(), Some(0));
        assert_eq!(p.current_enum_label(), Some("LPF"));

        p.set_from_f64(2.0);
        assert_eq!(p.value.as_enum(), Some(2));
        assert_eq!(p.current_enum_label(), Some("BPF"));

        assert_eq!(p.display_value(), "BPF");
    }

    #[test]
    fn test_normalized() {
        let mut p = PluginParameter::float("gain", "增益", -60.0, 60.0, 0.0, "dB");
        // 0.0 is midpoint → normalized = 0.5
        assert!((p.normalized() - 0.5).abs() < 1e-10);

        p.set_from_f64(-60.0);
        assert!((p.normalized() - 0.0).abs() < 1e-10);

        p.set_from_f64(60.0);
        assert!((p.normalized() - 1.0).abs() < 1e-10);

        // roundtrip
        p.set_normalized(0.25);
        let expected = -60.0 + 0.25 * 120.0; // = -30.0
        assert!((p.as_f64() - expected).abs() < 1e-10);
    }

    #[test]
    fn test_display_value() {
        let p1 = PluginParameter::float("gain", "增益", 0.0, 10.0, 5.5, "dB");
        assert!(p1.display_value().contains("5.50"));
        assert!(p1.display_value().contains("dB"));

        let p2 = PluginParameter::bool_param("on", "开关", true);
        assert_eq!(p2.display_value(), "On");

        let p3 = PluginParameter::int("count", "数量", 1, 10, 3, "个");
        assert!(p3.display_value().contains("3"));
        assert!(p3.display_value().contains("个"));
    }

    #[test]
    fn test_param_info_roundtrip() {
        let original = crate::ParamInfo::new("gain", "增益", -60.0, 60.0, 0.0, "dB");
        let param = PluginParameter::from_param_info(&original);
        let back = param.to_param_info();

        assert_eq!(back.id, original.id);
        assert_eq!(back.min, original.min);
        assert_eq!(back.max, original.max);
    }

    #[test]
    fn test_is_default() {
        let mut p = PluginParameter::float("test", "测试", 0.0, 10.0, 5.0, "");
        assert!(p.is_default());
        p.set_from_f64(7.0);
        assert!(!p.is_default());
        p.reset();
        assert!(p.is_default());
    }
}
