#!/usr/bin/env sh
set -eu

umask 077

DEFAULT_SECRET="local-development-audit-secret"
if [ -z "${TRADEPULSE_AUDIT_SECRET:-}" ]; then
  export TRADEPULSE_AUDIT_SECRET="$DEFAULT_SECRET"
  echo "[tradepulse] TRADEPULSE_AUDIT_SECRET not provided, using development default" >&2
fi

HTTP_HOST="${TRADEPULSE_HTTP_HOST:-0.0.0.0}"
HTTP_PORT="${TRADEPULSE_HTTP_PORT:-8000}"
CONFIG_VAULT_PATH="${TRADEPULSE_CONFIG_VAULT_PATH:-/tmp/tradepulse/config_vault.json}"
KILL_SWITCH_PATH="${TRADEPULSE_KILL_SWITCH_STORE_PATH:-/tmp/tradepulse/kill_switch_state.sqlite}"

mkdir -p "$(dirname "$CONFIG_VAULT_PATH")"
mkdir -p "$(dirname "$KILL_SWITCH_PATH")"

exec python -m uvicorn application.api.service:app \
  --host "$HTTP_HOST" \
  --port "$HTTP_PORT" \
  "$@"
