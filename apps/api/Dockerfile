# syntax=docker/dockerfile:1.7
#
# Multi-stage build:
#   * `builder` installs the api deps with uv (10-100x faster than pip,
#     produces a self-contained site-packages we can copy into the runtime
#     stage).
#   * `runtime` is a slim python image with only the installed packages
#     and the aipacken source — no build-essential, no pip cache, no uv.
#
# Result: the final image drops build-essential + apt caches from ~650 MB
# to ~300 MB and reinstall time on a pyproject.toml change goes from ~90 s
# to ~10 s locally (thanks to uv + the BuildKit cache mount).

FROM python:3.11-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PYTHON_DOWNLOADS=never

# build-essential + curl only for wheels that need a C toolchain
# (psycopg/binary ships wheels; argon2-cffi and pyarrow are wheel-only
# on x86_64 + arm64). Still install them to be safe — the stage is
# discarded.
RUN apt-get update && apt-get install -y --no-install-recommends \
      build-essential \
      curl \
    && rm -rf /var/lib/apt/lists/*

# Install uv. Pinned commit to keep the layer cached; bump when needed.
COPY --from=ghcr.io/astral-sh/uv:0.5.4 /uv /usr/local/bin/uv

WORKDIR /app

# Install deps first into a throwaway /opt/venv so the source-code layer
# below is independent of pyproject.toml changes (Docker layer cache
# behaviour — editing aipacken/*.py does not invalidate the install layer).
COPY apps/api/pyproject.toml ./pyproject.toml
RUN --mount=type=cache,target=/root/.cache/uv \
    uv venv /opt/venv \
    && uv pip install --python /opt/venv/bin/python --no-cache ".[dev]"

COPY apps/api/aipacken ./aipacken
COPY apps/api/alembic.ini ./alembic.ini
COPY apps/api/migrations ./migrations


FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:${PATH}"

# Runtime-only system deps: libgomp1 for xgboost/lightgbm (wheels at
# import time) and curl for ops debugging. No toolchain.
RUN apt-get update && apt-get install -y --no-install-recommends \
      libgomp1 \
      curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy the pre-built virtualenv + the api source from the builder.
COPY --from=builder /opt/venv /opt/venv
COPY --from=builder /app /app

EXPOSE 8000

CMD ["uvicorn", "aipacken.main:app", "--host", "0.0.0.0", "--port", "8000"]
