# OpenDAW 部署指南

本指南涵盖 Docker 部署、二进制部署和桌面应用安装。

## Docker 部署

### 开发环境

```bash
docker run -d \
  --name opendaw \
  -p 3000:3000 \
  -p 3001:3001 \
  ghcr.io/youbanzhishi/opendaw/opendaw:latest
```

### Docker Compose

```bash
# 使用项目自带的 docker-compose.yml
docker compose up -d
```

### 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| OPENDAW_HOST | 0.0.0.0 | 监听地址 |
| OPENDAW_PORT | 3000 | API 端口 |
| OPENDAW_WS_PORT | 3001 | WebSocket 端口 |
| RUST_LOG | opendaw=info | 日志级别 |

---

## 非 Docker 部署（二进制直接部署）

### 方式一：下载预编译二进制

从 [GitHub Releases](https://github.com/youbanzhishi/OpenDAW/releases) 下载对应平台的二进制：

```bash
# Linux x86_64
curl -L https://github.com/youbanzhishi/OpenDAW/releases/latest/download/opendaw-linux-amd64.tar.gz | tar xz
chmod +x opendaw
sudo mv opendaw /usr/local/bin/

# macOS (Apple Silicon)
curl -L https://github.com/youbanzhishi/OpenDAW/releases/latest/download/opendaw-macos-arm64.tar.gz | tar xz
chmod +x opendaw
sudo mv opendaw /usr/local/bin/

# Windows
# 下载 opendaw-windows-amd64.exe.zip，解压后使用
```

#### 创建 systemd 服务（Linux）

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
sudo systemctl enable opendaw
sudo systemctl start opendaw
```

### 方式二：从源码编译（⚠️ 必须使用项目脚本）

> **强制要求：新团队/新机器接手本项目时，必须使用 `scripts/` 下的脚本部署，禁止手动安装。**
> 脚本包含完整的踩坑记录和环境适配，手动安装 = 重复踩坑 = 浪费时间。
> 没有脚本覆盖的场景，先补充脚本再部署。

```bash
# 1. 克隆仓库
git clone https://github.com/youbanzhishi/OpenDAW.git
cd OpenDAW

# 2. 一键安装Rust环境（含系统依赖+国内镜像配置+内存自适应）
bash scripts/setup-rust.sh [版本号]    # 默认1.95.0

# 3. 配置cargo镜像（默认USTC，国内唯一稳定源）
bash scripts/cargo-mirror.sh ustc

# 4. 编译
bash scripts/build.sh --release              # 全部构建
bash scripts/build.sh --release --bin opendaw      # 只构建CLI
bash scripts/build.sh --release --bin opendaw-api  # 只构建API服务

# 5. 启动服务
bash scripts/deploy-local.sh start    # 启动（端口8080）
bash scripts/deploy-local.sh status   # 查看状态
bash scripts/deploy-local.sh logs     # 查看日志
bash scripts/deploy-local.sh stop     # 停止
```

#### 脚本说明

| 脚本 | 用途 | 踩坑记录 |
|------|------|----------|
| `setup-rust.sh` | 安装Rust+系统依赖+镜像 | USTC唯一可用、ivolces源DNS不通、内存≤4G限2线程 |
| `cargo-mirror.sh` | 切换cargo镜像源 | 清华/rsproxy在云电脑不可用，USTC sparse唯一稳定 |
| `build.sh` | 编译构建 | bin名是opendaw不是opendaw-cli、/app/data挂载慢用/tmp |
| `deploy-local.sh` | 服务管理(start/stop/status/logs) | — |

#### 手动编译（不推荐，仅脚本不可用时）

```bash
# 安装 Rust（必须走USTC镜像，官方源国内不可达）
export RUSTUP_DIST_SERVER=https://mirrors.ustc.edu.cn/rust-static
export RUSTUP_UPDATE_ROOT=https://mirrors.ustc.edu.cn/rust-static/rustup
curl -L -o /tmp/rustup-init https://mirrors.ustc.edu.cn/rust-static/rustup/dist/x86_64-unknown-linux-gnu/rustup-init
chmod +x /tmp/rustup-init && /tmp/rustup-init -y --default-toolchain 1.95.0

# 编译
source ~/.cargo/env
cargo build --release --bin opendaw-api
```

#### 编译依赖（Linux）

```bash
sudo apt-get install build-essential pkg-config libssl-dev libasound2-dev
```

#### 编译依赖（macOS）

```bash
xcode-select --install
```

---

## 桌面应用安装

OpenDAW 提供基于 Tauri 的桌面应用，支持 macOS、Windows 和 Linux。

### 下载安装

从 [GitHub Releases](https://github.com/youbanzhishi/OpenDAW/releases) 下载对应平台安装包：

| 平台 | 文件 | 说明 |
|------|------|------|
| Linux | `OpenDAW_amd64.AppImage` | 免安装，chmod +x 后直接运行 |
| Linux | `OpenDAW_amd64.deb` | Debian/Ubuntu 包 |
| macOS | `OpenDAW_aarch64.dmg` | Apple Silicon |
| macOS | `OpenDAW_x64.dmg` | Intel Mac |
| Windows | `OpenDAW_x64-setup.exe` | NSIS 安装程序 |
| Windows | `OpenDAW_x64_en-US.msi` | MSI 安装包 |

### Linux 安装

```bash
# AppImage（推荐，免安装）
chmod +x OpenDAW_amd64.AppImage
./OpenDAW_amd64.AppImage

# DEB 包
sudo dpkg -i OpenDAW_amd64.deb
sudo apt-get install -f  # 安装依赖

# 依赖：webkit2gtk
sudo apt-get install libwebkit2gtk-4.1-0 libappindicator3-1
```

### macOS 安装

1. 打开 `.dmg` 文件
2. 将 OpenDAW 拖入 Applications 文件夹
3. 首次打开需右键 → 打开（绕过 Gatekeeper）

### Windows 安装

1. 运行 `OpenDAW_x64-setup.exe` 或 `OpenDAW_x64_en-US.msi`
2. 按安装向导完成安装

---

## 完整服务部署（API + WebSocket + 桌面客户端）

生产环境推荐部署 API + WebSocket 后端，桌面客户端连接远程服务：

```bash
# 1. 启动 API 服务
opendaw-api --host 0.0.0.0 --port 3000 &

# 2. 启动 WebSocket 服务
opendaw-ws --host 0.0.0.0 --port 3001 &

# 3. 或使用 opendaw CLI 一键启动
opendaw serve --host 0.0.0.0 --port 3000 --ws-port 3001
```

### Nginx 反向代理

```nginx
server {
    listen 80;
    server_name daw.example.com;

    # API
    location / {
        proxy_pass http://127.0.0.1:3000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    # WebSocket
    location /ws {
        proxy_pass http://127.0.0.1:3001;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
```
