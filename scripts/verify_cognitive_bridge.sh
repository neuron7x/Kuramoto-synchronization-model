#!/usr/bin/env bash
# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
#
# One-shot end-to-end verification of the cognitive bridge stack.
# Run: scripts/verify_cognitive_bridge.sh
#
# Checks (in order):
#   1.  geosync-bridge.service is active
#   2.  port 18790 is listening
#   3.  GET /healthz returns OK
#   4.  POST /v1/cognitive-bridge/exchange roundtrip echoes correlation_id
#   5.  Python quality stack (ruff/black/mypy --strict) clean
#   6.  All 63 cognitive_bridge tests pass
#   7.  Coverage ≥ 95%
#   8.  Both demos run end-to-end
#
# Exit codes:
#   0   all green
#   N   number of failed checks

set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

PORT=18790
ENDPOINT="/v1/cognitive-bridge/exchange"
HEALTH="http://127.0.0.1:${PORT}/healthz"
EXCHANGE="http://127.0.0.1:${PORT}${ENDPOINT}"
FAILED=0

green()  { printf "  \033[32m✓\033[0m %s\n" "$1"; }
red()    { printf "  \033[31m✗\033[0m %s\n" "$1"; FAILED=$((FAILED + 1)); }
header() { printf "\n\033[1m%s\033[0m\n" "$1"; }

header "1. systemd unit"
if systemctl --user is-active geosync-bridge.service >/dev/null 2>&1; then
  green "geosync-bridge.service active"
else
  red "geosync-bridge.service not active (systemctl --user start geosync-bridge)"
fi

header "2. port listening"
if ss -ltn 2>/dev/null | grep -q ":${PORT} "; then
  green "127.0.0.1:${PORT} listening"
else
  red "port ${PORT} not bound"
fi

header "3. healthz"
HEALTH_BODY="$(curl -s --max-time 2 "${HEALTH}" 2>/dev/null || echo "")"
if echo "${HEALTH_BODY}" | grep -q '"status":"ok"'; then
  green "/healthz: ${HEALTH_BODY}"
else
  red "/healthz failed: ${HEALTH_BODY:-no response}"
fi

header "4. wire roundtrip"
CID="abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789"
ENVELOPE='{"correlation_id":"'"${CID}"'","request":{"protocol_version":"cb-1.0.0","agent_state":"REVIEW","coherence":0.82,"kill_switch_active":false,"stressed_state":false,"question":"verification probe","context":{}}}'
REPLY="$(curl -s --max-time 2 -X POST "${EXCHANGE}" -H 'content-type: application/json' -d "${ENVELOPE}" 2>/dev/null || echo "")"
if echo "${REPLY}" | grep -q "\"correlation_id\":\"${CID}\""; then
  green "/exchange: correlation_id echoed, status=$(echo "${REPLY}" | grep -oE '"status":"[a-z]+"')"
else
  red "/exchange wire mismatch: ${REPLY:-no response}"
fi

header "5. Python quality stack"
if ruff check runtime/cognitive_bridge tests/runtime/cognitive_bridge >/dev/null 2>&1; then
  green "ruff clean"
else
  red "ruff failures"
fi
if black --check -q runtime/cognitive_bridge tests/runtime/cognitive_bridge >/dev/null 2>&1; then
  green "black clean"
else
  red "black failures"
fi
if mypy --strict runtime/cognitive_bridge tests/runtime/cognitive_bridge >/dev/null 2>&1; then
  green "mypy --strict clean"
else
  red "mypy --strict failures"
fi

header "6. pytest + coverage"
COV_OUT="$(python -m pytest tests/runtime/cognitive_bridge --cov=runtime.cognitive_bridge --cov-report=term 2>&1)"
COV_RC=$?
TEST_LINE="$(echo "${COV_OUT}" | grep -oE '[0-9]+ passed[^=]*' | tail -1)"
if [ "${COV_RC}" -eq 0 ] && [ -n "${TEST_LINE}" ]; then
  green "pytest: ${TEST_LINE}"
elif [ "${COV_RC}" -eq 0 ]; then
  green "pytest passed (exit 0)"
else
  red "pytest failed (exit ${COV_RC})"
fi
COV_PCT="$(echo "${COV_OUT}" | grep -E '^TOTAL' | grep -oE '[0-9]+\.[0-9]+%' | tail -1)"
if [ -n "${COV_PCT}" ]; then
  COV_INT="${COV_PCT%.*}"
  if [ "${COV_INT}" -ge 95 ]; then
    green "coverage ${COV_PCT} (≥95%)"
  else
    red "coverage ${COV_PCT} below 95%"
  fi
else
  red "coverage parse failed"
fi

header "7. demos"
if PYTHONPATH=. python examples/cognitive_bridge_demo.py >/dev/null 2>&1; then
  green "cognitive_bridge_demo.py OK"
else
  red "cognitive_bridge_demo.py failed"
fi
if PYTHONPATH=. python examples/semantic_sieve_demo.py >/dev/null 2>&1; then
  green "semantic_sieve_demo.py OK"
else
  red "semantic_sieve_demo.py failed"
fi

header "summary"
if [ "${FAILED}" -eq 0 ]; then
  printf "\033[32mall green\033[0m\n"
  exit 0
fi
printf "\033[31m%d check(s) failed\033[0m\n" "${FAILED}"
exit "${FAILED}"
