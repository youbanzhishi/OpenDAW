//! 延迟线 — 采样级精确延迟补偿
//!
//! 用于微调左右声道的时间对齐，消除因物理路径差异
//! 造成的相位偏移。

/// 延迟线（环形缓冲区实现）
pub struct DelayLine {
    buffer: Vec<f64>,
    write_pos: usize,
    delay_samples: usize,
}

impl DelayLine {
    pub fn new(max_delay: usize) -> Self {
        let size = max_delay.max(1);
        Self {
            buffer: vec![0.0; size],
            write_pos: 0,
            delay_samples: 0,
        }
    }

    pub fn set_delay(&mut self, samples: usize) {
        self.delay_samples = samples.min(self.buffer.len() - 1);
    }

    pub fn reset(&mut self) {
        self.buffer.fill(0.0);
        self.write_pos = 0;
    }

    pub fn process(&mut self, sample: f64) -> f64 {
        // 写入
        self.buffer[self.write_pos] = sample;

        // 读取（延迟位置）
        let read_pos = if self.write_pos >= self.delay_samples {
            self.write_pos - self.delay_samples
        } else {
            self.buffer.len() - (self.delay_samples - self.write_pos)
        };

        let output = self.buffer[read_pos];

        // 推进写入位置
        self.write_pos = (self.write_pos + 1) % self.buffer.len();

        output
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_zero_delay() {
        let mut dl = DelayLine::new(1024);
        dl.set_delay(0);
        assert_eq!(dl.process(1.0), 1.0);
    }

    #[test]
    fn test_delay_3() {
        let mut dl = DelayLine::new(1024);
        dl.set_delay(3);

        assert_eq!(dl.process(1.0), 0.0);
        assert_eq!(dl.process(2.0), 0.0);
        assert_eq!(dl.process(3.0), 0.0);
        assert_eq!(dl.process(4.0), 1.0);
        assert_eq!(dl.process(5.0), 2.0);
    }

    #[test]
    fn test_delay_wrap() {
        let mut dl = DelayLine::new(8);
        dl.set_delay(4);

        for i in 0..8 {
            dl.process(i as f64);
        }
        // 8个采样后，buffer已绕回
        let out = dl.process(99.0);
        assert_eq!(out, 4.0); // 延迟4个采样
    }
}
