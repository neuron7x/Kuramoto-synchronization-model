#!/usr/bin/env bash
# audit_todo.sh — TODO / placeholder / unimplemented marker scanner.
#
# Per the canonical audit protocol Phase 6: "TODO|TBD|coming soon|
# future work|not implemented|placeholder are allowed only if clearly
# marked as limitations or future work."
#
# This script reports raw counts. Whether a hit is a defect depends on
# context (a hit inside reports/TECH_DEBT_REGISTRY.md is the file's own
# job; a hit inside a customer-facing README is a defect).
#
# Usage:
#   ./tools/audit_todo.sh                # file-count summary
#   ./tools/audit_todo.sh --raw          # raw line-by-line hits
set -euo pipefail
cd "$(git rev-parse --show-toplevel 2>/dev/null || dirname "$(dirname "$(realpath "$0")")")"

PATTERN='TODO|TBD|coming soon|future work|not implemented|placeholder'
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

if [[ "${1:-}" == "--raw" ]]; then
  grep -rniE "$PATTERN" "${EXCLUDES[@]}" . 2>/dev/null
  exit 0
fi

TOTAL=$(grep -rniE "$PATTERN" "${EXCLUDES[@]}" . 2>/dev/null | wc -l)
FILES=$(grep -rliE "$PATTERN" "${EXCLUDES[@]}" . 2>/dev/null | wc -l)

echo "==================================================="
echo "  TODO / placeholder scan — $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "==================================================="
echo "  Total hits:           $TOTAL"
echo "  Distinct files:       $FILES"
echo ""
echo "  Per-file hit counts (top 20):"
grep -rliE "$PATTERN" "${EXCLUDES[@]}" . 2>/dev/null \
  | while read -r f; do
      n=$(grep -ciE "$PATTERN" "$f")
      printf "    %4d  %s\n" "$n" "$f"
    done \
  | sort -rn \
  | head -20
echo ""
echo "  Hits inside reports/TECH_DEBT_REGISTRY.md, ROBUSTNESS_*, and"
echo "  KNOWN_LIMITATIONS-style files are by design and not defects."
echo "  Hits in customer-facing README/installation/usage docs ARE defects."
