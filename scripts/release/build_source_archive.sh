#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
#
# build_source_archive.sh — deterministic, byte-reproducible source-release
# archive for GeoSync (REL-010).
#
# WHY THIS EXISTS
# ---------------
# A source release must be *byte-reproducible*: two independent builds of the
# same tree, on any machine, at any wall-clock time, must yield an archive with
# an IDENTICAL sha256. That property is what lets a downstream consumer verify
# they received the exact release-approved source and nothing else.
#
# Two things break reproducibility of a naive `tar czf`:
#   1. tar records per-file mtime/uid/gid/mode from the working tree, which vary
#      by checkout time and by user.
#   2. gzip embeds the compression wall-clock timestamp (and the original file
#      name) in its header.
#
# This builder removes BOTH sources of nondeterminism:
#   * `git archive` streams ONLY git-tracked content (no untracked/ignored
#      cruft), with normalized ownership (uid/gid 0), normalized mode, and a
#      single fixed mtime. The set of files is exactly the flattened tree
#      `git ls-tree -r <ref>`.
#   * `gzip -n` drops the gzip header timestamp AND the embedded name, so the
#      compressed stream is a pure function of the tar stream.
#
# WE ARCHIVE THE COMMIT OBJECT, AND WHERE THE FIXED mtime COMES FROM
# -----------------------------------------------------------------
# Measured behavior on git 2.43 (the mental model in some SOURCE_DATE_EPOCH docs
# is inaccurate here — trust the measurement, not the folklore):
#   * `git archive <COMMIT>`  -> every tar entry's mtime is pinned to the
#     commit's own committer date. SOURCE_DATE_EPOCH is IGNORED. The output is
#     byte-identical across independent invocations and wall-clock times.
#   * `git archive <TREE>`    -> HONORS SOURCE_DATE_EPOCH for entry mtime, BUT
#     also writes a LIVE `now` field, so it is NOT byte-reproducible even with a
#     fixed epoch. (Do not archive a bare tree for a reproducible release.)
# Therefore the reproducible primitive is the COMMIT object. Determinism is
# sourced from the commit's fixed committer date, which for the canonical seal
# equals SOURCE_DATE_EPOCH below. We still export SOURCE_DATE_EPOCH: it is the
# recorded provenance stamp (and would govern any downstream tool that honors
# it), and by construction it matches the effective mtime.
#
# DETERMINISM CONTRACT
# --------------------
#   prefix           : geosync-<version>/   (pinned, default geosync-1.1.0/)
#   SOURCE_DATE_EPOCH: a FIXED epoch, passed in (default = canonical commit's
#                      author date). NEVER `now`.
#   file set         : == `git ls-files <ref>` (tracked only)
#   ownership/mode   : normalized by git archive
#   gzip             : `gzip -n` (no timestamp, no name)
#
# USAGE
# -----
#   scripts/release/build_source_archive.sh [OUT_DIR]
#
# Environment:
#   SOURCE_DATE_EPOCH  fixed epoch seconds (default: author date of REF)
#   GEOSYNC_VERSION    version string for the prefix (default: contents of VERSION)
#   GEOSYNC_REF        git ref to archive (default: HEAD)
#
# OUT_DIR defaults to /tmp. The archive is ~hundreds of MB and MUST NEVER be
# committed into the repository or a worktree.
#
# On success prints two lines to stdout:
#   ARCHIVE=<abs path to .tar.gz>
#   SHA256=<hex digest>
#
set -euo pipefail

REPO_ROOT="$(git -C "$(dirname "$0")" rev-parse --show-toplevel)"
cd "$REPO_ROOT"

OUT_DIR="${1:-/tmp}"
REF="${GEOSYNC_REF:-HEAD}"

if [[ -n "${GEOSYNC_VERSION:-}" ]]; then
  VERSION="$GEOSYNC_VERSION"
elif [[ -f VERSION ]]; then
  VERSION="$(tr -d '[:space:]' < VERSION)"
else
  echo "build_source_archive: cannot determine version (no GEOSYNC_VERSION, no VERSION file)" >&2
  exit 2
fi

# SOURCE_DATE_EPOCH MUST be a fixed epoch. Default to the author date of REF so
# that a plain invocation is still deterministic and never uses `now`.
if [[ -z "${SOURCE_DATE_EPOCH:-}" ]]; then
  SOURCE_DATE_EPOCH="$(git show -s --format=%at "$REF")"
fi
export SOURCE_DATE_EPOCH

PREFIX="geosync-${VERSION}/"
ARCHIVE="${OUT_DIR%/}/geosync-${VERSION}.tar.gz"

mkdir -p "$OUT_DIR"

# Archive the COMMIT object (byte-reproducible; mtime pinned to the commit's
# committer date — see the header note). Tracked content only, normalized
# ownership/mode. gzip -n: drop the gzip header timestamp and name.
git archive --format=tar --prefix="$PREFIX" "$REF" | gzip -n > "$ARCHIVE"

SHA256="$(sha256sum "$ARCHIVE" | awk '{print $1}')"

echo "ARCHIVE=$ARCHIVE"
echo "SHA256=$SHA256"
