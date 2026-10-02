# syntax=docker/dockerfile:1
#
# Build context: the repository root.
#   docker build -f deploy/docker/Dockerfile -t ai-arbiter:dev .
#
# Not built on the development machine (ADR-0025): CI builds and smoke-tests this image.

FROM python:3.12-slim AS build

COPY --from=ghcr.io/astral-sh/uv:0.12 /uv /usr/local/bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/opt/arbiter

WORKDIR /src

# Dependencies first: this layer is rebuilt only when the lock file changes.
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-dev --no-install-project --extra gateway --extra otel

COPY pyproject.toml uv.lock README.md LICENSE NOTICE ./
COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-editable --extra gateway --extra otel


FROM python:3.12-slim AS runtime

RUN groupadd --system --gid 10001 arbiter \
    && useradd --system --uid 10001 --gid arbiter --create-home --home-dir /home/arbiter arbiter

COPY --from=build /opt/arbiter /opt/arbiter

ENV PATH="/opt/arbiter/bin:${PATH}" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

USER 10001:10001
WORKDIR /home/arbiter
EXPOSE 8080

HEALTHCHECK --interval=10s --timeout=3s --start-period=20s --retries=6 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/healthz', timeout=2)"]

ENTRYPOINT ["arbiter"]
CMD ["serve", "--host", "0.0.0.0", "--port", "8080"]
