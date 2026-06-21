#!/usr/bin/env bash
set -euo pipefail

source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
require_root
load_env

if ! sudo -u postgres psql -tAc "SELECT 1 FROM pg_roles WHERE rolname='${VCP_DB_USER}'" | grep -q 1; then
  sudo -u postgres psql -v ON_ERROR_STOP=1 -c \
    "CREATE USER ${VCP_DB_USER} WITH PASSWORD '${VCP_DB_PASSWORD}';"
  log "Created PostgreSQL user ${VCP_DB_USER}"
else
  sudo -u postgres psql -v ON_ERROR_STOP=1 -c \
    "ALTER USER ${VCP_DB_USER} WITH PASSWORD '${VCP_DB_PASSWORD}';"
  log "Updated password for ${VCP_DB_USER}"
fi

if ! sudo -u postgres psql -tAc "SELECT 1 FROM pg_database WHERE datname='${VCP_DB_NAME}'" | grep -q 1; then
  sudo -u postgres psql -v ON_ERROR_STOP=1 -c \
    "CREATE DATABASE ${VCP_DB_NAME} OWNER ${VCP_DB_USER};"
  log "Created database ${VCP_DB_NAME}"
fi

sudo -u postgres psql -v ON_ERROR_STOP=1 -c \
  "GRANT ALL PRIVILEGES ON DATABASE ${VCP_DB_NAME} TO ${VCP_DB_USER};"

log "PostgreSQL ready"
