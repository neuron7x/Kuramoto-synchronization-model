#!/usr/bin/env bash
# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
# Resilient data synchronization helper that demonstrates robust scripting practices.
#
# Features implemented:
#   * Idempotency using lock files, content hashing, and execution markers.
#   * Structured JSON logging to stdout/stderr.
#   * Retries with exponential backoff and jitter for network operations.
#   * Timeouts and a simple circuit breaker to protect remote resources.
#   * Environment validation for required external tools and their versions.
#   * Safe handling of temporary files via mktemp + trap.

set -euo pipefail

SCRIPT_NAME="$(basename "$0")"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEFAULT_SOURCE_URL="file://${REPO_ROOT}/sample.csv"
DEFAULT_DESTINATION="${REPO_ROOT}/reports/resilient-sync/sample.csv"
DEFAULT_LOCK_DIR="${REPO_ROOT}/reports/resilient-sync/.locks"

MAX_RETRIES=5
INITIAL_BACKOFF=1
MAX_BACKOFF=16
REQUEST_TIMEOUT=30
CIRCUIT_BREAKER_TTL=300
RUN_ID="$(python3 -c 'import uuid; print(uuid.uuid4().hex)' 2>/dev/null || uuidgen 2>/dev/null || date +%s)"

# shellcheck disable=SC2034  # referenced inside python logging helper
SCRIPT_VERSION="1.0.0"

require_command() {
  local cmd="$1"
  if ! command -v "$cmd" >/dev/null 2>&1; then
    log_json "error" "missing required command" "stderr" "command=${cmd}"
    exit 42
  fi
}

log_json() {
  local level="$1"
  shift
  local message="$1"
  shift
  local stream="${1:-stdout}"
  shift
  local ts
  ts="$(date -u +"%Y-%m-%dT%H:%M:%S.%6NZ")"
  python3 - "$level" "$message" "$stream" "$ts" "$SCRIPT_NAME" "$RUN_ID" "$SCRIPT_VERSION" "$@" <<'PY'
import json
import os
import sys

level, message, stream, ts, script_name, run_id, script_version, *kv_pairs = sys.argv[1:]
payload = {
    "ts": ts,
    "level": level,
    "message": message,
    "script": script_name,
    "run_id": run_id,
    "pid": os.getpid(),
    "version": script_version,
}
for pair in kv_pairs:
    if "=" not in pair:
        continue
    key, value = pair.split("=", 1)
    payload[key] = value
output = sys.stdout if stream == "stdout" else sys.stderr
json.dump(payload, output, ensure_ascii=False)
output.write("\n")
PY
}

usage() {
  cat <<USAGE
Usage: ${SCRIPT_NAME} [--source-url URL] [--destination PATH] [--lock-dir DIR]
                     [--max-retries N] [--timeout SEC] [--circuit-ttl SEC]
                     [--help]

Synchronise data from a remote URL into the repository with resilience features.
Defaults pull from the sample.csv shipped with the repository to remain offline-friendly.
USAGE
}

SOURCE_URL="$DEFAULT_SOURCE_URL"
DESTINATION="$DEFAULT_DESTINATION"
LOCK_DIR="$DEFAULT_LOCK_DIR"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --source-url)
      SOURCE_URL="$2"
      shift 2
      ;;
    --destination)
      DESTINATION="$2"
      shift 2
      ;;
    --lock-dir)
      LOCK_DIR="$2"
      shift 2
      ;;
    --max-retries)
      MAX_RETRIES="$2"
      shift 2
      ;;
    --timeout)
      REQUEST_TIMEOUT="$2"
      shift 2
      ;;
    --circuit-ttl)
      CIRCUIT_BREAKER_TTL="$2"
      shift 2
      ;;
    --help | -h)
      usage
      exit 0
      ;;
    *)
      log_json "error" "unknown argument" "stderr" "argument=$1"
      usage
      exit 64
      ;;
  esac
done

if [[ -z "$SOURCE_URL" || -z "$DESTINATION" ]]; then
  log_json "error" "source and destination must not be empty" "stderr"
  exit 64
fi

require_command curl
require_command python3
require_command sha256sum
require_command mktemp
require_command flock
require_command timeout

log_json "info" "validated environment" "stdout" \
  "python_version=$(python3 --version 2>&1 | tr -d '\n')" \
  "curl_version=$(curl --version 2>/dev/null | head -n 1 | tr -d '\n')"

mkdir -p "$(dirname "$DESTINATION")" "$LOCK_DIR"

lock_key="$(printf '%s\n' "$SOURCE_URL|$DESTINATION" | sha256sum | awk '{print $1}')"
lock_file="${LOCK_DIR}/${lock_key}.lock"
marker_file="${LOCK_DIR}/${lock_key}.marker"
circuit_file="${LOCK_DIR}/${lock_key}.circuit"

exec {LOCK_FD}>"$lock_file"
if ! flock -n "$LOCK_FD"; then
  log_json "warning" "another synchronization is in progress" "stderr" \
    "lock_file=$lock_file"
  exit 0
fi

touch "$lock_file"

cleanup() {
  local exit_code=$?
  if [[ -n "${WORKDIR:-}" && -d "${WORKDIR:-}" ]]; then
    rm -rf "$WORKDIR"
  fi
  if [[ -n "${LOCK_FD:-}" ]]; then
    flock -u "$LOCK_FD" || true
    exec {LOCK_FD}>&- || true
  fi
  if [[ $exit_code -eq 0 ]]; then
    log_json "info" "cleanup complete" "stdout" "exit_code=$exit_code"
  else
    log_json "error" "cleanup after failure" "stderr" "exit_code=$exit_code"
  fi
}
trap cleanup EXIT INT TERM

now=$(date +%s)
if [[ -f "$circuit_file" ]]; then
  circuit_open=$(stat -c %Y "$circuit_file" 2>/dev/null || echo 0)
  if ((now - circuit_open < CIRCUIT_BREAKER_TTL)); then
    log_json "error" "circuit breaker open" "stderr" \
      "circuit_file=$circuit_file" \
      "seconds_until_retry=$((CIRCUIT_BREAKER_TTL - (now - circuit_open)))"
    exit 75
  else
    rm -f "$circuit_file"
    log_json "info" "circuit breaker reset" "stdout"
  fi
fi

if [[ -f "$marker_file" && -f "$DESTINATION" ]]; then
  existing_hash="$(sha256sum "$DESTINATION" | awk '{print $1}')"
  marker_hash="$(awk -F= '/^hash=/ {print $2}' "$marker_file" 2>/dev/null || true)"
  if [[ "$existing_hash" == "$marker_hash" && -n "$existing_hash" ]]; then
    log_json "info" "destination already up-to-date" "stdout" \
      "destination=$DESTINATION" \
      "hash=$existing_hash"
    exit 0
  fi
fi

WORKDIR="$(mktemp -d -t resilient-sync.XXXXXX)"
log_json "info" "created workspace" "stdout" "workspace=$WORKDIR"

download_file() {
  local destination="$1"
  local attempt=1
  local backoff=$INITIAL_BACKOFF
  while ((attempt <= MAX_RETRIES)); do
    log_json "info" "attempting download" "stderr" \
      "attempt=$attempt" \
      "source_url=$SOURCE_URL"
    if timeout "$REQUEST_TIMEOUT" curl -fsSL --retry 0 --output "$destination" "$SOURCE_URL"; then
      log_json "info" "download successful" "stderr" "attempt=$attempt"
      return 0
    fi
    local status=$?
    log_json "warning" "download failed" "stderr" \
      "attempt=$attempt" \
      "status=$status"
    if ((attempt == MAX_RETRIES)); then
      log_json "error" "exhausted retries" "stderr" \
        "max_retries=$MAX_RETRIES"
      return 1
    fi
    local jitter
    jitter="$(python3 -c 'import random; print(f"{random.uniform(0.1,0.5):.3f}")' 2>/dev/null || echo "0.2")"
    local sleep_for
    sleep_for=$(
      python3 - "$backoff" "$jitter" <<'PY'
import sys
backoff = float(sys.argv[1])
jitter = float(sys.argv[2])
print(f"{min(backoff + jitter, 60.0):.3f}")
PY
    )
    log_json "info" "sleeping before retry" "stderr" \
      "seconds=$sleep_for"
    sleep "$sleep_for"
    backoff=$((backoff * 2))
    if ((backoff > MAX_BACKOFF)); then
      backoff=$MAX_BACKOFF
    fi
    ((attempt++))
  done
  return 1
}

payload_path="$WORKDIR/payload"
download_file "$payload_path" || {
  touch "$circuit_file"
  log_json "error" "failed to download after retries" "stderr"
  exit 70
}

new_hash="$(sha256sum "$payload_path" | awk '{print $1}')"
log_json "info" "computed payload hash" "stdout" "hash=$new_hash"

if [[ -f "$DESTINATION" ]]; then
  existing_hash="$(sha256sum "$DESTINATION" | awk '{print $1}')"
  if [[ "$existing_hash" == "$new_hash" ]]; then
    log_json "info" "download matches existing destination" "stdout" \
      "destination=$DESTINATION"
    printf 'hash=%s\nsource=%s\nsynced_at=%s\n' "$new_hash" "$SOURCE_URL" "$(date -u +"%Y-%m-%dT%H:%M:%SZ")" >"$marker_file"
    exit 0
  fi
fi

tmp_dest="$WORKDIR/destination"
cp "$payload_path" "$tmp_dest"
chmod 0644 "$tmp_dest"

mv "$tmp_dest" "$DESTINATION"
log_json "info" "updated destination" "stdout" \
  "destination=$DESTINATION"

printf 'hash=%s\nsource=%s\nsynced_at=%s\n' "$new_hash" "$SOURCE_URL" "$(date -u +"%Y-%m-%dT%H:%M:%SZ")" >"$marker_file"
rm -f "$circuit_file"
log_json "info" "synchronization complete" "stdout" \
  "destination=$DESTINATION" \
  "hash=$new_hash"
