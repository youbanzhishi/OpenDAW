//! DSP 公共工具
//!
//! 提供通用数学函数和音频处理辅助。

/// 将角度从度转换为弧度
pub fn deg_to_rad(deg: f64) -> f64 {
    deg * std::f64::consts::PI / 180.0
}

/// 将角度从弧度转换为度
pub fn rad_to_deg(rad: f64) -> f64 {
    rad * 180.0 / std::f64::consts::PI
}

/// 快速近似 atan2（用于矢量示波器角度计算）
pub fn fast_atan2(y: f64, x: f64) -> f64 {
    if x.abs() < f64::EPSILON && y.abs() < f64::EPSILON {
        return 0.0;
    }
    y.atan2(x)
}

/// 线性插值
pub fn lerp(a: f64, b: f64, t: f64) -> f64 {
    a + (b - a) * t
}

/// 将频率转换为MIDI音符编号
pub fn freq_to_midi(freq: f64) -> f64 {
    12.0 * (freq / 440.0).log2() + 69.0
}

/// 将MIDI音符编号转换为频率
pub fn midi_to_freq(midi: f64) -> f64 {
    440.0 * 2.0f64.powf((midi - 69.0) / 12.0)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_deg_rad_roundtrip() {
        let angles = [0.0, 45.0, 90.0, 180.0, 270.0, 360.0];
        for &deg in &angles {
            let rad = deg_to_rad(deg);
            let back = rad_to_deg(rad);
            assert!(
                (back - deg).abs() < 1e-10,
                "角度往返失败: {} → {} → {}",
                deg,
                rad,
                back
            );
        }
    }

    #[test]
    fn test_lerp() {
        assert_eq!(lerp(0.0, 10.0, 0.5), 5.0);
        assert_eq!(lerp(-10.0, 10.0, 0.0), -10.0);
        assert_eq!(lerp(-10.0, 10.0, 1.0), 10.0);
    }

    #[test]
    fn test_freq_midi() {
        // A4 = 440Hz = MIDI 69
        assert!((freq_to_midi(440.0) - 69.0).abs() < 0.01);
        assert!((midi_to_freq(69.0) - 440.0).abs() < 0.01);
    }
}
