#!/usr/bin/env bash
# ============================================================================
# build.sh - OpenDAW 构建脚本
#
# 基于模板: 项目文档/open-dev-tools/scripts/build.sh
# 适配: CARGO_BUILD_JOBS=2防OOM + 先check后build快速失败
#
# 用法：./scripts/build.sh [项目目录] [--release] [--package <crate名>]
#
# 参数：
#   [项目目录]        可选，默认当前目录(.)
#   --release         可选，执行release构建（默认debug）
#   --package <name>  可选，指定构建的crate名（workspace场景）
#
# 环境变量：
#   CARGO_BUILD_JOBS  并行编译job数（默认2，防OOM，参考rust-oom.md）
# ============================================================================
set -euo pipefail

# ---------- PATH修复 ----------
# 确保rustup安装的cargo优先于系统cargo
if [ -d "$HOME/.cargo/bin" ]; then
    export PATH="$HOME/.cargo/bin:$PATH"
fi

# ---------- TARGET_DIR优化 ----------
# hpvs_fs（/app/data/）极慢，将编译输出设到/tmp
if [[ "$(pwd)" == /app/data/* ]]; then
    export CARGO_TARGET_DIR="${CARGO_TARGET_DIR:-/tmp/cargo-target}"
fi

# ---------- 颜色定义 ----------
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

info()  { echo -e "${BLUE}[build]${NC} $*"; }
ok()    { echo -e "${GREEN}[build]${NC} ✅ $*"; }
warn()  { echo -e "${YELLOW}[build]${NC} ⚠️  $*"; }
fail()  { echo -e "${RED}[build]${NC} ❌ $*"; exit 1; }

# ---------- 解析参数 ----------
PROJECT_DIR="."
BUILD_MODE="debug"
PACKAGE_FLAG=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --release)
            BUILD_MODE="release"
            shift
            ;;
        --package)
            if [[ -z "${2:-}" ]]; then
                fail "--package 需要指定 crate 名称"
            fi
            PACKAGE_FLAG="--package $2"
            shift 2
            ;;
        -*)
            fail "未知参数: $1"
            ;;
        *)
            PROJECT_DIR="$1"
            shift
            ;;
    esac
done

# ---------- 校验项目目录 ----------
if [[ ! -d "${PROJECT_DIR}" ]]; then
    fail "项目目录不存在: ${PROJECT_DIR}"
fi

if [[ ! -f "${PROJECT_DIR}/Cargo.toml" ]]; then
    fail "未找到 Cargo.toml: ${PROJECT_DIR}/Cargo.toml"
fi

# ---------- 配置并行数 ----------
# 默认 CARGO_BUILD_JOBS=2 防 OOM（参考: 共享知识/踩坑记录/rust-oom.md）
# GitHub Actions(7G内存)不限，云电脑(4G)限2，ECS(1.8G)限1-2
export CARGO_BUILD_JOBS="${CARGO_BUILD_JOBS:-2}"
info "并行编译数: CARGO_BUILD_JOBS=${CARGO_BUILD_JOBS}"

# ---------- 构建标志 ----------
COMMON_FLAGS=""
if [[ "${BUILD_MODE}" == "release" ]]; then
    COMMON_FLAGS="--release"
fi

if [[ -n "${PACKAGE_FLAG}" ]]; then
    COMMON_FLAGS="${COMMON_FLAGS} ${PACKAGE_FLAG}"
fi

# ---------- 读取项目名 ----------
PROJECT_NAME=$(grep -m1 '^name' "${PROJECT_DIR}/Cargo.toml" | sed 's/name *= *"\(.*\)"/\1/' || basename "${PROJECT_DIR}")
info "项目: ${PROJECT_NAME}  模式: ${BUILD_MODE}  目录: ${PROJECT_DIR}"

# ---------- 步骤1：cargo check（快速验证编译，快速失败） ----------
info "步骤1: cargo check（快速编译验证）..."
CHECK_START=$(date +%s)

if (cd "${PROJECT_DIR}" && cargo check ${COMMON_FLAGS} --all-targets 2>&1); then
    CHECK_END=$(date +%s)
    CHECK_TIME=$((CHECK_END - CHECK_START))
    ok "check 通过 (${CHECK_TIME}s)"
else
    CHECK_END=$(date +%s)
    CHECK_TIME=$((CHECK_END - CHECK_START))
    fail "check 失败 (${CHECK_TIME}s)，请修复编译错误后重试"
fi

# ---------- 步骤2：cargo build（实际构建） ----------
info "步骤2: cargo build（实际编译）..."
BUILD_START=$(date +%s)

if (cd "${PROJECT_DIR}" && cargo build ${COMMON_FLAGS} 2>&1); then
    BUILD_END=$(date +%s)
    BUILD_TIME=$((BUILD_END - BUILD_START))
    ok "构建成功！(${BUILD_TIME}s)"
else
    BUILD_END=$(date +%s)
    BUILD_TIME=$((BUILD_END - BUILD_START))
    fail "构建失败 (${BUILD_TIME}s)"
fi

# ---------- 输出结果 ----------
TOTAL_TIME=$(($(date +%s) - CHECK_START))

# 查找构建产物
ARTIFACT_DIR="${PROJECT_DIR}/target/${BUILD_MODE}"
if [[ -f "${ARTIFACT_DIR}/${PROJECT_NAME}" ]]; then
    ARTIFACT_SIZE=$(du -h "${ARTIFACT_DIR}/${PROJECT_NAME}" | cut -f1)
    info "构建产物: ${ARTIFACT_DIR}/${PROJECT_NAME} (${ARTIFACT_SIZE})"
elif [[ -d "${ARTIFACT_DIR}" ]]; then
    EXECUTABLES=$(find "${ARTIFACT_DIR}" -maxdepth 1 -type f -executable 2>/dev/null || true)
    if [[ -n "${EXECUTABLES}" ]]; then
        for exe in ${EXECUTABLES}; do
            EXE_SIZE=$(du -h "${exe}" | cut -f1)
            info "构建产物: ${exe} (${EXE_SIZE})"
        done
    else
        info "构建产物目录: ${ARTIFACT_DIR}/"
    fi
fi

echo ""
echo "============================================"
info "📊 构建报告 - ${PROJECT_NAME}"
echo "============================================"
echo "构建模式:    ${BUILD_MODE}"
echo "check 耗时:  ${CHECK_TIME}s"
echo "build 耗时:  ${BUILD_TIME}s"
echo "总耗时:      ${TOTAL_TIME}s"
echo "并行数:      ${CARGO_BUILD_JOBS}"
echo "============================================"
