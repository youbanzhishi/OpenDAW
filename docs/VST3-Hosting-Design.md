# VST3 Hosting Design — OpenDAW Phase 9

## 1. Overview

VCMix 的终极目标是成为完整的 DAW。当前 20 个 VC 插件全部是内部 DSP 处理（CLI subprocess），
但要成为真正的 DAW，必须能加载第三方 VST3 插件（Serum、FabFilter、Waves 等）。

本文档设计 VST3 Hosting 的两层架构，先跑通最小可用路径，再逐步优化性能。

## 2. Architecture — Two-Layer Design

```
┌─────────────────────────────────────────────────────────┐
│                  VCMix Python Layer                      │
│                                                          │
│  YAML Config ──▶ vst3_track.py ──▶ vst3_proxy.py        │
│                       │                  │                │
│                       │                  ▼                │
│                       │          subprocess.call(         │
│                       │            vst3_host CLI)         │
└───────────────────────┼──────────────────────────────────┘
                        │ IPC (WAV file / stdin JSON)
┌───────────────────────▼──────────────────────────────────┐
│              C++ VST3 Host Process                        │
│                                                           │
│  ┌──────────────┐  ┌────────────────┐  ┌──────────────┐  │
│  │ VST3Host     │  │ PluginWrapper  │  │ AudioFileIO  │  │
│  │ (JUCE VST3   │─▶│ (param set +   │─▶│ (dr_wav      │  │
│  │  FormatMgr)  │  │  MIDI + render)│  │  read/write) │  │
│  └──────────────┘  └────────────────┘  └──────────────┘  │
│                                                           │
│  JUCE Framework ── VST3PluginFormat ── VST3 SDK          │
└───────────────────────────────────────────────────────────┘
```

**Layer 1: Python 管理器** — 在 VCMix YAML 中声明 VST3 插件轨道，
通过 `VST3Track` → `VST3Proxy` 调用 C++ host CLI。

**Layer 2: C++ Hosting 引擎** — 基于 JUCE `VST3PluginFormat` 的独立进程，
负责加载 VST3 插件、设置参数、注入 MIDI、渲染音频。

## 3. VST3 Plugin Format Specification (Key Points)

### 3.1 Bundle Structure
```
MyPlugin.vst3/
├── Contents/
│   ├── Info.plist          (macOS)
│   ├── Resources/          (presets, UI bitmaps)
│   └── {OS}/               (binary)
│       ├── MyPlugin.so     (Linux)
│       ├── MyPlugin.dll    (Windows)
│       └── MyPlugin.vst3   (macOS universal)
```

### 3.2 Component Model
- **IComponent**: 参数管理、状态保存/恢复
- **IEditController**: UI 控制（host 不需要实现编辑器）
- **IAudioProcessor**: 音频处理核心 — `process()` 方法
- **IConnectionPoint**: 组件间通信
- **IMidiMapping**: MIDI CC → paramID 映射

### 3.3 Parameter System
- 每个参数有唯一 `paramID`（uint32）
- 归一化值范围 [0.0, 1.0]
- 参数类型: Range, Switch, Category
- 参数标题用于 UI 显示

### 3.4 Audio Processing
- 固定块大小处理（可配置，推荐 512 或 1024 samples）
- 输入/输出 bus 配置（1-in/1-out, 2-in/2-out 等）
- 32-bit float 交错/平面格式

### 3.5 Preset Format (.vstpreset)
```
Header:  "VST3Preset" magic + version + classID
Chunks:  [ComponentState] [ControllerState] [MetaInfo]
```

## 4. JUCE VST3PluginFormat Usage

### 4.1 Setup
```cpp
#include <juce_audio_processors/juce_audio_processors.h>

// 1. 创建 format manager
juce::AudioPluginFormatManager formatManager;
formatManager.addDefaultFormats();  // 自动添加 VST3, AU, etc.

// 2. 获取 VST3 format
auto* vst3Format = formatManager.getFormat(juce::AudioPluginFormatManager::VST3);

// 3. 扫描已知插件
juce::KnownPluginList pluginList;
auto fileSearchPath = juce::FileSearchPath("/usr/lib/vst3;/usr/local/lib/vst3");
auto results = vst3Format->searchPathsForPlugins(fileSearchPath, true);
```

### 4.2 Loading Plugin
```cpp
juce::PluginDescription desc;
desc.fileOrIdentifier = "/usr/lib/vst3/Serum.vst3";
desc.uniqueId = 0;  // VST3 uses file path as identifier
desc.pluginFormatName = "VST3";

std::unique_ptr<juce::AudioPluginInstance> plugin;
plugin = formatManager.createPluginInstance(desc, sampleRate, bufferSize, error);
```

### 4.3 Parameter Access
```cpp
// 遍历所有参数
for (auto* param : plugin->getParameters()) {
    juce::String name = param->getName(64);
    float value = param->getValue();         // 归一化 [0,1]
    param->setValue(0.5f);                    // 设置归一化值
}

// 按 index 设置
auto* param = plugin->getParameters()[index];
param->setValue(normalizedValue);
```

### 4.4 Audio Processing
```cpp
// 准备处理
plugin->prepareToPlay(sampleRate, bufferSize);

// 处理音频块
juce::AudioBuffer<float> buffer(numChannels, numSamples);
juce::MidiBuffer midiBuffer;

// 添加 MIDI 事件
midiBuffer.addEvent(juce::MidiMessage::noteOn(1, 60, 0.8f), samplePosition);

// 处理
plugin->processBlock(buffer, midiBuffer);
```

### 4.5 Preset Loading
```cpp
// VST3 preset 文件 (.vstpreset)
juce::File presetFile("/path/to/preset.vstpreset");
auto state = presetFile.loadFileAsData();
plugin->setStateInformation(state.getData(), state.getSize());
```

## 5. IPC Communication Schemes

### 5.1 方案 A: WAV File Exchange (推荐 — 先跑通)

```
Python                         C++ vst3_host
  │                                │
  ├─ write input.wav ─────────────▶│
  ├─ subprocess.call(              │
  │    vst3_host process           │
  │    --plugin X.vst3             │
  │    --input input.wav           │
  │    --output output.wav         │
  │    --param 1=0.5               │
  │  )                             │
  │◀────── write output.wav ───────┤
  ├─ read output.wav               │
```

**优点**:
- 实现最简单，零依赖（dr_wav 头文件即可）
- 天然支持任意采样率/位深
- Debug 友好（可手动检查中间 WAV 文件）
- 进程隔离，VST3 崩溃不影响主进程

**缺点**:
- 磁盘 I/O 开销（对于短音频可忽略）
- 不适合实时场景（但 VCMix 是离线渲染，不是问题）
- MIDI 事件需通过 JSON 命令行传递

**延迟估算**: 10s 音频 @ 44.1kHz/32bit ≈ 1.7MB WAV
- 写入: ~5ms (SSD)
- 处理: ~50-200ms (取决于插件)
- 读取: ~5ms
- **总延迟: ~60-210ms** — 对离线渲染完全可接受

### 5.2 方案 B: Shared Memory (Phase 9.1 优化)

```
Python                         C++ vst3_host
  │                                │
  ├─ mmap shared region ─────────▶│
  │   [audio_in | audio_out]       │
  ├─ JSON cmd via Unix socket ────▶│
  │◀────── result via socket ──────┤
```

**优点**: 零拷贝，低延迟
**缺点**: 实现复杂，需处理同步、大小协商

### 5.3 方案 C: gRPC/Unix Socket Streaming (Phase 9.2 优化)

```
Python ──gRPC──▶ C++ vst3_host (长期运行守护进程)
  │                  │
  │  StreamAudio()   │  保持插件加载
  │  SetParam()      │  避免重复初始化
  │  LoadPreset()    │
```

**优点**: 最优性能，插件常驻内存
**缺点**: 需 protobuf/gRPC 依赖，守护进程管理复杂

### 5.4 推荐路线

| Phase | 方案 | 目标 |
|-------|------|------|
| 9.0 | **方案 A** (WAV file) | 跑通端到端，验证架构 |
| 9.1 | 方案 B (shared memory) | 降低延迟 |
| 9.2 | 方案 C (gRPC daemon) | 实时场景支持 |

## 6. VST3 Parameter Mapping

### 6.1 YAML → VST3 映射

```yaml
tracks:
  - name: synth
    type: vst3
    plugin_path: "/usr/lib/vst3/Serum.vst3"
    params:
      - index: 1      # VST3 param index (0-based)
        value: 0.5    # 归一化值 [0.0, 1.0]
      - index: 2
        value: 0.8
```

映射规则:
- `index` → `plugin->getParameters()[index]`
- `value` → 归一化 [0.0, 1.0]（VST3 标准范围）
- `name` 映射（备选）: 通过参数名查找 paramID

### 6.2 命名参数映射 (未来)

```yaml
params:
  - name: "Filter Cutoff"
    value: 0.7
```

实现: 遍历 `getParameters()` 匹配 `getName()`，建立 name→index 索引。

### 6.3 dB 值自动转换

对于已知的 dB 参数（如增益、阈值），提供 dB→归一化辅助:

```python
def db_to_normalized(db_value: float, param_info: VST3ParamInfo) -> float:
    """Convert dB to normalized [0,1] using param's range."""
    t = (db_value - param_info.min_db) / (param_info.max_db - param_info.min_db)
    return max(0.0, min(1.0, t))
```

## 7. Preset Loading

### 7.1 .vstpreset 文件解析

VST3 preset 文件结构:
```
Offset  Size   Content
0       8      Magic: "VST3Preset"
8       4      Version (1)
12      16     Class ID (GUID)
28      8      Component State offset + size
36      8      Controller State offset + size
44      8      Meta Info offset + size
...     ...    Chunk data
```

### 7.2 加载流程

```cpp
// 方式1: 通过 JUCE setStateInformation (推荐)
juce::File presetFile("/path/to/preset.vstpreset");
auto data = presetFile.loadFileAsData();
plugin->setStateInformation(data.getData(), data.getSize());

// 方式2: 解析 preset chunk，只取 ComponentState
// (某些插件需要 ControllerState 才能正确恢复)
```

### 7.3 YAML 中的预设指定

```yaml
tracks:
  - name: synth
    type: vst3
    plugin_path: "/usr/lib/vst3/Serum.vst3"
    preset: "Init"           # 内置预设名
    # 或
    preset_file: "/presets/Serum/Pad.vstpreset"  # 外部文件
```

## 8. MIDI Integration

### 8.1 MIDI 事件传递

VST3 instrument 插件需要 MIDI 输入才能发声。

方案 A 中通过 JSON 文件传递 MIDI:
```bash
vst3_host process \
  --plugin "Serum.vst3" \
  --output output.wav \
  --midi-file melody.json
```

### 8.2 MIDI JSON 格式

```json
{
  "ppq": 480,
  "bpm": 120,
  "events": [
    {"type": "note_on",  "channel": 0, "note": 60, "velocity": 100, "tick": 0},
    {"type": "note_off", "channel": 0, "note": 60, "velocity": 0,   "tick": 480},
    {"type": "cc",       "channel": 0, "cc": 74,   "value": 64,     "tick": 0}
  ]
}
```

### 8.3 MIDI File 支持

直接解析 .mid 文件:
```bash
vst3_host process \
  --plugin "Serum.vst3" \
  --output output.wav \
  --midi-file melody.mid \
  --bpm 120
```

C++ 端使用 JUCE 的 `juce::MidiFile` 解析。

## 9. Error Handling

### 9.1 插件加载失败
- VST3 路径不存在 → 明确报错 + 列出可用插件
- 插件格式损坏 → 捕获 JUCE 异常，返回 JSON 错误
- 插件初始化超时 → 10s 超时保护

### 9.2 渲染失败
- 崩溃恢复: C++ 进程 crash → Python 检测 exit code ≠ 0
- 超时: 可配置渲染超时 (默认 300s)
- 音频校验: 检查输出 WAV 是否为全零（静音检测）

### 9.3 参数验证
- index 越界 → 报告可用参数范围
- value 超出 [0,1] → clamp + 警告
- 预设不存在 → 列出可用预设

## 10. Thread Safety & Lifecycle

### 10.1 进程模型
- 每个 VST3 track = 一次 CLI 调用 = 独立 C++ 进程
- 进程间完全隔离，无共享状态
- VST3 插件在进程中只初始化一次

### 10.2 初始化顺序
```
1. 创建 AudioPluginFormatManager
2. 注册 VST3PluginFormat
3. 加载插件 → createPluginInstance()
4. 设置参数 → param->setValue()
5. 加载预设 → setStateInformation() (可选)
6. prepareToPlay(sampleRate, blockSize)
7. 处理音频 → processBlock()
8. 释放资源
```

### 10.3 资源管理
- RAII: JUCE `std::unique_ptr<AudioPluginInstance>` 自动释放
- 临时 WAV 文件由 Python 端在 `finally` 块中清理
- C++ 进程退出时 OS 自动回收所有资源

## 11. Build System

### 11.1 CMake 配置

```cmake
cmake_minimum_required(VERSION 3.22)
project(vst3_host VERSION 0.1.0)

include(FetchContent)
FetchContent_Declare(JUCE
    GIT_REPOSITORY https://github.com/juce-framework/JUCE.git
    GIT_TAG        7.0.9
)
FetchContent_MakeAvailable(JUCE)

add_executable(vst3_host
    src/main.cpp
    src/VST3Host.cpp
    src/PluginWrapper.cpp
    src/AudioFileIO.cpp
)

target_link_libraries(vst3_host PRIVATE
    juce::juce_audio_processors
    juce::juce_audio_utils
    juce::juce_core
)

target_compile_definitions(vst3_host PRIVATE
    JUCE_VST3_CAN_REPLACE_VST2=0
    JUCE_STANDALONE_APPLICATION=1
)
```

### 11.2 依赖
| 依赖 | 版本 | 来源 |
|------|------|------|
| JUCE | 7.0.9+ | FetchContent (GitHub) |
| VST3 SDK | 3.7.9+ | Bundled with JUCE |
| dr_wav | latest | Single header (GitHub) |
| CMake | 3.22+ | System |

## 12. Future Optimizations (Post Phase 9.0)

1. **持久化 C++ 守护进程** — 避免重复加载 VST3 插件
2. **参数缓存** — 首次加载后导出参数列表，后续渲染直接使用缓存
3. **离线渲染优化** — 比实时更快的 offline processing
4. **并行渲染** — 多个 VST3 track 同时在不同进程中渲染
5. **VST3 plugin sandbox** — 沙箱隔离不稳定插件
6. **AU (AudioUnit) 支持** — macOS 用户的核心需求
7. **LV2 支持** — Linux 开源生态
