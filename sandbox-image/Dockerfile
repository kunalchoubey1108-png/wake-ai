# Wake.ai sandbox image — tools only; no secrets.
# Base pinned by digest from docker hub (python:3.12.7-slim-bookworm).
FROM python:3.12.7-slim-bookworm@sha256:60d9996b6a8a3689d36db740b49f4327be3be09a21122bd02fb8895abb38b50d

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
      'ruff>=0.4' \
      'flask>=3.0'

WORKDIR /workspace
USER wake
CMD ["sleep", "infinity"]
