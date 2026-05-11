# OpenDAW 项目索引

> 最后更新：2026-05-12

## 项目概览

AI-native 开源 DAW（数字音频工作站），Rust 核心引擎 + Tauri 桌面应用 + Python AI 后端。

## 仓库结构

```
OpenDAW/
├── audio-engine/          — Rust 音频引擎（实时混音/路由/效果链）
├── opendaw-core/          — 核心库（扩展注册中心/插件接口）
├── opendaw-extension/     — 扩展系统（插件/脚本/AI模型/Hook）
├── jsfx-engine/           — JSFX 脚本引擎（REAPER 兼容效果器）
├── plugin-host/           — VST3 插件宿主
├── crates/
│   ├── opendaw-api/       — FastAPI REST API
│   ├── opendaw-ws/        — WebSocket 实时通信
│   └── opendaw-cli/       — 命令行工具
├── desktop/
│   └── src-tauri/
│       ├── frontend/      — 前端 UI（专业 DAW 布局 + 触控支持）
│       │   ├── components/   — UI 组件模块
│       │   ├── canvas/       — Canvas 渲染模块
│       │   └── utils/        — 工具模块
│       └── src/           — Rust Tauri 后端
└── docs/                  — 设计文档
```

## 前端架构

- **框架**：Tauri 2.0 + 纯 HTML/CSS/JS（无 React/Vue）
- **布局**：专业 DAW 四面板（传输栏/轨道列表/编曲区/混音台+检视器）
- **渲染**：Canvas 绘制波形/时间线/MIDI 块
- **触控**：Pointer Events API 统一鼠标/触摸/笔输入
- **响应式**：CSS Grid + media queries（桌面/平板/手机三档）
- **主题**：CSS 自定义属性（dark/midnight）

## Tauri 命令

所有 Tauri 命令通过 `TauriBridge` 模块统一调用，自动降级到 HTTP API。

### 传输控制
- `audio_play` / `audio_stop` / `audio_pause` — 播放控制
- `audio_set_master_volume` — 主音量
- `audio_load_and_play` — 加载并播放

### 引擎控制
- `engine_start` / `engine_stop` / `engine_pause` — 引擎生命周期
- `engine_get_state` / `engine_get_position` — 状态查询
- `engine_set_track_volume` / `engine_toggle_track_mute` — 轨道控制

### 项目管理
- HTTP API: `/api/v1/projects` CRUD
- `render_project` — 渲染导出

## 关联角色

- 前端开发（P0）
- Rust/音频引擎开发（P0）
- AI Agent 开发（P1）

## 关联知识

- [DAW界面设计规范](../../角色/前端开发/knowledge/DAW界面设计规范.md)
- [前端踩坑经验](../../角色/前端开发/knowledge/OpenDAW前端踩坑.md)
