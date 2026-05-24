//! 相位旋转器 — 连续相位旋转 0°~360°
//!
//! 基于希尔伯特变换实现全频段相位旋转。
//! 原理：将信号分解为正交分量（I/Q），然后旋转指定角度。

/// 相位旋转器状态
pub struct PhaseRotator {
    /// 目标相位（度）
    phase_deg: f64,
    /// 希尔伯特变换延迟线（FIR，21阶）
    hilbert_l: [f64; 21],
    hilbert_r: [f64; 21],
    /// 延迟线索引
    index: usize,
}

// 21阶希尔伯特变换FIR系数（对称）
const HILBERT_COEFFS: [f64; 21] = [
    0.0,
    -0.0352680306327327,
    0.0,
    -0.0796216262746694,
    0.0,
    -0.1591549430918953,
    0.0,
    -0.477464829275686,
    0.0,
    0.0,
    1.0,
    0.0,
    -0.477464829275686,
    0.0,
    -0.1591549430918953,
    0.0,
    -0.0796216262746694,
    0.0,
    -0.0352680306327327,
    0.0,
    0.0,
];

impl PhaseRotator {
    pub fn new(_sample_rate: f64) -> Self {
        Self {
            phase_deg: 0.0,
            hilbert_l: [0.0; 21],
            hilbert_r: [0.0; 21],
            index: 0,
        }
    }

    pub fn set_phase(&mut self, degrees: f64) {
        self.phase_deg = degrees;
    }

    pub fn reset(&mut self) {
        self.hilbert_l.fill(0.0);
        self.hilbert_r.fill(0.0);
        self.index = 0;
    }

    /// 处理单个采样点
    ///
    /// 使用希尔伯特变换得到正交分量，然后旋转：
    /// out = in * cos(θ) + hilbert(in) * sin(θ)
    pub fn process(&mut self, sample: f64) -> f64 {
        if self.phase_deg.abs() < 0.01 {
            return sample; // 0°旋转=直通
        }
        if (self.phase_deg - 180.0).abs() < 0.01 {
            return -sample; // 180°=反转
        }

        // 写入延迟线
        let idx = self.index % 21;
        self.hilbert_l[idx] = sample;

        // 计算希尔伯特变换（正交分量）
        let mut quadrature = 0.0f64;
        for (i, &coeff) in HILBERT_COEFFS.iter().enumerate() {
            let read_idx = (self.index + 21 - i) % 21;
            quadrature += coeff * self.hilbert_l[read_idx];
        }

        // 直通延迟（补偿希尔伯特变换的群延迟=10个采样点）
        let delayed_idx = (self.index + 21 - 10) % 21;
        let in_phase = self.hilbert_l[delayed_idx];

        // 旋转
        let angle = self.phase_deg * std::f64::consts::PI / 180.0;
        let cos_a = angle.cos();
        let sin_a = angle.sin();

        self.index += 1;

        in_phase * cos_a + quadrature * sin_a
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_passthrough() {
        let mut rotator = PhaseRotator::new(44100.0);
        rotator.set_phase(0.0);
        // 填充延迟线
        for i in 0..25 {
            let val = rotator.process(1.0);
            if i >= 20 {
                assert!(
                    (val - 1.0).abs() < 0.1,
                    "0°旋转应近似直通: {}",
                    val
                );
            }
        }
    }

    #[test]
    fn test_180_invert() {
        let mut rotator = PhaseRotator::new(44100.0);
        rotator.set_phase(180.0);
        let val = rotator.process(1.0);
        assert!(
            (val + 1.0).abs() < 0.01,
            "180°旋转应反转: {}",
            val
        );
    }
}
