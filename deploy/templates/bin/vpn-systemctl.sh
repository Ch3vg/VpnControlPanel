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
  wait-ready)
    if [[ -z "${SERVICE}" || "${SERVICE}" != "${PREFIX}"* ]]; then
      echo "Service name must start with ${PREFIX}" >&2
      exit 1
    fi
    TIMEOUT="${VPN_SERVICE_READY_TIMEOUT:-30}"
    SETTLE="${VPN_SERVICE_READY_SETTLE:-2}"
    LOG_PATTERN="${VPN_SERVICE_READY_LOG_PATTERN:-started|listening}"
    deadline=$((SECONDS + TIMEOUT))
    while (( SECONDS < deadline )); do
      if /bin/systemctl is-active --quiet "${SERVICE}"; then
        substate="$(/bin/systemctl show -p SubState --value "${SERVICE}")"
        if [[ "${substate}" == "running" ]]; then
          sleep "${SETTLE}"
          if /bin/systemctl is-active --quiet "${SERVICE}"; then
            substate="$(/bin/systemctl show -p SubState --value "${SERVICE}")"
            if [[ "${substate}" == "running" ]]; then
              if journalctl -u "${SERVICE}" -n 40 --no-pager | grep -qiE "${LOG_PATTERN}"; then
                exit 0
              fi
            fi
          fi
        fi
      fi
      sleep 1
    done
    echo "Service ${SERVICE} did not become ready within ${TIMEOUT}s" >&2
    journalctl -u "${SERVICE}" -n 20 --no-pager >&2 || true
    exit 1
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
