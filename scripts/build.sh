#!/usr/bin/env bash
# ============================================================================
# build.sh - OpenDAW 构建脚本
#
# 踩坑记录(2026-05-14)：
#   - bin名是 opendaw 不是 opendaw-cli（Cargo.toml [[bin]] name = "opendaw"）
#   - /app/data/ 挂载点极慢，CARGO_TARGET_DIR 必须设到 /tmp
#   - 内存<=4G 必须 CARGO_BUILD_JOBS=2，否则OOM
#   - USTC镜像个别包会超时，已配retry=10
#
# 用法：
#   bash scripts/build.sh              # debug构建全部
#   bash scripts/build.sh --release    # release构建全部
#   bash scripts/build.sh --release --bin opendaw      # 只构建CLI
#   bash scripts/build.sh --release --bin opendaw-api  # 只构建API服务
#
# 产物：
#   target/{debug|release}/opendaw       — CLI工具
#   target/{debug|release}/opendaw-api   — HTTP API服务(含WebUI)
# ============================================================================
set -euo pipefail

# ---------- PATH修复 ----------
if [ -d "$HOME/.cargo/bin" ]; then
    export PATH="$HOME/.cargo/bin:$PATH"
fi
source "$HOME/.cargo/env" 2>/dev/null || true

# ---------- TARGET_DIR优化 ----------
# /app/data/ (hpvs_fs) 极慢，编译输出设到 /tmp
if [[ "$(pwd)" == /app/data/* ]]; then
    export CARGO_TARGET_DIR="${CARGO_TARGET_DIR:-/tmp/cargo-target}"
fi

# ---------- 颜色 ----------
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'
info()  { echo -e "${BLUE}[build]${NC} $*"; }
ok()    { echo -e "${GREEN}[build]${NC} ✅ $*"; }
warn()  { echo -e "${YELLOW}[build]${NC} ⚠️  $*"; }
fail()  { echo -e "${RED}[build]${NC} ❌ $*"; exit 1; }

# ---------- 解析参数 ----------
BUILD_MODE="debug"
BIN_FLAG=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --release) BUILD_MODE="release"; shift ;;
        --bin)
            [[ -z "${2:-}" ]] && fail "--bin 需要指定名称 (opendaw / opendaw-api)"
            BIN_FLAG="--bin $2"; shift 2 ;;
        *) fail "未知参数: $1" ;;
    esac
done

# ---------- 校验 ----------
[[ ! -f "Cargo.toml" ]] && fail "未找到 Cargo.toml，请在项目根目录运行"

# ---------- 并行数 ----------
export CARGO_BUILD_JOBS="${CARGO_BUILD_JOBS:-2}"
info "并行编译数: CARGO_BUILD_JOBS=${CARGO_BUILD_JOBS}"

# ---------- 构建标志 ----------
COMMON_FLAGS=""
[[ "${BUILD_MODE}" == "release" ]] && COMMON_FLAGS="--release"
[[ -n "${BIN_FLAG}" ]] && COMMON_FLAGS="${COMMON_FLAGS} ${BIN_FLAG}"

# ---------- 步骤1：cargo check（快速失败） ----------
info "步骤1: cargo check（快速编译验证）..."
CHECK_START=$(date +%s)

if cargo check ${COMMON_FLAGS} --all-targets 2>&1; then
    CHECK_TIME=$(( $(date +%s) - CHECK_START ))
    ok "check 通过 (${CHECK_TIME}s)"
else
    CHECK_TIME=$(( $(date +%s) - CHECK_START ))
    fail "check 失败 (${CHECK_TIME}s)，修复后重试"
fi

# ---------- 步骤2：cargo build ----------
info "步骤2: cargo build (${BUILD_MODE})..."
BUILD_START=$(date +%s)

if cargo build ${COMMON_FLAGS} 2>&1; then
    BUILD_TIME=$(( $(date +%s) - BUILD_START ))
    ok "构建成功！(${BUILD_TIME}s)"
else
    BUILD_TIME=$(( $(date +%s) - BUILD_START ))
    fail "构建失败 (${BUILD_TIME}s)"
fi

# ---------- 输出产物 ----------
TOTAL_TIME=$(( $(date +%s) - CHECK_START ))
ARTIFACT_DIR="target/${BUILD_MODE}"

echo ""
echo "============================================"
info "📊 构建报告"
echo "============================================"
echo "模式:      ${BUILD_MODE}"
echo "check:     ${CHECK_TIME}s"
echo "build:     ${BUILD_TIME}s"
echo "总耗时:    ${TOTAL_TIME}s"
echo "并行数:    ${CARGO_BUILD_JOBS}"
echo ""

# 列出可执行文件
EXECUTABLES=$(find "${ARTIFACT_DIR}" -maxdepth 1 -type f -executable 2>/dev/null || true)
if [[ -n "${EXECUTABLES}" ]]; then
    echo "产物："
    for exe in ${EXECUTABLES}; do
        EXE_SIZE=$(du -h "${exe}" | cut -f1)
        echo "  $(basename ${exe})  ${EXE_SIZE}"
    done
else
    warn "未找到可执行文件"
fi
echo "============================================"

# ---------- 提示下一步 ----------
if echo "${COMMON_FLAGS}" | grep -q "opendaw-api"; then
    echo ""
    ok "启动服务: cd $(pwd) && ./target/${BUILD_MODE}/opendaw-api"
    info "Web UI:  http://localhost:8080/"
    info "API:     http://localhost:8080/api/v1/"
fi
