//! 分析器模块 — 相位相关度计 + 矢量示波器 + 自动对齐
//!
//! - CorrelationMeter: 实时 L/R 相位相关度（-1~+1）
//! - VectorScope: Lissajous 相位图数据
//! - AutoAligner: 自动检测并修正相位偏移

/// 相位相关度计
///
/// 计算 L/R 互相关归一化值：
/// ρ = Σ(L·R) / √(Σ(L²)·Σ(R²))
pub struct CorrelationMeter {
    sum_lr: f64,
    sum_ll: f64,
    sum_rr: f64,
    alpha: f64, // 平滑系数
    value: f64,
}

impl CorrelationMeter {
    pub fn new() -> Self {
        Self {
            sum_lr: 0.0,
            sum_ll: 0.0,
            sum_rr: 0.0,
            alpha: 0.999,
            value: 1.0,
        }
    }

    pub fn reset(&mut self) {
        self.sum_lr = 0.0;
        self.sum_ll = 0.0;
        self.sum_rr = 0.0;
        self.value = 1.0;
    }

    pub fn update(&mut self, l: &[f64], r: &[f64], frames: usize) {
        for i in 0..frames {
            let lv = l[i];
            let rv = r[i];

            self.sum_lr = self.alpha * self.sum_lr + lv * rv;
            self.sum_ll = self.alpha * self.sum_ll + lv * lv;
            self.sum_rr = self.alpha * self.sum_rr + rv * rv;
        }

        let denom = (self.sum_ll * self.sum_rr).sqrt();
        if denom > f64::EPSILON {
            self.value = (self.sum_lr / denom).clamp(-1.0, 1.0);
        }
    }

    pub fn value(&self) -> f64 {
        self.value
    }
}

/// 矢量示波器（Lissajous图）
///
/// 输出 L/R 关系的 X/Y 坐标数据，用于绘制相位图。
pub struct VectorScope {
    /// 最近N帧的数据 (x, y)
    buffer: Vec<(f64, f64)>,
    write_pos: usize,
    size: usize,
}

impl VectorScope {
    pub fn new() -> Self {
        let size = 512;
        Self {
            buffer: vec![(0.0, 0.0); size],
            write_pos: 0,
            size,
        }
    }

    pub fn reset(&mut self) {
        self.buffer.fill((0.0, 0.0));
        self.write_pos = 0;
    }

    pub fn update(&mut self, l: &[f64], r: &[f64], frames: usize) {
        for i in 0..frames {
            // X = L+R (Mid), Y = L-R (Side)
            let x = l[i] + r[i];
            let y = l[i] - r[i];
            self.buffer[self.write_pos] = (x, y);
            self.write_pos = (self.write_pos + 1) % self.size;
        }
    }

    /// 获取当前帧数据
    pub fn get_data(&self) -> &[(f64, f64)] {
        &self.buffer
    }
}

/// 自动相位对齐器
///
/// 通过互相关分析检测 L/R 声道间的相位偏移，
/// 返回建议的延迟补偿和相位旋转值。
pub struct AutoAligner {
    /// 分析缓冲区大小
    analysis_size: usize,
}

impl AutoAligner {
    pub fn new() -> Self {
        Self {
            analysis_size: 4096,
        }
    }

    /// 分析 L/R 偏移并返回建议的补偿值
    ///
    /// 返回 Some((delay_samples, phase_degrees)) 或 None（无法确定）
    pub fn analyze(
        &self,
        l: &[f64],
        r: &[f64],
        frames: usize,
        sample_rate: f64,
    ) -> Option<(i32, f64)> {
        if frames < 64 {
            return None;
        }

        let n = frames.min(self.analysis_size);

        // 计算零延迟互相关
        let mut correlation_0 = 0.0f64;
        let mut energy_l = 0.0f64;
        let mut energy_r = 0.0f64;
        for i in 0..n {
            correlation_0 += l[i] * r[i];
            energy_l += l[i] * l[i];
            energy_r += r[i] * r[i];
        }

        // 归一化
        let norm = (energy_l * energy_r).sqrt();
        if norm < f64::EPSILON {
            return None;
        }
        let corr_normalized = correlation_0 / norm;

        // 如果相关度已经很高，无需调整
        if corr_normalized > 0.95 {
            return Some((0, 0.0));
        }

        // 尝试不同延迟偏移，找到最大互相关
        let max_lag = (128.min(n / 2)) as i32;
        let mut best_lag: i32 = 0;
        let mut best_corr = corr_normalized;

        for lag in -max_lag..=max_lag {
            let mut corr = 0.0f64;
            let mut count = 0usize;

            for i in 0..n {
                let r_idx = (i as i32) + lag;
                if r_idx >= 0 && (r_idx as usize) < n {
                    corr += l[i] * r[r_idx as usize];
                    count += 1;
                }
            }

            if count > 0 {
                corr /= count as f64;
                if corr > best_corr {
                    best_corr = corr;
                    best_lag = lag;
                }
            }
        }

        // 估算残余相位偏移（从互相关虚部近似）
        let phase_est = if best_corr < 0.0 {
            180.0 // 反相关→建议180°翻转
        } else {
            // 从相关度推算相位差
            let cos_theta = best_corr.min(1.0);
            cos_theta.acos() * 180.0 / std::f64::consts::PI
        };

        if best_lag == 0 && phase_est < 5.0 {
            return None; // 无需调整
        }

        Some((best_lag, phase_est))
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_correlation_in_phase() {
        let mut meter = CorrelationMeter::new();
        let l: Vec<f64> = (0..1000).map(|i| (i as f64 * 0.01).sin()).collect();
        let r = l.clone();

        meter.update(&l, &r, 1000);
        assert!(meter.value() > 0.9, "同相应高度相关: {}", meter.value());
    }

    #[test]
    fn test_correlation_anti_phase() {
        let mut meter = CorrelationMeter::new();
        let l: Vec<f64> = (0..1000).map(|i| (i as f64 * 0.01).sin()).collect();
        let r: Vec<f64> = l.iter().map(|&v| -v).collect();

        meter.update(&l, &r, 1000);
        assert!(meter.value() < -0.9, "反相应高度负相关: {}", meter.value());
    }

    #[test]
    fn test_vectorscope_update() {
        let mut scope = VectorScope::new();
        let l = vec![1.0; 100];
        let r = vec![0.5; 100];
        scope.update(&l, &r, 100);
        let data = scope.get_data();
        assert_eq!(data.len(), 512);
    }

    #[test]
    fn test_auto_align_no_shift() {
        let aligner = AutoAligner::new();
        let l: Vec<f64> = (0..4096).map(|i| (i as f64 * 0.1).sin()).collect();
        let r = l.clone();

        let result = aligner.analyze(&l, &r, 4096, 44100.0);
        // 同相信号应返回无需调整或(0, ~0)
        if let Some((delay, phase)) = result {
            assert!(delay == 0, "无偏移不应建议延迟");
            assert!(phase < 10.0, "无偏移相位应接近0: {}", phase);
        }
    }

    #[test]
    fn test_auto_align_delayed() {
        let aligner = AutoAligner::new();
        let base: Vec<f64> = (0..4096).map(|i| (i as f64 * 0.1).sin()).collect();

        // 右声道延迟10个采样
        let mut r = vec![0.0; 4096];
        r[10..].copy_from_slice(&base[..4086]);

        let result = aligner.analyze(&base, &r, 4096, 44100.0);
        if let Some((delay, _phase)) = result {
            assert!(
                delay.abs() > 0,
                "延迟信号应检测到偏移: delay={}",
                delay
            );
        }
    }
}
