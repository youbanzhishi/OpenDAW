# ============================================================
# justfile - OpenDAW 项目命令入口
#
# 基于模板: 项目文档/open-dev-tools/templates/rust/justfile
# 适配OpenDAW: 根目录构建 + Python + Docker + Tauri
#
# 使用方式:
#   运行: just <命令>
#   查看所有命令: just --list
#
# 安装 just: cargo install just
# ============================================================

# ---------- 项目变量 ----------
project-dir := "."
project-name := "opendaw"

# ---------- 默认命令 ----------
default:
    @just --list

# ---------- 环境设置 ----------
# 一键安装 Rust 开发环境（含镜像配置）
setup:
    ./scripts/setup-rust.sh

# ---------- 构建命令 ----------
# 开发构建（debug 模式）
build:
    ./scripts/build.sh {{project-dir}}

# 发布构建（release 模式，带优化）
build-release:
    ./scripts/build.sh {{project-dir}} --release

# ---------- 检查命令 ----------
# 快速编译检查（不生成二进制，速度最快）
check:
    cd {{project-dir}} && CARGO_BUILD_JOBS=2 cargo check --all-targets

# 代码格式化
fmt:
    cd {{project-dir}} && cargo fmt --all

# 格式化检查（CI用）
fmt-check:
    cd {{project-dir}} && cargo fmt --all -- --check

# 代码检查（clippy 严格模式，警告视为错误）
lint:
    cd {{project-dir}} && cargo clippy --all-targets -- -D warnings

# ---------- 测试命令 ----------
# 运行 Rust 测试
test:
    cd {{project-dir}} && CARGO_BUILD_JOBS=2 cargo test --all-targets

# 运行 Rust 测试（详细输出）
test-verbose:
    cd {{project-dir}} && CARGO_BUILD_JOBS=2 cargo test --all-targets -- --nocapture

# ---------- Python 命令 ----------
# 安装 Python 依赖
pip-install:
    pip install -e ".[dev]"

# 运行 Python 测试
py-test:
    pytest tests/ -x -q

# 启动 Python Web 服务
serve:
    vcmix serve --profile core --host 0.0.0.0 --port 8000

# ---------- Docker 命令 ----------
# Docker 构建（本地验证）
docker-build:
    ./scripts/docker-build.sh {{project-dir}} {{project-name}}

# Docker 构建（指定标签）
docker-tag TAG="latest":
    ./scripts/docker-build.sh {{project-dir}} {{project-name}}:{{TAG}}

# Docker 推送到 GHCR
docker-push:
    docker push ghcr.io/youbanzhishi/{{project-name}}:core-latest

# ---------- Tauri 命令 ----------
# Tauri 开发模式
tauri-dev:
    cd desktop && npm install && npm run tauri dev

# Tauri 构建
tauri-build:
    cd desktop && npm install && npm run tauri build

# ---------- 安全审计 ----------
# 检查依赖安全漏洞
audit:
    cd {{project-dir}} && cargo audit

# 检查依赖是否有过时版本
outdated:
    cd {{project-dir}} && cargo outdated 2>/dev/null || echo "请安装: cargo install cargo-outdated"

# ---------- 工具命令 ----------
# 更新依赖
update:
    cd {{project-dir}} && cargo update

# 查看依赖树
tree:
    cd {{project-dir}} && cargo tree --depth 1

# 清理构建缓存（释放磁盘空间）
clean:
    cd {{project-dir}} && cargo clean
    @echo "✅ 构建缓存已清理"

# 查看项目信息
info:
    @echo "项目:     {{project-name}}"
    @echo "目录:     {{project-dir}}"
    @echo "Rust版本: $$(rustc --version)"
    @echo "Cargo版本: $$(cargo --version)"
    @echo "镜像配置: $$(grep 'replace-with' ~/.cargo/config.toml 2>/dev/null || echo '未配置')"

# ---------- CI 全流程 ----------
# CI 完整流水线：检查 → 格式化 → lint → 测试 → release构建
ci: check fmt-check lint test build-release
    @echo "✅ CI 全流程通过"
