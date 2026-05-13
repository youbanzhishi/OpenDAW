# OpenDAW Architecture

> 最后更新：2026-05-13 | 反映Rust架构（VCMix Python版已废弃）

## Overview

OpenDAW是AI原生、YAML驱动的跨平台数字音频工作站引擎。9个Rust crate组成workspace，CLI/API/桌面三入口共享核心引擎。

**核心原则**：Reaper有的我们要有，Reaper没有的我们也要有。

## Design Principles

1. **YAML-First** — 项目文件人类可读、Agent可写、git可diff
2. **Extension Registry** — 新功能=注册扩展，架构永远不改
3. **JSFX Compatible** — 兼容Reaper自定义效果器生态，其他DAW做不到
4. **AI Agent Friendly** — CLI零GUI + 结构化JSON + REST API + WebSocket

## Module Architecture

```
┌──────────────────────────────────────────────────────┐
│                  Desktop (Tauri v2)                   │
│   Web UI (HTML/JS/CSS) + Rust Backend + Audio Engine │
└────────────────────┬─────────────────────────────────┘
                     │
        ┌────────────┼────────────────┐
        │            │                │
┌───────▼──────┐ ┌──▼───────────┐ ┌──▼───────────┐
│  opendaw-api │ │  opendaw-cli │ │  opendaw-ws  │
│  (Axum)      │ │  (Clap)      │ │  (WebSocket) │
│  REST API    │ │  项目管理     │ │  协作编辑     │
│  Web UI服务  │ │  渲染/混音    │ │  实时同步     │
│  Agent端点   │ │  插件/REPL    │ │              │
└───────┬──────┘ └──────┬───────┘ └──────┬───────┘
        │               │                │
        └────────────┬──┘────────────────┘
                     │
┌────────────────────▼─────────────────────────────────┐
│               opendaw-core (核心)                      │
│  Project / Track / Plugin / Extension Registry        │
│  YAML解析 / Schema验证 / 渲染调度 / 混音管道          │
└──┬─────────────┬──────────────┬───────────────────────┘
   │             │              │
┌──▼──────────┐ ┌▼───────────┐ ┌▼─────────────────────┐
│audio-engine │ │plugin-host │ │opendaw-extension      │
│实时音频引擎  │ │插件加载/扫描│ │扩展接口定义            │
│零拷贝管道    │ │VC适配器     │ │Plugin API             │
│采样率/缓冲区 │ │            │ │Script Runtime         │
│             │ │            │ │Model Bus              │
│             │ │            │ │Hook System            │
└─────────────┘ └┬───────────┘ └───────────────────────┘
                 │
           ┌─────▼──────┐
           │ jsfx-engine │
           │ EEL2 VM     │
           │ JSFX兼容    │
           └─────────────┘
```

## Signal Flow

```
Track Audio → [Insert Chain] → Mixer → [Master Inserts] → Output File
```

Each track has an insert chain of plugins processed sequentially.
All tracks are mixed together, then the master insert chain is applied.

## Crate Overview

| Crate | 行数 | 职责 |
|-------|------|------|
| opendaw-core | ~16,800 | 核心层：Project/Track/Plugin/Extension Registry |
| plugin-host | ~5,500 | 插件加载、扫描、VC适配器 |
| jsfx-engine | ~5,100 | EEL2 VM，Reaper JSFX脚本兼容 |
| audio-engine | ~2,800 | 实时音频引擎，零拷贝管道 |
| opendaw-extension | ~2,500 | 扩展接口四柱定义 |
| opendaw-ws | ~1,800 | WebSocket协作服务 |
| opendaw-api | ~1,400 | REST API + Web UI静态服务 |
| opendaw-cli | ~800 | 命令行工具 |
| desktop | Tauri | 桌面应用 |

## Extension Registry 四柱

新功能=注册扩展，架构本身永远不需要改：

| 柱 | 职责 | 示例 |
|----|------|------|
| Plugin API | 效果器和乐器统一接口 | VC-EQ, VC-Compressor |
| Script Runtime | 脚本语言运行时 | JSFX/EEL2 |
| Model Bus | AI模型推理总线 | 自动混音、转录 |
| Hook System | 生命周期钩子 | 渲染前/后拦截 |

详见 [ADR-004](docs/adr/004-extension-registry.md)

## Key Decisions

| 决策 | ADR |
|------|-----|
| Python重写为Rust | [ADR-001](docs/adr/001-python-to-rust-rewrite.md) |
| Axum作为API框架 | [ADR-002](docs/adr/002-axum-as-api-framework.md) |
| CLI serve是占位代码 | [ADR-003](docs/adr/003-cli-serve-is-stub.md) |
| Extension Registry四柱 | [ADR-004](docs/adr/004-extension-registry.md) |
| JSFX兼容 | [ADR-005](docs/adr/005-jsfx-compatibility.md) |
| YAML优先项目格式 | [ADR-006](docs/adr/006-yaml-first-project-format.md) |
| Tauri v2桌面框架 | [ADR-007](docs/adr/007-tauri-v2-desktop.md) |

## Phase Roadmap

| Phase | Key Addition | Architecture Impact |
|-------|-------------|-------------------|
| 1-19 | VCMix Python版（已废弃） | — |
| 20 | Rust重写启动 | Workspace骨架 |
| 21 | JSFX EEL2 VM | jsfx-engine crate |
| 22-35 | 核心功能完整实现 | 9 crate全就位 |
| v1.0.0 | 首个Release | CI + Desktop + Release |
| v1.0.1 | 品牌升级VCMix→OpenDAW | 全局重命名 |
| v1.0.2 | Docker部署修复 | opendaw-api+Web UI |
| Next | 完整DAW | MIDI编辑器/自动化/评分 |

## Dependencies

| Crate | Purpose |
|-------|---------|
| axum + tower-http | REST API + 中间件 |
| tokio | 异步运行时 |
| serde + serde_json | 序列化 |
| clap | CLI框架 |
| tauri | 桌面应用 |
