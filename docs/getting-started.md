# OpenDAW 快速入门指南

## 安装

### 从源码构建

```bash
# 克隆仓库
git clone https://github.com/youbanzhishi/OpenDAW.git
cd OpenDAW

# 构建（需要Rust 1.75+）
cargo build --release

# 构建CLI工具
cargo build --release -p opendaw-cli

# 构建API服务
cargo build --release -p opendaw-api
```

### 前置依赖

- Rust 1.75+（推荐1.85+以获得完整CLAP插件支持）
- 系统音频驱动（ALSA/PulseAudio/CoreAudio）

## CLI基本操作

### 创建项目

```bash
# 创建空白项目
opendaw new "My Project"

# 从模板创建
opendaw new "Band Demo" --template Band
opendaw new "Podcast EP1" --template Podcast
opendaw new "EDM Track" --template EDM
opendaw new "Symphony" --template Orchestral
```

可用模板：
- `Empty` — 空项目
- `Band` — 乐队4轨（鼓/贝斯/吉他/人声）
- `Podcast` — 播客3轨（主持/嘉宾/音效）
- `EDM` — 电子7轨（Kick/Snare/HiHat/Bass/Lead/Pad/FX）
- `Orchestral` — 管弦乐12轨

### 项目操作

```bash
# 打开项目
opendaw open project.yaml

# 添加轨道
opendaw track add "Vocals" --type audio --volume 0.8

# 添加插件
opendaw plugin add "Vocals" --name "vc-eq"
opendaw plugin add "Vocals" --name "vc-compressor"

# 设置音量/声像
opendaw track set "Vocals" --volume 0.75 --pan -0.2

# 保存项目
opendaw save
```

### 混音

```bash
# 查看混音建议
opendaw mix suggest

# 应用自动混音
opendaw mix auto --style pop

# 查看轨道分析
opendaw track analyze "Vocals"
```

## 导出

### 音频导出

```bash
# 导出为WAV（16-bit）
opendaw export --format wav --output render.wav

# 导出为WAV（24-bit）
opendaw export --format wav --bit-depth 24 --output render.wav

# 导出为FLAC
opendaw export --format flac --output render.flac

# 导出指定范围
opendaw export --format wav --start-beat 0 --end-beat 64 --output intro.wav

# 导出并归一化
opendaw export --format wav --normalize --output final.wav
```

### MIDI导出

```bash
# 导出MIDI文件
opendaw export-midi --output song.mid

# 导出为Format 1（多轨MIDI）
opendaw export-midi --format 1 --output song.mid
```

## API服务

### 启动API服务

```bash
opendaw-api --port 3000
```

### REST API示例

```bash
# 创建项目
curl -X POST http://localhost:3000/api/v1/projects \
  -H "Content-Type: application/json" \
  -d '{"name": "My Project"}'

# 列出项目
curl http://localhost:3000/api/v1/projects

# 触发渲染
curl -X POST http://localhost:3000/api/v1/projects/{id}/render

# AI自动混音
curl -X POST http://localhost:3000/api/v1/projects/{id}/automix
```

## 项目文件格式

OpenDAW支持三种项目文件格式：

| 格式 | 扩展名 | 特点 |
|------|--------|------|
| YAML | `.yaml` | 人类可读，适合手动编辑 |
| JSON | `.json` | 机器友好，适合程序处理 |
| Binary | `.bin` | 体积最小，加载最快 |

格式互转：

```bash
opendaw convert project.yaml project.json
opendaw convert project.json project.bin
```

## 插件系统

OpenDAW支持多种插件格式：

- **VC-Plugin** — OpenDAW原生插件格式
- **JSFX** — 兼容Reaper的脚本效果器
- **CLAP** — 开源插件标准（需要Rust 1.85+）
- **VST3** — 预留支持

### 插件市场

```bash
# 搜索插件
opendaw marketplace search "reverb"

# 安装插件
opendaw marketplace install plugin-id

# 查看插件详情
opendaw marketplace info plugin-id
```

## 下一步

- 阅读 [API参考文档](./api-reference.md)
- 学习 [插件开发](./plugin-development.md)
- 加入社区讨论
