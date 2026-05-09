#!/usr/bin/env bash
# ============================================================================
# setup-rust.sh - 一键安装Rust开发环境 (OpenDAW适配版)
#
# 基于模板: 项目文档/open-dev-tools/scripts/setup-rust.sh
# 适配: 加入国内镜像配置(清华+rsproxy)
#
# 用法：./scripts/setup-rust.sh
#
# 特性：
#   - 幂等：重复运行不出错，已安装则跳过
#   - Rust >= 1.82 则跳过安装
#   - 自动配置清华镜像加速下载
#   - 自动安装 just 命令运行器
#   - 适配 Debian / Ubuntu / 云电脑环境
# ============================================================================
set -euo pipefail

# 处理 HOME 可能为空的情况（沙箱环境）
HOME="${HOME:-$(eval echo ~)}"

# ---------- 颜色定义 ----------
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

info()  { echo -e "${BLUE}[setup-rust]${NC} $*"; }
ok()    { echo -e "${GREEN}[setup-rust]${NC} ✅ $*"; }
warn()  { echo -e "${YELLOW}[setup-rust]${NC} ⚠️  $*"; }
fail()  { echo -e "${RED}[setup-rust]${NC} ❌ $*"; exit 1; }

# ---------- 获取脚本所在目录 ----------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ---------- 检测当前 Rust 版本 ----------
MIN_RUST_VERSION="1.82.0"

needs_rust_install() {
    if ! command -v rustc &>/dev/null; then
        return 0  # 需要安装
    fi

    local current_version
    current_version=$(rustc --version | grep -oP '\d+\.\d+\.\d+' | head -1)

    info "当前 Rust 版本: ${current_version}"

    # 版本比较
    local IFS='.'
    read -ra CUR <<< "${current_version}"
    read -ra MIN <<< "${MIN_RUST_VERSION}"

    if (( CUR[0] > MIN[0] )); then return 1; fi
    if (( CUR[0] < MIN[0] )); then return 0; fi
    if (( CUR[1] > MIN[1] )); then return 1; fi
    if (( CUR[1] < MIN[1] )); then return 0; fi
    if (( CUR[2] >= MIN[2] )); then return 1; fi
    return 0
}

# ---------- 步骤1：安装系统依赖 ----------
info "检查系统依赖..."

MISSING_DEPS=()
for cmd in curl git gcc pkg-config; do
    if ! command -v "${cmd}" &>/dev/null; then
        MISSING_DEPS+=("${cmd}")
    fi
done

if [[ ${#MISSING_DEPS[@]} -gt 0 ]]; then
    info "安装缺失依赖: ${MISSING_DEPS[*]}"
    if command -v apt-get &>/dev/null; then
        sudo apt-get update -qq
        # OpenDAW额外依赖: libasound2-dev(Tauri音频) libwebkit2gtk-4.1-dev(Tauri Linux)
        sudo apt-get install -y -qq "${MISSING_DEPS[@]}" libssl-dev libpq-dev libasound2-dev libwebkit2gtk-4.1-dev libappindicator3-dev librsvg2-dev patchelf 2>/dev/null || true
    elif command -v yum &>/dev/null; then
        sudo yum install -y "${MISSING_DEPS[@]}" openssl-devel postgresql-devel alsa-lib-devel 2>/dev/null || true
    else
        warn "无法自动安装依赖，请手动安装: ${MISSING_DEPS[*]}"
    fi
else
    ok "系统依赖已满足"
fi

# ---------- 步骤2：安装/升级 Rust ----------
if needs_rust_install; then
    info "安装/升级 Rust (目标版本 >= ${MIN_RUST_VERSION})..."

    # 设置清华镜像加速（国内环境）
    export RUSTUP_DIST_SERVER="https://mirrors.tuna.tsinghua.edu.cn/rustup"
    export RUSTUP_UPDATE_ROOT="https://mirrors.tuna.tsinghua.edu.cn/rustup/rustup"

    if command -v rustup &>/dev/null; then
        info "rustup 已存在，尝试升级..."
        rustup update stable || warn "rustup update 失败，尝试重新安装"
    fi

    if needs_rust_install; then
        info "通过 rustup-init 安装 Rust..."
        curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs \
            | sh -s -- -y --default-toolchain stable

        # 加载环境变量
        # shellcheck source=/dev/null
        source "${HOME}/.cargo/env"
    fi

    # 验证安装
    if command -v rustc &>/dev/null; then
        ok "Rust 安装完成: $(rustc --version)"
    else
        # 尝试 source env
        source "${HOME}/.cargo/env" 2>/dev/null || true
        if command -v rustc &>/dev/null; then
            ok "Rust 安装完成: $(rustc --version)"
        else
            fail "Rust 安装失败，请检查日志"
        fi
    fi
else
    ok "Rust 版本满足要求 ($(rustc --version))，跳过安装"
fi

# ---------- 步骤3：配置 cargo 镜像（国内加速） ----------
info "配置 cargo 镜像源（清华+rsproxy）..."
CARGO_DIR="${HOME}/.cargo"
CONFIG_FILE="${CARGO_DIR}/config.toml"
mkdir -p "${CARGO_DIR}"

# 检查是否已配置清华镜像
if [[ -f "${CONFIG_FILE}" ]] && grep -q "mirrors.tuna.tsinghua.edu.cn" "${CONFIG_FILE}"; then
    ok "cargo 镜像已配置（清华）"
else
    # 备份已有配置
    if [[ -f "${CONFIG_FILE}" ]]; then
        BACKUP="${CONFIG_FILE}.bak.$(date +%Y%m%d%H%M%S)"
        cp "${CONFIG_FILE}" "${BACKUP}"
        info "已备份原配置到 ${BACKUP}"
    fi

    cat >> "${CONFIG_FILE}" << 'MIRROREOF'

# ============================================================
# Cargo 镜像配置（由 setup-rust.sh 生成）
# ============================================================

[source.tuna]
registry = "https://mirrors.tuna.tsinghua.edu.cn/git/crates.io-index.git"

[source.rsproxy]
registry = "https://rsproxy.cn/crates.io-index"

[source.crates-io]
replace-with = "tuna"

# 备用切换：如需临时切换到 rsproxy，修改上面 replace-with 值为 "rsproxy"
MIRROREOF

    ok "镜像配置已写入 ${CONFIG_FILE}（主源：清华 / 备源：rsproxy）"
fi

# ---------- 步骤4：安装 just ----------
if command -v just &>/dev/null; then
    ok "just 已安装: $(just --version)"
else
    info "安装 just 命令运行器..."
    # 限制并行数防 OOM（参考: rust-oom.md）
    CARGO_BUILD_JOBS=2 cargo install just || warn "just 安装失败，可稍后手动安装: cargo install just"
    if command -v just &>/dev/null; then
        ok "just 安装完成: $(just --version)"
    else
        warn "just 安装未成功，请确保 ~/.cargo/bin 在 PATH 中"
    fi
fi

# ---------- 步骤5：输出环境信息 ----------
echo ""
echo "============================================"
info "🔧 OpenDAW Rust 开发环境信息"
echo "============================================"
echo "Rust 版本:       $(rustc --version 2>/dev/null || echo '未安装')"
echo "Cargo 版本:      $(cargo --version 2>/dev/null || echo '未安装')"
echo "rustup 版本:     $(rustup --version 2>/dev/null || echo '未安装')"
echo "just 版本:       $(just --version 2>/dev/null || echo '未安装')"
echo "工具链:          $(rustup show active-toolchain 2>/dev/null || echo '未知')"
echo "Cargo 镜像:      $(grep 'replace-with' ~/.cargo/config.toml 2>/dev/null || echo '未配置')"
echo "CARGO_BUILD_JOBS: ${CARGO_BUILD_JOBS:-未设置（默认2）}"
echo "============================================"
echo ""
ok "环境设置完成！下一步：运行 just build"
