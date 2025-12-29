#!/usr/bin/env bash
# Action Pinning Guard - Ensures GitHub Actions are pinned to commit SHA
# This script is used in CI to enforce supply chain security

set -euo pipefail

echo "🔒 Action Pinning Guard - Checking GitHub Actions pinning..."

# Find all workflow files
WORKFLOW_DIR=".github/workflows"
UNPINNED_ACTIONS=()

if [[ ! -d "$WORKFLOW_DIR" ]]; then
    echo "❌ ERROR: Workflow directory not found: $WORKFLOW_DIR"
    exit 1
fi

# Check each workflow file
for workflow in "$WORKFLOW_DIR"/*.yml; do
    if [[ ! -f "$workflow" ]]; then
        continue
    fi
    
    # Find all 'uses:' lines that are not:
    # - Pinned to SHA (40 hex chars)
    # - Local actions (starts with ./)
    # - Docker actions (starts with docker://)
    while IFS=: read -r line_no line_content; do
        # Extract the action reference (everything after 'uses:')
        action=$(echo "$line_content" | sed -n 's/.*uses:\s*\(.*\)/\1/p' | tr -d "'" | tr -d '"' | xargs)
        
        # Skip local actions
        if [[ "$action" =~ ^\./  ]]; then
            continue
        fi
        
        # Skip docker actions
        if [[ "$action" =~ ^docker:// ]]; then
            continue
        fi
        
        # Check if pinned to SHA (@ followed by 40 hex chars)
        if ! [[ "$action" =~ @[a-f0-9]{40}($|[[:space:]]) ]]; then
            UNPINNED_ACTIONS+=("$workflow:$line_no - $action")
        fi
    done < <(grep -nE '^[[:space:]-]*uses:' "$workflow" || true)
done

# Report findings
if [[ ${#UNPINNED_ACTIONS[@]} -gt 0 ]]; then
    echo ""
    echo "❌ FAILURE: Found ${#UNPINNED_ACTIONS[@]} unpinned GitHub Actions!"
    echo ""
    echo "Actions must be pinned to full commit SHA (40 hex characters) to prevent supply chain attacks."
    echo ""
    echo "Unpinned actions:"
    echo ""
    for action in "${UNPINNED_ACTIONS[@]}"; do
        echo "  ❌ $action"
    done
    echo ""
    echo "Remediation:"
    echo "  1. Use Dependabot to automatically pin and update actions:"
    echo "     - Add .github/dependabot.yml with github-actions ecosystem"
    echo "     - Dependabot will create PRs with pinned SHAs"
    echo ""
    echo "  2. Manual pinning process:"
    echo "     - Find the commit SHA for the tag: git ls-remote <repo> <tag>"
    echo "     - Replace: uses: owner/repo@v4"
    echo "     - With: uses: owner/repo@<40-char-sha>  # v4"
    echo ""
    echo "  3. Allowlist (do not pin):"
    echo "     - Local actions: uses: ./path/to/action"
    echo "     - Docker actions: uses: docker://..."
    echo ""
    exit 1
fi

echo "✅ SUCCESS: All GitHub Actions are properly pinned to commit SHA"
exit 0
