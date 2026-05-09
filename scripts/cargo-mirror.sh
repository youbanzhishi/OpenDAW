#!/usr/bin/env bash
# ============================================================================
# cargo-mirror.sh - 配置cargo使用国内镜像源 (OpenDAW适配版)
#
# 基于模板: 项目文档/open-dev-tools/scripts/cargo-mirror.sh
# 适配: 清华镜像(主) + rsproxy(备)
#
# 用法：./scripts/cargo-mirror.sh
#
# 特性：
#   - 幂等：已有配置不覆盖，仅在未配置时写入
#   - 同时配置清华镜像和 rsproxy 作为 fallback
# ============================================================================
set -euo pipefail

# 处理 HOME 可能为空的情况（沙箱环境）
HOME="${HOME:-$(eval echo ~)}"
CARGO_DIR="${HOME}/.cargo"
CONFIG_FILE="${CARGO_DIR}/config.toml"

# 确保 .cargo 目录存在
mkdir -p "${CARGO_DIR}"

# 检查是否已配置清华镜像
if [[ -f "${CONFIG_FILE}" ]] && grep -q "mirrors.tuna.tsinghua.edu.cn" "${CONFIG_FILE}"; then
    echo "[cargo-mirror] 检测到已有清华镜像配置，跳过写入"
    echo "[cargo-mirror] 当前配置："
    grep -A2 "replace-with" "${CONFIG_FILE}" || true
    exit 0
fi

# 备份已有配置
if [[ -f "${CONFIG_FILE}" ]]; then
    BACKUP="${CONFIG_FILE}.bak.$(date +%Y%m%d%H%M%S)"
    cp "${CONFIG_FILE}" "${BACKUP}"
    echo "[cargo-mirror] 已备份原配置到 ${BACKUP}"
fi

# 写入镜像配置
cat >> "${CONFIG_FILE}" << 'EOF'

# ============================================================
# Cargo 镜像配置（由 scripts/cargo-mirror.sh 生成）
# ============================================================

[source.tuna]
registry = "https://mirrors.tuna.tsinghua.edu.cn/git/crates.io-index.git"

[source.rsproxy]
registry = "https://rsproxy.cn/crates.io-index"

[source.crates-io]
replace-with = "tuna"

# 备用切换：如需临时切换到 rsproxy，修改上面 replace-with 值为 "rsproxy"

EOF

echo "[cargo-mirror] ✅ 镜像配置已写入 ${CONFIG_FILE}"
echo "[cargo-mirror] 主源：清华 tuna"
echo "[cargo-mirror] 备源：rsproxy（需手动切换 replace-with 值）"
echo "[cargo-mirror] 运行 'cat ${CONFIG_FILE}' 查看完整配置"
