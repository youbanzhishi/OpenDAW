//! # Phase Cancel — 专业相位抵消与对齐插件
//!
//! OpenDAW 的相位处理瑞士军刀，集成以下能力：
//!
//! - **相位反转**：180° 翻转（单声道/立体声/仅Side）
//! - **相位旋转**：连续 0°~360° 旋转（全频段）
//! - **全通滤波**：频率相关相位调整（1阶/2阶）
//! - **Mid/Side 相位处理**：独立控制 Mid/Side 相位
//! - **自动相位对齐**：检测并修正立体声相位偏移
//! - **相位相关度计**：实时监测 L/R 相位关系
//! - **矢量示波器**：Lissajous 相位图
//! - **延迟补偿**：采样级微调对齐
//!
//! # 快速开始
//!
//! ```ignore
//! use phase_cancel::PhaseCancelPlugin;
//! use opendaw_extension::VcPlugin;
//!
//! let mut plugin = PhaseCancelPlugin::new();
//! plugin.init(44100.0, 512).unwrap();
//!
//! // 翻转右声道相位
//! plugin.set_param("invert_r", 1.0).unwrap();
//! ```

mod allpass;
mod analysis;
mod delay_line;
mod dsp;
mod ms_processor;
mod phase_rotator;

use opendaw_extension::{AudioBuffer, ParamInfo, PluginError, PluginInfo, PluginType, VcPlugin};

// ── 参数ID常量 ──────────────────────────────────────────────────

const PARAM_INVERT_L: &str = "invert_l";
const PARAM_INVERT_R: &str = "invert_r";
const PARAM_PHASE_ROTATE_L: &str = "phase_rotate_l";
const PARAM_PHASE_ROTATE_R: &str = "phase_rotate_r";
const PARAM_ALLPASS_FREQ: &str = "allpass_freq";
const PARAM_ALLPASS_Q: &str = "allpass_q";
const PARAM_ALLPASS_ORDER: &str = "allpass_order";
const PARAM_MS_WIDTH: &str = "ms_width";
const PARAM_MS_PHASE_MID: &str = "ms_phase_mid";
const PARAM_MS_PHASE_SIDE: &str = "ms_phase_side";
const PARAM_AUTO_ALIGN: &str = "auto_align";
const PARAM_DELAY_SAMPLES_L: &str = "delay_samples_l";
const PARAM_DELAY_SAMPLES_R: &str = "delay_samples_r";
const PARAM_MIX: &str = "mix";
const PARAM_CORRELATION: &str = "correlation"; // read-only analyzer output
const PARAM_BALANCE: &str = "balance";

/// 专业相位抵消与对齐插件
pub struct PhaseCancelPlugin {
    sample_rate: f64,
    buffer_size: usize,

    // 参数存储
    params: std::collections::HashMap<String, f64>,

    // DSP状态
    phase_rotator_l: phase_rotator::PhaseRotator,
    phase_rotator_r: phase_rotator::PhaseRotator,
    allpass_filter_l: allpass::AllPassChain,
    allpass_filter_r: allpass::AllPassChain,
    ms_processor: ms_processor::MSProcessor,
    delay_l: delay_line::DelayLine,
    delay_r: delay_line::DelayLine,

    // 分析器状态
    correlation_meter: analysis::CorrelationMeter,
    vectorscope: analysis::VectorScope,

    // 自动对齐
    auto_aligner: analysis::AutoAligner,
    auto_align_pending: bool,

    // 参数定义（缓存）
    param_defs: Vec<ParamInfo>,
}

impl PhaseCancelPlugin {
    /// 创建新插件实例
    pub fn new() -> Self {
        let param_defs = Self::build_param_defs();
        let mut params = std::collections::HashMap::new();
        for p in &param_defs {
            params.insert(p.id.clone(), p.default);
        }

        Self {
            sample_rate: 44100.0,
            buffer_size: 512,
            params,
            phase_rotator_l: phase_rotator::PhaseRotator::new(44100.0),
            phase_rotator_r: phase_rotator::PhaseRotator::new(44100.0),
            allpass_filter_l: allpass::AllPassChain::new(44100.0),
            allpass_filter_r: allpass::AllPassChain::new(44100.0),
            ms_processor: ms_processor::MSProcessor::new(44100.0),
            delay_l: delay_line::DelayLine::new(4096),
            delay_r: delay_line::DelayLine::new(4096),
            correlation_meter: analysis::CorrelationMeter::new(),
            vectorscope: analysis::VectorScope::new(),
            auto_aligner: analysis::AutoAligner::new(),
            auto_align_pending: false,
            param_defs,
        }
    }

    fn build_param_defs() -> Vec<ParamInfo> {
        vec![
            // ── 相位反转 ──
            ParamInfo::new(PARAM_INVERT_L, "反转左声道", 0.0, 1.0, 0.0, ""),
            ParamInfo::new(PARAM_INVERT_R, "反转右声道", 0.0, 1.0, 0.0, ""),
            // ── 相位旋转 ──
            ParamInfo::new(PARAM_PHASE_ROTATE_L, "左声道相位旋转", 0.0, 360.0, 0.0, "°"),
            ParamInfo::new(PARAM_PHASE_ROTATE_R, "右声道相位旋转", 0.0, 360.0, 0.0, "°"),
            // ── 全通滤波 ──
            ParamInfo::new(PARAM_ALLPASS_FREQ, "全通频率", 20.0, 20000.0, 1000.0, "Hz"),
            ParamInfo::new(PARAM_ALLPASS_Q, "全通Q值", 0.1, 18.0, 0.707, ""),
            ParamInfo::new(PARAM_ALLPASS_ORDER, "全通阶数", 1.0, 4.0, 1.0, ""),
            // ── Mid/Side ──
            ParamInfo::new(PARAM_MS_WIDTH, "立体声宽度", 0.0, 200.0, 100.0, "%"),
            ParamInfo::new(PARAM_MS_PHASE_MID, "Mid相位旋转", 0.0, 360.0, 0.0, "°"),
            ParamInfo::new(PARAM_MS_PHASE_SIDE, "Side相位旋转", 0.0, 360.0, 0.0, "°"),
            // ── 自动对齐 ──
            ParamInfo::new(PARAM_AUTO_ALIGN, "自动对齐", 0.0, 1.0, 0.0, ""),
            ParamInfo::new(PARAM_DELAY_SAMPLES_L, "左声道延迟", 0.0, 4096.0, 0.0, "smp"),
            ParamInfo::new(PARAM_DELAY_SAMPLES_R, "右声道延迟", 0.0, 4096.0, 0.0, "smp"),
            // ── 混音/平衡 ──
            ParamInfo::new(PARAM_MIX, "干湿比", 0.0, 100.0, 100.0, "%"),
            ParamInfo::new(PARAM_BALANCE, "左右平衡", -100.0, 100.0, 0.0, "%"),
            // ── 分析器输出（只读）──
            ParamInfo::new(PARAM_CORRELATION, "相位相关度", -1.0, 1.0, 0.0, ""),
        ]
    }

    fn get_f64(&self, id: &str) -> f64 {
        self.params.get(id).copied().unwrap_or(0.0)
    }

    fn is_on(&self, id: &str) -> bool {
        self.get_f64(id) >= 0.5
    }
}

impl VcPlugin for PhaseCancelPlugin {
    fn plugin_id(&self) -> &str {
        "vc-phase-cancel"
    }

    fn plugin_name(&self) -> &str {
        "相位抵消对齐器"
    }

    fn plugin_type(&self) -> PluginType {
        PluginType::Effect
    }

    fn version(&self) -> &str {
        "1.0.0"
    }

    fn get_info(&self) -> PluginInfo {
        PluginInfo::new(self.plugin_id(), self.plugin_name(), self.plugin_type())
            .with_author("OpenDAW Team")
            .with_version(self.version())
            .with_parameters(self.get_params())
    }

    fn init(&mut self, sample_rate: f64, buffer_size: usize) -> Result<(), PluginError> {
        self.sample_rate = sample_rate;
        self.buffer_size = buffer_size;

        self.phase_rotator_l = phase_rotator::PhaseRotator::new(sample_rate);
        self.phase_rotator_r = phase_rotator::PhaseRotator::new(sample_rate);
        self.allpass_filter_l = allpass::AllPassChain::new(sample_rate);
        self.allpass_filter_r = allpass::AllPassChain::new(sample_rate);
        self.ms_processor = ms_processor::MSProcessor::new(sample_rate);
        self.delay_l = delay_line::DelayLine::new(4096);
        self.delay_r = delay_line::DelayLine::new(4096);

        Ok(())
    }

    fn process(&mut self, input: &AudioBuffer, output: &mut AudioBuffer) {
        let frames = input.frames.min(output.frames);
        if frames == 0 {
            return;
        }

        let channels = input.channels.min(output.channels).min(2);
        let mix = self.get_f64(PARAM_MIX) / 100.0;
        let invert_l = self.is_on(PARAM_INVERT_L);
        let invert_r = self.is_on(PARAM_INVERT_R);
        let phase_l = self.get_f64(PARAM_PHASE_ROTATE_L);
        let phase_r = self.get_f64(PARAM_PHASE_ROTATE_R);
        let allpass_freq = self.get_f64(PARAM_ALLPASS_FREQ);
        let allpass_q = self.get_f64(PARAM_ALLPASS_Q);
        let allpass_order = self.get_f64(PARAM_ALLPASS_ORDER).round() as usize;
        let ms_width = self.get_f64(PARAM_MS_WIDTH) / 100.0;
        let ms_phase_mid = self.get_f64(PARAM_MS_PHASE_MID);
        let ms_phase_side = self.get_f64(PARAM_MS_PHASE_SIDE);
        let delay_l_val = self.get_f64(PARAM_DELAY_SAMPLES_L).round() as usize;
        let delay_r_val = self.get_f64(PARAM_DELAY_SAMPLES_R).round() as usize;
        let balance = self.get_f64(PARAM_BALANCE) / 100.0;

        // 更新DSP参数
        self.phase_rotator_l.set_phase(phase_l);
        self.phase_rotator_r.set_phase(phase_r);
        self.allpass_filter_l
            .set_params(allpass_freq, allpass_q, allpass_order);
        self.allpass_filter_r
            .set_params(allpass_freq, allpass_q, allpass_order);
        self.ms_processor.set_width(ms_width);
        self.ms_processor.set_mid_phase(ms_phase_mid);
        self.ms_processor.set_side_phase(ms_phase_side);
        self.delay_l.set_delay(delay_l_val);
        self.delay_r.set_delay(delay_r_val);

        // 自动对齐触发
        if self.is_on(PARAM_AUTO_ALIGN) && !self.auto_align_pending {
            self.auto_align_pending = true;
        }

        // 逐帧处理
        let mut frame_l = vec![0.0f64; frames];
        let mut frame_r = vec![0.0f64; frames];

        for i in 0..frames {
            let mut l = if channels > 0 {
                input.sample(0, i)
            } else {
                0.0
            };
            let mut r = if channels > 1 { input.sample(1, i) } else { l };

            // 1. 相位反转
            if invert_l {
                l = -l;
            }
            if invert_r {
                r = -r;
            }

            // 2. 相位旋转
            l = self.phase_rotator_l.process(l);
            r = self.phase_rotator_r.process(r);

            // 3. 全通滤波
            l = self.allpass_filter_l.process(l);
            r = self.allpass_filter_r.process(r);

            // 4. Mid/Side处理
            let (l_ms, r_ms) = self.ms_processor.process(l, r);
            l = l_ms;
            r = r_ms;

            // 5. 延迟补偿
            l = self.delay_l.process(l);
            r = self.delay_r.process(r);

            // 6. 平衡
            if balance.abs() > f64::EPSILON {
                let gain_l = (1.0 - balance).max(0.0).sqrt();
                let gain_r = (1.0 + balance).max(0.0).sqrt();
                l *= gain_l;
                r *= gain_r;
            }

            // 7. 干湿比混合
            let dry_l = if channels > 0 {
                input.sample(0, i)
            } else {
                0.0
            };
            let dry_r = if channels > 1 {
                input.sample(1, i)
            } else {
                dry_l
            };
            l = dry_l * (1.0 - mix) + l * mix;
            r = dry_r * (1.0 - mix) + r * mix;

            frame_l[i] = l;
            frame_r[i] = r;
        }

        // 写入输出
        for i in 0..frames {
            if output.channels > 0 {
                output.set_sample(0, i, frame_l[i]);
            }
            if output.channels > 1 {
                output.set_sample(1, i, frame_r[i]);
            }
        }

        // 更新分析器
        self.correlation_meter.update(&frame_l, &frame_r, frames);
        self.vectorscope.update(&frame_l, &frame_r, frames);

        // 自动对齐处理
        if self.auto_align_pending {
            let result = self
                .auto_aligner
                .analyze(&frame_l, &frame_r, frames, self.sample_rate);
            if let Some((delay_offset, phase_offset)) = result {
                // 应用对齐结果
                if delay_offset > 0 {
                    let _ = self.set_param(PARAM_DELAY_SAMPLES_R, delay_offset as f64);
                } else if delay_offset < 0 {
                    let _ = self.set_param(PARAM_DELAY_SAMPLES_L, (-delay_offset) as f64);
                }
                if phase_offset.abs() > f64::EPSILON {
                    let _ = self.set_param(PARAM_PHASE_ROTATE_R, phase_offset);
                }
            }
            // 关闭自动对齐
            let _ = self.set_param(PARAM_AUTO_ALIGN, 0.0);
            self.auto_align_pending = false;
        }

        // 更新相关度参数
        self.params.insert(
            PARAM_CORRELATION.to_string(),
            self.correlation_meter.value(),
        );
    }

    fn get_params(&self) -> Vec<ParamInfo> {
        self.param_defs
            .iter()
            .map(|def| ParamInfo {
                id: def.id.clone(),
                name: def.name.clone(),
                min: def.min,
                max: def.max,
                default: def.default,
                step: def.step,
                value: self.params.get(&def.id).copied().unwrap_or(def.default),
                unit: def.unit.clone(),
            })
            .collect()
    }

    fn set_param(&mut self, id: &str, value: f64) -> Result<(), PluginError> {
        if let Some(def) = self.param_defs.iter().find(|p| p.id == id) {
            let clamped = value.clamp(def.min, def.max);
            self.params.insert(id.to_string(), clamped);
            Ok(())
        } else {
            Err(PluginError::ProcessFailed(format!("未知参数: {}", id)))
        }
    }

    fn get_param(&self, id: &str) -> Option<f64> {
        self.params.get(id).copied()
    }

    fn preset_names(&self) -> Vec<String> {
        vec![
            "相位抵消（全翻转）".to_string(),
            "立体声增宽".to_string(),
            "单声道低频".to_string(),
            "Side增强".to_string(),
            "自动对齐".to_string(),
            "微调修复".to_string(),
        ]
    }

    fn load_preset(&mut self, name: &str) -> Result<(), PluginError> {
        match name {
            "相位抵消（全翻转）" => {
                self.set_param(PARAM_INVERT_L, 1.0)?;
                self.set_param(PARAM_INVERT_R, 1.0)?;
                self.set_param(PARAM_PHASE_ROTATE_L, 0.0)?;
                self.set_param(PARAM_PHASE_ROTATE_R, 0.0)?;
                self.set_param(PARAM_MIX, 100.0)?;
            }
            "立体声增宽" => {
                self.set_param(PARAM_MS_WIDTH, 150.0)?;
                self.set_param(PARAM_MS_PHASE_SIDE, 15.0)?;
                self.set_param(PARAM_MIX, 100.0)?;
            }
            "单声道低频" => {
                self.set_param(PARAM_MS_WIDTH, 0.0)?;
                self.set_param(PARAM_ALLPASS_FREQ, 200.0)?;
                self.set_param(PARAM_ALLPASS_ORDER, 2.0)?;
                self.set_param(PARAM_MIX, 100.0)?;
            }
            "Side增强" => {
                self.set_param(PARAM_MS_WIDTH, 130.0)?;
                self.set_param(PARAM_MS_PHASE_SIDE, 30.0)?;
                self.set_param(PARAM_INVERT_L, 0.0)?;
                self.set_param(PARAM_INVERT_R, 0.0)?;
                self.set_param(PARAM_MIX, 100.0)?;
            }
            "自动对齐" => {
                self.set_param(PARAM_AUTO_ALIGN, 1.0)?;
                self.set_param(PARAM_MIX, 100.0)?;
            }
            "微调修复" => {
                self.set_param(PARAM_PHASE_ROTATE_L, 5.0)?;
                self.set_param(PARAM_PHASE_ROTATE_R, 5.0)?;
                self.set_param(PARAM_DELAY_SAMPLES_R, 3.0)?;
                self.set_param(PARAM_MIX, 100.0)?;
            }
            _ => return Err(PluginError::ProcessFailed(format!("未知预设: {}", name))),
        }
        Ok(())
    }

    fn destroy(&mut self) {
        // 清理DSP状态
        self.phase_rotator_l.reset();
        self.phase_rotator_r.reset();
        self.allpass_filter_l.reset();
        self.allpass_filter_r.reset();
        self.ms_processor.reset();
        self.delay_l.reset();
        self.delay_r.reset();
        self.correlation_meter.reset();
        self.vectorscope.reset();
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_plugin_creation() {
        let plugin = PhaseCancelPlugin::new();
        assert_eq!(plugin.plugin_id(), "vc-phase-cancel");
        assert_eq!(plugin.plugin_type(), PluginType::Effect);
    }

    #[test]
    fn test_init_process() {
        let mut plugin = PhaseCancelPlugin::new();
        plugin.init(44100.0, 256).unwrap();

        let input = AudioBuffer::new(2, 256);
        let mut output = AudioBuffer::new(2, 256);
        plugin.process(&input, &mut output);

        // 静音输入→静音输出
        for ch in 0..2 {
            for i in 0..256 {
                assert!(output.sample(ch, i).abs() < 1e-10, "静音输入应产生静音输出");
            }
        }
    }

    #[test]
    fn test_phase_invert() {
        let mut plugin = PhaseCancelPlugin::new();
        plugin.init(44100.0, 256).unwrap();
        plugin.set_param(PARAM_INVERT_R, 1.0).unwrap();

        let mut input = AudioBuffer::new(2, 256);
        // 填充1.0到两个声道
        for i in 0..256 {
            input.set_sample(0, i, 1.0);
            input.set_sample(1, i, 1.0);
        }

        let mut output = AudioBuffer::new(2, 256);
        plugin.process(&input, &mut output);

        // 左声道应近似1.0（可能有极小的旋转误差），右声道应为-1.0
        let l_avg: f64 = (0..256).map(|i| output.sample(0, i)).sum::<f64>() / 256.0;
        let r_avg: f64 = (0..256).map(|i| output.sample(1, i)).sum::<f64>() / 256.0;
        assert!(l_avg > 0.9, "左声道应保持正相位: {}", l_avg);
        assert!(r_avg < -0.9, "右声道应被反转: {}", r_avg);
    }

    #[test]
    fn test_presets() {
        let mut plugin = PhaseCancelPlugin::new();
        plugin.init(44100.0, 256).unwrap();

        let names = plugin.preset_names();
        assert_eq!(names.len(), 6);

        for name in &names {
            assert!(plugin.load_preset(name).is_ok(), "预设 '{}' 加载失败", name);
        }

        assert!(plugin.load_preset("不存在的预设").is_err());
    }

    #[test]
    fn test_mix_parameter() {
        let mut plugin = PhaseCancelPlugin::new();
        plugin.init(44100.0, 256).unwrap();
        plugin.set_param(PARAM_INVERT_L, 1.0).unwrap();
        plugin.set_param(PARAM_MIX, 50.0).unwrap();

        let mut input = AudioBuffer::new(2, 256);
        for i in 0..256 {
            input.set_sample(0, i, 1.0);
            input.set_sample(1, i, 1.0);
        }

        let mut output = AudioBuffer::new(2, 256);
        plugin.process(&input, &mut output);

        // 50% mix: 左声道应约为0 (1.0 * 0.5 + (-1.0) * 0.5)
        let l_avg: f64 = (0..256).map(|i| output.sample(0, i)).sum::<f64>() / 256.0;
        assert!(l_avg.abs() < 0.15, "50%混合下左声道应接近零: {}", l_avg);
    }

    #[test]
    fn test_correlation_meter() {
        let mut plugin = PhaseCancelPlugin::new();
        plugin.init(44100.0, 256).unwrap();

        // 同相信号 → 相关度接近1
        let mut input = AudioBuffer::new(2, 256);
        for i in 0..256 {
            let val = (2.0 * std::f64::consts::PI * 440.0 * (i as f64 / 44100.0)).sin();
            input.set_sample(0, i, val);
            input.set_sample(1, i, val);
        }

        let mut output = AudioBuffer::new(2, 256);
        for _ in 0..10 {
            plugin.process(&input, &mut output);
        }

        let corr = plugin.get_param(PARAM_CORRELATION).unwrap_or(0.0);
        assert!(corr > 0.8, "同相信号相关度应接近1.0: {}", corr);
    }

    #[test]
    fn test_param_clamping() {
        let mut plugin = PhaseCancelPlugin::new();
        plugin.init(44100.0, 256).unwrap();

        // 超范围值应被clamp
        plugin.set_param(PARAM_PHASE_ROTATE_L, 500.0).unwrap();
        assert_eq!(plugin.get_param(PARAM_PHASE_ROTATE_L), Some(360.0));

        plugin.set_param(PARAM_PHASE_ROTATE_L, -50.0).unwrap();
        assert_eq!(plugin.get_param(PARAM_PHASE_ROTATE_L), Some(0.0));
    }

    #[test]
    fn test_unknown_param() {
        let mut plugin = PhaseCancelPlugin::new();
        let result = plugin.set_param("nonexistent", 1.0);
        assert!(result.is_err());
    }
}
