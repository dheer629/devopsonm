# DevOpsSentinel Web -- browser edition container.
#
# Build from the repository root, because the FastAPI backend resolves the Bash
# engine one directory above the web project (see backend/app/config.py):
#
#   docker build -f devopssentinel-web/Dockerfile -t devopssentinel-web:1.0.0 .
#   docker run -d --name devopssentinel-web -p 8765:8765 devopssentinel-web:1.0.0
#   # http://127.0.0.1:8765
#
# The frontend is served from the prebuilt devopssentinel-web/frontend/dist.
# Run ./scripts/build.sh first if that directory is missing.
FROM python:3.12-slim-bookworm

ARG KUBECTL_VERSION=v1.31.4
ARG TARGETARCH=amd64

# The Bash engine remains the operational source of truth and needs these.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        bash jq openssl curl ca-certificates gawk util-linux procps coreutils \
        iproute2 less file diffutils libc-bin \
    && rm -rf /var/lib/apt/lists/*

# kubectl pinned and checksum-verified, mirroring the repository Dockerfile.
RUN curl -fsSLo /usr/local/bin/kubectl \
        "https://dl.k8s.io/release/${KUBECTL_VERSION}/bin/linux/${TARGETARCH}/kubectl" \
    && curl -fsSLo /tmp/kubectl.sha256 \
        "https://dl.k8s.io/release/${KUBECTL_VERSION}/bin/linux/${TARGETARCH}/kubectl.sha256" \
    && printf '%s  /usr/local/bin/kubectl\n' "$(cat /tmp/kubectl.sha256)" | sha256sum -c - \
    && chmod 755 /usr/local/bin/kubectl \
    && rm -f /tmp/kubectl.sha256

RUN useradd --create-home --uid 10001 --shell /usr/sbin/nologin dsweb

WORKDIR /app
# Dependencies first so application edits do not invalidate the pip layer.
COPY devopssentinel-web/backend/requirements.txt /app/devopssentinel-web/backend/requirements.txt
RUN pip install --no-cache-dir -r /app/devopssentinel-web/backend/requirements.txt

COPY --chmod=755 DevOps_K8s_Sentinel_FINAL_GP.sh /app/DevOps_K8s_Sentinel_FINAL_GP.sh
COPY devopssentinel-web/backend /app/devopssentinel-web/backend
COPY devopssentinel-web/frontend/dist /app/devopssentinel-web/frontend/dist

USER 10001:10001
ENV HOME=/home/dsweb \
    PYTHONPATH=/app/devopssentinel-web/backend \
    PYTHONUNBUFFERED=1 \
    DSWEB_HOST=0.0.0.0 \
    DSWEB_PORT=8765 \
    DSWEB_ENGINE_PATH=/app/DevOps_K8s_Sentinel_FINAL_GP.sh

EXPOSE 8765

HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=5 \
    CMD curl -fsS http://127.0.0.1:8765/api/v1/version || exit 1

WORKDIR /app/devopssentinel-web/backend
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8765"]
