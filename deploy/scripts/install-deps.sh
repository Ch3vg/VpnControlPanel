#!/usr/bin/env bash
set -euo pipefail

source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
require_root

export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y \
  python3 \
  python3-venv \
  python3-pip \
  postgresql \
  nginx \
  git \
  openssl \
  gettext-base \
  rsync

log "System packages installed"
