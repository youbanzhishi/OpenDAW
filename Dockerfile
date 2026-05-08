# ============================================================
# VCMix Dockerfile — 按需加载的音频混音宿主
# ============================================================
# 构建模式：
#   core — 轻量版(~450MB镜像)，不含AI/Demucs，适合1G内存服务器
#   full — 完整版(~2GB镜像)，包含全部AI功能
#
# 构建命令：
#   docker build -t vcmix:core  --build-arg VCMIX_PROFILE=core .
#   docker build -t vcmix:full  --build-arg VCMIX_PROFILE=full .
#   docker build -t vcmix:latest .                          # 默认core
#
# 说明：
#   源码和CLI插件二进制都在构建时自动下载，你只需3个文件：
#   Dockerfile / docker-compose.yml / .env.example
#
# 国内加速：
#   apt/pip默认使用阿里云镜像，无需额外配置
# ============================================================

FROM python:3.11-slim AS base

# ── 构建参数 ──────────────────────────────────────────────
# VCMIX_PROFILE: 启动模式，core=轻量 / full=完整
ARG VCMIX_PROFILE=core
# OpenDAW源码版本（tag或branch）
ARG OPENDAW_VERSION=v0.22.2
# AudioFX CLI插件版本（tag）
ARG AUDIOFX_RELEASE_VERSION=v2.8.0

# ── 换国内源 ──────────────────────────────────────────────
# apt换阿里云镜像（兼容bookworm和trixie两种格式）
# bookworm用/etc/apt/sources.list，trixie用/etc/apt/sources.list.d/debian.sources
RUN set -eux; \
    if [ -f /etc/apt/sources.list.d/debian.sources ]; then \
      sed -i 's|deb.debian.org|mirrors.aliyun.com|g' /etc/apt/sources.list.d/debian.sources; \
    fi; \
    if [ -f /etc/apt/sources.list ]; then \
      sed -i 's|deb.debian.org|mirrors.aliyun.com|g' /etc/apt/sources.list; \
    fi; \
    true

# pip换阿里云镜像
RUN pip config set global.index-url https://mirrors.aliyun.com/pypi/simple/ && \
    pip config set global.trusted-host mirrors.aliyun.com

# ── 系统依赖 ──────────────────────────────────────────────
# libsndfile1: 读写WAV/FLAC音频文件（soundfile库依赖）
# ffmpeg: MP3/FLAC格式导出（必须有）
# curl: 下载源码和CLI二进制用
# 修复apt Post-Invoke脚本报错：删掉docker-clean配置（Debian trixie已知问题）
RUN set -eux; \
    rm -f /etc/apt/apt.conf.d/docker-clean; \
    apt-get update; \
    apt-get install -y --no-install-recommends \
      libsndfile1 \
      ffmpeg \
      curl \
    ; \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# ── 下载VCMix源码 ────────────────────────────────────────
# 使用GitHub archive下载（比git clone更快，单次HTTP请求）
# 如果下载失败，重试一次
RUN set -eux; \
    echo "下载OpenDAW源码 ${OPENDAW_VERSION}..."; \
    curl -fsSL --retry 3 --retry-delay 5 \
      "https://github.com/youbanzhishi/OpenDAW/archive/refs/tags/${OPENDAW_VERSION}.tar.gz" \
      -o /tmp/opendaw.tar.gz; \
    tar xzf /tmp/opendaw.tar.gz -C /tmp/; \
    SRC_DIR="/tmp/OpenDAW-${OPENDAW_VERSION#v}"; \
    if [ ! -d "$SRC_DIR" ]; then \
      # 某些tag格式可能不同，尝试找目录
      SRC_DIR=$(ls -d /tmp/OpenDAW-* | head -1); \
    fi; \
    cp "$SRC_DIR/pyproject.toml" "$SRC_DIR/setup.py" \
       "$SRC_DIR/README.md" "$SRC_DIR/LICENSE" ./ 2>/dev/null || true; \
    cp -r "$SRC_DIR/src" ./src; \
    cp -r "$SRC_DIR/presets" ./presets 2>/dev/null || mkdir -p presets; \
    rm -rf /tmp/opendaw.tar.gz "$SRC_DIR"

# ── 安装Python依赖 ────────────────────────────────────────
# core模式：只装web相关（FastAPI/uvicorn/numpy/scipy等）
RUN pip install --no-cache-dir ".[web]"

# full模式：额外装AI依赖（Demucs/PyTorch，约1.5GB）
RUN if [ "$VCMIX_PROFILE" = "full" ]; then \
        pip install --no-cache-dir ".[ai]"; \
    fi

# ── VC插件CLI二进制（24个，共~1.3MB）──────────────────────
# 从GitHub Release自动下载
# 如果下载失败（网络问题），构建会失败并给出明确提示
RUN set -eux; \
    mkdir -p /app/plugins; \
    ARCH=$(uname -m); \
    echo "下载CLI插件二进制 ${AUDIOFX_RELEASE_VERSION} (${ARCH})..."; \
    curl -fsSL --retry 3 --retry-delay 5 \
      "https://github.com/youbanzhishi/AudioFX/releases/download/${AUDIOFX_RELEASE_VERSION}/VocalChain-CLI-Linux-${ARCH}.tar.gz" \
      -o /tmp/vc-cli.tar.gz; \
    tar xzf /tmp/vc-cli.tar.gz -C /app/plugins/; \
    rm /tmp/vc-cli.tar.gz; \
    chmod +x /app/plugins/VC-*/VC-*-CLI-Standalone 2>/dev/null || true; \
    CLI_COUNT=$(find /app/plugins -name "*-CLI-Standalone" | wc -l); \
    echo "已安装 ${CLI_COUNT} 个CLI插件"

# ── 创建项目/输出目录 ────────────────────────────────────
RUN mkdir -p /app/projects /app/output

# ── 环境变量 ──────────────────────────────────────────────
# VCMIX_PROFILE: 运行模式，Docker启动时读取
# VC_AUDIOFX_DIR: 插件CLI搜索路径，容器内固定为/app/plugins
ENV VCMIX_PROFILE=${VCMIX_PROFILE}
ENV VC_AUDIOFX_DIR=/app/plugins

EXPOSE 8000

# ── 健康检查 ──────────────────────────────────────────────
# 每30秒请求/api/health，连续3次失败才判定不健康
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health')" || exit 1

# ── 启动命令 ──────────────────────────────────────────────
# 根据VCMIX_PROFILE环境变量选择core/full模式
# ── Pre-flight check: verify web dependencies ────────────────────────
RUN python -c "from vcmix.web.app import create_app; print('Web UI OK')" \
    || (echo "ERROR: Web UI dependencies not installed!" && exit 1)

CMD ["sh", "-c", "vcmix serve --profile ${VCMIX_PROFILE:-core} --host 0.0.0.0 --port 8000"]
