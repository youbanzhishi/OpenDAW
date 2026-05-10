# OpenDAW 插件开发指南

## 概述

OpenDAW支持多种插件格式，最推荐使用 **VC-Plugin** 原生格式进行开发。VC-Plugin是OpenDAW的Rust原生插件API，提供最佳的性能和集成体验。

## VC-Plugin 清单格式

每个VC-Plugin必须包含一个`plugin.yaml`清单文件：

```yaml
# plugin.yaml — 插件清单
api_version: "1.0"
id: "com.example.my-plugin"
name: "My Awesome Plugin"
version: "1.0.0"
author: "Your Name"
description: "A brief description of the plugin"
license: "MIT"
category: "Effect"  # Effect | Instrument | Utility
tags:
  - "reverb"
  - "spatial"

# 插件入口
entry_point: "libmy_plugin.so"  # Linux
# entry_point: "my_plugin.dll"  # Windows
# entry_point: "my_plugin.dylib"  # macOS

# 参数定义
parameters:
  - id: "mix"
    name: "Dry/Wet Mix"
    min: 0.0
    max: 1.0
    default: 0.5
    unit: "ratio"

  - id: "decay"
    name: "Decay Time"
    min: 0.1
    max: 10.0
    default: 2.0
    unit: "seconds"

# 平台兼容性
platforms:
  - os: "linux"
    arch: "x86_64"
  - os: "windows"
    arch: "x86_64"
  - os: "macos"
    arch: "x86_64"
  - os: "macos"
    arch: "aarch64"

# 依赖
dependencies:
  - id: "opendaw-core"
    version: ">=1.0.0"

# 预置
presets:
  - name: "Default"
    values:
      mix: 0.5
      decay: 2.0

  - name: "Large Hall"
    values:
      mix: 0.7
      decay: 5.0
```

## 开发流程

### 1. 创建项目

```bash
# 创建插件项目目录
mkdir my-plugin && cd my-plugin

# 创建清单文件
cat > plugin.yaml << 'EOF'
api_version: "1.0"
id: "com.example.my-plugin"
name: "My Plugin"
version: "0.1.0"
author: "Developer"
description: "My first OpenDAW plugin"
category: "Effect"
tags: ["demo"]
parameters: []
platforms:
  - os: "linux"
    arch: "x86_64"
EOF
```

### 2. 实现插件逻辑

使用Rust实现VC-Plugin接口：

```rust
use opendaw_extension::{VcPlugin, AudioBuffer, ParamInfo, PluginType};

struct MyPlugin {
    sample_rate: f64,
    mix: f32,
}

impl VcPlugin for MyPlugin {
    fn name(&self) -> &str { "My Plugin" }
    
    fn plugin_type(&self) -> PluginType {
        PluginType::Effect
    }
    
    fn parameters(&self) -> Vec<ParamInfo> {
        vec![
            ParamInfo {
                id: "mix".into(),
                name: "Dry/Wet".into(),
                min_value: 0.0,
                max_value: 1.0,
                default_value: 0.5,
            }
        ]
    }
    
    fn set_parameter(&mut self, id: &str, value: f32) {
        match id {
            "mix" => self.mix = value,
            _ => {}
        }
    }
    
    fn get_parameter(&self, id: &str) -> f32 {
        match id {
            "mix" => self.mix,
            _ => 0.0,
        }
    }
    
    fn process(&mut self, input: &AudioBuffer, output: &mut AudioBuffer) {
        for ch in 0..output.channels {
            for frame in 0..output.frames {
                let dry = input.sample(ch, frame);
                // Apply your DSP here
                let wet = dry * 0.5; // Simple example
                output.set_sample(ch, frame, dry * (1.0 - self.mix) + wet * self.mix);
            }
        }
    }
    
    fn set_sample_rate(&mut self, rate: f64) {
        self.sample_rate = rate;
    }
}
```

### 3. 构建和测试

```bash
# 构建插件
cargo build --release

# 本地测试
opendaw plugin test ./path/to/plugin/

# 在项目中使用
opendaw plugin add "Vocals" --path ./path/to/plugin/
```

## 测试

### 单元测试

为每个插件编写单元测试：

```rust
#[cfg(test)]
mod tests {
    use super::*;
    
    #[test]
    fn test_plugin_creation() {
        let plugin = MyPlugin::new(44100.0);
        assert_eq!(plugin.name(), "My Plugin");
    }
    
    #[test]
    fn test_parameter_range() {
        let mut plugin = MyPlugin::new(44100.0);
        plugin.set_parameter("mix", 1.5);
        // Parameter should be clamped
        assert!(plugin.get_parameter("mix") <= 1.0);
    }
    
    #[test]
    fn test_process_silence() {
        let mut plugin = MyPlugin::new(44100.0);
        let input = AudioBuffer::new(2, 256, 44100.0);
        let mut output = AudioBuffer::new(2, 256, 44100.0);
        plugin.process(&input, &mut output);
        // Silence in should produce silence (or near-silence)
        let max = output.as_slice().iter().map(|s| s.abs()).fold(0.0f32, |a, b| a.max(b));
        assert!(max < 0.001);
    }
}
```

### 集成测试

```bash
# 在OpenDAW项目中测试插件
opendaw new "Plugin Test" --template Empty
opendaw track add "Test Track" --type audio
opendaw plugin add "Test Track" --path ./my-plugin/
opendaw export --format wav --output test_output.wav
```

## 发布到市场

### 1. 准备发布包

```bash
# 打包插件
mkdir -p release/
cp plugin.yaml release/
cp target/release/libmy_plugin.so release/
tar czf my-plugin-1.0.0.tar.gz -C release/ .
```

### 2. 提交到市场

```bash
# 使用CLI发布
opendaw marketplace publish ./my-plugin-1.0.0.tar.gz

# 或通过API
curl -X POST http://localhost:3000/api/v1/marketplace/submit \
  -F "package=@my-plugin-1.0.0.tar.gz"
```

### 3. 版本管理

- 遵循语义化版本（SemVer）：`MAJOR.MINOR.PATCH`
- 破坏性变更 → 升级MAJOR
- 新功能 → 升级MINOR
- Bug修复 → 升级PATCH

## JSFX插件开发

OpenDAW也支持JSFX脚本插件，兼容Reaper的EEL2语言：

```eel
desc:Simple Gain
slider1:0<-60,24,0.1>Gain (dB)

@slider
gain = 10^(slider1/20);

@sample
spl0 = spl0 * gain;
spl1 = spl1 * gain;
```

将`.jsfx`文件放入插件目录即可使用。

## 最佳实践

1. **参数范围** — 始终为参数设定合理的min/max范围
2. **防削波** — 输出信号应始终clamp到[-1.0, 1.0]
3. **平滑处理** — 参数变化时应使用平滑插值，避免爆音
4. **零延迟** — 尽量避免引入额外延迟
5. **内存管理** — 避免在process()中分配内存
6. **线程安全** — process()可能在不同线程调用
7. **采样率无关** — 插件应能在任意采样率下工作

## 常见问题

**Q: 如何调试插件？**
A: 使用`RUST_LOG=debug`环境变量启用日志输出。

**Q: 插件加载失败怎么办？**
A: 检查清单文件格式、平台兼容性和依赖版本。

**Q: 如何支持多平台？**
A: 为每个目标平台分别编译，在清单中列出所有平台。
