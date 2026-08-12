#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
#
# build_canonical_bundle.sh — build a git bundle for the GeoSync release capsule
# that contains ONLY the canonical release refs, so that a plain `git clone` of
# the bundle checks out the sealed release directly — with NO manual ref
# selection.
#
# WHY THIS EXISTS (REL-006)
# -------------------------
# Prior release bundles were built with `git bundle create ... --all` (363 refs,
# many stale branch heads). A `git clone <bundle>` of such a bundle is ambiguous:
# the caller has to know which of the 363 refs is "the release", and a naive
# clone can land on an unintended HEAD. This script emits a bundle with exactly
# two named refs plus a HEAD that resolves to the canonical release tree.
#
# CANONICAL RELEASE REF
# ---------------------
#   tag    : geosync-canonical-8080e4b4
#   commit : 8080e4b475efe054901804f25b37b80bd06203f4  (the "Merge ... into main" seal)
#   tree   : 9060de4a097ea467f7ab5d52ecb660ba345f671b  <-- checkout MUST match this
#
# The release capsule pins branch `main` to the canonical commit (the sealed
# release state). The live repository's `main` may have advanced past the seal;
# that is expected — the capsule is immutable at the sealed ref, and the tag is
# the source of truth. `main` inside the bundle is a convenience head so that a
# plain clone lands on the release.
#
# The bundle is written to /tmp by default and is ~150 MB; it MUST NEVER be
# committed into the repository or a worktree.
#
# Usage:
#   scripts/release/build_canonical_bundle.sh [OUTPUT_PATH]
#
# Environment overrides (rarely needed):
#   CANONICAL_TAG   (default: geosync-canonical-8080e4b4)
#   EXPECTED_TREE   (default: 9060de4a097ea467f7ab5d52ecb660ba345f671b)
#   EXPECTED_COMMIT (default: 8080e4b475efe054901804f25b37b80bd06203f4)
#
# Exit codes:
#   0  bundle built and self-verified
#   2  contract violation (missing tag, tree mismatch, malformed bundle)

set -euo pipefail

CANONICAL_TAG="${CANONICAL_TAG:-geosync-canonical-8080e4b4}"
EXPECTED_TREE="${EXPECTED_TREE:-9060de4a097ea467f7ab5d52ecb660ba345f671b}"
EXPECTED_COMMIT="${EXPECTED_COMMIT:-8080e4b475efe054901804f25b37b80bd06203f4}"

OUTPUT_PATH="${1:-/tmp/geosync-canonical-${CANONICAL_TAG}.bundle}"

# Repo root = two levels up from this script (scripts/release/..).
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "${SCRIPT_DIR}/../.." && pwd)"

die() {
    echo "build_canonical_bundle: FATAL: $*" >&2
    exit 2
}

# --- Resolve and verify the canonical ref inside the source repo -------------
git -C "${REPO_ROOT}" rev-parse --git-dir >/dev/null 2>&1 \
    || die "not a git repository: ${REPO_ROOT}"

git -C "${REPO_ROOT}" cat-file -t "refs/tags/${CANONICAL_TAG}" >/dev/null 2>&1 \
    || die "canonical tag not present: ${CANONICAL_TAG}"

TAG_COMMIT="$(git -C "${REPO_ROOT}" rev-parse "${CANONICAL_TAG}^{commit}")"
TAG_TREE="$(git -C "${REPO_ROOT}" rev-parse "${CANONICAL_TAG}^{tree}")"

[ "${TAG_COMMIT}" = "${EXPECTED_COMMIT}" ] \
    || die "canonical commit mismatch: got ${TAG_COMMIT}, expected ${EXPECTED_COMMIT}"
[ "${TAG_TREE}" = "${EXPECTED_TREE}" ] \
    || die "canonical tree mismatch: got ${TAG_TREE}, expected ${EXPECTED_TREE}"

# --- Assemble a pinned scratch repo so the bundle HEAD is deterministic -------
# We do NOT touch the source repo's refs or HEAD. Instead we build a throwaway
# bare repo whose ONLY refs are the canonical release, with HEAD -> main -> the
# canonical commit, then `bundle create --all` from it. `--no-verify` skips the
# source repo's pre-push hooks (irrelevant to a local object transfer).
SCRATCH_GIT="$(mktemp -d /tmp/geosync-canonical-scratch.XXXXXX)/rel.git"
cleanup() { rm -rf "$(dirname -- "${SCRATCH_GIT}")"; }
trap cleanup EXIT

git init -q --bare "${SCRATCH_GIT}"
git -C "${REPO_ROOT}" push -q --no-verify "${SCRATCH_GIT}" \
    "${EXPECTED_COMMIT}:refs/heads/main"
git -C "${REPO_ROOT}" push -q --no-verify "${SCRATCH_GIT}" \
    "refs/tags/${CANONICAL_TAG}:refs/tags/${CANONICAL_TAG}"
git --git-dir="${SCRATCH_GIT}" symbolic-ref HEAD refs/heads/main

# --- Build the bundle ---------------------------------------------------------
mkdir -p "$(dirname -- "${OUTPUT_PATH}")"
rm -f "${OUTPUT_PATH}"
git --git-dir="${SCRATCH_GIT}" bundle create "${OUTPUT_PATH}" --all >&2

# --- Self-verify the emitted bundle ------------------------------------------
git bundle verify "${OUTPUT_PATH}" >/dev/null 2>&1 \
    || die "bundle failed git-bundle verify: ${OUTPUT_PATH}"

HEADS="$(git bundle list-heads "${OUTPUT_PATH}")"
NAMED_REFS="$(echo "${HEADS}" | grep -E 'refs/(heads|tags)/' | awk '{print $2}' | sort)"
EXPECTED_REFS="$(printf '%s\n%s\n' \
    "refs/heads/main" "refs/tags/${CANONICAL_TAG}" | sort)"
[ "${NAMED_REFS}" = "${EXPECTED_REFS}" ] \
    || die "bundle contains unexpected refs:"$'\n'"${NAMED_REFS}"

# HEAD in the bundle must resolve to the canonical commit (so clone checks out
# the canonical tree without manual ref selection).
BUNDLE_HEAD="$(echo "${HEADS}" | awk '$2=="HEAD"{print $1}')"
[ "${BUNDLE_HEAD}" = "${EXPECTED_COMMIT}" ] \
    || die "bundle HEAD ${BUNDLE_HEAD} != canonical commit ${EXPECTED_COMMIT}"

echo "build_canonical_bundle: OK" >&2
echo "  output : ${OUTPUT_PATH}" >&2
echo "  tag    : ${CANONICAL_TAG}" >&2
echo "  commit : ${EXPECTED_COMMIT}" >&2
echo "  tree   : ${EXPECTED_TREE}" >&2
echo "  refs   : refs/heads/main, refs/tags/${CANONICAL_TAG} (HEAD -> main)" >&2

# Emit the resolved output path on stdout for machine consumers.
echo "${OUTPUT_PATH}"
