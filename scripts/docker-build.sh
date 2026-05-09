#!/usr/bin/env bash
# ============================================================================
# docker-build.sh - OpenDAW Docker构建脚本
#
# 基于模板: 项目文档/open-dev-tools/scripts/docker-build.sh
# 适配: GHCR推流(github.repository_owner) + 多Profile镜像(core/full)
#
# 用法：./scripts/docker-build.sh [项目目录] [镜像名]
#
# 参数：
#   [项目目录]  可选，默认当前目录(.)
#   [镜像名]    可选，默认用opendaw:时间戳
#
# 示例：
#   ./scripts/docker-build.sh
#   ./scripts/docker-build.sh . ghcr.io/youbanzhishi/vcmix:core-latest
# ============================================================================
set -euo pipefail

# ---------- 颜色定义 ----------
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

info()  { echo -e "${BLUE}[docker-build]${NC} $*"; }
ok()    { echo -e "${GREEN}[docker-build]${NC} ✅ $*"; }
warn()  { echo -e "${YELLOW}[docker-build]${NC} ⚠️  $*"; }
fail()  { echo -e "${RED}[docker-build]${NC} ❌ $*"; exit 1; }

# ---------- 检查Docker ----------
if ! command -v docker &>/dev/null; then
    fail "未安装 docker，请先安装"
fi

# ---------- 解析参数 ----------
PROJECT_DIR="${1:-.}"
IMAGE_NAME="${2:-}"

if [[ ! -d "${PROJECT_DIR}" ]]; then
    fail "项目目录不存在: ${PROJECT_DIR}"
fi

# ---------- 检测Dockerfile ----------
DOCKERFILE="${PROJECT_DIR}/Dockerfile"
if [[ ! -f "${DOCKERFILE}" ]]; then
    if [[ -f "${PROJECT_DIR}/docker/Dockerfile" ]]; then
        DOCKERFILE="${PROJECT_DIR}/docker/Dockerfile"
    else
        fail "未找到 Dockerfile (检查了 ${PROJECT_DIR}/Dockerfile 和 ${PROJECT_DIR}/docker/Dockerfile)"
    fi
fi

# ---------- 设置镜像名 ----------
if [[ -z "${IMAGE_NAME}" ]]; then
    PROJECT_NAME="vcmix"
    TIMESTAMP=$(date +%Y%m%d%H%M%S)
    IMAGE_NAME="${PROJECT_NAME}:${TIMESTAMP}"
    info "未指定镜像名，自动生成: ${IMAGE_NAME}"
fi

# ---------- 构建参数 ----------
BUILD_ARGS=(
    --file "${DOCKERFILE}"
    --tag "${IMAGE_NAME}"
    --build-arg "CARGO_MIRROR=https://mirrors.tuna.tsinghua.edu.cn/git/crates.io-index.git"
    --build-arg "RUSTUP_DIST_SERVER=https://mirrors.tuna.tsinghua.edu.cn/rustup"
    "${PROJECT_DIR}"
)

# ---------- 执行构建 ----------
info "开始 Docker 构建..."
info "Dockerfile: ${DOCKERFILE}"
info "镜像名:     ${IMAGE_NAME}"
info "上下文:     ${PROJECT_DIR}"

BUILD_START=$(date +%s)

if docker build "${BUILD_ARGS[@]}" 2>&1; then
    BUILD_END=$(date +%s)
    BUILD_TIME=$((BUILD_END - BUILD_START))
    ok "构建成功 (${BUILD_TIME}s)"
else
    BUILD_END=$(date +%s)
    BUILD_TIME=$((BUILD_END - BUILD_START))
    fail "构建失败 (${BUILD_TIME}s)"
fi

# ---------- Smoke test ----------
info "运行 Smoke test..."
if docker run --rm "${IMAGE_NAME}" python -c "from vcmix.web.app import create_app; print('Web UI OK')" 2>&1; then
    ok "Smoke test 通过"
else
    warn "Smoke test 失败，镜像可能不完整"
fi

# ---------- 输出镜像信息 ----------
IMAGE_ID=$(docker images -q "${IMAGE_NAME}" 2>/dev/null | head -1)
if [[ -n "${IMAGE_ID}" ]]; then
    IMAGE_SIZE=$(docker image inspect "${IMAGE_ID}" --format='{{.Size}}' 2>/dev/null || echo "unknown")
    if [[ "${IMAGE_SIZE}" != "unknown" ]]; then
        IMAGE_SIZE_HR=$(numfmt --to=iec-i --suffix=B "${IMAGE_SIZE}" 2>/dev/null || echo "${IMAGE_SIZE} bytes")
    fi

    echo ""
    echo "============================================"
    info "🐳 Docker 构建报告"
    echo "============================================"
    echo "镜像名:    ${IMAGE_NAME}"
    echo "镜像ID:    ${IMAGE_ID:0:12}"
    echo "镜像大小:  ${IMAGE_SIZE_HR:-${IMAGE_SIZE}}"
    echo "构建耗时:  ${BUILD_TIME}s"
    echo "============================================"
    echo ""
    info "推送到GHCR: docker tag ${IMAGE_NAME} ghcr.io/youbanzhishi/vcmix:core-latest && docker push ghcr.io/youbanzhishi/vcmix:core-latest"
else
    warn "无法获取镜像信息"
fi
