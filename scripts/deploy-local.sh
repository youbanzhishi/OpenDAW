#!/usr/bin/env bash
# ============================================================================
# deploy-local.sh - OpenDAW 本地二进制部署脚本（云电脑用）
#
# 适用场景：云电脑/本地开发机，直接运行二进制（不用Docker）
#
# 用法：
#   bash scripts/deploy-local.sh start    # 启动服务
#   bash scripts/deploy-local.sh stop     # 停止服务
#   bash scripts/deploy-local.sh status   # 查看状态
#   bash scripts/deploy-local.sh restart  # 重启服务
#   bash scripts/deploy-local.sh logs     # 查看日志
#
# 配置（环境变量覆盖）：
#   OPENDAW_PORT    监听端口（默认8080）
#   OPENDAW_DIR     项目目录（默认脚本所在目录的上级）
# ============================================================================
set -euo pipefail

# ---------- 配置 ----------
OPENDAW_PORT="${OPENDAW_PORT:-8080}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OPENDAW_DIR="${OPENDAW_DIR:-$(dirname "${SCRIPT_DIR}")}"
BIN_DIR="${OPENDAW_DIR}/target/release"
PID_FILE="/tmp/opendaw-api.pid"
LOG_FILE="/tmp/opendaw-api.log"

# ---------- 颜色 ----------
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'
info()  { echo -e "${BLUE}[deploy]${NC} $*"; }
ok()    { echo -e "${GREEN}[deploy]${NC} ✅ $*"; }
warn()  { echo -e "${YELLOW}[deploy]${NC} ⚠️  $*"; }
fail()  { echo -e "${RED}[deploy]${NC} ❌ $*"; exit 1; }

# ---------- 检查二进制 ----------
check_binary() {
    if [[ ! -x "${BIN_DIR}/opendaw-api" ]]; then
        fail "二进制不存在: ${BIN_DIR}/opendaw-api\n  请先构建: bash scripts/build.sh --release --bin opendaw-api"
    fi
}

# ---------- 获取PID ----------
get_pid() {
    if [[ -f "${PID_FILE}" ]]; then
        local pid
        pid=$(cat "${PID_FILE}" 2>/dev/null)
        if kill -0 "${pid}" 2>/dev/null; then
            echo "${pid}"
            return 0
        fi
    fi
    # fallback: 通过端口查找
    local pid
    pid=$(lsof -ti :${OPENDAW_PORT} 2>/dev/null | head -1 || true)
    if [[ -n "${pid}" ]]; then
        echo "${pid}"
        return 0
    fi
    return 1
}

# ---------- 启动 ----------
do_start() {
    check_binary

    local pid
    if pid=$(get_pid); then
        warn "服务已在运行 (PID: ${pid})"
        return 0
    fi

    info "启动 OpenDAW API (端口: ${OPENDAW_PORT})..."

    cd "${OPENDAW_DIR}"
    nohup "${BIN_DIR}/opendaw-api" > "${LOG_FILE}" 2>&1 &
    local new_pid=$!
    echo "${new_pid}" > "${PID_FILE}"

    # 等待启动
    sleep 2
    if kill -0 "${new_pid}" 2>/dev/null; then
        ok "服务已启动 (PID: ${new_pid})"
        echo "  Web UI:  http://localhost:${OPENDAW_PORT}/"
        echo "  API:     http://localhost:${OPENDAW_PORT}/api/v1/"
        echo "  日志:    tail -f ${LOG_FILE}"
    else
        fail "服务启动失败，查看日志: cat ${LOG_FILE}"
    fi
}

# ---------- 停止 ----------
do_stop() {
    local pid
    if pid=$(get_pid); then
        info "停止服务 (PID: ${pid})..."
        kill "${pid}" 2>/dev/null || true
        sleep 2
        if kill -0 "${pid}" 2>/dev/null; then
            warn "进程未响应，强制kill..."
            kill -9 "${pid}" 2>/dev/null || true
        fi
        rm -f "${PID_FILE}"
        ok "服务已停止"
    else
        warn "服务未在运行"
    fi
}

# ---------- 状态 ----------
do_status() {
    local pid
    if pid=$(get_pid); then
        ok "服务运行中 (PID: ${pid})"
        echo "  Web UI:  http://localhost:${OPENDAW_PORT}/"
        echo "  API:     http://localhost:${OPENDAW_PORT}/api/v1/"
        # 快速健康检查
        if curl -s -o /dev/null -w "%{http_code}" "http://localhost:${OPENDAW_PORT}/" 2>/dev/null | grep -q "200"; then
            ok "健康检查: OK"
        else
            warn "健康检查: 无响应（服务可能正在启动）"
        fi
    else
        warn "服务未运行"
        echo "  启动: bash scripts/deploy-local.sh start"
    fi
}

# ---------- 日志 ----------
do_logs() {
    if [[ -f "${LOG_FILE}" ]]; then
        tail -50 "${LOG_FILE}"
    else
        warn "日志文件不存在: ${LOG_FILE}"
    fi
}

# ---------- 主入口 ----------
case "${1:-}" in
    start)   do_start ;;
    stop)    do_stop ;;
    restart) do_stop; sleep 1; do_start ;;
    status)  do_status ;;
    logs)    do_logs ;;
    *)
        echo "用法: bash scripts/deploy-local.sh {start|stop|restart|status|logs}"
        echo ""
        echo "  start    启动OpenDAW API服务"
        echo "  stop     停止服务"
        echo "  restart  重启服务"
        echo "  status   查看服务状态"
        echo "  logs     查看最近日志"
        echo ""
        echo "环境变量:"
        echo "  OPENDAW_PORT=8080   监听端口"
        echo "  OPENDAW_DIR=.       项目目录"
        exit 1
        ;;
esac
