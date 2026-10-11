# MemoPop connector: the image Railway runs at memopop.didi.sh.
#
#   docker build -t memopop-connector .
#   docker run --rm -p 8080:8080 -v memopop-data:/data \
#     -e MEMOPOP_STATIC_KEYS=test-firm=... -e MEMOPOP_PUBLIC_BASE_URL=http://localhost:8080 \
#     memopop-connector
#
# Serves src/connector/serve.py (the connector and /healthz), never the Tauri
# sidecar app. See docs/operator/deploy.md for every variable.
#
# Python 3.13 to match CI (.github/workflows/connector-tests.yml), where the
# suite runs. .dockerignore is an allowlist: io/, .env, logs, and output never
# enter the build context.

FROM python:3.13-slim-bookworm

ARG JJ_VERSION=0.46.0
ARG TARGETARCH

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH=/opt/venv/bin:$PATH \
    MEMO_IO_ROOT=/data/firms \
    PORT=8080

# System tools the memo needs:
#   pandoc                         markdown conversion
#   pango, harfbuzz, cairo, gdk-pixbuf, fonts   WeasyPrint (compile's PDF export)
#   poppler-utils                  pdftoppm / pdftotext (deck and dataroom pages)
#   tesseract-ocr                  OCR for scanned materials
#   ghostscript, imagemagick       image and PDF normalisation
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      ca-certificates curl \
      pandoc \
      libpango-1.0-0 libpangoft2-1.0-0 libpangocairo-1.0-0 libharfbuzz0b libharfbuzz-subset0 \
      libcairo2 libgdk-pixbuf-2.0-0 libffi8 shared-mime-info \
      fonts-dejavu-core fonts-liberation \
      poppler-utils \
      tesseract-ocr tesseract-ocr-eng \
      ghostscript \
      imagemagick \
 && rm -rf /var/lib/apt/lists/*

# jj keeps each firm's history; without it history is silently off.
RUN case "${TARGETARCH:-amd64}" in \
      amd64) JJ_ARCH=x86_64 ;; \
      arm64) JJ_ARCH=aarch64 ;; \
      *) echo "unsupported arch ${TARGETARCH}" >&2; exit 1 ;; \
    esac \
 && curl -fsSL "https://github.com/jj-vcs/jj/releases/download/v${JJ_VERSION}/jj-v${JJ_VERSION}-${JJ_ARCH}-unknown-linux-musl.tar.gz" \
      | tar -xz -C /usr/local/bin ./jj \
 && jj --version

COPY --from=ghcr.io/astral-sh/uv:0.6.14 /uv /usr/local/bin/uv

WORKDIR /app

# Dependencies first, from the lockfile, so code changes don't reinstall them.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project \
 && rm -rf /root/.cache

COPY src ./src
# compile renders through cli/export_branded.py (src/connector/compile/pipeline.py).
COPY cli ./cli
COPY templates ./templates
COPY scripts/health_check.py scripts/provision_firm.py scripts/docker-entrypoint.sh ./scripts/

RUN useradd --system --create-home --home-dir /home/memopop --uid 10001 memopop \
 && chmod +x scripts/docker-entrypoint.sh \
 && mkdir -p /data \
 && python -c "import src.connector.serve"

EXPOSE 8080
ENTRYPOINT ["/app/scripts/docker-entrypoint.sh"]
