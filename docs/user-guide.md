# OpenDAW 用户指南

> AI原生的数字音频工作站 — 配好模型API即可使用AI辅助做音乐

---

## 目录

1. [安装与部署](#1-安装与部署)
2. [快速上手](#2-快速上手)
3. [AI模型配置](#3-ai模型配置)
4. [AI Agent功能](#4-ai-agent功能)
5. [项目工作流](#5-项目工作流)
6. [插件市场](#6-插件市场)
7. [常见问题FAQ](#7-常见问题faq)

---

## 1. 安装与部署

### 1.1 Docker一键部署

最简单的方式，拉取即用：

```bash
# 直接运行
docker run -d \
  --name opendaw \
  -p 3000:3000 \
  -p 3001:3001 \
  ghcr.io/youbanzhishi/opendaw/opendaw:latest
```

或使用 docker-compose：

```bash
# 使用项目自带的 docker-compose.yml
docker compose up -d
```

| 环境变量 | 默认值 | 说明 |
|----------|--------|------|
| `OPENDAW_HOST` | `0.0.0.0` | 监听地址 |
| `OPENDAW_PORT` | `3000` | API端口 |
| `OPENDAW_WS_PORT` | `3001` | WebSocket端口 |
| `RUST_LOG` | `opendaw=info` | 日志级别 |

部署完成后访问 `http://localhost:3000` 进入WebUI。

### 1.2 二进制下载安装

从 [GitHub Releases](https://github.com/youbanzhishi/OpenDAW/releases) 下载对应平台的预编译二进制：

**Linux x86_64**：

```bash
curl -L https://github.com/youbanzhishi/OpenDAW/releases/latest/download/opendaw-linux-amd64.tar.gz | tar xz
chmod +x opendaw
sudo mv opendaw /usr/local/bin/
```

**macOS Apple Silicon**：

```bash
curl -L https://github.com/youbanzhishi/OpenDAW/releases/latest/download/opendaw-macos-arm64.tar.gz | tar xz
chmod +x opendaw
sudo mv opendaw /usr/local/bin/
```

**macOS Intel**：

```bash
curl -L https://github.com/youbanzhishi/OpenDAW/releases/latest/download/opendaw-macos-x64.tar.gz | tar xz
chmod +x opendaw
sudo mv opendaw /usr/local/bin/
```

**Windows**：

下载 `opendaw-windows-amd64.exe.zip`，解压后使用。

**Linux systemd 服务**（可选）：

```bash
sudo tee /etc/systemd/system/opendaw.service << 'EOF'
[Unit]
Description=OpenDAW Server
After=network.target

[Service]
Type=simple
User=opendaw
Group=opendaw
WorkingDirectory=/var/lib/opendaw
Environment=RUST_LOG=opendaw=info
Environment=OPENDAW_HOST=0.0.0.0
Environment=OPENDAW_PORT=3000
ExecStart=/usr/local/bin/opendaw serve
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

sudo useradd -r -s /bin/false opendaw
sudo mkdir -p /var/lib/opendaw
sudo chown opendaw:opendaw /var/lib/opendaw
sudo systemctl daemon-reload
sudo systemctl enable --now opendaw
```

### 1.3 桌面应用安装

基于 Tauri v2 的原生桌面应用，从 [GitHub Releases](https://github.com/youbanzhishi/OpenDAW/releases) 下载：

| 平台 | 文件 | 说明 |
|------|------|------|
| Linux | `OpenDAW_amd64.AppImage` | 免安装，`chmod +x` 后直接运行 |
| Linux | `OpenDAW_amd64.deb` | Debian/Ubuntu 包 |
| macOS | `OpenDAW_aarch64.dmg` | Apple Silicon |
| macOS | `OpenDAW_x64.dmg` | Intel Mac |
| Windows | `OpenDAW_x64-setup.exe` | NSIS安装程序 |
| Windows | `OpenDAW_x64_en-US.msi` | MSI安装包 |

**Linux AppImage**：

```bash
chmod +x OpenDAW_amd64.AppImage
./OpenDAW_amd64.AppImage
# 依赖：libwebkit2gtk-4.1-0
sudo apt-get install libwebkit2gtk-4.1-0 libappindicator3-1
```

**macOS**：打开 `.dmg` → 拖入 Applications → 首次打开需右键→打开（绕过Gatekeeper）

**Windows**：运行安装程序，按向导完成安装

### 1.4 源码编译

**前置依赖**：

- **Rust 1.86+**（必需，`icu` 依赖需要 edition 2024）
- **C/C++编译器**（gcc 或 clang）
- Linux额外：`build-essential pkg-config libssl-dev libasound2-dev`
- macOS额外：`xcode-select --install`
- 桌面应用额外：Node.js 18+

```bash
# 安装 Rust
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh

# 克隆仓库
git clone https://github.com/youbanzhishi/OpenDAW.git
cd OpenDAW

# 编译 CLI
cargo build --release -p opendaw-cli

# 编译 API 服务
cargo build --release -p opendaw-api

# 编译 WebSocket 服务
cargo build --release -p opendaw-ws

# 安装
sudo cp target/release/opendaw /usr/local/bin/
sudo cp target/release/opendaw-api /usr/local/bin/
```

---

## 2. 快速上手

### 2.1 CLI方式

```bash
# 创建空白项目
opendaw new "My Project"

# 从模板创建
opendaw new "Band Demo" --template Band
opendaw new "Podcast EP1" --template Podcast
opendaw new "EDM Track" --template EDM
opendaw new "Symphony" --template Orchestral
```

可用模板：`Empty`、`Band`、`Podcast`、`EDM`、`Orchestral`

**添加轨道与插件**：

```bash
opendaw track add "Vocals" --type audio --volume 0.8
opendaw track add "Guitar" --type audio

opendaw plugin add "Vocals" --name "vc-eq"
opendaw plugin add "Vocals" --name "vc-compressor"
opendaw plugin add "Vocals" --name "vc-reverb"
```

**混音与导出**：

```bash
# 查看混音建议
opendaw mix suggest

# AI自动混音
opendaw mix auto --style pop

# 导出
opendaw export --format wav --output render.wav
opendaw export --format wav --bit-depth 24 --normalize --output final.wav
opendaw export --format flac --output render.flac
```

**启动API服务**：

```bash
opendaw serve --host 0.0.0.0 --port 3000 --ws-port 3001
```

### 2.2 WebUI使用

1. 启动服务后访问 `http://localhost:3000`
2. 在Web界面中创建/打开项目
3. 使用界面按钮添加轨道、插件
4. 打开AI对话面板，直接与AI Agent对话

### 2.3 桌面应用使用

1. 启动桌面应用
2. 应用自动启动后端服务（或连接已有后端）
3. 使用原生界面操作项目
4. 内置AI对话窗口，通过 `agent_chat` 命令与AI交互

---

## 3. AI模型配置

> 这是使用AI功能的前提。配好模型后，AI对话即可直接使用。

### 3.1 支持的模型后端

| 后端 | 类型 | 说明 | 默认 base_url |
|------|------|------|----------------|
| **OpenAI** | 云端 | GPT-4o等，需要API Key | `https://api.openai.com/v1` |
| **Anthropic** | 云端 | Claude系列，兼容层 | `https://api.anthropic.com/v1` |
| **Ollama** | 本地 | 开源模型，无需API Key | `http://localhost:11434/v1` |
| **vLLM** | 本地 | 自部署模型，无需API Key | `http://localhost:8000/v1` |

所有后端均通过 OpenAI SDK 兼容接口访问，统一调用 `/chat/completions`。

### 3.2 OpenAI配置

1. 获取API Key：前往 [platform.openai.com](https://platform.openai.com/api-keys) 创建
2. 推荐模型：`gpt-4o`（综合最佳）、`gpt-4o-mini`（经济快速）

**配置文件方式**（`config/default.toml`）：

```toml
[model]
provider = "openai"
model = "gpt-4o"
api_key = "sk-xxxxxxxxxxxxxxxx"
base_url = "https://api.openai.com/v1"
temperature = 0.3
max_tokens = 2048
```

**环境变量方式**：

```bash
export OPENDAW_MODEL_PROVIDER=openai
export OPENDAW_MODEL_MODEL=gpt-4o
export OPENDAW_MODEL_API_KEY=sk-xxxxxxxxxxxxxxxx
export OPENDAW_MODEL_BASE_URL=https://api.openai.com/v1
export OPENDAW_MODEL_TEMPERATURE=0.3
export OPENDAW_MODEL_MAX_TOKENS=2048
```

环境变量优先级高于配置文件。

### 3.3 Anthropic配置

Anthropic通过兼容层接入，使用 OpenAI SDK 兼容接口调用。

1. 获取API Key：前往 [console.anthropic.com](https://console.anthropic.com/) 创建
2. 推荐模型：`claude-3.5-sonnet`（均衡）、`claude-3-opus`（最强推理）

```toml
[model]
provider = "anthropic"
model = "claude-3.5-sonnet"
api_key = "sk-ant-xxxxxxxxxxxxxxxx"
base_url = "https://api.anthropic.com/v1"
temperature = 0.3
max_tokens = 2048
```

> **注意**：Anthropic的兼容层会自动将请求转换为OpenAI格式。如果使用第三方代理（如OpenRouter），修改 `base_url` 即可。

### 3.4 Ollama本地模型配置

完全免费，数据不出本机，适合隐私敏感场景。

**第一步：安装Ollama**

```bash
# Linux
curl -fsSL https://ollama.com/install.sh | sh

# macOS
brew install ollama

# 启动服务
ollama serve
```

**第二步：拉取模型**

```bash
# 推荐：70B参数，混音理解力强
ollama pull llama3.3:70b

# 备选：72B参数，中文能力强
ollama pull qwen2.5:72b

# 轻量：适合快速对话
ollama pull deepseek-r1
```

**第三步：配置OpenDAW**

```toml
[model]
provider = "ollama"
model = "llama3.3:70b"
api_key = ""          # Ollama无需API Key
base_url = "http://localhost:11434/v1"
temperature = 0.3
max_tokens = 2048
```

> **提示**：Ollama默认占用11434端口，启动后即可访问。如果修改了端口，同步修改 `base_url`。

### 3.5 vLLM本地部署配置

vLLM适合需要高性能推理的自部署场景。

**第一步：安装vLLM**

```bash
pip install vllm
```

**第二步：启动vLLM服务**

```bash
# 示例：启动一个模型服务
python -m vllm.entrypoints.openai.api_server \
  --model /path/to/your/model \
  --host 0.0.0.0 \
  --port 8000
```

**第三步：配置OpenDAW**

```toml
[model]
provider = "vllm"
model = "custom-mix-engine-v1"
api_key = ""          # 本地部署无需API Key
base_url = "http://localhost:8000/v1"
temperature = 0.3
max_tokens = 2048
```

### 3.6 配置文件位置和格式

| 来源 | 路径 |
|------|------|
| 默认配置 | `config/default.toml` 中的 `[model]` 段 |
| 环境变量 | `OPENDAW_MODEL_*` 前缀的环境变量 |

**ModelConfig 完整字段**：

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `provider` | string | `"openai"` | 后端：openai/anthropic/ollama/vllm |
| `model` | string | `"gpt-4o"` | 模型名称 |
| `api_key` | string | `""` | API密钥（本地模型可留空） |
| `base_url` | string | `"https://api.openai.com/v1"` | API地址 |
| `temperature` | float | `0.3` | 温度参数（0-1），越低越确定 |
| `max_tokens` | int | `2048` | 最大输出token数 |

### 3.7 配置后使用

配置完成后，在任何界面的AI对话框中直接输入即可：

- **CLI**：`opendaw repl` 进入交互模式后对话
- **WebUI**：点击对话面板输入
- **桌面应用**：打开AI对话窗口
- **API**：`POST /api/v1/agent/chat` 发送消息

### 3.8 模型选择建议

| 场景 | 推荐方案 | 原因 |
|------|----------|------|
| 日常混音辅助 | OpenAI gpt-4o | 综合能力最强，工具调用准确 |
| 成本敏感 | OpenAI gpt-4o-mini | 便宜快速，够用 |
| 隐私/离线 | Ollama llama3.3:70b | 完全本地，数据不出本机 |
| 高端推理 | Anthropic claude-3-opus | 复杂混音分析推理更强 |
| 中文交互 | Ollama qwen2.5:72b | 中文理解力好 |
| 批量处理 | vLLM自部署 | 高吞吐，适合批量混音 |
| 快速实验 | Ollama deepseek-r1 | 轻量，拉取快 |

---

## 4. AI Agent功能

### 4.1 Agent对话使用方式

OpenDAW内置AI Agent，支持自然语言对话，自动理解意图并执行操作。

**使用入口**：

- **WebUI**：对话面板，直接输入
- **桌面应用**：AI对话窗口
- **CLI**：`opendaw repl` 交互模式
- **API**：`POST /api/v1/agent/chat`

**对话示例**：

```
你：帮我分析一下当前项目的频谱
Agent：🔧 调用工具: analyze_project({"project_id": "xxx"})
       📊 工具结果: {"loudness": -14.2, "spectral_balance": ...}
       当前项目整体响度 -14.2 LUFS，频谱分析如下...

你：人声轨道有点闷，帮我在2-4kHz补偿一下
Agent：🔧 调用工具: update_effect({"track_name": "vocal", "effect_index": 2, "params": {"peak_gain": 3, "peak_freq": 3000}})
       已为vocal轨道的EQ增加 3dB @ 3kHz 增益，补偿Presence频段...

你：现在自动混音一下
Agent：🔧 调用工具: ai_auto_mix({"project_id": "xxx", "mode": "step"})
       已生成自动混音建议，包含3项调整...
```

### 4.2 内置Persona说明

Persona决定Agent的角色、专业领域和沟通风格。

| Persona ID | 名称 | 特点 | 执行模式 |
|------------|------|------|----------|
| `mix-engineer` | 混音工程师 | 专业混音，精通EQ/压缩/空间处理，使用技术术语 | confirm |
| `vocal-expert` | 人声专家 | 专注人声处理，去齿音/人声EQ/混响/和声 | confirm |
| `beginner-coach` | 新手教练 | 用比喻解释概念，一次一步，不使用未解释的术语 | suggest |

**默认**：未指定Persona时使用通用混音助手。

**选择方式**：在对话中或通过API指定 `persona_id`。

### 4.3 执行模式说明

| 模式 | 行为 | 适用场景 |
|------|------|----------|
| `auto` | 自动执行，无需确认 | 批量操作、信任Agent |
| `confirm` | 执行前请求用户确认 | 默认模式，安全可控 |
| `suggest` | 仅建议，不执行 | 学习/探索，新手友好 |

- `mix-engineer` 和 `vocal-expert` 默认 `confirm` 模式
- `beginner-coach` 默认 `suggest` 模式

### 4.4 Agent能做什么

| 功能 | 说明 |
|------|------|
| **自动混音** | 分析项目并调整各轨电平、EQ、压缩、空间平衡 |
| **AI母带** | 优化响度、立体声宽度、最终润色 |
| **EQ建议** | 频谱分析 → 诊断频率问题 → 推荐EQ调整 |
| **动态处理** | 压缩/限制/门限参数建议和调整 |
| **频谱分析** | 获取轨道FFT频谱，诊断频率遮蔽问题 |
| **效果器管理** | 添加/修改/删除轨道效果器 |
| **编排建议** | AI作曲引擎，生成完整编排 |
| **预设应用** | 查询和应用效果链预设、混音预设 |
| **项目快照** | 创建版本快照，支持回滚 |
| **Stem导出** | 导出各轨道单独音频文件 |

### 4.5 工具调用说明

Agent通过ReAct循环（Reason + Act）执行工具，最多5轮工具调用。

**Agent可调用的20个工具**：

| 工具 | 说明 | 必需参数 |
|------|------|----------|
| `analyze_project` | 分析项目音频特征 | `project_id` |
| `list_plugins` | 列出可用插件 | 无 |
| `add_effect` | 添加效果器到轨道 | `project_id`, `track_name`, `effect_name` |
| `update_effect` | 更新效果器参数 | `project_id`, `track_name`, `effect_index`, `params` |
| `remove_effect` | 移除效果器 | `project_id`, `track_name`, `effect_index` |
| `get_project` | 获取项目详情 | `project_id` |
| `render_project` | 触发渲染 | `project_id` |
| `ai_auto_mix` | AI自动混音 | `project_id` |
| `ai_master` | AI母带处理 | `project_id` |
| `get_waveform` | 获取波形数据 | `project_id`, `track_name` |
| `get_spectrum` | 获取频谱数据 | `project_id`, `track_name` |
| `add_track` | 添加轨道 | `project_id`, `name` |
| `update_track` | 更新轨道属性 | `project_id`, `track_name` |
| `remove_track` | 删除轨道 | `project_id`, `track_name` |
| `validate_project` | 验证项目配置 | `project_id` |
| `get_presets` | 列出预设 | `preset_type`（可选） |
| `apply_preset` | 应用预设 | `project_id`, `preset_name` |
| `ai_compose` | AI作曲 | `genre`, `bpm`, `key`等（可选） |
| `create_snapshot` | 创建项目快照 | `project_id` |
| `export_stems` | 导出Stem | `project_id` |

---

## 5. 项目工作流

### 5.1 项目文件格式

| 格式 | 扩展名 | 特点 |
|------|--------|------|
| YAML | `.yaml` | 人类可读，适合手动编辑和版本控制 |
| JSON | `.json` | 机器友好，适合程序处理 |
| Binary | `.bin` | 体积最小，加载最快 |

格式互转：

```bash
opendaw convert project.yaml project.json
opendaw convert project.json project.bin
```

### 5.2 YAML项目格式

完整示例（基于 `examples/jiuwanzi.yaml`）：

```yaml
name: "九万字"
bpm: 62
sample_rate: 44100

tracks:
  - name: vocal
    file: "vocal_dry.wav"
    volume: 1.0
    effects:
      - name: vc-deesser
        params:
          threshold: -40
          reduction: -6
      - name: vc-gain
        params:
          gain: 6
      - name: vc-eq
        params:
          low_cut: 80
          high_shelf: 8000
          peak_gain: -3
      - name: vc-comp
        params:
          threshold: -30
          ratio: 2.5
          attack: 5
          release: 50
      - name: vc-reverb
        params:
          room: 30
          decay: 35
          damping: 50
          mix: 10
          predelay: 50
          wetlpf: 5000

  - name: accomp
    file: "accomp.wav"
    volume: 1.0
    effects: []

master:
  levels:
    vocal: 0.8
    accomp: 0.35
  effects: []
  output: "jiuwanzi_mix.wav"
```

### 5.3 轨道操作

```bash
# 添加轨道
opendaw track add "Vocals" --type audio --volume 0.8
opendaw track add "Bass" --type audio
opendaw track add "Drums" --type midi

# 修改轨道
opendaw track set "Vocals" --volume 0.75 --pan -0.2
opendaw track set "Bass" --mute

# 分析轨道
opendaw track analyze "Vocals"

# 删除轨道
opendaw track remove "Drums"
```

### 5.4 插件使用

OpenDAW支持四种插件格式：

| 格式 | 说明 |
|------|------|
| **VC-Plugin** | OpenDAW原生插件，内置丰富效果器 |
| **JSFX** | 兼容Reaper的脚本效果器 |
| **CLAP** | 开源插件标准（需要Rust 1.85+） |
| **VST3** | 预留支持 |

**内置VC-Plugin列表**：

| 插件 | 类型 | 关键参数 |
|------|------|----------|
| VC-EQ | 参数均衡 | low_cut, high_shelf, peak_gain, peak_freq |
| VC-Comp | 压缩器 | threshold, ratio, attack, release |
| VC-Reverb | 混响（FDN） | room, decay, damping, mix, predelay, wetlpf |
| VC-Delay | 延迟 | time, feedback, mix |
| VC-DeEsser | 齿音消除 | threshold, reduction |
| VC-Gain | 增益 | gain |
| VC-Saturator | 饱和 | drive, mix |
| VC-Limiter | 限幅 | ceiling, release |
| VC-DynamicEQ | 动态EQ | frequency, threshold, q, attack, release |
| VC-Distortion | 失真 | drive, tone, mix |
| VC-Noise | 降噪 | threshold, reduction |
| VC-Tune | 音高修正 | speed, scale, transpose, autokey |
| VC-Gate | 噪声门 | threshold, ratio, attack, hold, release, range |
| VC-Chorus | 合唱 | rate, depth, voices, mix, width |
| VC-Stereo | 立体声 | width, pan, mono_bass, bass_freq |
| VC-PitchShift | 变调 | semitones, cents, formant |

```bash
# 添加插件
opendaw plugin add "Vocals" --name "vc-eq"
opendaw plugin add "Vocals" --name "vc-comp"

# 修改参数
opendaw plugin set "Vocals" --index 0 --params "low_cut=80,peak_gain=3"

# 移除插件
opendaw plugin remove "Vocals" --index 2
```

### 5.5 混音流程

```bash
# 1. 查看混音建议
opendaw mix suggest

# 2. AI自动混音（指定风格）
opendaw mix auto --style pop

# 3. 或通过API获取建议
curl http://localhost:3000/api/v1/mixer/{project_id}/suggestions

# 4. AI自动混音API
curl -X POST http://localhost:3000/api/v1/projects/{project_id}/automix \
  -H "Content-Type: application/json" \
  -d '{"style": "pop", "apply": false}'
```

### 5.6 导出设置

```bash
# WAV 16-bit
opendaw export --format wav --output render.wav

# WAV 24-bit
opendaw export --format wav --bit-depth 24 --output render.wav

# FLAC
opendaw export --format flac --output render.flac

# 导出指定范围
opendaw export --format wav --start-beat 0 --end-beat 64 --output intro.wav

# 归一化导出
opendaw export --format wav --normalize --output final.wav

# MIDI导出
opendaw export-midi --output song.mid
opendaw export-midi --format 1 --output song.mid
```

---

## 6. 插件市场

### 6.1 搜索与安装

```bash
# 搜索插件
opendaw marketplace search "reverb"

# 按分类搜索
opendaw marketplace search --category effect

# 安装插件
opendaw marketplace install plugin-id

# 查看插件详情
opendaw marketplace info plugin-id
```

**API方式**：

```bash
# 搜索
curl "http://localhost:3000/api/v1/marketplace/search?q=reverb&category=effect"

# 安装
curl -X POST http://localhost:3000/api/v1/marketplace/{plugin-id}/install

# 查看分类
curl http://localhost:3000/api/v1/marketplace/categories
```

### 6.2 评分与评价

```bash
# 提交评价（1-5分）
curl -X POST http://localhost:3000/api/v1/marketplace/{plugin-id}/review \
  -H "Content-Type: application/json" \
  -d '{"user_id": "my-user-id", "rating": 5, "comment": "Great plugin!"}'
```

---

## 7. 常见问题FAQ

### Q: 模型API连接失败，怎么排查？

**步骤**：

1. **检查API Key**：确认 `api_key` 正确，没有多余空格
2. **检查base_url**：确保URL末尾是 `/v1`，不是 `/v1/` 或缺少 `/v1`
3. **测试连通性**：
   ```bash
   # OpenAI
   curl https://api.openai.com/v1/models -H "Authorization: Bearer sk-xxx"

   # Ollama
   curl http://localhost:11434/v1/models

   # vLLM
   curl http://localhost:8000/v1/models
   ```
4. **检查防火墙**：本地模型（Ollama/vLLM）确保端口未被防火墙阻断
5. **查看日志**：设置 `RUST_LOG=opendaw=debug` 查看详细错误信息
6. **代理设置**：如果使用代理访问OpenAI，确保代理正常工作

### Q: Ollama模型拉取很慢怎么办？

- 使用国内镜像：`OLLAMA_MIRROR=https://xxx ollama pull llama3.3:70b`
- 先拉取小模型测试：`ollama pull deepseek-r1`
- 确认磁盘空间充足（70B模型约需40GB）

### Q: 音频设备配置问题？

- **Linux**：确保安装 `libasound2-dev`（ALSA）或 PulseAudio
- **macOS**：CoreAudio 通常即插即用
- **Windows**：确认ASIO/WASAPI驱动正常
- 桌面应用中可通过 `audio_get_devices` 命令查看可用设备

### Q: 导出格式怎么选？

| 格式 | 适用场景 |
|------|----------|
| WAV 16-bit | 通用交付、CD品质 |
| WAV 24-bit | 专业制作、后期处理 |
| WAV 32-bit float | 无损中间文件、多次处理 |
| FLAC | 无损压缩、节省空间 |
| MP3 | 交付试听、播客发布 |

### Q: Agent工具调用次数不够用？

Agent最多执行5轮工具调用。如果需要更多轮次：
1. 将复杂任务拆分为多个对话轮次
2. 使用 `auto` 执行模式减少确认步骤
3. 通过 `create_snapshot` 在关键节点保存状态

### Q: 如何切换Persona？

在对话中指定或通过API设置：
- API：在请求中添加 `"persona": "mix-engineer"`
- CLI：`opendaw repl --persona mix-engineer`

### Q: 本地模型效果不好怎么办？

- 优先使用 70B 及以上参数量的模型
- 适当提高 `temperature`（0.3→0.5）获得更灵活的响应
- 降低 `temperature`（0.3→0.1）获得更精确的工具调用
- 尝试不同的模型：llama3.3:70b vs qwen2.5:72b vs deepseek-r1
