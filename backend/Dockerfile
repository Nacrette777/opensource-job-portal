# GradBridge / PeelJobs API (Django + gunicorn). Build context: backend/
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONUTF8=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/.venv

COPY --from=ghcr.io/astral-sh/uv:0.12.17 /uv /usr/local/bin/uv

WORKDIR /app

# Dependencies first, from the lock file, so code changes reuse this layer.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY . .

ENV PATH="/app/.venv/bin:$PATH" \
    DJANGO_SETTINGS_MODULE=jobsp.settings_gradbridge \
    GRADBRIDGE_PRIVATE_MEDIA_ROOT=/data/private_media \
    MEDIA_ROOT=/data/media

RUN useradd --system --uid 10001 --home /app app \
    && mkdir -p /data/private_media /data/media \
    && chown -R app:app /data \
    && chmod +x /app/docker-entrypoint.sh

USER app
VOLUME ["/data"]
EXPOSE 8000

ENTRYPOINT ["/app/docker-entrypoint.sh"]
# No control socket: it is for the gunicornc admin CLI and would need a
# writable $HOME.
CMD ["gunicorn", "jobsp.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3", "--timeout", "120", "--access-logfile", "-", "--no-control-socket"]
