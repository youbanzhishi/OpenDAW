# OpenDAW 快速部署指南

## 方式一：Docker（推荐）

### 1. 拉最新代码
```bash
cd /root/songjian/docker-compose/opendaw/
git pull origin main
```

### 2. 启动
```bash
docker compose up -d --build
```

> ⚠️ 服务器1.8G内存，本地构建可能OOM。推荐方式三。

### 3. 访问
- Web UI: http://IP:8080/
- API: http://IP:8080/api/v1/

---

## 方式二：预构建镜像（推荐，省内存）

等CI构建完Docker镜像（~10分钟），直接pull：

```bash
# 创建部署目录
mkdir -p /root/songjian/docker-compose/opendaw && cd /root/songjian/docker-compose/opendaw

# 只需要docker-compose.yml + .env
# 从仓库拉或手动创建

docker pull ghcr.io/youbanzhishi/opendaw/opendaw:latest
docker compose up -d
```

---

## 方式三：二进制直接运行（最快）

从GitHub Release下载opendaw-api二进制：

```bash
# 下载
curl -L https://github.com/youbanzhishi/OpenDAW/releases/latest/download/opendaw-api-linux-amd64.tar.gz -o opendaw-api.tar.gz
tar xzf opendaw-api.tar.gz

# 前端文件
git clone --depth 1 https://github.com/youbanzhishi/OpenDAW.git /tmp/opendaw-ui
cp -r /tmp/opendaw-ui/desktop/src-tauri/frontend ./static

# 运行
export OPENDAW_WEB_DIR=./static
./opendaw-api
```

---

## 从旧vcmix迁移

旧容器（端口8000/Python后端）和新容器（端口8080/Rust后端）可以共存：

```bash
# 旧容器不动
docker ps | grep vcmix

# 新容器启动
docker compose up -d

# 验证新容器正常后，再停旧的
# docker stop vcmix-server
```

## 关键区别

| | 旧版 (vcmix) | 新版 (opendaw) |
|---|---|---|
| 后端 | Python FastAPI | Rust Axum |
| 端口 | 8000 | 8080 |
| Web UI | 内置 | 从./static/自动挂载 |
| 部署 | docker pull ghcr.io/youbanzhishi/vcmix | docker compose up -d |
