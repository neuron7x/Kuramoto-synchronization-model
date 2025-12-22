#!/usr/bin/env bash
# Action Pinning Guard - Ensures GitHub Actions are pinned to commit SHA
# This script is used in CI to enforce supply chain security

set -euo pipefail

echo "🔒 Action Pinning Guard - Checking GitHub Actions pinning..."

python -m tools.ci.check_actions_pinned --workflows .github/workflows --fail-on-unpinned
