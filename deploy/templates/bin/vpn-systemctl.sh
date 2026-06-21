#!/usr/bin/env bash
# Restricted systemctl wrapper for vpn-worker (per-config VPN units only).
set -euo pipefail

ACTION="${1:?action required}"
SERVICE="${2:-}"
PREFIX="${VPN_SERVICE_PREFIX:-vpn-}"

case "${ACTION}" in
  daemon-reload) ;;
  write-unit)
    if [[ -z "${SERVICE}" || "${SERVICE}" != "${PREFIX}"* ]]; then
      echo "Service name must start with ${PREFIX}" >&2
      exit 1
    fi
    UNIT_PATH="/etc/systemd/system/${SERVICE}.service"
    TMP="$(mktemp)"
    trap 'rm -f "${TMP}"' EXIT
    cat > "${TMP}"
    install -m 644 "${TMP}" "${UNIT_PATH}"
    exit 0
    ;;
  remove-unit)
    if [[ -z "${SERVICE}" || "${SERVICE}" != "${PREFIX}"* ]]; then
      echo "Service name must start with ${PREFIX}" >&2
      exit 1
    fi
    UNIT_PATH="/etc/systemd/system/${SERVICE}.service"
    /bin/systemctl stop "${SERVICE}" 2>/dev/null || true
    /bin/systemctl disable "${SERVICE}" 2>/dev/null || true
    rm -f "${UNIT_PATH}"
    /bin/systemctl daemon-reload
    exit 0
    ;;
  enable|disable|restart|stop|start)
    if [[ -z "${SERVICE}" || "${SERVICE}" != "${PREFIX}"* ]]; then
      echo "Service name must start with ${PREFIX}" >&2
      exit 1
    fi
    ;;
  *)
    echo "Unsupported action: ${ACTION}" >&2
    exit 1
    ;;
esac

if [[ "${ACTION}" == "daemon-reload" ]]; then
  exec /bin/systemctl daemon-reload
fi

exec /bin/systemctl "${ACTION}" "${SERVICE}"
