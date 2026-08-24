#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SRC="${ROOT}/panel/web/static/js/cm6-src"
OUT="${ROOT}/panel/web/static/js/lib/config-editor.bundle.js"

mkdir -p "$(dirname "${OUT}")"
cd "${SRC}"
npm install --no-fund --no-audit
npx esbuild entry.js --bundle --format=esm --outfile="${OUT}" --minify
echo "Built ${OUT}"
