# syntax=docker/dockerfile:1

FROM python:3.12-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

# Development image: adds test and lint tooling; compose.yml mounts the source.
FROM base AS dev
COPY requirements-dev.txt .
RUN pip install -r requirements-dev.txt
COPY . .
ENTRYPOINT ["/app/entrypoint.sh"]

# Production image (default target): runtime dependencies only, non-root user.
FROM base AS prod
ENV APP_MODE=production \
    PORT=8000
RUN groupadd --system app \
    && useradd --system --gid app --home-dir /app --no-create-home --shell /usr/sbin/nologin app
COPY --chown=app:app . .
# collectstatic needs no secrets, so run it with development settings at build time.
RUN APP_MODE=development python manage.py collectstatic --noinput \
    && chmod +x /app/entrypoint.sh
USER app
EXPOSE 8000
ENTRYPOINT ["/app/entrypoint.sh"]
