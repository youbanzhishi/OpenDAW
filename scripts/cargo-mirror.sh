#!/usr/bin/env bash
# ============================================================================
# cargo-mirror.sh - 配置cargo使用国内镜像源
#
# 踩坑记录(2026-05-14)：
#   - 清华tuna: git索引模式在云电脑拉不动
#   - rsproxy: sparse模式config.json找不到，git模式index不完整
#   - USTC sparse: 唯一稳定可用，偶尔超时但retry=10能搞定
#
# 用法：bash scripts/cargo-mirror.sh [ustc|tuna|rsproxy|official]
#   默认: ustc
# ============================================================================
set -euo pipefail

HOME="${HOME:-$(eval echo ~)}"
MIRROR="${1:-ustc}"
CARGO_DIR="${HOME}/.cargo"
CONFIG_FILE="${CARGO_DIR}/config.toml"

mkdir -p "${CARGO_DIR}"

# 备份
if [[ -f "${CONFIG_FILE}" ]]; then
    BACKUP="${CONFIG_FILE}.bak.$(date +%Y%m%d%H%M%S)"
    cp "${CONFIG_FILE}" "${BACKUP}"
    echo "[cargo-mirror] 已备份原配置到 ${BACKUP}"
fi

case "${MIRROR}" in
    ustc)
        cat > "${CONFIG_FILE}" << 'EOF'
# Cargo 镜像配置（由 cargo-mirror.sh 生成）
# USTC sparse — 云电脑环境唯一稳定可用的国内源

[source.crates-io]
replace-with = 'ustc'

[source.ustc]
registry = "sparse+https://mirrors.ustc.edu.cn/crates.io-index/"

[net]
retry = 10
offline = false
EOF
        echo "[cargo-mirror] ✅ 已配置: USTC sparse（推荐）"
        ;;
    tuna)
        cat > "${CONFIG_FILE}" << 'EOF'
# Cargo 镜像配置（清华tuna）
# 注意：git索引模式较慢，建议用ustc

[source.crates-io]
replace-with = 'tuna'

[source.tuna]
registry = "https://mirrors.tuna.tsinghua.edu.cn/git/crates.io-index.git"

[net]
retry = 10
EOF
        echo "[cargo-mirror] ✅ 已配置: 清华tuna（git索引，较慢）"
        ;;
    rsproxy)
        cat > "${CONFIG_FILE}" << 'EOF'
# Cargo 镜像配置（rsproxy字节跳动）
# 注意：云电脑实测index不完整，部分crate找不到

[source.crates-io]
replace-with = 'rsproxy'

[source.rsproxy]
registry = "https://rsproxy.cn/crates.io-index"

[net]
retry = 10
EOF
        echo "[cargo-mirror] ✅ 已配置: rsproxy（可能不完整）"
        ;;
    official)
        cat > "${CONFIG_FILE}" << 'EOF'
# Cargo 官方源（无镜像）

[source.crates-io]

[net]
retry = 5
EOF
        echo "[cargo-mirror] ✅ 已配置: 官方源（国内慢）"
        ;;
    *)
        echo "用法: bash scripts/cargo-mirror.sh [ustc|tuna|rsproxy|official]"
        exit 1
        ;;
esac

echo "[cargo-mirror] 配置文件: ${CONFIG_FILE}"
