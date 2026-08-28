#!/usr/bin/env bash
# Grant vpn-worker / vpn-panel read access to Let's Encrypt material used by
# profile tls_cert_file / tls_key_file (and keep access after certbot renew).
set -euo pipefail

source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
require_root
load_env

SSL_GROUP="${VCP_SSL_CERT_GROUP:-ssl-cert}"
LE_ROOT="${VCP_LETSENCRYPT_DIR:-/etc/letsencrypt}"
HOOK_DIR="${LE_ROOT}/renewal-hooks/deploy"
INSTALLED_BIN="/usr/local/bin/vpn-le-perms"

ensure_ssl_group() {
  if ! getent group "${SSL_GROUP}" >/dev/null; then
    groupadd --system "${SSL_GROUP}"
    log "Created group ${SSL_GROUP}"
  fi
}

add_users_to_ssl_group() {
  local user
  for user in "${VCP_WORKER_USER}" "${VCP_PANEL_USER}"; do
    if id "${user}" &>/dev/null; then
      usermod -aG "${SSL_GROUP}" "${user}"
      log "Added ${user} to group ${SSL_GROUP}"
    fi
  done
}

# Standalone helper for certbot renew hooks (no deploy/.env required).
install_vpn_le_perms_bin() {
  cat >"${INSTALLED_BIN}" <<EOF
#!/usr/bin/env bash
# Installed by VpnControlPanel — re-apply LE ACL after certbot renew.
set -euo pipefail
SSL_GROUP="${SSL_GROUP}"
LE_ROOT="${LE_ROOT}"
if [[ ! -d "\${LE_ROOT}" ]]; then
  exit 0
fi
if ! getent group "\${SSL_GROUP}" >/dev/null; then
  groupadd --system "\${SSL_GROUP}"
fi
for user in ${VCP_WORKER_USER} ${VCP_PANEL_USER}; do
  if id "\${user}" &>/dev/null; then
    usermod -aG "\${SSL_GROUP}" "\${user}" 2>/dev/null || true
  fi
done
chmod 755 "\${LE_ROOT}" 2>/dev/null || true
for sub in live archive; do
  [[ -d "\${LE_ROOT}/\${sub}" ]] || continue
  chgrp -R "\${SSL_GROUP}" "\${LE_ROOT}/\${sub}"
  chmod 750 "\${LE_ROOT}/\${sub}"
  find "\${LE_ROOT}/\${sub}" -type d -exec chmod 750 {} \\;
  find "\${LE_ROOT}/\${sub}" -type f -exec chmod 640 {} \\;
  # Public leaf certs may stay world-readable; keys stay group-readable only.
  find "\${LE_ROOT}/\${sub}" -type f \\( -name 'fullchain*.pem' -o -name 'cert*.pem' -o -name 'chain*.pem' \\) \\
    -exec chmod 644 {} \\; 2>/dev/null || true
  find "\${LE_ROOT}/\${sub}" -type f -name 'privkey*.pem' -exec chmod 640 {} \\; 2>/dev/null || true
done
EOF
  chmod 755 "${INSTALLED_BIN}"
  log "Installed ${INSTALLED_BIN}"
}

install_certbot_hook() {
  if [[ ! -d "${LE_ROOT}" ]]; then
    return 0
  fi
  mkdir -p "${HOOK_DIR}"
  cat >"${HOOK_DIR}/vpn-panel-le-perms.sh" <<EOF
#!/usr/bin/env bash
# VpnControlPanel: keep LE readable by vpn-worker after renew.
exec ${INSTALLED_BIN}
EOF
  chmod 755 "${HOOK_DIR}/vpn-panel-le-perms.sh"
  log "Installed certbot deploy hook ${HOOK_DIR}/vpn-panel-le-perms.sh"
}

fix_letsencrypt_tree() {
  if [[ ! -d "${LE_ROOT}" ]]; then
    log "No ${LE_ROOT} yet — skip LE ACL (will apply on first certbot / make fix-le-perms)"
    return 0
  fi
  bash "${INSTALLED_BIN}"
  log "Let's Encrypt ACL applied under ${LE_ROOT} (group ${SSL_GROUP})"
}

ensure_ssl_group
add_users_to_ssl_group
install_vpn_le_perms_bin
install_certbot_hook
fix_letsencrypt_tree

log "LE permissions ready (restart vpn-worker@* if group membership just changed)"
