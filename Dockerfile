# ============================================================
# OpenDAW Dockerfile — API Server + Web UI
# ============================================================
# 构建: docker build -t opendaw:latest .
# 运行: docker run -p 8080:8080 opendaw:latest
# 浏览器访问: http://localhost:8080/ → Web UI
# API: http://localhost:8080/api/v1/
# ============================================================

# ── Stage 1: Build Rust API server ──
FROM rust:1.85-slim AS builder
WORKDIR /app
COPY . .
RUN cargo build --release -p opendaw-api

# ── Stage 2: Runtime ──
FROM debian:bookworm-slim
RUN apt-get update && apt-get install -y ca-certificates curl && rm -rf /var/lib/apt/lists/*

# API server binary
COPY --from=builder /app/target/release/opendaw-api /usr/local/bin/opendaw-api

# Web UI 静态文件（opendaw-api 自动查找 ./static/ 挂载 Web UI）
COPY --from=builder /app/desktop/src-tauri/frontend /app/static

WORKDIR /app

EXPOSE 8080

# opendaw-api 默认监听 0.0.0.0:8080
# 自动发现 ./static/ → 浏览器访问 / 即为 Web UI
# API 端点在 /api/v1/*
CMD ["opendaw-api"]
