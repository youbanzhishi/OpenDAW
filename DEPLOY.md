# VCMix Deployment Guide

Deploy VCMix on low-resource cloud servers. Two approaches available.

---

## Quick Start

### 方案B：预构建镜像（推荐）

**最适合**：1G内存服务器、快速部署、不想编译

```bash
# 1. 下载部署文件（只需要2个文件）
# 从仓库获取 docker-compose.yml 和 .env.example

# 2. 配置环境变量
cp .env.example .env
# 编辑 .env，按需修改端口和模式

# 3. 一键启动
docker compose up -d

# 4. 访问
# 浏览器打开 http://your-server-ip:8000
```

**就这么简单！** 不需要 Dockerfile，不需要 build，不需要 2G 内存。

### 方案A：自建镜像

**最适合**：需要自定义版本、网络无法访问 ghcr.io、想修改源码

```bash
# 1. 确保有 Dockerfile（在同目录下）
# 2. 配置环境变量
cp .env.example .env
# 编辑 .env 中的 OPENDAW_VERSION 和 AUDIOFX_RELEASE_VERSION

# 3. 构建并启动（需要至少2G内存）
docker compose up -d --build

# 4. 访问
# 浏览器打开 http://your-server-ip:8000
```

---

## 方案对比

| | 方案B：预构建镜像 | 方案A：自建镜像 |
|---|---|---|
| **推荐度** | ⭐ 推荐 | 按需 |
| **命令** | `docker compose up -d` | `docker compose up -d --build` |
| **所需文件** | docker-compose.yml + .env | Dockerfile + docker-compose.yml + .env |
| **服务器内存要求** | 1G 即可 | 至少 2G（build 时需要） |
| **首次部署速度** | 快（~450MB download） | 慢（需编译，3-10分钟） |
| **版本控制** | VCMIX_IMAGE_TAG 指定 | OPENDAW_VERSION / AUDIOFX_RELEASE_VERSION |
| **网络要求** | 需访问 ghcr.io | 需访问 GitHub（archive + release） |
| **自定义能力** | 无 | 可改源码、改版本、改依赖 |

---

## Core vs Full 模式

| 模式 | 镜像体积 | 运行内存 | 适合 |
|------|---------|---------|------|
| **core** | ~450MB | ~300MB | 1G 服务器，日常混音渲染 |
| **full** | ~2GB | ~1.5GB | 4G+ 服务器，含 AI/Demucs/协作/可视化 |

切换方式：编辑 `.env` 中的 `VCMIX_PROFILE`

```bash
# 切换到 full 模式
VCMIX_PROFILE=full
VCMIX_MEMORY_LIMIT=2G    # full 模式需要更多内存

# 重启
docker compose up -d
```

---

## Environment Variables

| Variable | Default | Description | 方案 |
|---|---|---|---|
| `VCMIX_IMAGE_TAG` | `latest` | 预构建镜像标签（`latest` / `v0.22.2`） | B |
| `VCMIX_PROFILE` | `core` | 运行模式（`core` / `full`） | A+B |
| `VCMIX_PORT` | `8000` | 宿主机端口 | A+B |
| `VCMIX_MEMORY_LIMIT` | `512M` | 容器内存上限 | A+B |
| `VCMIX_CPU_LIMIT` | `1.0` | 容器 CPU 核数 | A+B |
| `VCMIX_PROJECTS_DIR` | `./projects` | 工程文件目录 | A+B |
| `VCMIX_OUTPUT_DIR` | `./output` | 渲染输出目录 | A+B |
| `VCMIX_LOG_LEVEL` | `info` | 日志级别（debug/info/warning/error） | A+B |
| `OPENDAW_VERSION` | `v0.22.2` | OpenDAW 源码版本（tag） | A |
| `AUDIOFX_RELEASE_VERSION` | `v2.8.0` | AudioFX CLI 插件版本（tag） | A |

### VCMIX_IMAGE_TAG 可用值

| Tag | 说明 |
|-----|------|
| `latest` | 最新版（推荐） |
| `v0.22.2` | 指定版本 |

完整镜像名格式：`ghcr.io/youbanzhishi/vcmix:{profile}-{tag}`

示例：
- `ghcr.io/youbanzhishi/vcmix:core-latest`
- `ghcr.io/youbanzhishi/vcmix:full-latest`
- `ghcr.io/youbanzhishi/vcmix:core-v0.22.2`
- `ghcr.io/youbanzhishi/vcmix:full-v0.22.2`

---

## 预构建镜像详情

### 镜像来源

VCMix 预构建镜像由 GitHub Actions CI 自动构建并推送到 GitHub Container Registry (ghcr.io)。

- **仓库**：`ghcr.io/youbanzhishi/vcmix`
- **可见性**：公开（无需 `docker login`）
- **构建触发**：每次推送到 main 分支或发布 tag 时自动构建

### 国内镜像加速

如果 ghcr.io 访问缓慢，可以配置 Docker 镜像加速：

```bash
# 编辑 /etc/docker/daemon.json
sudo tee /etc/docker/daemon.json <<EOF
{
  "registry-mirrors": [
    "https://mirror.ghcr.io"
  ]
}
EOF

# 重启 Docker
sudo systemctl restart docker
```

或者手动 pull 后加载：

```bash
# 在网络好的机器上 pull 并导出
docker pull ghcr.io/youbanzhishi/vcmix:core-latest
docker save ghcr.io/youbanzhishi/vcmix:core-latest -o vcmix-core.tar

# 传输到目标服务器后加载
docker load -i vcmix-core.tar
docker compose up -d
```

### 指定版本部署

```bash
# 在 .env 中设置
VCMIX_IMAGE_TAG=v0.22.2

# 或者命令行
VCMIX_IMAGE_TAG=v0.22.2 docker compose up -d
```

---

## Feature Comparison: Core vs Full

| Feature | Core | Full |
|---|:---:|:---:|
| **Render API** (`/api/render`) | ✅ | ✅ |
| **Plugin Management** (`/api/plugins`) | ✅ | ✅ |
| **Preset Browser** (`/api/presets`) | ✅ | ✅ |
| **MIDI Scanning** (`/api/midi`) | ✅ | ✅ |
| **Automation** (`/api/automation`) | ✅ | ✅ |
| **Arrangement Analysis** (`/api/arrangement`) | ✅ | ✅ |
| **Auto-Mixing** (`/api/automix`) | ✅ | ✅ |
| **Agent API** (`/api/v1/projects`) | ✅ | ✅ |
| **AI Mixing Suggestions** (`/api/v1/ai/mix`) | ✅ | ✅ |
| **AI Mastering Suggestions** (`/api/v1/ai/master`) | ✅ | ✅ |
| **Render WebSocket** (`/ws/render/{id}`) | ✅ | ✅ |
| **AI Decision WebSocket** (`/ws/ai/{id}`) | ✅ | ✅ |
| **AI Transcription** (`/api/v1/ai/transcribe`) | ❌ | ✅ |
| **Style Match/Transfer** (`/api/v1/ai/style-*`) | ❌ | ✅ |
| **One-Click Remix** (`/api/v1/ai/remix`) | ❌ | ✅ |
| **Collaboration WebSocket** (`/ws/collab/{id}`) | ❌ | ✅ |
| **Multi-format Export** (`/api/v1/projects/{id}/export`) | ❌ | ✅ |
| **Stem Export** (`/api/v1/projects/{id}/export-stems`) | ❌ | ✅ |
| **Project Snapshots** (`/api/v1/projects/{id}/snapshots`) | ❌ | ✅ |
| **Waveform Visualization** (`/api/v1/waveform/`) | ❌ | ✅ |
| **Spectrum Analysis** (`/api/v1/spectrum/`) | ❌ | ✅ |
| **Piano Roll** (`/api/v1/midi/{id}/{track}`) | ❌ | ✅ |
| **Estimated RAM (idle)** | ~180MB | ~450MB |
| **Image Size** | ~450MB | ~2GB |
| **Demucs/Torch loaded** | No | Yes |

> In core mode, disabled endpoints return HTTP 501 with instructions to switch to full profile.

---

## Memory Optimization

### For 1GB servers (core profile)

- Container memory limit: 512MB (leaves ~512MB for OS)
- CPU limit: 1 core
- Core profile: no demucs/torch loaded

If you still encounter memory issues:

1. **Monitor usage**: `docker stats vcmix-server`
2. **Add swap** (if not already):
   ```bash
   sudo fallocate -l 1G /swapfile
   sudo chmod 600 /swapfile
   sudo mkswap /swapfile
   sudo swapon /swapfile
   # 持久化
   echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
   ```

### Upgrading to Full Mode

Full mode requires **4GB+ RAM**:

```bash
# Edit .env
VCMIX_PROFILE=full
VCMIX_MEMORY_LIMIT=2G

# Restart
docker compose up -d
```

---

## Troubleshooting

### 预构建镜像 pull 失败

```bash
# 检查能否访问 ghcr.io
curl -I https://ghcr.io/v2/

# 如果超时，配置镜像加速（见上方"国内镜像加速"章节）

# 如果是 403/401，检查是否需要登录（公开镜像不需要）
docker login ghcr.io
```

### 自建镜像 build 失败（内存不足）

```bash
# 症状：build 过程被 OOM kill
# 原因：pip install 需要 ~1.5GB 内存

# 解决方案1：使用预构建镜像（推荐）
docker compose up -d    # 不加 --build

# 解决方案2：添加 swap
sudo fallocate -l 2G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile

# 解决方案3：限制并行度
# 在 Dockerfile 中 pip install 加 --no-compile 减少内存占用
```

### Container won't start / OOM killed

```bash
# Check if OOM killed
dmesg | grep -i oom

# Reduce memory or switch to core profile
echo "VCMIX_PROFILE=core" >> .env
echo "VCMIX_MEMORY_LIMIT=512M" >> .env
docker compose up -d
```

### Health check failing

```bash
# Check container logs
docker compose logs vcmix

# Manual health check
curl http://localhost:8000/api/health

# 等待启动完成（首次启动可能需要30秒）
docker compose logs -f vcmix
```

### Port already in use

```bash
# Change port in .env
echo "VCMIX_PORT=8080" >> .env
docker compose up -d
```

### 网络问题（GitHub 下载失败，仅自建方案）

```bash
# Dockerfile 已配置国内镜像源（apt 阿里云 + pip 阿里云）
# 如果 GitHub archive 下载失败：
# 1. 重试（已内置 --retry 3）
# 2. 手动下载源码放到构建上下文
# 3. 改用预构建镜像方案
```

### Render fails with ffmpeg error

The Docker image includes ffmpeg. If running without Docker:

```bash
# Ubuntu/Debian
sudo apt-get install ffmpeg

# macOS
brew install ffmpeg
```

---

## Architecture

```
┌──────────────────────────────────────────┐
│              VCMix Container              │
│                                          │
│  ┌────────────────────────────────────┐  │
│  │         FastAPI Application        │  │
│  │                                    │  │
│  │  [core routes]  [full routes]      │  │
│  │   render         ai_transcription  │  │
│  │   plugins        collaboration     │  │
│  │   presets        waveform          │  │
│  │   midi           piano_roll        │  │
│  │   automation                       │  │
│  │   arrangement                      │  │
│  │   automix                          │  │
│  │   agent_api                        │  │
│  └────────────────────────────────────┘  │
│                                          │
│  /app/plugins   /app/projects  /app/output│
└──────────────────────────────────────────┘
       ↕              ↕            ↕
  host:projects  host:output  host:presets
```

---

## Plugin Architecture

```
┌──────────────────────────────────────────────┐
│              VCMix Plugin System              │
│                                              │
│  vc_plugins.py                               │
│    ├─ VC CLI subprocess adapter (default)    │
│    │   Path: /app/plugins/VC-{Name}/...      │
│    │   Env: VC_AUDIOFX_DIR=/app/plugins      │
│    │                                         │
│    └─ Native Python adapter (planned)        │
│        numpy/scipy implementations           │
│                                              │
│  23 VC Plugins:                              │
│    20 effects: EQ, Comp, Gain, DeEsser,      │
│      Saturator, Limiter, Delay, Reverb,      │
│      DynamicEQ, Smooth, SurgicalDeEsser,     │
│      Distortion, Noise, Tune, Gate, Chorus,  │
│      MultiBand, Harmonizer, PitchShift,      │
│      Stereo                                  │
│    3 instruments: Synth, Drum, Arp           │
│                                              │
│  Total CLI binary size: ~2.9MB               │
└──────────────────────────────────────────────┘
```

### Plugin Path Resolution (priority order)

1. `params["cli_path"]` — per-effect override
2. Environment variable `VC_{NAME}_CLI` — e.g. `VC_REVERB_CLI`
3. YAML config `plugin_paths` section
4. Default: `$VC_AUDIOFX_DIR/VC-{Name}/VC-{Name}-CLI-Standalone`

### Docker Build: CLI Binary Strategy

| Method | How | Use Case |
|--------|-----|----------|
| **Pre-built image** (default) | CLI already included in ghcr.io image | Quick deploy, 1GB servers |
| **GitHub Release download** (self-build) | Build auto-downloads from AudioFX releases | CI/CD, custom builds |
| **Local docker/plugins/** | Place pre-built binaries before `docker build` | Air-gapped, offline builds |

---

## Without Docker

```bash
# Core profile (no AI deps)
pip install ".[web]"
vcmix serve --profile core --host 0.0.0.0 --port 8000

# Full profile (with AI deps)
pip install ".[web,ai]"
vcmix serve --profile full --host 0.0.0.0 --port 8000

# Default is full (backward compatible)
vcmix serve
```
