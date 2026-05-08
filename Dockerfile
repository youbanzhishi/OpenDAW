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
# ============================================================

FROM python:3.11-slim AS base

# ── 构建参数 ──────────────────────────────────────────────
# VCMIX_PROFILE: 启动模式，core=轻量 / full=完整
ARG VCMIX_PROFILE=core
# OpenDAW源码版本（tag或branch）
ARG OPENDAW_VERSION=v0.22.0
# AudioFX CLI插件版本（tag）
ARG AUDIOFX_RELEASE_VERSION=v2.7.0

# ── 换国内源 ──────────────────────────────────────────────
# apt换阿里云镜像（解决国内服务器apt慢/超时）
RUN sed -i 's|deb.debian.org|mirrors.aliyun.com|g' /etc/apt/sources.list.d/debian.sources 2>/dev/null; \
    sed -i 's|deb.debian.org|mirrors.aliyun.com|g' /etc/apt/sources.list 2>/dev/null; \
    true

# pip换阿里云镜像
RUN pip config set global.index-url https://mirrors.aliyun.com/pypi/simple/ && \
    pip config set global.trusted-host mirrors.aliyun.com

# ── 系统依赖 ──────────────────────────────────────────────
# libsndfile1: 读写WAV/FLAC音频文件
# ffmpeg: MP3/FLAC格式导出（必须有）
# git: 克隆源码用
# curl: 下载CLI二进制用
# 修复apt Post-Invoke脚本报错：删掉docker-clean配置
RUN rm -f /etc/apt/apt.conf.d/docker-clean && \
    apt-get update || apt-get update && \
    apt-get install -y --no-install-recommends \
    libsndfile1 \
    ffmpeg \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# ── 克隆VCMix源码 ────────────────────────────────────────
# 从GitHub自动拉取指定版本，无需手动clone
RUN git clone --depth 1 --branch ${OPENDAW_VERSION} \
    https://github.com/youbanzhishi/OpenDAW.git /tmp/opendaw && \
    cp /tmp/opendaw/pyproject.toml /tmp/opendaw/setup.py \
       /tmp/opendaw/README.md /tmp/opendaw/LICENSE ./ 2>/dev/null || true && \
    cp -r /tmp/opendaw/src ./src && \
    cp -r /tmp/opendaw/presets ./presets 2>/dev/null || mkdir -p presets && \
    rm -rf /tmp/opendaw

# ── 安装Python依赖 ────────────────────────────────────────
# core模式：只装web相关（FastAPI/uvicorn/numpy/scipy等）
RUN pip install --no-cache-dir ".[web]"

# full模式：额外装AI依赖（Demucs/PyTorch，约1.5GB）
RUN if [ "$VCMIX_PROFILE" = "full" ]; then \
        pip install --no-cache-dir ".[ai]"; \
    fi

# ── VC插件CLI二进制（23个，共~2.9MB）──────────────────────
# 从GitHub Release自动下载
RUN mkdir -p /app/plugins && \
    echo "下载CLI插件二进制 ${AUDIOFX_RELEASE_VERSION}..." && \
    ARCH=$(uname -m) && \
    curl -fsSL \
      "https://github.com/youbanzhishi/AudioFX/releases/download/${AUDIOFX_RELEASE_VERSION}/VocalChain-CLI-Linux-${ARCH}.tar.gz" \
      -o /tmp/vc-cli.tar.gz && \
    tar xzf /tmp/vc-cli.tar.gz -C /app/plugins/ && \
    rm /tmp/vc-cli.tar.gz && \
    chmod +x /app/plugins/VC-*/VC-*-CLI-Standalone 2>/dev/null || true

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
CMD ["sh", "-c", "vcmix serve --profile ${VCMIX_PROFILE:-core} --host 0.0.0.0 --port 8000"]
