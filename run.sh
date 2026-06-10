#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

# Activate venv if present
if [ -d ".venv" ]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi

: "${UPSTREAM_BASE_URL:=http://localhost:4000}"
: "${LISTEN_HOST:=127.0.0.1}"
: "${LISTEN_PORT:=8787}"

export UPSTREAM_BASE_URL LISTEN_HOST LISTEN_PORT

echo "litellm-prefill-proxy -> ${UPSTREAM_BASE_URL}  (listening on ${LISTEN_HOST}:${LISTEN_PORT})"
exec uvicorn app.main:app --host "${LISTEN_HOST}" --port "${LISTEN_PORT}"
