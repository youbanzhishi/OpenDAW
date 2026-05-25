//! 全通滤波器链 — 频率相关相位调整
//!
//! 一阶和二阶全通滤波器，在改变相位的同时保持幅度响应不变。
//! 支持级联1~4阶。

/// 单个二阶全通滤波器
#[derive(Clone)]
struct SecondOrderAllPass {
    x1: f64,
    x2: f64,
    y1: f64,
    y2: f64,
    a1: f64,
    a2: f64,
}

impl SecondOrderAllPass {
    fn new() -> Self {
        Self {
            x1: 0.0,
            x2: 0.0,
            y1: 0.0,
            y2: 0.0,
            a1: 0.0,
            a2: 0.0,
        }
    }

    fn set_params(&mut self, freq: f64, q: f64, sample_rate: f64) {
        let omega = 2.0 * std::f64::consts::PI * freq / sample_rate;
        let sin_omega = omega.sin();
        let cos_omega = omega.cos();
        let alpha = sin_omega / (2.0 * q);

        let _b0 = 1.0 - alpha; // 全通滤波器b0系数未直接使用
        let b1 = -2.0 * cos_omega;
        let b2 = 1.0 + alpha;
        let a0 = 1.0 + alpha;

        // 全通: H(z) = (a2 + a1*z^-1 + z^-2) / (1 + a1*z^-1 + a2*z^-2)
        self.a1 = b1 / a0;
        self.a2 = b2 / a0;
    }

    fn process(&mut self, x: f64) -> f64 {
        let y = -self.a2 * x + self.a1 * self.x1 + self.x2 - self.a1 * self.y1 - self.a2 * self.y2;

        self.x2 = self.x1;
        self.x1 = x;
        self.y2 = self.y1;
        self.y1 = y;

        y
    }

    fn reset(&mut self) {
        self.x1 = 0.0;
        self.x2 = 0.0;
        self.y1 = 0.0;
        self.y2 = 0.0;
    }
}

/// 全通滤波器链（1~4阶）
pub struct AllPassChain {
    filters: Vec<SecondOrderAllPass>,
    sample_rate: f64,
    freq: f64,
    q: f64,
    order: usize,
}

impl AllPassChain {
    pub fn new(sample_rate: f64) -> Self {
        Self {
            filters: vec![SecondOrderAllPass::new(); 4],
            sample_rate,
            freq: 1000.0,
            q: 0.707,
            order: 1,
        }
    }

    pub fn set_params(&mut self, freq: f64, q: f64, order: usize) {
        self.freq = freq.max(20.0).min(20000.0);
        self.q = q.max(0.1).min(18.0);
        self.order = order.max(1).min(4);

        for f in &mut self.filters {
            f.set_params(self.freq, self.q, self.sample_rate);
        }
    }

    pub fn process(&mut self, sample: f64) -> f64 {
        let mut out = sample;
        for (i, f) in self.filters.iter_mut().enumerate() {
            if i < self.order {
                out = f.process(out);
            }
        }
        out
    }

    pub fn reset(&mut self) {
        for f in &mut self.filters {
            f.reset();
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_allpass_unit_gain() {
        let mut chain = AllPassChain::new(44100.0);
        chain.set_params(1000.0, 0.707, 1);

        // 全通滤波器应保持幅度不变
        let mut max_out = 0.0f64;
        for i in 0..44100 {
            let input = (2.0 * std::f64::consts::PI * 440.0 * (i as f64 / 44100.0)).sin();
            let output = chain.process(input);
            max_out = max_out.max(output.abs());
        }
        // 输出幅度应接近1.0（允许建立期误差）
        assert!((max_out - 1.0).abs() < 0.15, "全通应保持幅度: {}", max_out);
    }

    #[test]
    fn test_allpass_cascade() {
        let mut chain = AllPassChain::new(44100.0);
        chain.set_params(500.0, 1.0, 4);

        // 4阶级联仍应保持幅度
        let mut energy = 0.0f64;
        for i in 100..1000 {
            let input = (2.0 * std::f64::consts::PI * 440.0 * (i as f64 / 44100.0)).sin();
            let output = chain.process(input);
            energy += output * output;
        }
        let rms = (energy / 900.0).sqrt();
        assert!((rms - 0.707).abs() < 0.2, "4阶全通应保持幅度: RMS={}", rms);
    }
}
