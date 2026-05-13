# ADR-007: Tauri v2作为桌面框架

## 状态
已采纳

## 背景
需要跨平台桌面应用（Windows/macOS/Linux），替代Electron等方案。

## 决策
选Tauri v2作为桌面框架。

## 理由
- Rust后端原生集成，与opendaw-core零成本调用
- 包体小（~10MB vs Electron ~200MB）
- Web前端可复用opendaw-api的UI组件
- 安全沙箱，比Electron更安全
- 系统原生webview，性能好

## 后果
- 需要webkit2gtk等系统库（Linux构建复杂度高）
- Docker构建需额外处理前端静态文件
- 前端是原生HTML/JS/CSS，不用React/Vue（保持轻量）
- tauri-bridge.js做了Tauri/HTTP双模式适配
