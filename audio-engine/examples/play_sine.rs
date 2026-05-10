//! 播放 440Hz 正弦波示例
//!
//! 使用 AudioEngine 播放 2 秒 440Hz 正弦波。
//! 需要启用 `audio` feature：`cargo run --example play_sine --features audio`
//!
//! 无 audio feature 时也可运行（模拟模式），用于验证音频数据注入和渲染逻辑。

use audio_engine::{AudioBuffer, AudioEngine};

/// 生成正弦波音频缓冲区
fn generate_sine_wave(
    frequency: f64,
    sample_rate: f64,
    channels: usize,
    frames: usize,
    amplitude: f32,
) -> AudioBuffer {
    let mut buffer = AudioBuffer::new(channels, frames, sample_rate);
    for frame in 0..frames {
        let t = frame as f64 / sample_rate;
        let sample = (2.0 * std::f64::consts::PI * frequency * t).sin() as f32 * amplitude;
        for ch in 0..channels {
            buffer.set_sample(ch, frame, sample);
        }
    }
    buffer
}

fn main() -> Result<(), Box<dyn std::error::Error>> {
    println!("🎵 OpenDAW 音频引擎 - 正弦波播放示例");
    println!("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━");

    // 参数配置
    let sample_rate = 44100.0;
    let frequency = 440.0; // A4 标准音
    let duration = 2.0;
    let frames = (sample_rate * duration) as usize;
    let amplitude = 0.5; // 50% 音量避免削波

    println!("📊 配置:");
    println!("   频率: {:.0}Hz", frequency);
    println!("   采样率: {:.0}Hz", sample_rate);
    println!("   时长: {:.1}秒", duration);
    println!("   声道: 立体声 (2)");
    println!("   帧数: {}", frames);
    println!();

    // 创建引擎
    let mut engine = AudioEngine::new();
    println!("✅ 音频引擎已创建");

    // 生成正弦波
    let buffer = generate_sine_wave(frequency, sample_rate, 2, frames, amplitude);
    println!(
        "✅ 正弦波已生成: {:.0}Hz, {:.1}秒, {:.0}帧",
        frequency, duration, frames
    );

    // 注册音轨并注入音频
    engine.register_track("sine")?;
    engine.inject_buffer("sine", buffer)?;
    println!("✅ 音轨 'sine' 已注册并注入音频数据");

    // 尝试启动音频引擎
    #[cfg(feature = "audio")]
    {
        match engine.start(sample_rate, 256) {
            Ok(()) => {
                println!("✅ 音频引擎已启动（CPAL 实时模式）");
                println!("   实际采样率: {:.0}Hz", engine.sample_rate());
                println!("   缓冲区大小: {}帧", engine.buffer_size());
                println!();
                println!("🔊 正在播放 440Hz 正弦波...");
                println!("   (等待 {:.0}ms...)", duration * 1000.0);

                // 等待播放完成
                std::thread::sleep(std::time::Duration::from_millis(
                    (duration * 1000.0) as u64 + 500,
                ));

                engine.stop()?;
                println!("✅ 播放结束");
            }
            Err(e) => {
                eprintln!("⚠️ 无法启动音频设备: {}", e);
                eprintln!("   原因可能是:");
                eprintln!("   - Linux: 未安装 ALSA (sudo apt install libasound2-dev)");
                eprintln!("   - macOS: 无音频输出设备");
                eprintln!("   - Windows: 音频服务未运行");
                eprintln!();
                println!("🔄 切换到模拟模式进行验证...");

                // 模拟模式验证
                run_simulation_mode(&mut engine, sample_rate);
            }
        }
    }

    #[cfg(not(feature = "audio"))]
    {
        println!("🔄 编译时未启用 audio feature，使用模拟模式");
        run_simulation_mode(&mut engine, sample_rate);
    }

    println!();
    println!("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━");
    println!("✅ 示例完成");

    Ok(())
}

/// 模拟模式验证
fn run_simulation_mode(engine: &mut AudioEngine, sample_rate: f64) {
    println!();
    println!("📋 模拟模式验证:");

    // 启动引擎（模拟模式）
    engine.start(sample_rate, 256).unwrap();
    println!("   ✓ 引擎已启动");

    // 渲染几个 buffer 验证音频数据
    let channels = 2;
    let frames_per_buffer = 256;

    for i in 0..3 {
        let mut output = vec![0.0f32; frames_per_buffer * channels];
        let has_more = engine.render_frame(&mut output, frames_per_buffer);

        // 检查输出
        let max_sample = output.iter().fold(0.0f32, |max, &s| max.max(s.abs()));
        let non_zero_count = output.iter().filter(|&&s| s != 0.0).count();

        println!(
            "   Buffer {}: {} 样本非零, 最大振幅={:.4}",
            i + 1,
            non_zero_count,
            max_sample
        );

        if !has_more {
            println!("   (所有音轨已播放完毕)");
            break;
        }
    }

    // 验证频率（通过采样点计算）
    println!();
    println!("📈 频率验证:");
    let mut engine2 = AudioEngine::new();
    engine2.register_track("sine").unwrap();
    let short_frames = 882; // 20ms @ 44100Hz
    let buffer = generate_sine_wave(440.0, sample_rate, 1, short_frames, 1.0);
    engine2.inject_buffer("sine", buffer).unwrap();
    engine2.start(sample_rate, 256).unwrap();

    let mut output = vec![0.0f32; short_frames];
    engine2.render_frame(&mut output, short_frames);

    // 计算过零点数量估算频率
    let zero_crossings = output
        .windows(2)
        .filter(|w| (w[0] >= 0.0) != (w[1] >= 0.0))
        .count();
    let estimated_freq = zero_crossings as f64 * sample_rate / (short_frames as f64 * 2.0);
    println!("   预期频率: 440.0Hz");
    println!("   估算频率: {:.1}Hz", estimated_freq);
    println!(
        "   误差: {:.2}%",
        (estimated_freq - 440.0).abs() / 440.0 * 100.0
    );

    engine2.stop().unwrap();
    engine.stop().unwrap();
}
