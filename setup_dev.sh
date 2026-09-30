#!/usr/bin/env bash

set -euo pipefail

COMPOSE_FILE="compose.yml"
APP_SERVICE="app"
ENV_FILE=".env"
EXAMPLE_ENV_FILE="example.env"
MAX_ATTEMPTS=60
SLEEP_SECONDS=2

if [ ! -f "${ENV_FILE}" ]; then
  echo "${ENV_FILE} not found. Copying ${EXAMPLE_ENV_FILE}..."
  cp "${EXAMPLE_ENV_FILE}" "${ENV_FILE}"
fi

echo "Starting the development stack..."
docker compose -f "${COMPOSE_FILE}" up -d --build

echo "Waiting for ${APP_SERVICE} to become healthy..."
attempt=1
while [ "${attempt}" -le "${MAX_ATTEMPTS}" ]; do
  status="$(docker compose -f "${COMPOSE_FILE}" ps --format json "${APP_SERVICE}")"

  if echo "${status}" | grep -q '"Health":"healthy"'; then
    break
  fi

  if [ "${attempt}" -eq "${MAX_ATTEMPTS}" ]; then
    echo "${APP_SERVICE} did not become healthy in time." >&2
    exit 1
  fi

  sleep "${SLEEP_SECONDS}"
  attempt=$((attempt + 1))
done

echo "Running tests..."
docker compose -f "${COMPOSE_FILE}" exec -T "${APP_SERVICE}" python manage.py test

read -r -p "Seed the database with demo data? [y/N]: " run_seeds
case "${run_seeds}" in
  y|Y|yes|YES)
    echo "Running seed_fixed_tables..."
    docker compose -f "${COMPOSE_FILE}" exec -T "${APP_SERVICE}" python manage.py seed_fixed_tables

    echo "Running seed_custom_bulk (requires SEED_USER_PASSWORD in ${ENV_FILE})..."
    docker compose -f "${COMPOSE_FILE}" exec -T "${APP_SERVICE}" python manage.py seed_custom_bulk

    echo "Running create_admin_user (requires DJANGO_SUPERUSER_* in ${ENV_FILE})..."
    docker compose -f "${COMPOSE_FILE}" exec -T "${APP_SERVICE}" python manage.py create_admin_user
    ;;
  *)
    echo "Skipping seeds."
    ;;
esac

echo "Development environment ready."
