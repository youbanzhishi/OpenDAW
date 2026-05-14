#!/usr/bin/env bash
# ============================================================================
# setup-rust.sh - 一键安装Rust开发环境 (OpenDAW云电脑版)
#
# 踩坑记录(2026-05-14)：
#   - 清华镜像/官方源/rsproxy 在云电脑全部不通
#   - USTC镜像是唯一稳定可用的国内源
#   - apt源 mirrors.ivolces.com DNS不通，必须换 mirrors.aliyun.com
#   - static.rust-lang.org 不可达，必须走镜像下载rustup-init
#   - 首次安装约需3-5分钟（取决于网速）
#
# 用法：bash scripts/setup-rust.sh [版本号]
#   默认版本：1.95.0
#
# 特性：
#   - 幂等：已安装且版本>=要求则跳过
#   - 自动换apt源（阿里云）
#   - 自动配置USTC cargo镜像
#   - 内存<=4G时自动限制CARGO_BUILD_JOBS=2
# ============================================================================
set -euo pipefail

HOME="${HOME:-$(eval echo ~)}"
RUST_VERSION="${1:-1.95.0}"

# ---------- 颜色 ----------
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'
info()  { echo -e "${BLUE}[setup-rust]${NC} $*"; }
ok()    { echo -e "${GREEN}[setup-rust]${NC} ✅ $*"; }
warn()  { echo -e "${YELLOW}[setup-rust]${NC} ⚠️  $*"; }
fail()  { echo -e "${RED}[setup-rust]${NC} ❌ $*"; exit 1; }

# ---------- 步骤0：换apt源（云电脑ivolces源DNS不通） ----------
fix_apt_source() {
    if ! grep -q "mirrors.aliyun.com" /etc/apt/sources.list 2>/dev/null; then
        if grep -q "mirrors.ivolces.com" /etc/apt/sources.list 2>/dev/null; then
            info "替换apt源: ivolces → aliyun..."
            cp /etc/apt/sources.list /etc/apt/sources.list.bak.$(date +%Y%m%d%H%M%S)
            sed -i 's|mirrors.ivolces.com|mirrors.aliyun.com|g' /etc/apt/sources.list
            apt-get update -qq 2>/dev/null || true
            ok "apt源已替换为阿里云"
        fi
    fi
}

# ---------- 版本比较 ----------
needs_rust_install() {
    if ! command -v rustc &>/dev/null; then return 0; fi
    local current_version
    current_version=$(rustc --version | grep -oP '\d+\.\d+\.\d+' | head -1)
    info "当前 Rust 版本: ${current_version}，要求: >= ${RUST_VERSION}"

    local IFS='.'
    read -ra CUR <<< "${current_version}"
    read -ra REQ <<< "${RUST_VERSION}"

    if (( CUR[0] > REQ[0] )); then return 1; fi
    if (( CUR[0] < REQ[0] )); then return 0; fi
    if (( CUR[1] > REQ[1] )); then return 1; fi
    if (( CUR[1] < REQ[1] )); then return 0; fi
    if (( CUR[2] >= REQ[2] )); then return 1; fi
    return 0
}

# ---------- 步骤1：系统依赖 ----------
info "步骤1: 检查系统依赖..."
fix_apt_source

MISSING_DEPS=()
for cmd in curl git gcc pkg-config; do
    command -v "${cmd}" &>/dev/null || MISSING_DEPS+=("${cmd}")
done

if [[ ${#MISSING_DEPS[@]} -gt 0 ]]; then
    info "安装缺失依赖: ${MISSING_DEPS[*]}"
    apt-get update -qq 2>/dev/null || true
    apt-get install -y --no-install-recommends \
        "${MISSING_DEPS[@]}" \
        build-essential pkg-config libssl-dev libasound2-dev \
        2>/dev/null || warn "部分依赖安装失败，尝试继续..."
else
    ok "系统依赖已满足"
fi

# ---------- 步骤2：安装Rust ----------
if needs_rust_install; then
    info "步骤2: 安装 Rust ${RUST_VERSION}..."

    # USTC镜像 — 唯一在云电脑环境稳定可用的国内源
    export RUSTUP_DIST_SERVER="https://mirrors.ustc.edu.cn/rust-static"
    export RUSTUP_UPDATE_ROOT="https://mirrors.ustc.edu.cn/rust-static/rustup"

    # 先下载rustup-init二进制（小文件，USTC镜像快）
    RUSTUP_INIT="/tmp/rustup-init-$$"
    info "下载 rustup-init (USTC镜像)..."
    curl -L --connect-timeout 30 --retry 3 \
        -o "${RUSTUP_INIT}" \
        "https://mirrors.ustc.edu.cn/rust-static/rustup/dist/x86_64-unknown-linux-gnu/rustup-init" \
        || fail "rustup-init 下载失败，检查网络"

    chmod +x "${RUSTUP_INIT}"

    # 如果已装了旧版rustup，先卸载
    if command -v rustup &>/dev/null; then
        info "检测到旧版rustup，先卸载..."
        rustup self uninstall -y 2>/dev/null || true
    fi

    info "执行安装 (toolchain=${RUST_VERSION})..."
    "${RUSTUP_INIT}" -y --default-toolchain "${RUST_VERSION}" --profile default
    rm -f "${RUSTUP_INIT}"

    # 加载环境
    # shellcheck source=/dev/null
    source "${HOME}/.cargo/env" 2>/dev/null || true

    if command -v rustc &>/dev/null; then
        ok "Rust 安装完成: $(rustc --version)"
    else
        fail "Rust 安装失败，请检查日志"
    fi
else
    ok "步骤2: Rust 版本满足 ($(rustc --version))，跳过安装"
fi

# ---------- 步骤3：配置cargo镜像 ----------
info "步骤3: 配置 cargo USTC镜像..."
CARGO_DIR="${HOME}/.cargo"
CONFIG_FILE="${CARGO_DIR}/config.toml"
mkdir -p "${CARGO_DIR}"

# 始终覆写为USTC sparse镜像（实测最稳定）
cat > "${CONFIG_FILE}" << 'MIRROREOF'
# Cargo 镜像配置（由 setup-rust.sh 生成）
# 踩坑：清华/rsproxy在云电脑不可用，USTC sparse是唯一稳定源

[source.crates-io]
replace-with = 'ustc'

[source.ustc]
registry = "sparse+https://mirrors.ustc.edu.cn/crates.io-index/"

[net]
retry = 10
offline = false
MIRROREOF

ok "cargo 镜像已配置: USTC sparse"

# ---------- 步骤4：内存限制 ----------
TOTAL_MEM_KB=$(grep MemTotal /proc/meminfo 2>/dev/null | awk '{print $2}' || echo "0")
TOTAL_MEM_MB=$((TOTAL_MEM_KB / 1024))

if [[ ${TOTAL_MEM_MB} -le 4096 ]]; then
    CARGO_JOBS=2
else
    CARGO_JOBS=$(nproc 2>/dev/null || echo 4)
fi

# 写入环境变量到 .bashrc（持久化）
BASHRC="${HOME}/.bashrc"
if ! grep -q "CARGO_BUILD_JOBS" "${BASHRC}" 2>/dev/null; then
    echo "" >> "${BASHRC}"
    echo "# Rust编译并行数（防OOM）" >> "${BASHRC}"
    echo "export CARGO_BUILD_JOBS=${CARGO_JOBS}" >> "${BASHRC}"
    info "已写入 CARGO_BUILD_JOBS=${CARGO_JOBS} 到 .bashrc"
fi

export CARGO_BUILD_JOBS="${CARGO_JOBS}"

# ---------- 步骤5：输出 ----------
echo ""
echo "============================================"
info "🔧 Rust 开发环境"
echo "============================================"
echo "Rust:          $(rustc --version 2>/dev/null || echo '未安装')"
echo "Cargo:         $(cargo --version 2>/dev/null || echo '未安装')"
echo "Toolchain:     $(rustup show active-toolchain 2>/dev/null || echo '未知')"
echo "Cargo镜像:     USTC sparse"
echo "BUILD_JOBS:    ${CARGO_BUILD_JOBS} (内存${TOTAL_MEM_MB}MB)"
echo "============================================"
echo ""
ok "环境安装完成！下一步: bash scripts/build.sh --release"
