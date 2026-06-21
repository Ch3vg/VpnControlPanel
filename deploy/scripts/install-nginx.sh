#!/usr/bin/env bash
set -euo pipefail

source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
require_root
load_env

bash "${SCRIPT_DIR}/render.sh"

install -m 644 "${OUTPUT_DIR}/nginx/vpn-panel.conf" "/etc/nginx/sites-available/vpn-panel.conf"
ln -sf /etc/nginx/sites-available/vpn-panel.conf /etc/nginx/sites-enabled/vpn-panel.conf

if nginx -t; then
  systemctl reload nginx
  log "Nginx config installed (run certbot if TLS certs are missing)"
else
  die "nginx -t failed — install TLS certs or adjust ${OUTPUT_DIR}/nginx/vpn-panel.conf"
fi
