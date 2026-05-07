# VCMix — AI-native open-source DAW
# Multi-stage Docker image for one-click deployment

FROM python:3.11-slim AS base

# System dependencies for audio processing
RUN apt-get update && apt-get install -y --no-install-recommends \
    libsndfile1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy project files
COPY pyproject.toml setup.py README.md LICENSE ./
COPY src/ src/
COPY presets/ presets/

# Install VCMix with web UI support
RUN pip install --no-cache-dir ".[web]"

# Create directories for projects and output
RUN mkdir -p /app/projects /app/output

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/plugins')" || exit 1

CMD ["vcmix", "serve", "--host", "0.0.0.0", "--port", "8000"]
