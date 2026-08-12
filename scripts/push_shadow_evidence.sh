#!/usr/bin/env bash
# Auto-commit + auto-push shadow evidence after each shadow cycle.
#
# Contract:
#   - Fail-closed is reserved for signal/data invariants; git push
#     failure is an *operational delivery* failure: we log it as an
#     incident, but we do NOT break the shadow systemd unit (exit 0),
#     because the evidence on the local disk is still correct and
#     append-only — push is recovery-delivery, not correctness.
#   - Commits are always local (cheap, auditable). Push is conditional
#     on a remote being configured.
#   - The committed diff is scoped to
#     results/cross_asset_kuramoto/shadow_validation/ — no other path.

set -u

REPO="${SHADOW_REPO:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
SHADOW_DIR="results/cross_asset_kuramoto/shadow_validation"
INCIDENTS="${REPO}/${SHADOW_DIR}/operational_incidents.csv"
TODAY_UTC="$(date -u +%Y-%m-%d)"
NOW_UTC="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

cd "${REPO}" || { echo "FATAL: cannot cd ${REPO}" >&2; exit 0; }

_append_incident() {
  local itype="$1" sev="$2" desc="$3"
  mkdir -p "$(dirname "${INCIDENTS}")"
  if [[ ! -f "${INCIDENTS}" ]]; then
    printf 'incident_ts,incident_type,severity,affected_run_date,description,resolved_yes_no,resolution_ts,changed_artifacts_yes_no\n' > "${INCIDENTS}"
  fi
  # CSV-escape: double any embedded quotes, wrap in quotes
  local esc
  esc="${desc//\"/\"\"}"
  printf '%s,%s,%s,%s,"%s",no,,no\n' \
    "${NOW_UTC}" "${itype}" "${sev}" "${TODAY_UTC}" "${esc}" >> "${INCIDENTS}"
}

# Stage only the shadow directory — we never auto-commit outside of it.
git add -- "${SHADOW_DIR}" 2>&1 || {
  _append_incident "git_add_failed" "HIGH" "git add ${SHADOW_DIR} failed at ${NOW_UTC}"
  exit 0
}

if git diff --cached --quiet -- "${SHADOW_DIR}"; then
  echo "push_shadow_evidence: nothing to commit under ${SHADOW_DIR}"
  exit 0
fi

# Local commit (always safe; low blast radius).
if ! git -c user.email="shadow-runner@local" -c user.name="shadow-runner" \
     commit -q -m "shadow: auto-evidence ${TODAY_UTC}"; then
  _append_incident "git_commit_failed" "HIGH" "git commit failed at ${NOW_UTC}"
  exit 0
fi

# Push only if a remote is configured. No remote → log LOW incident, exit 0.
if ! git remote get-url origin >/dev/null 2>&1; then
  _append_incident "push_skipped_no_remote" "LOW" \
    "Local shadow commit made at ${NOW_UTC}; no 'origin' remote configured, push skipped."
  echo "push_shadow_evidence: no origin remote configured; committed locally only"
  exit 0
fi

# Push fail-closed to incident ledger, exit 0 (next run will try again;
# repository stays consistent with remote once network is back).
if ! git push --quiet origin HEAD 2>/tmp/push_shadow_err.$$; then
  err="$(cat /tmp/push_shadow_err.$$ 2>/dev/null || true)"
  rm -f /tmp/push_shadow_err.$$
  _append_incident "git_push_failed" "MEDIUM" \
    "git push origin HEAD failed at ${NOW_UTC}: ${err}"
  echo "push_shadow_evidence: push failed (logged as incident)"
  exit 0
fi

echo "push_shadow_evidence: commit + push OK for ${TODAY_UTC}"
exit 0
