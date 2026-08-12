#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
# Compatibility wrapper for the structured PR preflight runner.

set -u

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPORT_DIR="${ROOT}/artifacts/pr_preflight"
REPORT_PATH="${REPORT_DIR}/preflight_report.json"
LEDGER_PATH="${REPORT_DIR}/inference_ledger.jsonl"

if command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN="python3"
elif command -v python >/dev/null 2>&1; then
    PYTHON_BIN="python"
else
    echo "ERROR: python3 or python is required to run PR preflight" >&2
    # No runner could execute, so no evidence report exists — do not point
    # callers at a non-existent artifact.
    exit 1
fi

"${PYTHON_BIN}" "${ROOT}/tools/ci/pr_preflight.py" --root "${ROOT}" --report-dir "${REPORT_DIR}" "$@"
exit_code=$?

# Append the inference-ledger entry only when the runner actually produced its
# evidence report; on a BLOCKED/crash run the report is absent.
if [[ -f "${REPORT_PATH}" ]]; then
    "${PYTHON_BIN}" "${ROOT}/tools/ci/preflight_ledger.py" --report "${REPORT_PATH}" --ledger "${LEDGER_PATH}"
    ledger_exit=$?
    if [[ "${exit_code}" -eq 0 && "${ledger_exit}" -ne 0 ]]; then
        exit_code="${ledger_exit}"
    fi
elif [[ "${exit_code}" -eq 0 ]]; then
    echo "ERROR: PR preflight completed without ${REPORT_PATH}" >&2
    exit_code=1
fi

# Only advertise the evidence artifact when it was actually written (fail-closed
# triage: never point callers at a missing file on the BLOCKED path).
if [[ -f "${REPORT_PATH}" ]]; then
    echo "FIRST_FILE_TO_OPEN=${REPORT_PATH}"
fi
exit "${exit_code}"
