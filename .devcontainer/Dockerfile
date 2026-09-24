# AG Profit Trading — Dev Container
# Python 3.12 + Node 22 + Bun (Linux). MT5 is Windows-only and skipped here.
FROM python:3.12-slim

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    git \
    unzip \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Node.js 22 LTS (via NodeSource)
RUN curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

# Bun (preferred package manager for web/)
RUN curl -fsSL https://bun.sh/install | bash
ENV PATH="/root/.bun/bin:${PATH}"

# Verify toolchain
RUN python --version && node --version && npm --version && bun --version

WORKDIR /workspace