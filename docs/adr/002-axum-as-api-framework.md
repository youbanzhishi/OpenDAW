# ADR-002: Axum作为API框架

## 状态
已采纳

## 背景
OpenDAW需要REST API + WebSocket支持AI Agent远程控制和协作编辑。需要选择HTTP框架。

## 决策
选Axum作为opendaw-api的HTTP框架。

## 理由
- tower/tower-http生态兼容，中间件复用（CORS/tracing/静态文件）
- tokio原生支持，不引入额外运行时
- 类型安全路由，编译期检查路径参数
- 社区活跃，Rust HTTP框架事实标准
- 比Actix更轻量，比Warp更易读

## 后果
- opendaw-api 508行实现完整CRUD + Marketplace + Agent端点 + Web UI静态服务
- Axum 0.7 + tower-http 0.6组合稳定
- WebSocket协作通过opendaw-ws独立crate实现
