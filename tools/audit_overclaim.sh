#!/usr/bin/env bash
# audit_overclaim.sh — re-runnable overclaim scanner (canonical-2026-05-05).
#
# Scans every Markdown file under the repo (excluding .git, .venv,
# .claude/worktrees, .mypy_cache, node_modules, vendor, newsfragments) for
# the forbidden-terminology set defined in docs/audit/CANONICAL_DOCUMENTATION_QUALITY_AUDIT.md
# and reports counts per file.
#
# A hit is NOT automatically a defect — many remaining hits are inside
# legitimate context (negation, governance rule, claim-tier definition,
# self-audit catalog). The script exists so any operator can re-run the
# same query the auditor used and diff against the snapshot in
# docs/audit/CANONICAL_DOCUMENTATION_QUALITY_AUDIT.md.
#
# Usage:
#   ./tools/audit_overclaim.sh                # full repo, file-count report
#   ./tools/audit_overclaim.sh --raw          # raw line-by-line hits (long)
#   ./tools/audit_overclaim.sh --strict-only  # zero-tolerance phrases only
#
# Exit codes:
#   0 — scan succeeded (regardless of hit count)
#   2 — no Markdown files found at all (repo layout broken)
set -euo pipefail

cd "$(git rev-parse --show-toplevel 2>/dev/null || dirname "$(dirname "$(realpath "$0")")")"

STRICT='world-class|breakthrough|revolutionary|state-of-the-art|best-in-class|scientifically proven|mathematically proven|battle-tested|OpenAI-level|Anthropic-level'

WIDE='production-grade|production-ready|production grade|enterprise-grade|state-of-the-art|world-class|best-in-class|breakthrough|revolutionary|fully verified|fully validated|100% reproducible|guaranteed|scientifically proven|mathematically proven|battle-tested|deployment-ready|industry-grade'

PATTERN="$WIDE"
MODE="counts"

for arg in "$@"; do
  case "$arg" in
    --raw) MODE="raw" ;;
    --strict-only) PATTERN="$STRICT" ;;
    -h|--help)
      sed -n '2,30p' "$0" | sed 's/^# \?//'
      exit 0
      ;;
  esac
done

EXCLUDES=(
  --include="*.md"
  --exclude-dir=.git
  --exclude-dir=.venv
  --exclude-dir=.claude/worktrees
  --exclude-dir=.mypy_cache
  --exclude-dir=newsfragments
  --exclude-dir=node_modules
  --exclude-dir=vendor
)

if [[ "$MODE" == "raw" ]]; then
  grep -rniE "$PATTERN" "${EXCLUDES[@]}" . 2>/dev/null
  exit 0
fi

TOTAL=$(grep -rniE "$PATTERN" "${EXCLUDES[@]}" . 2>/dev/null | wc -l)
FILES=$(grep -rliE "$PATTERN" "${EXCLUDES[@]}" . 2>/dev/null | wc -l)

echo "==================================================="
echo "  Overclaim scan — $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "==================================================="
echo "  Total hits:           $TOTAL"
echo "  Distinct files:       $FILES"
echo "  Pattern set:          $([ "$PATTERN" = "$STRICT" ] && echo strict || echo wide)"
echo ""
echo "  Per-file hit counts (top 25):"
grep -rniE "$PATTERN" "${EXCLUDES[@]}" . 2>/dev/null \
  | awk -F: '{print $1}' \
  | sort \
  | uniq -c \
  | sort -rn \
  | head -25 \
  | awk '{printf "    %4d  %s\n", $1, $2}'
echo ""
echo "  See docs/audit/CANONICAL_DOCUMENTATION_QUALITY_AUDIT.md for"
echo "  the catalog of files where overclaim is INTENTIONAL (negation,"
echo "  governance rule, claim-tier definition, formal contract,"
echo "  self-audit catalog) — those hits are not defects."
