# Ensure top-level stream{} exists and includes stream.d (Debian/Ubuntu).
# Idempotent: safe to run multiple times.

set -euo pipefail

NGINX_CONF="${1:-/etc/nginx/nginx.conf}"
STREAM_DIR="${2:-/etc/nginx/stream.d}"

mkdir -p "${STREAM_DIR}"

# Load stream module if packaged as dynamic (Debian nginx).
if [[ -d /etc/nginx/modules-enabled ]]; then
  if [[ -f /usr/share/nginx/modules-available/mod-stream.conf ]]; then
    ln -sf /usr/share/nginx/modules-available/mod-stream.conf \
      /etc/nginx/modules-enabled/50-mod-stream.conf 2>/dev/null || true
  fi
  # Some distros ship the .so without a snippet — load explicitly if needed.
  if ! grep -q 'ngx_stream_module' /etc/nginx/modules-enabled/* 2>/dev/null; then
    if [[ -f /usr/lib/nginx/modules/ngx_stream_module.so ]]; then
      echo 'load_module modules/ngx_stream_module.so;' > /etc/nginx/modules-enabled/50-mod-stream.conf
    fi
  fi
fi

if grep -qE '^\s*stream\s*\{' "${NGINX_CONF}"; then
  if ! grep -q "${STREAM_DIR}" "${NGINX_CONF}"; then
    # Insert include inside existing stream block — fragile; prefer manual fix.
    echo "WARNING: stream{} exists in ${NGINX_CONF} but does not include ${STREAM_DIR}" >&2
    echo "Add: include ${STREAM_DIR}/*.conf; inside stream {}" >&2
  fi
  exit 0
fi

# Append stream block at end of main config (outside http{}).
cat >> "${NGINX_CONF}" <<EOF

# VPN Control Panel — shared TCP 443 (SNI mux)
stream {
    include ${STREAM_DIR}/*.conf;
}
EOF
