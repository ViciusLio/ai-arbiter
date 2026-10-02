# Image of the development container (ADR-0026). Not the project image: that one is
# deploy/docker/Dockerfile.

FROM mcr.microsoft.com/devcontainers/base:ubuntu-24.04

# uv, from the official image. It installs the Python versions in post-create.sh.
COPY --from=ghcr.io/astral-sh/uv:0.12 /uv /uvx /usr/local/bin/

# psql, to inspect the test database by hand.
RUN apt-get update \
    && apt-get install -y --no-install-recommends postgresql-client \
    && rm -rf /var/lib/apt/lists/*
