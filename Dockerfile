# Dockerfile — Sandbox environment for BugHunterAgent testing
# Isolated container with Python 3.11, git, and a minimal project skeleton.

FROM python:3.11-slim

LABEL project="vibe-bug-hunting-trainer-agent"
LABEL description="Isolated sandbox for bug injection training"

RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /sandbox

# Copy BugHunterAgent into the container
COPY pyproject.toml .
COPY bughunter/ ./bughunter/

# Install dependencies
RUN pip install --no-cache-dir -e .

# Create a minimal sandbox project for training
RUN mkdir -p /sandbox/project && \
    cd /sandbox/project && \
    git init && \
    git config user.email "dev@sandbox.local" && \
    git config user.name "Sandbox Developer"

# Set required environment variable
ENV BUGHUNTER_ENV=sandbox

CMD ["/bin/bash"]
