#!/usr/bin/env bash
set -euo pipefail

source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

ACTION="${1:-status}"

case "${ACTION}" in
  restart)
    require_root
    load_env
    systemctl restart vpn-broker vpn-api
    worker_for_each restart
    log "Panel services restarted"
    ;;
  status)
    load_env
    systemctl status vpn-broker vpn-api --no-pager || true
    worker_for_each status --no-pager || true
    ;;
  logs)
    require_root
    load_env
    local_units=(vpn-broker vpn-api)
    count="$(worker_instances)"
    for ((i = 1; i <= count; i++)); do
      local_units+=("vpn-worker@${i}")
    done
    journalctl -u "${local_units[@]}" -f
    ;;
  *)
    die "Usage: panel-services.sh {restart|status|logs}"
    ;;
esac
