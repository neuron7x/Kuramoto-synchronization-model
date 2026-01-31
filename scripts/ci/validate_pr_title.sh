#!/usr/bin/env bash
# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
# Validate PR title against Conventional Commits specification.
# Usage: validate_pr_title.sh "<PR title>"
# Types align with towncrier fragment types in pyproject.toml.
set -euo pipefail

TITLE="${1:-}"

if [ -z "$TITLE" ]; then
  echo "::error::Usage: validate_pr_title.sh '<PR title>'"
  exit 1
fi

# Valid types (must match pyproject.toml [tool.towncrier.type] directories):
#   feat=feature, fix=bugfix, perf=performance, refactor=maintenance,
#   docs, test=tests, ci, build, security, chore, revert
PATTERN='^(feat|fix|perf|refactor|docs|test|ci|build|chore|security|revert)(\([a-zA-Z0-9_/-]+\))?: .{5,}'

if echo "$TITLE" | grep -qE "$PATTERN"; then
  echo "OK: PR title is valid — '$TITLE'"
  exit 0
fi

echo "::error::PR title does not match Conventional Commits format"
echo ""
echo "  Expected: type(scope): description (≥5 chars)"
echo "  Valid types: feat|fix|perf|refactor|docs|test|ci|build|chore|security|revert"
echo "  Got: '$TITLE'"
echo ""
echo "  Examples:"
echo "    feat(engine): add Ricci flow adaptive step sizing"
echo "    fix(execution): correct OMS fill reconciliation"
echo "    ci: add PR gate workflow"
exit 1
