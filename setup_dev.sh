#!/usr/bin/env bash

set -euo pipefail

COMPOSE_FILE="compose.yml"
APP_SERVICE="app"
ENV_FILE=".env"
EXAMPLE_ENV_FILE="example.env"
MAX_ATTEMPTS=60
SLEEP_SECONDS=2

if [ ! -f "${ENV_FILE}" ]; then
  echo "No se encontro ${ENV_FILE}. Copiando ${EXAMPLE_ENV_FILE}..."
  cp "${EXAMPLE_ENV_FILE}" "${ENV_FILE}"
fi

echo "Levantando entorno de desarrollo..."
docker compose -f "${COMPOSE_FILE}" up -d --build

echo "Esperando a que ${APP_SERVICE} este healthy..."
attempt=1
while [ "${attempt}" -le "${MAX_ATTEMPTS}" ]; do
  status="$(docker compose -f "${COMPOSE_FILE}" ps --format json "${APP_SERVICE}")"

  if echo "${status}" | grep -q '"Health":"healthy"'; then
    break
  fi

  if [ "${attempt}" -eq "${MAX_ATTEMPTS}" ]; then
    echo "El servicio ${APP_SERVICE} no alcanzo estado healthy a tiempo." >&2
    exit 1
  fi

  sleep "${SLEEP_SECONDS}"
  attempt=$((attempt + 1))
done

echo "Ejecutando tests..."
docker compose -f "${COMPOSE_FILE}" exec -T "${APP_SERVICE}" python manage.py test

read -r -p "¿Deseas ejecutar seeds de base de datos? [y/N]: " run_seeds
case "${run_seeds}" in
  y|Y|yes|YES|s|S|si|SI)
    echo "Ejecutando seed_demo_data..."
    docker compose -f "${COMPOSE_FILE}" exec -T "${APP_SERVICE}" python manage.py seed_demo_data

    echo "Ejecutando create_admin_user..."
    docker compose -f "${COMPOSE_FILE}" exec -T "${APP_SERVICE}" python manage.py create_admin_user
    ;;
  *)
    echo "Seeds omitidos."
    ;;
esac

echo "Entorno listo."
