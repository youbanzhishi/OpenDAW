//! AudioBuffer 桥接层
//!
//! 在 opendaw-extension (f64) 和 audio-engine (f32) 之间进行类型转换
//!
//! # 数据布局
//!
//! 两种 AudioBuffer 都使用平面格式存储：
//! `data[channel * frames + frame]`
//!
//! # 转换策略
//!
//! - `ext_to_engine`: f64 → f32，直接 cast
//! - `engine_to_ext`: f32 → f64，直接 cast
//! - 数据布局相同，无需重排

use opendaw_extension::AudioBuffer as ExtAudioBuffer;
use audio_engine::buffer::AudioBuffer as EngineAudioBuffer;

/// Extension AudioBuffer (f64) → Engine AudioBuffer (f32)
///
/// 通道数和帧数必须匹配，数据直接从 f64 转换为 f32。
///
/// # Panics
///
/// 如果 channels * frames 不匹配缓冲区大小
#[inline]
pub fn ext_to_engine(ext: &ExtAudioBuffer, engine: &mut EngineAudioBuffer) {
    let total = ext.channels * ext.frames;
    assert_eq!(
        total, ext.data.len(),
        "Extension buffer 数据大小不匹配: {}x{} vs {}",
        ext.channels, ext.frames, ext.data.len()
    );

    // 确保目标缓冲区大小匹配
    if engine.channels != ext.channels || engine.frames != ext.frames {
        *engine = EngineAudioBuffer::new(ext.channels, ext.frames, 44100.0);
    }

    // f64 → f32 转换
    for (i, &sample) in ext.data.iter().enumerate() {
        engine.as_mut_slice()[i] = sample as f32;
    }
}

/// Engine AudioBuffer (f32) → Extension AudioBuffer (f64)
///
/// 通道数和帧数必须匹配，数据直接从 f32 转换为 f64。
///
/// # Panics
///
/// 如果 engine.as_slice().len() 不等于 channels * frames
#[inline]
pub fn engine_to_ext(engine: &EngineAudioBuffer, ext: &mut ExtAudioBuffer) {
    let total = engine.channels * engine.frames;
    assert_eq!(
        total, engine.as_slice().len(),
        "Engine buffer 数据大小不匹配: {}x{} vs {}",
        engine.channels, engine.frames, engine.as_slice().len()
    );

    // 确保目标缓冲区大小匹配
    if ext.channels != engine.channels || ext.frames != engine.frames {
        ext.channels = engine.channels;
        ext.frames = engine.frames;
        ext.data.resize(total, 0.0);
    }

    // f32 → f64 转换
    for (i, &sample) in engine.as_slice().iter().enumerate() {
        ext.data[i] = sample as f64;
    }
}

/// 创建匹配的 Extension AudioBuffer
///
/// 根据 engine 缓冲区创建兼容的 extension 缓冲区
#[inline]
pub fn engine_to_ext_new(engine: &EngineAudioBuffer) -> ExtAudioBuffer {
    let total = engine.channels * engine.frames;
    ExtAudioBuffer {
        channels: engine.channels,
        frames: engine.frames,
        data: engine.as_slice().iter().map(|&s| s as f64).collect(),
    }
}

/// 创建匹配的 Engine AudioBuffer
///
/// 根据 ext 缓冲区创建兼容的 engine 缓冲区
#[inline]
pub fn ext_to_engine_new(ext: &ExtAudioBuffer) -> EngineAudioBuffer {
    EngineAudioBuffer::new(ext.channels, ext.frames, 44100.0)
}

/// 从 Extension AudioBuffer 创建 Engine AudioBuffer（包含数据转换）
///
/// 便捷函数，同时完成创建和转换
#[inline]
pub fn ext_to_engine_full(ext: &ExtAudioBuffer) -> EngineAudioBuffer {
    let mut engine = EngineAudioBuffer::new(ext.channels, ext.frames, 44100.0);
    ext_to_engine(ext, &mut engine);
    engine
}

/// 从 Engine AudioBuffer 创建 Extension AudioBuffer（包含数据转换）
///
/// 便捷函数，同时完成创建和转换
#[inline]
pub fn engine_to_ext_full(engine: &EngineAudioBuffer) -> ExtAudioBuffer {
    let mut ext = ExtAudioBuffer::new(engine.channels, engine.frames);
    engine_to_ext(engine, &mut ext);
    ext
}

// ========================================================================
// 单元测试
// ========================================================================

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_ext_to_engine_basic() {
        // 创建 f64 缓冲区
        let ext = ExtAudioBuffer::new(2, 4);
        for i in 0..8 {
            // [L0, L1, L2, L3, R0, R1, R2, R3]
            ext.data[i] = (i as f64) * 0.5;
        }

        let mut engine = EngineAudioBuffer::new(2, 4, 44100.0);

        ext_to_engine(&ext, &mut engine);

        // 验证数据
        let engine_data = engine.as_slice();
        for i in 0..8 {
            assert!((engine_data[i] - (i as f32) * 0.5).abs() < 1e-6,
                "Index {}: expected {}, got {}",
                i, (i as f32) * 0.5, engine_data[i]);
        }
    }

    #[test]
    fn test_engine_to_ext_basic() {
        // 创建 f32 缓冲区
        let mut engine = EngineAudioBuffer::new(2, 4, 44100.0);
        for i in 0..8 {
            engine.as_mut_slice()[i] = (i as f32) * 0.25;
        }

        let mut ext = ExtAudioBuffer::new(2, 4);

        engine_to_ext(&engine, &mut ext);

        // 验证数据
        for i in 0..8 {
            assert!((ext.data[i] - (i as f64) * 0.25).abs() < 1e-9,
                "Index {}: expected {}, got {}",
                i, (i as f64) * 0.25, ext.data[i]);
        }
    }

    #[test]
    fn test_roundtrip() {
        // 创建原始数据
        let original = ExtAudioBuffer::new(2, 256);
        for i in 0..512 {
            original.data[i] = (i as f64) * 0.1;
        }

        // ext → engine
        let mut engine = EngineAudioBuffer::new(2, 256, 44100.0);
        ext_to_engine(&original, &mut engine);

        // engine → ext
        let mut roundtrip = ExtAudioBuffer::new(2, 256);
        engine_to_ext(&engine, &mut roundtrip);

        // 验证往返精度
        for i in 0..512 {
            let diff = (original.data[i] - roundtrip.data[i]).abs();
            assert!(diff < 1e-5, "Index {}: diff too large: {}", i, diff);
        }
    }

    #[test]
    fn test_new_functions() {
        let mut engine = EngineAudioBuffer::new(2, 100, 48000.0);
        for i in 0..200 {
            engine.as_mut_slice()[i] = i as f32;
        }

        // 使用便捷函数
        let ext = engine_to_ext_full(&engine);
        assert_eq!(ext.channels, 2);
        assert_eq!(ext.frames, 100);
        assert_eq!(ext.data.len(), 200);

        let back = ext_to_engine_full(&ext);
        assert_eq!(back.channels, 2);
        assert_eq!(back.frames, 100);
    }

    #[test]
    fn test_single_channel() {
        let ext = ExtAudioBuffer::new(1, 100);
        for i in 0..100 {
            ext.data[i] = (i as f64) * 0.01;
        }

        let mut engine = EngineAudioBuffer::new(1, 100, 44100.0);
        ext_to_engine(&ext, &mut engine);

        assert_eq!(engine.channels, 1);
        assert_eq!(engine.frames, 100);

        let mut ext2 = ExtAudioBuffer::new(1, 100);
        engine_to_ext(&engine, &mut ext2);

        for i in 0..100 {
            assert!((ext.data[i] - ext2.data[i]).abs() < 1e-6);
        }
    }

    #[test]
    fn test_mono_stereo_conversion() {
        // 单声道 → 双声道
        let ext = ExtAudioBuffer::new(1, 100);
        for i in 0..100 {
            ext.data[i] = i as f64;
        }

        let mut engine = EngineAudioBuffer::new(2, 100, 44100.0);
        ext_to_engine(&ext, &mut engine);

        // engine 应正确扩展
        assert_eq!(engine.channels, 2);
        assert_eq!(engine.frames, 100);
        assert_eq!(engine.as_slice().len(), 200);
    }
}
