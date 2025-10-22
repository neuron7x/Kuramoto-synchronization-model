#!/usr/bin/env sh
set -eu

# Ensure the FastAPI service always has a valid audit signing secret. Prefer the
# explicit environment variables when provided. Otherwise synthesise an
# ephemeral secret so the container can start in smoke-test and local
# environments without leaking credentials in version control.
if [ "${TRADEPULSE_AUDIT_SECRET-}" != "" ]; then
  :
elif [ "${TRADEPULSE_AUDIT_SECRET_PATH-}" != "" ] && [ -f "$TRADEPULSE_AUDIT_SECRET_PATH" ]; then
  TRADEPULSE_AUDIT_SECRET="$(tr -d '\r\n' <"$TRADEPULSE_AUDIT_SECRET_PATH")"
  export TRADEPULSE_AUDIT_SECRET
else
  if command -v python >/dev/null 2>&1; then
    TRADEPULSE_AUDIT_SECRET="$(python - <<'PY'
import secrets
print(secrets.token_hex(32))
PY
)"
  else
    TRADEPULSE_AUDIT_SECRET="$(LC_ALL=C tr -dc 'a-zA-Z0-9' </dev/urandom | head -c64)"
  fi
  export TRADEPULSE_AUDIT_SECRET
  printf '%s\n' "[entrypoint] Generated ephemeral TRADEPULSE_AUDIT_SECRET" >&2
fi

exec "$@"
