# Changelog

> CHANGELOG是项目交接协议，每条记录必须回答：做了什么、为什么做、下一步是什么
> 格式：### {模块}: {简述}
>        - **为什么**: {决策理由}
>        - **下一步**: {后续计划，没有写"无"}

## [1.0.3] - 2026-05-13

### Docker: 修复构建依赖缺失
- **为什么**: opendaw-api依赖audio-engine需要libasound2-dev，Dockerfile没装导致CI失败
- **下一步**: 确认Docker Build & Push CI全绿

### Docker: 构建opendaw-api + 打包Web UI
- **为什么**: v1.0.1只构建opendaw-cli（serve是占位代码），运维无法部署Web UI
- **下一步**: 验证docker run后浏览器能访问Web UI

### 前端: tauri-bridge.js API地址改为同源
- **为什么**: Docker部署时API和Web UI在同一端口，硬编码localhost:8000不通
- **下一步**: 无

## [1.0.2] - 2026-05-13

### 项目: 新增交接体系（ADR/PR模板/CONTRIBUTING）
- **为什么**: 新团队需要快速上手，决策需要记录，变更需要反哺
- **下一步**: 持续补充ADR

### 项目: architecture.md重写为Rust架构
- **为什么**: 旧文档还画Python架构图，误导新人
- **下一步**: 逐步更新getting-started等文档

## [1.0.1] - 2026-05-11

### Added
