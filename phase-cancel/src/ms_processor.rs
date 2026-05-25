//! Mid/Side 处理器 — 立体声宽度与相位控制
//!
//! 将 L/R 转为 M/S，独立控制 Mid/Side 相位旋转，
//! 调整立体声宽度后转回 L/R。

use super::phase_rotator::PhaseRotator;

/// Mid/Side 相位处理器
pub struct MSProcessor {
    width: f64, // 0.0~2.0 (0%=mono, 100%=normal, 200%=extra wide)
    mid_rotator: PhaseRotator,
    side_rotator: PhaseRotator,
}

impl MSProcessor {
    pub fn new(sample_rate: f64) -> Self {
        Self {
            width: 1.0,
            mid_rotator: PhaseRotator::new(sample_rate),
            side_rotator: PhaseRotator::new(sample_rate),
        }
    }

    pub fn set_width(&mut self, width_pct: f64) {
        self.width = width_pct.max(0.0).min(2.0);
    }

    pub fn set_mid_phase(&mut self, degrees: f64) {
        self.mid_rotator.set_phase(degrees);
    }

    pub fn set_side_phase(&mut self, degrees: f64) {
        self.side_rotator.set_phase(degrees);
    }

    pub fn reset(&mut self) {
        self.mid_rotator.reset();
        self.side_rotator.reset();
    }

    /// 处理一帧: L/R → M/S → 处理 → L/R
    pub fn process(&mut self, l: f64, r: f64) -> (f64, f64) {
        // L/R → M/S
        let mid = (l + r) * 0.5;
        let side = (l - r) * 0.5;

        // 独立相位旋转
        let mid_processed = self.mid_rotator.process(mid);
        let side_processed = self.side_rotator.process(side);

        // 宽度控制
        let mid_out = mid_processed;
        let side_out = side_processed * self.width;

        // M/S → L/R
        let l_out = mid_out + side_out;
        let r_out = mid_out - side_out;

        (l_out, r_out)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_ms_width_100() {
        let mut proc = MSProcessor::new(44100.0);
        proc.set_width(1.0); // 100% = normal

        // 跳过建立期
        for _ in 0..25 {
            proc.process(1.0, 1.0);
        }

        let (l, r) = proc.process(1.0, 1.0);
        // 同相信号: mid=1.0, side=0.0 → L=1.0, R=1.0
        assert!((l - r).abs() < 0.1, "100%宽度应保持L/R近似相等");
    }

    #[test]
    fn test_ms_width_0() {
        let mut proc = MSProcessor::new(44100.0);
        proc.set_width(0.0); // 0% = mono

        // 跳过建立期
        for _ in 0..25 {
            proc.process(0.5, 0.8);
        }

        let (l, r) = proc.process(0.5, 0.8);
        // 0%宽度: side被消除 → L=R=mid
        assert!((l - r).abs() < 0.15, "0%宽度应输出单声道: L={}, R={}", l, r);
    }
}
