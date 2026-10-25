# Wake.ai sandbox image — tools only; no secrets.
# Production: rebuild with --build-arg BASE_DIGEST=sha256:... after docker buildx imagetools inspect.
ARG BASE_IMAGE=python:3.12.7-slim-bookworm
FROM ${BASE_IMAGE}

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update && apt-get install -y --no-install-recommends \
      git ca-certificates curl \
    && rm -rf /var/lib/apt/lists/*

RUN useradd --uid 65532 --create-home --shell /usr/sbin/nologin wake \
 && mkdir -p /workspace /tmp \
 && chown -R wake:wake /workspace /tmp

RUN pip install --no-cache-dir \
      'pytest>=7.0' \
      'vulture>=2.0' \
      'ruff>=0.4'

# Optional: node + knip for JS repos
# RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
#  && apt-get install -y nodejs && npm install -g knip

WORKDIR /workspace
USER wake
CMD ["sleep", "infinity"]
