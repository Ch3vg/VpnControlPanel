#!/usr/bin/env bash
set -euo pipefail

source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

load_env

if [[ -z "${VCP_JWT_SECRET:-}" ]]; then
  update_env_var "VCP_JWT_SECRET" "$(openssl rand -hex 32)"
fi
if [[ -z "${VCP_ENCRYPTION_KEY:-}" ]]; then
  update_env_var "VCP_ENCRYPTION_KEY" "$(openssl rand -hex 32)"
fi
if [[ -z "${VCP_BROKER_API_KEY:-}" ]]; then
  update_env_var "VCP_BROKER_API_KEY" "$(openssl rand -hex 32)"
fi
if [[ -z "${VCP_DB_PASSWORD:-}" ]]; then
  update_env_var "VCP_DB_PASSWORD" "$(openssl rand -hex 16)"
fi

set -a
source "${ENV_FILE}"
set +a

if [[ "${VCP_JWT_SECRET}" == "${VCP_ENCRYPTION_KEY}" ]]; then
  die "VCP_JWT_SECRET must differ from VCP_ENCRYPTION_KEY"
fi

log "Secrets ready in ${ENV_FILE}"
