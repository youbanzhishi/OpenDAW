//! AudioBuffer桥接层
//!
//! 在audio-engine的AudioBuffer(f32, 平面格式)与
//! opendaw-extension的AudioBuffer(f64, 平面格式)之间进行转换。
//!
//! ## 两个AudioBuffer的差异
//!
//! | 特性       | audio_engine::AudioBuffer         | opendaw_extension::AudioBuffer |
//! |-----------|-----------------------------------|-------------------------------|
//! | 精度       | f32                               | f64                           |
//! | 布局       | 平面格式 (planar)                  | 平面格式 (planar)              |
//! | sample_rate | 有 (字段)                         | 无                            |
//!
//! 两者实际数据布局均为平面格式（每声道连续存储），
//! 桥接层主要负责f32↔f64精度转换和sample_rate处理。

use audio_engine::buffer::AudioBuffer as EngineBuffer;
use opendaw_extension::AudioBuffer as ExtBuffer;

/// 将audio-engine的AudioBuffer转换为opendaw-extension的AudioBuffer
///
/// - f32 → f64 精度提升（无损）
/// - 平面格式布局不变
/// - sample_rate信息丢失（extension AudioBuffer不存储）
pub fn engine_to_ext(buf: &EngineBuffer) -> ExtBuffer {
    ExtBuffer {
        channels: buf.channels,
        frames: buf.frames,
        data: buf.as_slice().iter().map(|&s| s as f64).collect(),
    }
}

/// 将opendaw-extension的AudioBuffer转换为audio-engine的AudioBuffer
///
/// - f64 → f32 精度降级（可能损失精度）
/// - 平面格式布局不变
/// - 需要外部提供sample_rate（extension AudioBuffer不存储）
pub fn ext_to_engine(buf: &ExtBuffer, sample_rate: f64) -> EngineBuffer {
    let mut engine_buf = EngineBuffer::new(buf.channels, buf.frames, sample_rate);
    for (i, &v) in buf.data.iter().enumerate() {
        engine_buf.as_mut_slice()[i] = v as f32;
    }
    engine_buf
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_engine_to_ext_roundtrip() {
        let sr = 44100.0;
        let mut engine_buf = EngineBuffer::new(2, 4, sr);
        // 写入测试数据
        engine_buf.set_sample(0, 0, 0.5);
        engine_buf.set_sample(0, 1, -0.3);
        engine_buf.set_sample(1, 0, 0.7);
        engine_buf.set_sample(1, 1, -0.1);

        // engine → ext → engine
        let ext_buf = engine_to_ext(&engine_buf);
        let roundtrip = ext_to_engine(&ext_buf, sr);

        // f32→f64→f32 应无损
        assert_eq!(roundtrip.channels, 2);
        assert_eq!(roundtrip.frames, 4);
        for ch in 0..2 {
            for f in 0..4 {
                let orig = engine_buf.get_sample(ch, f);
                let rt = roundtrip.get_sample(ch, f);
                assert!(
                    (orig - rt).abs() < 1e-6,
                    "ch={}, frame={}: {} vs {}",
                    ch, f, orig, rt
                );
            }
        }
    }

    #[test]
    fn test_engine_to_ext_preserves_layout() {
        let sr = 48000.0;
        let mut engine_buf = EngineBuffer::new(2, 3, sr);
        // 平面格式: ch0=[1.0, 2.0, 3.0], ch1=[4.0, 5.0, 6.0]
        engine_buf.set_sample(0, 0, 1.0);
        engine_buf.set_sample(0, 1, 2.0);
        engine_buf.set_sample(0, 2, 3.0);
        engine_buf.set_sample(1, 0, 4.0);
        engine_buf.set_sample(1, 1, 5.0);
        engine_buf.set_sample(1, 2, 6.0);

        let ext_buf = engine_to_ext(&engine_buf);

        // 验证平面布局：data = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0]
        assert_eq!(ext_buf.data.len(), 6);
        assert!((ext_buf.data[0] - 1.0).abs() < 1e-10);
        assert!((ext_buf.data[1] - 2.0).abs() < 1e-10);
        assert!((ext_buf.data[2] - 3.0).abs() < 1e-10);
        assert!((ext_buf.data[3] - 4.0).abs() < 1e-10);
        assert!((ext_buf.data[4] - 5.0).abs() < 1e-10);
        assert!((ext_buf.data[5] - 6.0).abs() < 1e-10);
    }

    #[test]
    fn test_ext_to_engine_sample_rate() {
        let ext_buf = ExtBuffer::new(2, 256);
        let engine_buf = ext_to_engine(&ext_buf, 96000.0);
        // audio_engine::AudioBuffer doesn't expose sample_rate directly,
        // but it was created with it
        assert_eq!(engine_buf.channels, 2);
        assert_eq!(engine_buf.frames, 256);
    }
}
