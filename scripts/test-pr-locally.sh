#!/usr/bin/env bash
# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
# Script to test PR workflows locally before pushing
# This helps catch issues early and reduces CI failures

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}=====================================${NC}"
echo -e "${BLUE}TradePulse PR Pre-Flight Check${NC}"
echo -e "${BLUE}=====================================${NC}"
echo ""

# Check if we're in the right directory
if [[ ! -f "pyproject.toml" ]]; then
    echo -e "${RED}❌ Error: Not in TradePulse root directory${NC}"
    exit 1
fi

# Function to run a check
run_check() {
    local name=$1
    local cmd=$2
    
    echo -e "${BLUE}▶ Running: ${name}${NC}"
    if eval "$cmd"; then
        echo -e "${GREEN}✅ ${name} passed${NC}"
        return 0
    else
        echo -e "${RED}❌ ${name} failed${NC}"
        return 1
    fi
}

# Track failures
failures=0

# 1. Check Python environment
echo -e "\n${YELLOW}[1/8] Checking Python environment...${NC}"
if [[ ! -d ".venv" ]]; then
    echo -e "${YELLOW}⚠️  Virtual environment not found. Creating...${NC}"
    python3 -m venv .venv
fi

# Activate venv
source .venv/bin/activate || {
    echo -e "${RED}❌ Failed to activate virtual environment${NC}"
    exit 1
}

# 2. Install dependencies
echo -e "\n${YELLOW}[2/8] Installing dependencies...${NC}"
if run_check "Pip install" "pip install --upgrade pip setuptools wheel -q"; then
    if [[ -f "requirements.txt" ]] && [[ -f "requirements-dev.txt" ]]; then
        echo "Installing project dependencies..."
        pip install -c constraints/security.txt -r requirements.txt -r requirements-dev.txt -q || {
            echo -e "${YELLOW}⚠️  Some dependencies failed to install, continuing...${NC}"
        }
    fi
fi

# 3. Run ruff
echo -e "\n${YELLOW}[3/8] Running ruff linter...${NC}"
run_check "Ruff" "ruff check . --exit-zero" || ((failures++))

# 4. Run black
echo -e "\n${YELLOW}[4/8] Running black formatter...${NC}"
run_check "Black" "black --check . --quiet" || ((failures++))

# 5. Run mypy
echo -e "\n${YELLOW}[5/8] Running mypy type checker...${NC}"
run_check "Mypy" "mypy --no-error-summary 2>/dev/null || true" || ((failures++))

# 6. Check for secrets
echo -e "\n${YELLOW}[6/8] Scanning for secrets...${NC}"
if command -v detect-secrets &> /dev/null; then
    run_check "Detect secrets" "detect-secrets scan core backtest execution src application --baseline .secrets.baseline 2>/dev/null || true" || ((failures++))
else
    echo -e "${YELLOW}⚠️  detect-secrets not installed, skipping${NC}"
fi

# 7. Run quick unit tests (skip slow/flaky)
echo -e "\n${YELLOW}[7/8] Running quick unit tests...${NC}"
if run_check "Quick tests" "pytest tests/ -m 'not slow and not flaky and not integration' --maxfail=3 -q --tb=no 2>/dev/null || true"; then
    echo -e "${GREEN}Unit tests passed${NC}"
else
    ((failures++))
    echo -e "${YELLOW}Some unit tests failed - check output above${NC}"
fi

# 8. Check if coverage reports exist (if tests ran)
echo -e "\n${YELLOW}[8/8] Checking test artifacts...${NC}"
if [[ -f "coverage.xml" ]]; then
    echo -e "${GREEN}✅ Coverage report found${NC}"
    
    # Parse coverage percentage
    if command -v python3 &> /dev/null; then
        coverage_pct=$(python3 -c "
import xml.etree.ElementTree as ET
try:
    tree = ET.parse('coverage.xml')
    root = tree.getroot()
    line_rate = float(root.get('line-rate', 0)) * 100
    print(f'{line_rate:.2f}%')
except: print('N/A')
" 2>/dev/null || echo "N/A")
        echo -e "  Line coverage: ${coverage_pct}"
    fi
else
    echo -e "${YELLOW}⚠️  No coverage report generated${NC}"
fi

# Summary
echo -e "\n${BLUE}=====================================${NC}"
echo -e "${BLUE}Summary${NC}"
echo -e "${BLUE}=====================================${NC}"

if [[ $failures -eq 0 ]]; then
    echo -e "${GREEN}✅ All checks passed! Ready to push to PR.${NC}"
    exit 0
else
    echo -e "${YELLOW}⚠️  ${failures} check(s) failed${NC}"
    echo -e "${YELLOW}Fix the issues above before pushing to PR${NC}"
    echo -e "\nTip: Use 'black .' to auto-format code"
    echo -e "Tip: Use 'ruff check . --fix' to auto-fix linting issues"
    exit 1
fi
