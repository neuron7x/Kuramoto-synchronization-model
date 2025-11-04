#!/usr/bin/env bash
# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
# Validation script for Kubernetes manifests in the deploy directory

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEPLOY_DIR="$(dirname "$SCRIPT_DIR")"

echo "======================================"
echo "TradePulse Deployment Validation"
echo "======================================"
echo ""

# Track validation status
VALIDATION_ERRORS=0

# Function to print status
print_status() {
    local status=$1
    local message=$2
    if [ "$status" = "pass" ]; then
        echo -e "${GREEN}✓${NC} $message"
    elif [ "$status" = "fail" ]; then
        echo -e "${RED}✗${NC} $message"
        ((VALIDATION_ERRORS++))
    elif [ "$status" = "warn" ]; then
        echo -e "${YELLOW}⚠${NC} $message"
    else
        echo "  $message"
    fi
}

# Check prerequisites
echo "Checking prerequisites..."
if command -v kubectl &> /dev/null; then
    print_status "pass" "kubectl found: $(kubectl version --client --short 2>/dev/null || kubectl version --client 2>&1 | head -1)"
else
    print_status "fail" "kubectl not found - install from https://kubernetes.io/docs/tasks/tools/"
fi

if command -v kustomize &> /dev/null; then
    print_status "pass" "kustomize found: $(kustomize version --short 2>/dev/null || kustomize version 2>&1 | head -1)"
else
    print_status "warn" "kustomize not found (kubectl has built-in kustomize support)"
fi

echo ""

# Validate standalone manifests
echo "Validating standalone manifests (YAML syntax)..."
for manifest in "$DEPLOY_DIR"/*.yaml; do
    if [ -f "$manifest" ]; then
        filename=$(basename "$manifest")
        if python3 -c "import yaml, sys; list(yaml.safe_load_all(open('$manifest')))" 2>/dev/null; then
            print_status "pass" "$filename has valid YAML syntax"
        else
            print_status "fail" "$filename YAML syntax validation failed"
            python3 -c "import yaml, sys; list(yaml.safe_load_all(open('$manifest')))" 2>&1 | sed 's/^/    /'
        fi
    fi
done

echo ""

# Validate base kustomization
echo "Validating base kustomization..."
if kubectl kustomize "$DEPLOY_DIR/kustomize/base" > /dev/null 2>&1; then
    print_status "pass" "Base kustomization is valid"
    resource_count=$(kubectl kustomize "$DEPLOY_DIR/kustomize/base" | grep -c "^kind:" || true)
    print_status "info" "  Generated $resource_count resources"
else
    print_status "fail" "Base kustomization validation failed"
    kubectl kustomize "$DEPLOY_DIR/kustomize/base" 2>&1 | sed 's/^/    /'
fi

echo ""

# Validate staging overlay
echo "Validating staging overlay..."
if kubectl kustomize "$DEPLOY_DIR/kustomize/overlays/staging" > /dev/null 2>&1; then
    print_status "pass" "Staging overlay is valid"
    resource_count=$(kubectl kustomize "$DEPLOY_DIR/kustomize/overlays/staging" | grep -c "^kind:" || true)
    print_status "info" "  Generated $resource_count resources"
else
    print_status "fail" "Staging overlay validation failed"
    kubectl kustomize "$DEPLOY_DIR/kustomize/overlays/staging" 2>&1 | sed 's/^/    /'
fi

echo ""

# Validate production overlay
echo "Validating production overlay..."
if kubectl kustomize "$DEPLOY_DIR/kustomize/overlays/production" > /dev/null 2>&1; then
    print_status "pass" "Production overlay is valid"
    resource_count=$(kubectl kustomize "$DEPLOY_DIR/kustomize/overlays/production" | grep -c "^kind:" || true)
    print_status "info" "  Generated $resource_count resources"
else
    print_status "fail" "Production overlay validation failed"
    kubectl kustomize "$DEPLOY_DIR/kustomize/overlays/production" 2>&1 | sed 's/^/    /'
fi

echo ""

# Check for required ConfigMaps
echo "Checking addon configurations..."
for addon_config in \
    "$DEPLOY_DIR/kustomize/addons/logging/config/filebeat.yml" \
    "$DEPLOY_DIR/kustomize/addons/logging/config/logstash.conf"; do
    if [ -f "$addon_config" ]; then
        print_status "pass" "$(basename "$addon_config") exists"
    else
        print_status "fail" "$(basename "$addon_config") not found at $addon_config"
    fi
done

echo ""

# Validate YAML syntax for all files
echo "Validating YAML syntax..."
yaml_errors=0
while IFS= read -r -d '' yaml_file; do
    if python3 -c "import yaml, sys; [_ for _ in yaml.safe_load_all(open('$yaml_file'))]" 2>/dev/null; then
        : # Silent success
    else
        print_status "fail" "YAML syntax error in $yaml_file"
        ((yaml_errors++))
    fi
done < <(find "$DEPLOY_DIR" -name "*.yaml" -o -name "*.yml" -print0)

if [ $yaml_errors -eq 0 ]; then
    print_status "pass" "All YAML files have valid syntax"
fi

echo ""

# Security checks
echo "Running security checks..."

# Check for resources without resource limits
echo "  Checking for missing resource limits..."
staging_output=$(kubectl kustomize "$DEPLOY_DIR/kustomize/overlays/staging" 2>/dev/null || echo "")
if echo "$staging_output" | grep -A 20 "kind: Deployment" | grep -q "resources:"; then
    print_status "pass" "Deployments have resource specifications"
else
    print_status "warn" "Some deployments may be missing resource specifications"
fi

# Check for security contexts
if echo "$staging_output" | grep -q "securityContext:"; then
    print_status "pass" "Security contexts are configured"
else
    print_status "warn" "Security contexts may be missing"
fi

# Check for network policies
if echo "$staging_output" | grep -q "kind: NetworkPolicy"; then
    print_status "pass" "NetworkPolicies are defined"
else
    print_status "warn" "No NetworkPolicies found - consider adding network policies for security"
fi

echo ""

# Summary
echo "======================================"
if [ $VALIDATION_ERRORS -eq 0 ]; then
    echo -e "${GREEN}✓ All validations passed!${NC}"
    echo ""
    echo "Next steps:"
    echo "  1. Review the generated manifests:"
    echo "     kubectl kustomize deploy/kustomize/overlays/staging"
    echo ""
    echo "  2. Create required secrets before deployment"
    echo ""
    echo "  3. Deploy to staging:"
    echo "     kubectl apply -k deploy/kustomize/overlays/staging"
    echo ""
    exit 0
else
    echo -e "${RED}✗ Validation failed with $VALIDATION_ERRORS error(s)${NC}"
    echo ""
    echo "Please fix the errors above before deploying."
    exit 1
fi
