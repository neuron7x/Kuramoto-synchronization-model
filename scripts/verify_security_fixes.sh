#!/bin/bash
# Verification script for security vulnerability fixes
# This script verifies that all critical vulnerabilities have been addressed

set -euo pipefail

echo "🔍 Verifying security vulnerability fixes..."
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Counter for issues
CRITICAL_ISSUES=0

echo "📋 Checking constraints/security.txt for required package versions..."

# Check if constraints file exists
if [ ! -f "constraints/security.txt" ]; then
    echo -e "${RED}❌ ERROR: constraints/security.txt not found${NC}"
    exit 1
fi

# Verify configobj version
if grep -q "configobj>=5.0.9" constraints/security.txt; then
    echo -e "${GREEN}✅ configobj >= 5.0.9 (ReDoS fix)${NC}"
else
    echo -e "${RED}❌ MISSING: configobj >= 5.0.9${NC}"
    ((CRITICAL_ISSUES++))
fi

# Verify setuptools version
if grep -q "setuptools>=78.1.1" constraints/security.txt; then
    echo -e "${GREEN}✅ setuptools >= 78.1.1 (RCE & path traversal fix)${NC}"
else
    echo -e "${RED}❌ MISSING: setuptools >= 78.1.1${NC}"
    ((CRITICAL_ISSUES++))
fi

# Verify twisted version
if grep -q "twisted>=24.7.0" constraints/security.txt; then
    echo -e "${GREEN}✅ twisted >= 24.7.0 (XSS & request ordering fix)${NC}"
else
    echo -e "${RED}❌ MISSING: twisted >= 24.7.0${NC}"
    ((CRITICAL_ISSUES++))
fi

echo ""
echo "📊 Summary:"
if [ $CRITICAL_ISSUES -eq 0 ]; then
    echo -e "${GREEN}✅ All critical vulnerabilities have been addressed in constraints/security.txt${NC}"
    echo ""
    echo "🎉 Security fixes verified successfully!"
    echo ""
    echo "Next steps:"
    echo "1. Run: pip install -c constraints/security.txt -r requirements.txt"
    echo "2. Run: pip-audit --desc"
    echo "3. Run tests to ensure compatibility"
    exit 0
else
    echo -e "${RED}❌ Found $CRITICAL_ISSUES critical issues${NC}"
    echo ""
    echo "Please update constraints/security.txt with the required package versions."
    exit 1
fi
