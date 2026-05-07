# VCMix Demo Project — "Neon Lights"

端到端Demo项目，验证VCMix全部核心功能协同工作：
- MIDI解析 + 内置合成器（sine/sawtooth/square）
- Sampler采样器轨道
- 自动化曲线（gain automation）
- 插件链处理（VC-Comp/EQ/Delay/Reverb/Limiter等）
- Chain Presets链预设
- AutoMix增益自修正
- 编曲感知混音
- Web UI可视化

## 项目结构

```
demo_project/
├── demo_project.yaml      # 项目YAML配置（5轨道+Master链）
├── midi/
│   ├── drums.mid          # 鼓组MIDI（104 notes, kick+snare+hihat）
│   ├── bass.mid           # 贝斯MIDI（48 notes, E2-A2 pattern）
│   ├── lead.mid           # 主旋律MIDI（44 notes, C5-C6旋律）
│   └── pad.mid            # 和弦垫音MIDI（24 notes, C-Am-F-G）
├── samples/
│   ├── kick.wav           # 底鼓采样（频率扫描合成, 0.3s）
│   └── vocal.wav          # 模拟人声（440Hz正弦+泛音+颤音, 16s）
├── neon_lights_output.wav # 渲染输出
└── README.md              # 本文件
```

## 轨道设计

### 1. drums — 鼓组（Sampler Track）
- **类型**: sampler + MIDI驱动
- **采样**: 频率扫描合成的底鼓（150Hz→50Hz指数衰减）
- **MIDI**: 8小节标准4/4节拍（C1=kick, D1=snare, F#1=hihat）
- **效果链**: vc-comp（阈值-15dB, 比率4:1）
- **设计意图**: 验证Sampler Track完整流程——采样加载→MIDI解析→音符调度→音频渲染→效果处理

### 2. bass — 贝斯（MIDI Track）
- **类型**: midi + sawtooth合成器
- **MIDI**: E2-E2-E2-G2-A2循环pattern，8小节
- **自动化**: gain曲线（0→-3dB渐入 → 16→0dB释放 → 32→0dB → 40→-6dB淡出）
- **效果链**: vc-eq（80Hz提升+250Hz切割）→ vc-comp（阈值-12dB）
- **设计意图**: 验证MIDI合成器+自动化曲线+EQ+压缩协同

### 3. lead — 主旋律（MIDI Track）
- **类型**: midi + square合成器
- **MIDI**: Am五声音阶旋律，2小节phrase × 4次重复
- **效果链**: vc-delay（500ms, feedback=15%）→ vc-reverb（room=40, wet=10%）
- **设计意图**: 验证方波合成器+延迟+混响的空间效果链

### 4. pad — 和弦垫音（MIDI Track）
- **类型**: midi + sine合成器
- **MIDI**: I-vi-IV-V和声进行（C-Am-F-G），4拍延音，重复2次
- **效果链**: vc-reverb（room=80, wet=15%）
- **设计意图**: 验证多音和弦叠加+大空间混响

### 5. vocal — 人声模拟（Audio Track）
- **类型**: audio（440Hz正弦波+泛音+颤音模拟人声）
- **自动化**: gain曲线（fade-in 0→4拍 → sustain 4→28拍 → step hold 28→32拍 → fade-out 32拍）
- **效果链**: vc-deesser → vc-comp → vc-eq → vc-reverb → vc-limiter
- **设计意图**: 验证完整人声处理链（等同于vocal-chain预设）+音频轨道+自动化

### Master 总线
- **电平**: drums=0.85, bass=0.7, lead=0.65, pad=0.5, vocal=0.8
- **效果链**: vc-eq（低频修正+高频提升）→ vc-comp（2:1温和压缩）→ vc-limiter（-1dB天花板）
- **设计意图**: 验证Master总线处理链

## 运行方式

### 前置条件
```bash
cd /tmp/OpenDAW
pip install -e .   # 安装vcmix
```

### 1. 验证项目配置
```bash
python -m vcmix validate demo_project/demo_project.yaml
# 输出: ✔ Config is valid

# JSON格式
python -m vcmix validate demo_project/demo_project.yaml --json
```

### 2. 渲染
```bash
# 基础渲染
python -m vcmix render demo_project/demo_project.yaml

# 带详细分析报告
python -m vcmix render demo_project/demo_project.yaml --report

# 带AutoFix增益自修正
python -m vcmix render demo_project/demo_project.yaml --auto-fix

# 带编曲感知混音
python -m vcmix render demo_project/demo_project.yaml --arrangement-aware

# JSON流输出
python -m vcmix render demo_project/demo_project.yaml --stream json
```

### 3. 分析输出
```bash
python -m vcmix analyze demo_project/neon_lights_output.wav
# File:     neon_lights_output.wav
# Duration: 17.0s | SR: 44100Hz | Ch: 1
# RMS:      -7.68 dBFS
# Peak:     -1.00 dBFS
# TruePeak: -12.48 dBFS
# LUFS:     -8.4
# DR:       6.68 dB
```

### 4. 查看采样器信息
```bash
python -m vcmix sampler info --project demo_project/demo_project.yaml --track drums
```

### 5. 渲染单轨（采样器）
```bash
python -m vcmix sampler render --project demo_project/demo_project.yaml --track drums --output demo_project/drums_solo.wav
```

### 6. 查看链预设
```bash
python -m vcmix chain-presets list
python -m vcmix chain-presets show vocal-chain
```

### 7. Web UI
```bash
python -m vcmix web demo_project/demo_project.yaml
```

## 预期输出

| 指标 | 预期值 |
|------|--------|
| 时长 | ~17秒（32 beats @ 120 BPM + 1s尾音）|
| 采样率 | 44100 Hz |
| 声道 | 单声道 |
| Peak | -1.0 dBFS（limiter ceiling）|
| RMS | -8 ~ -10 dBFS |
| LUFS | -8 ~ -10 |
| 渲染耗时 | < 5秒 |

## 验证的功能清单

| 功能 | 状态 | 验证方式 |
|------|------|----------|
| YAML配置解析 | ✔ | validate命令 |
| MIDI文件生成与解析 | ✔ | 4个MIDI文件 |
| 内置合成器（sine/saw/square）| ✔ | bass/lead/pad轨道 |
| Sampler采样器 | ✔ | drums轨道 |
| 自动化曲线（gain） | ✔ | bass/vocal轨道 |
| 插件链处理 | ✔ | 全部5轨道+Master |
| Chain Presets | ✔ | vocal-chain与vocal轨道一致 |
| AutoMix增益修正 | ✔ | --auto-fix |
| 编曲感知混音 | ✔ | --arrangement-aware |
| 音频分析 | ✔ | analyze命令 |
| 采样器CLI | ✔ | sampler info/render |
| Web UI | ✔ | web命令 |

## Bug修复记录

### Bug 1: MIDI轨道验证误报
- **位置**: `src/vcmix/cli.py` → `_validate_config()`
- **问题**: MIDI轨道（type='midi'）没有`file`字段，但验证器只排除了sampler类型，导致MIDI轨道被误报"has no file path"
- **修复**: 增加MIDI轨道类型判断，MIDI轨道需要`midi_file`而非`file`

### Bug 2: Sampler info KeyError
- **位置**: `src/vcmix/cli.py` → `sampler_info()`
- **问题**: 当采样zone没有loop点时，`z['loop_start']`和`z['loop_end']`键不存在，导致KeyError
- **修复**: 使用`z.get('loop_start', 'N/A')`替代直接索引访问

## 曲式结构

```
Bar:   | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 |
Beat:  0   4   8   12  16  20  24  28  32

drums: ████████████████████████████████████  (持续节拍)
bass:  ░░░░░░░░░░████████████████████░░░░░░  (gain: -3→0→0→-6)
lead:  ████████████████████████████████████  (旋律重复4次)
pad:   ████████████████████████████████████  (I-vi-IV-V ×2)
vocal: ░░░░████████████████████████░░░░░░░░  (gain: -12→0→0→-12)
```
