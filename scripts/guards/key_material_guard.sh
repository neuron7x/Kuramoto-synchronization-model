#!/usr/bin/env bash
# Key Material Guard - Prevents private keys from being committed
# This script is used in CI to enforce security policies

set -euo pipefail

echo "🔒 Key Material Guard - Checking for tracked private keys..."

# Check for tracked key files with private key patterns
echo "Checking git-tracked files for private key patterns..."
TRACKED_KEYS=()

# Check for .key and .key.pem files
while IFS= read -r file; do
    if [[ -f "$file" ]]; then
        TRACKED_KEYS+=("$file")
    fi
done < <(git ls-files | grep -E '\.(key|key\.pem)$' || true)

# Check for PEM files containing private key headers
while IFS= read -r file; do
    if [[ -f "$file" ]] && grep -q "BEGIN.*PRIVATE KEY" "$file" 2>/dev/null; then
        # Avoid duplicates
        if [[ ! " ${TRACKED_KEYS[*]} " =~ " ${file} " ]]; then
            TRACKED_KEYS+=("$file (contains PRIVATE KEY header)")
        fi
    fi
done < <(git ls-files | grep '\.pem$' || true)

# Report findings
if [[ ${#TRACKED_KEYS[@]} -gt 0 ]]; then
    echo "❌ FAILURE: Private keys detected in tracked files!"
    echo ""
    echo "The following files contain private keys and must NOT be committed:"
    echo ""
    for key in "${TRACKED_KEYS[@]}"; do
        echo "  ❌ $key"
    done
    echo ""
    echo "Remediation steps:"
    echo "  1. Remove from git tracking:"
    echo "     git rm --cached <file>"
    echo ""
    echo "  2. Add to .gitignore:"
    echo "     echo '<pattern>' >> .gitignore"
    echo ""
    echo "  3. For development keys, generate them locally:"
    echo "     See configs/tls/dev/README.md"
    echo ""
    exit 1
fi

echo "✅ SUCCESS: No private keys detected in tracked files"
exit 0
