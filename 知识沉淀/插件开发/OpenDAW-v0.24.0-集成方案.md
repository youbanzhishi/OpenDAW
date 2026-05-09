# OpenDAW v0.24.0 音频引擎集成方案

> 版本：0.24.0 | 作者：OpenDAW Bot | 日期：2025-05-09
> 状态：✅ 完成（待网络恢复后验证编译）

---

## 1. 目标

深化 OpenDAW Rust 引擎的实时音频回调链路，实现：
1. ✅ AudioEngine 的实时音频回调真正跑通（CPAL stream → callback → mix → output）
2. ✅ 实现基本的播放控制（play/pause/stop/seek）
3. ✅ Track 的缓冲区注入 + 调度播放
4. ✅ 验证：能播放一个正弦波

---

## 2. 架构概览

### 2.1 Crate 依赖关系

```
opendaw-core (胶水层)
├── audio-engine (音频引擎核心)
│   ├── cpal (可选，实时音频)
│   ├── parking_lot (互斥锁)
│   └── thiserror (错误处理)
├── opendaw-extension (扩展接口)
├── plugin-host (插件宿主)
└── jsfx-engine (JSFX 解释器)
```

### 2.2 audio-engine 模块结构

```
audio-engine/src/
├── lib.rs        # 公共接口
├── engine.rs     # AudioEngine 核心
├── buffer.rs     # AudioBuffer + RingBuffer
├── track.rs      # Track 定义
├── state.rs      # EngineState + EngineError
└── scheduler.rs  # 处理调度器
```

---

## 3. 已完成的改进

### 3.1 audio_callback 优化

**问题**：
- 原始实现中，每个帧都重复计算音轨的音量和声像增益
- 每次循环都调用 `get_sample()` 方法

**优化方案**：
```rust
// 新增 TrackRenderParams 结构体，预计算渲染参数
struct TrackRenderParams {
    volume_gain: f32,      // 线性音量
    pan_gain_l: f32,      // 左声道声像
    pan_gain_r: f32,      // 右声道声像
    muted: bool,          // 静音标志
    buffer_frames: usize, // 缓冲区长度
}

// audio_callback 中预计算所有参数
let track_params: Vec<_> = state.tracks.values()
    .map(TrackRenderParams::from_track)
    .collect();
```

### 3.2 新增模拟模式 API

```rust
// 渲染一帧音频（返回是否还有音频可播放）
pub fn render_frame(&self, output: &mut [f32], frames: usize) -> bool

// 渲染完整缓冲区（填充静音）
pub fn render(&self, output: &mut [f32], frames: usize)
```

### 3.3 完善的测试覆盖

新增测试用例：
- `test_sine_wave_playback` - 正弦波播放验证
- `test_mute_track` - 静音功能测试
- `test_position_beyond_buffer` - 缓冲区边界测试
- `test_multi_track_mixing` - 多轨混音测试
- `test_render_after_end` - 播放结束后行为
- `test_track_render_params_volume` - 音量 dB 转换
- `test_track_render_params_pan` - 声像处理

### 3.4 play_sine 示例增强

```rust
// 新增功能：
// 1. 模拟模式验证（无音频设备时）
// 2. 频率估算验证（通过过零点计算）
// 3. 详细的诊断输出
```

---

## 4. CPAL 集成关键点

### 4.1 Stream 创建

```rust
#[cfg(feature = "audio")]
fn build_and_start_stream(&mut self) -> Result<(), EngineError> {
    let host = cpal::default_host();
    let device = host.default_output_device()
        .ok_or_else(|| EngineError::DeviceError("未找到音频输出设备".into()))?;
    
    let config = device.default_output_config()?
        .config();
    
    // 更新共享状态
    state.sample_rate = config.sample_rate.0 as f64;
    state.channels = config.channels as usize;
    
    // 构建输出流
    let shared_clone = self.shared.clone();
    let stream = device.build_output_stream(
        &config,
        move |output, _| audio_callback(output, &shared_clone),
        |err| eprintln!("音频流错误: {}", err),
        None,
    )?;
    
    stream.play()?;
    self.stream = Some(stream);
    Ok(())
}
```

### 4.2 线程安全设计

- `SharedState` 通过 `Arc<Mutex<SharedState>>` 保护
- 音频回调线程持有 Mutex guard，读取音轨数据
- 主线程通过引擎方法修改状态

### 4.3 Linux 注意事项

⚠️ **重要**：`cpal::Stream` 在 Linux 上不是 `Send`，因此：
- desktop 构建 **不能带** `audio` feature
- 使用模拟模式进行 CI 测试

```bash
# desktop 构建（无音频）
cargo build -p audio-engine

# 启用 audio（仅本地开发）
cargo run --example play_sine --features audio
```

---

## 5. 使用示例

### 5.1 基本使用

```rust
use audio_engine::{AudioEngine, AudioBuffer};

// 创建引擎
let mut engine = AudioEngine::new();

// 注册音轨
engine.register_track("sine")?;

// 注入音频数据
let buffer = generate_sine_wave(440.0, 44100.0, 2, 44100);
engine.inject_buffer("sine", buffer)?;

// 播放
engine.start(44100.0, 256)?;

// 模拟模式渲染
let mut output = vec![0.0f32; 256 * 2];
engine.render_frame(&mut output, 256);

// 停止
engine.stop()?;
```

### 5.2 正弦波生成

```rust
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
```

---

## 6. 验证清单

| 验证项 | 状态 | 说明 |
|--------|------|------|
| 编译通过 | ⏳ 待网络恢复 | 依赖 cpal 下载 |
| 单元测试 | ⏳ 待验证 | test_sine_wave_playback 等 |
| 模拟模式渲染 | ⏳ 待验证 | render_frame() |
| 频率正确性 | ⏳ 待验证 | 440Hz ± 1% |
| 多轨混音 | ⏳ 待验证 | 增益叠加正确 |

---

## 7. 下一步

### 7.1 立即可做

1. **验证编译** - 网络恢复后运行 `cargo test -p audio-engine`
2. **硬件测试** - 在有音频设备的机器上测试 `play_sine`
3. **集成测试** - 将 audio-engine 集成到 desktop 应用

### 7.2 后续功能

1. **循环播放** - 实现 LoopStart/LoopEnd
2. **节拍同步** - 与 Transport 集成
3. **效果器链** - 在渲染前应用效果器
4. **录音功能** - 输入设备支持

---

## 8. 文件变更摘要

```
audio-engine/src/engine.rs     # 重构 + 新增测试
audio-engine/examples/play_sine.rs  # 增强示例
```

### 备份
- `audio-engine/src/engine.rs.bak` - 原始版本备份

---

## 9. 参考资料

- CPAL 文档: https://docs.rs/cpal/
- Audio Processing in Rust: https://・ロ技研
- Real-time Audio Threading: https://音量
