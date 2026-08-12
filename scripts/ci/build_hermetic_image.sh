#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
# =============================================================================
# build_hermetic_image.sh -- ENV-005 hermetic CPU container builder
# -----------------------------------------------------------------------------
# Deterministically builds Dockerfile.repro, tags it geosync-hermetic:repro,
# captures the resolved image digest/id + base digest + build args into
# artifacts/env/image_digest.json, runs a scanner if one is present into
# artifacts/env/image_scan_report.json, and prunes dangling build cache to
# protect the disk budget.
#
# Usage:
#   scripts/ci/build_hermetic_image.sh [--no-scan] [--tag TAG]
# =============================================================================
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${REPO_ROOT}"

IMAGE_TAG="geosync-hermetic:repro"
DOCKERFILE="Dockerfile.repro"
ART_DIR="artifacts/env"
DIGEST_JSON="${ART_DIR}/image_digest.json"
SCAN_JSON="${ART_DIR}/image_scan_report.json"
DO_SCAN=1

# Deterministic build timestamp; overridable for provenance replay.
SOURCE_DATE_EPOCH="${SOURCE_DATE_EPOCH:-0}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --no-scan) DO_SCAN=0; shift ;;
    --tag) IMAGE_TAG="$2"; shift 2 ;;
    *) echo "unknown arg: $1" >&2; exit 2 ;;
  esac
done

mkdir -p "${ART_DIR}"

echo "[build] ${IMAGE_TAG} <- ${DOCKERFILE} (SOURCE_DATE_EPOCH=${SOURCE_DATE_EPOCH})"
DOCKER_BUILDKIT=1 docker build \
  --file "${DOCKERFILE}" \
  --tag "${IMAGE_TAG}" \
  --build-arg "SOURCE_DATE_EPOCH=${SOURCE_DATE_EPOCH}" \
  .

# ---- capture image identity ----
IMAGE_ID="$(docker image inspect "${IMAGE_TAG}" --format '{{.Id}}')"
# Base image digest as pinned in the Dockerfile (single source of truth).
BASE_REF="$(grep -m1 '^FROM ' "${DOCKERFILE}" | awk '{print $2}')"
BASE_DIGEST="${BASE_REF#*@}"
BUILT_AT="$(date -u -d "@${SOURCE_DATE_EPOCH}" +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || echo "epoch:${SOURCE_DATE_EPOCH}")"

python3 - "$IMAGE_TAG" "$IMAGE_ID" "$BASE_REF" "$BASE_DIGEST" "$SOURCE_DATE_EPOCH" "$BUILT_AT" "$DIGEST_JSON" <<'PY'
import json, sys
tag, image_id, base_ref, base_digest, sde, built_at, out = sys.argv[1:8]
doc = {
    "schema": "geosync.env.image_digest/v1",
    "task": "ENV-005",
    "image_tag": tag,
    "image_id": image_id,
    "repo_digest": None,
    "base_image_ref": base_ref,
    "base_image_digest": base_digest,
    "build_args": {"SOURCE_DATE_EPOCH": sde},
    "built_at_utc": built_at,
    "note": (
        "repo_digest is null: image is local-only (not pushed to a registry), so "
        "no manifest RepoDigest exists yet. image_id is the pinned local content id. "
        "base_image_digest is the immutable pin from Dockerfile.repro."
    ),
}
with open(out, "w", encoding="utf-8") as fh:
    json.dump(doc, fh, indent=2, sort_keys=True)
    fh.write("\n")
print(f"[digest] wrote {out}: image_id={image_id[:19]}... base={base_digest[:19]}...")
PY

# ---- optional vulnerability scan ----
if [[ "${DO_SCAN}" -eq 1 ]]; then
  if command -v trivy >/dev/null 2>&1; then
    echo "[scan] trivy image ${IMAGE_TAG}"
    RAW_SCAN="$(mktemp)"
    trivy image --quiet --scanners vuln --severity CRITICAL,HIGH \
      --format json --output "${RAW_SCAN}" "${IMAGE_TAG}" || true
    TRIVY_VER="$(trivy --version 2>/dev/null | awk '/^Version/{print $2}')"
    # Build an acceptance envelope: CVEs with NO upstream fix are recorded as
    # ACCEPTED (unfixable at scan time, base-OS inherited); any CVE WITH a fix
    # is ACTIONABLE and flips the verdict to FAIL (fail-closed).
    python3 - "$RAW_SCAN" "$SCAN_JSON" "$IMAGE_TAG" "$TRIVY_VER" <<'PY'
import json, sys, datetime
raw_path, out, tag, ver = sys.argv[1:5]
raw = json.load(open(raw_path, encoding="utf-8"))
accepted, actionable = [], []
for r in raw.get("Results", []):
    for v in r.get("Vulnerabilities") or []:
        row = {"id": v["VulnerabilityID"], "severity": v["Severity"],
               "pkg": v["PkgName"], "installed": v.get("InstalledVersion"),
               "fixed_version": v.get("FixedVersion") or None,
               "status": v.get("Status"), "target": r.get("Target")}
        (actionable if row["fixed_version"] else accepted).append(row)
verdict = "PASS" if not actionable else "FAIL"
doc = {
    "schema": "geosync.env.image_scan/v1",
    "task": "ENV-005",
    "image_tag": tag,
    "scanner": "trivy",
    "scanner_version": ver,
    "generated_utc": datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
    "severity_filter": ["CRITICAL", "HIGH"],
    "totals": {"critical_high": len(accepted) + len(actionable),
               "actionable_fixable": len(actionable),
               "accepted_unfixable": len(accepted)},
    "verdict": verdict,
    "acceptance_policy": (
        "0 critical/high UNACCEPTED. A CVE is ACCEPTED iff no upstream fix "
        "exists (empty FixedVersion; Debian status affected/fix_deferred). "
        "These are inherited from the pinned python:3.12-slim (debian trixie) "
        "base and are not reachable through the pure-Python integrity gate "
        "(no perl/shell/ncurses in the gate path); the container runs "
        "non-root, read-only, offline. Any CVE that GAINS a fix becomes "
        "actionable and fails this gate. Re-pin the base digest to remediate."
    ),
    "actionable_unaccepted": actionable,
    "accepted_unfixable": accepted,
}
json.dump(doc, open(out, "w", encoding="utf-8"), indent=2, sort_keys=True)
open(out, "a").write("\n")
print(f"[scan] verdict={verdict} accepted_unfixable={len(accepted)} "
      f"actionable_fixable={len(actionable)}")
PY
    rm -f "${RAW_SCAN}"
    echo "[scan] wrote ${SCAN_JSON}"
  elif command -v grype >/dev/null 2>&1; then
    echo "[scan] grype ${IMAGE_TAG}"
    grype "${IMAGE_TAG}" -o json > "${SCAN_JSON}" || true
    echo "[scan] wrote ${SCAN_JSON}"
  else
    echo "[scan] no scanner (trivy/grype) found; recording scanner_absent"
    python3 - "$SCAN_JSON" "$IMAGE_TAG" <<'PY'
import json, sys
out, tag = sys.argv[1], sys.argv[2]
json.dump({"scanner_absent": True, "image_tag": tag,
           "note": "Install trivy or grype to produce a vulnerability report."},
          open(out, "w"), indent=2)
open(out, "a").write("\n")
PY
  fi
fi

# ---- disk hygiene: drop dangling images + build cache ----
echo "[cleanup] pruning dangling images and build cache"
docker image prune -f >/dev/null 2>&1 || true
docker builder prune -f >/dev/null 2>&1 || true

echo "[done] ${IMAGE_TAG} built; artifacts in ${ART_DIR}/"
