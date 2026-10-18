# One image for MatchLens. v1 runs one container, the delivery app, with the pipeline in-process
# (D23). Run: docker run -p 8000:8000 matchlens
FROM python:3.12.14-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/.venv

WORKDIR /app
RUN pip install --no-cache-dir uv==0.12.17

# Dependencies first, so a code change does not reinstall them.
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project

COPY apps ./apps
COPY matchlens ./matchlens
COPY web ./web
RUN uv sync --locked --no-dev

RUN useradd --uid 10001 --no-create-home matchlens
USER matchlens

EXPOSE 8000
CMD ["/app/.venv/bin/uvicorn", "apps.delivery:app", "--host", "0.0.0.0", "--port", "8000"]
