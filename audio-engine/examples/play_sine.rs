//! 播放 440Hz 正弦波示例
//!
//! 使用 AudioEngine 播放 2 秒 440Hz 正弦波。
//! 需要启用 `audio` feature：`cargo run --example play_sine --features audio`

use audio_engine::{AudioBuffer, AudioEngine};

fn main() -> Result<(), Box<dyn std::error::Error>> {
    println!("🎵 OpenDAW 音频引擎 - 正弦波播放示例");
    println!("   频率: 440Hz | 时长: 2秒 | 声道: 立体声");

    let mut engine = AudioEngine::new();

    // 采样率与时长
    let sample_rate = 44100.0;
    let duration = 2.0;
    let frames = (sample_rate * duration) as usize;

    // 生成 440Hz 正弦波
    let mut buffer = AudioBuffer::new(2, frames, sample_rate);
    let frequency = 440.0;
    for frame in 0..frames {
        let t = frame as f64 / sample_rate;
        let sample = (2.0 * std::f64::consts::PI * frequency * t).sin() as f32 * 0.5; // 音量50%
        buffer.set_sample(0, frame, sample); // 左声道
        buffer.set_sample(1, frame, sample); // 右声道
    }

    // 注册音轨并注入音频数据
    engine.register_track("sine")?;
    engine.inject_buffer("sine", buffer)?;

    println!("   注册音轨: sine ({}帧, {:.1}秒)", frames, duration);

    // 启动引擎（启用 audio feature 时将初始化 CPAL 音频流）
    match engine.start(sample_rate, 256) {
        Ok(()) => {
            println!("✅ 音频引擎已启动，正在播放...");
            println!("   采样率: {}Hz | 缓冲区: 256帧", engine.sample_rate());

            // 等待播放完成（留0.5秒余量）
            std::thread::sleep(std::time::Duration::from_millis(2500));

            engine.stop()?;
            println!("✅ 播放结束");
        }
        Err(e) => {
            eprintln!("⚠️ 无法启动音频设备: {}", e);
            eprintln!("   请确保系统有可用的音频输出设备");
            eprintln!("   Linux 用户请确认 ALSA 已安装（sudo apt install libasound2-dev）");
        }
    }

    Ok(())
}
