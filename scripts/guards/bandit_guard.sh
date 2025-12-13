#!/usr/bin/env bash
# Bandit MEDIUM/HIGH Guard - Ensures no MEDIUM or HIGH severity issues
# This script is used in CI to enforce code security standards

set -euo pipefail

echo "🔍 Bandit Security Guard - Checking for MEDIUM/HIGH severity issues..."

# Define scope for scanning
SCAN_PATHS=(
    "src"
    "backtest"
    "scripts"
)

# Run Bandit with LOW and above (-ll flag)
echo "Running Bandit on: ${SCAN_PATHS[*]}"

# Create temp file for results
TEMP_RESULT=$(mktemp)
trap 'rm -f "$TEMP_RESULT"' EXIT

# Run Bandit and capture exit code
set +e
python -m bandit -r "${SCAN_PATHS[@]}" -ll -f json -o "$TEMP_RESULT" 2>&1
BANDIT_EXIT=$?
set -e

# Parse results
if [[ ! -f "$TEMP_RESULT" ]] || [[ ! -s "$TEMP_RESULT" ]]; then
    echo "❌ FAILURE: Bandit did not produce output"
    exit 1
fi

# Count MEDIUM and HIGH issues
MEDIUM_COUNT=$(python -c "
import json, sys
try:
    with open('$TEMP_RESULT') as f:
        data = json.load(f)
    results = data.get('results', [])
    medium = [r for r in results if r.get('issue_severity') == 'MEDIUM']
    print(len(medium))
except Exception as e:
    print('ERROR:', e, file=sys.stderr)
    sys.exit(1)
" 2>&1)

HIGH_COUNT=$(python -c "
import json, sys
try:
    with open('$TEMP_RESULT') as f:
        data = json.load(f)
    results = data.get('results', [])
    high = [r for r in results if r.get('issue_severity') == 'HIGH']
    print(len(high))
except Exception as e:
    print('ERROR:', e, file=sys.stderr)
    sys.exit(1)
" 2>&1)

# Report findings
echo "Bandit Results:"
echo "  HIGH severity issues: $HIGH_COUNT"
echo "  MEDIUM severity issues: $MEDIUM_COUNT"

if [[ "$HIGH_COUNT" -gt 0 ]] || [[ "$MEDIUM_COUNT" -gt 0 ]]; then
    echo ""
    echo "❌ FAILURE: Found MEDIUM or HIGH severity security issues!"
    echo ""
    echo "Details:"
    python -c "
import json
with open('$TEMP_RESULT') as f:
    data = json.load(f)
results = data.get('results', [])
issues = [r for r in results if r.get('issue_severity') in ('MEDIUM', 'HIGH')]
for issue in issues:
    print(f\"  {issue['issue_severity']}: {issue['test_id']} - {issue['filename']}:{issue['line_number']}\")
    print(f\"    {issue['issue_text']}\")
    print()
"
    echo ""
    echo "Remediation steps:"
    echo "  1. Review each finding above"
    echo "  2. Fix the security issue with proper secure coding"
    echo "  3. If it's a false positive, add # nosec <TEST_ID> with justification"
    echo "  4. Re-run: python -m bandit -r src backtest scripts -ll"
    echo ""
    exit 1
fi

echo "✅ SUCCESS: No MEDIUM or HIGH severity issues found"
exit 0
