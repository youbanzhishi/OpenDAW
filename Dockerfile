# VCMix - AI-native open-source DAW
# Multi-stage Docker image with profile-based deployment
#
# Build targets:
#   core - Lightweight image (~450MB): no demucs/AI deps, for 1G servers
#   full - Complete image (~2GB): all AI features including demucs+torch
#
# Build examples:
#   docker build -t vcmix:core  --build-arg VCMIX_PROFILE=core .
#   docker build -t vcmix:full  --build-arg VCMIX_PROFILE=full .
#   docker build -t vcmix:latest .
#
# CLI plugins:
#   By default, CLI binaries are downloaded from GitHub Release.
#   To use local binaries, place them in docker/plugins/ before building.

FROM python:3.11-slim AS base

ARG VCMIX_PROFILE=core
ARG AUDIOFX_RELEASE_VERSION=v2.6.0

# System dependencies for audio processing + ffmpeg for MP3/FLAC export
RUN apt-get update && apt-get install -y --no-install-recommends \
    libsndfile1 \
    ffmpeg \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy project files
COPY pyproject.toml setup.py README.md LICENSE ./
COPY src/ src/
COPY presets/ presets/

# Core install: web UI only (no AI/demucs/torch)
RUN pip install --no-cache-dir ".[web]"

# Full install overlay: add AI dependencies when profile=full
RUN if [ "$VCMIX_PROFILE" = "full" ]; then \
        pip install --no-cache-dir ".[ai]"; \
    fi

# ── VC Plugin CLI binaries ──────────────────────────────────────────────
# 23 CLI binaries (~2.9MB total) needed for VCMix plugin processing.
# Strategy: try local docker/plugins/ first; if empty, download from GitHub Release.
RUN mkdir -p /app/plugins

COPY docker/plugins/ /app/plugins-local/

RUN if [ -f /app/plugins-local/VC-EQ/VC-EQ-CLI-Standalone ]; then \
        echo "Using local CLI binaries from docker/plugins/"; \
        cp -r /app/plugins-local/* /app/plugins/; \
    else \
        echo "Downloading CLI binaries from GitHub Release ${AUDIOFX_RELEASE_VERSION}..."; \
        ARCH=$(uname -m) && \
        curl -fsSL \
          "https://github.com/youbanzhishi/AudioFX/releases/download/${AUDIOFX_RELEASE_VERSION}/VocalChain-CLI-Linux-${ARCH}.tar.gz" \
          -o /tmp/vc-cli.tar.gz && \
        tar xzf /tmp/vc-cli.tar.gz -C /app/plugins/ && \
        rm /tmp/vc-cli.tar.gz; \
    fi && \
    rm -rf /app/plugins-local && \
    chmod +x /app/plugins/VC-*/VC-*-CLI-Standalone 2>/dev/null || true

# Create directories for projects and output
RUN mkdir -p /app/projects /app/output

# Environment: profile + plugin path
ENV VCMIX_PROFILE=${VCMIX_PROFILE}
ENV VC_AUDIOFX_DIR=/app/plugins

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health')" || exit 1

CMD ["sh", "-c", "vcmix serve --profile ${VCMIX_PROFILE:-core} --host 0.0.0.0 --port 8000"]
