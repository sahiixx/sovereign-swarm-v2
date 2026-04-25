"""Sovereign Swarm v2.0 — Docker production image.

Multi-stage build with all optional deps installed.
"""
FROM python:3.11-slim

WORKDIR /app

# Install system deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    git ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Copy and install the wheel
COPY dist/sovereign_swarm-*.whl /tmp/
RUN pip install --no-cache-dir aiohttp pydantic prometheus-client "$(ls /tmp/sovereign_swarm-*.whl | tail -1)"

# Create data dir
RUN mkdir -p /app/data
ENV SWARM_DATA_DIR=/app/data

EXPOSE 18789 18793 18797

ENTRYPOINT ["python", "-m", "sovereign_swarm"]
