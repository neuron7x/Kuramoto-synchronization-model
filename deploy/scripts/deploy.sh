#!/usr/bin/env bash
# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
# TradePulse deployment script for Kubernetes

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
ENVIRONMENT="${1:-staging}"
DRY_RUN="${DRY_RUN:-false}"
SKIP_VALIDATION="${SKIP_VALIDATION:-false}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEPLOY_DIR="$(dirname "$SCRIPT_DIR")"
KUSTOMIZE_OVERLAY="$DEPLOY_DIR/kustomize/overlays/$ENVIRONMENT"

# Print functions
info() { echo -e "${BLUE}ℹ${NC} $*"; }
success() { echo -e "${GREEN}✓${NC} $*"; }
warning() { echo -e "${YELLOW}⚠${NC} $*"; }
error() { echo -e "${RED}✗${NC} $*" >&2; }

# Usage
usage() {
    cat <<EOF
Usage: $(basename "$0") [ENVIRONMENT] [OPTIONS]

Deploy TradePulse to Kubernetes using Kustomize overlays.

ENVIRONMENT:
    staging     Deploy to staging environment (default)
    production  Deploy to production environment

OPTIONS:
    DRY_RUN=true              Preview changes without applying
    SKIP_VALIDATION=true      Skip pre-deployment validation

EXAMPLES:
    # Deploy to staging (default)
    ./deploy/scripts/deploy.sh

    # Deploy to production
    ./deploy/scripts/deploy.sh production

    # Preview production deployment
    DRY_RUN=true ./deploy/scripts/deploy.sh production

    # Deploy without validation (not recommended)
    SKIP_VALIDATION=true ./deploy/scripts/deploy.sh staging

PREREQUISITES:
    - kubectl configured with cluster access
    - Required secrets must exist:
      * tradepulse-secrets (audit-secret, oauth2-*)
      * tradepulse-mtls-client (client-ca.pem, client.crl)
      * tradepulse-timescale (url) - if using backup addon

For more information, see: deploy/README.md
EOF
    exit 0
}

# Check if help requested
if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
    usage
fi

# Validate environment
if [[ ! "$ENVIRONMENT" =~ ^(staging|production)$ ]]; then
    error "Invalid environment: $ENVIRONMENT"
    echo "Valid environments: staging, production"
    exit 1
fi

echo "======================================"
echo "  TradePulse Kubernetes Deployment"
echo "======================================"
echo ""
info "Environment: $ENVIRONMENT"
info "Overlay: $KUSTOMIZE_OVERLAY"
info "Dry run: $DRY_RUN"
echo ""

# Check prerequisites
info "Checking prerequisites..."

if ! command -v kubectl &> /dev/null; then
    error "kubectl not found. Please install from https://kubernetes.io/docs/tasks/tools/"
    exit 1
fi
success "kubectl found: $(kubectl version --client --short 2>/dev/null || kubectl version --client 2>&1 | head -1)"

# Check cluster connectivity
if ! kubectl cluster-info &> /dev/null; then
    error "Cannot connect to Kubernetes cluster"
    info "Please configure kubectl to connect to your cluster"
    exit 1
fi
success "Connected to cluster: $(kubectl config current-context)"

# Check if overlay exists
if [[ ! -d "$KUSTOMIZE_OVERLAY" ]]; then
    error "Overlay not found: $KUSTOMIZE_OVERLAY"
    exit 1
fi
success "Overlay directory found"

echo ""

# Run validation
if [[ "$SKIP_VALIDATION" != "true" ]]; then
    info "Running pre-deployment validation..."
    if [[ -x "$SCRIPT_DIR/validate.sh" ]]; then
        if "$SCRIPT_DIR/validate.sh"; then
            success "Validation passed"
        else
            error "Validation failed"
            exit 1
        fi
    else
        warning "Validation script not found or not executable"
    fi
    echo ""
fi

# Check for required secrets
NAMESPACE="tradepulse-$ENVIRONMENT"
info "Checking required secrets in namespace '$NAMESPACE'..."

check_secret() {
    local secret_name=$1
    if kubectl get secret "$secret_name" -n "$NAMESPACE" &> /dev/null; then
        success "Secret '$secret_name' exists"
        return 0
    else
        warning "Secret '$secret_name' not found"
        return 1
    fi
}

# Note: secrets might not exist if namespace doesn't exist yet
if kubectl get namespace "$NAMESPACE" &> /dev/null; then
    check_secret "tradepulse-secrets" || warning "  Run: kubectl create secret generic tradepulse-secrets -n $NAMESPACE ..."
    check_secret "tradepulse-mtls-client" || warning "  Run: kubectl create secret generic tradepulse-mtls-client -n $NAMESPACE ..."
else
    info "Namespace '$NAMESPACE' doesn't exist yet (will be created)"
fi

echo ""

# Build manifests
info "Building Kubernetes manifests..."
if ! kubectl kustomize "$KUSTOMIZE_OVERLAY" > /tmp/tradepulse-$ENVIRONMENT.yaml; then
    error "Failed to build manifests"
    exit 1
fi
resource_count=$(grep -c "^kind:" /tmp/tradepulse-$ENVIRONMENT.yaml || true)
success "Built $resource_count resources"

echo ""

# Show diff if possible
if kubectl get namespace "$NAMESPACE" &> /dev/null; then
    info "Checking for configuration changes..."
    if kubectl diff -k "$KUSTOMIZE_OVERLAY" &> /tmp/tradepulse-diff.txt; then
        info "No changes detected"
    else
        warning "Changes detected:"
        head -50 /tmp/tradepulse-diff.txt | sed 's/^/  /'
        echo ""
    fi
fi

# Apply or dry-run
if [[ "$DRY_RUN" == "true" ]]; then
    info "Dry run mode - showing manifest preview..."
    echo ""
    echo "===== Generated Manifests ====="
    head -100 /tmp/tradepulse-$ENVIRONMENT.yaml
    echo ""
    echo "===== End of Preview (first 100 lines) ====="
    info "Full manifest saved to: /tmp/tradepulse-$ENVIRONMENT.yaml"
    echo ""
    success "Dry run complete"
else
    warning "Applying changes to cluster..."
    
    # Check if running in non-interactive environment
    if [ -t 0 ]; then
        read -p "Continue with deployment to $ENVIRONMENT? (yes/no): " -t 30 confirm || {
            info "Timeout waiting for confirmation - defaulting to no"
            confirm="no"
        }
    else
        # Non-interactive mode - require explicit environment variable
        if [[ "${DEPLOY_CONFIRM:-no}" == "yes" ]]; then
            confirm="yes"
            info "Non-interactive mode - proceeding with deployment (DEPLOY_CONFIRM=yes)"
        else
            confirm="no"
            warning "Non-interactive mode - deployment cancelled (set DEPLOY_CONFIRM=yes to proceed)"
        fi
    fi
    
    if [[ "$confirm" != "yes" ]]; then
        info "Deployment cancelled"
        exit 0
    fi

    if kubectl apply -k "$KUSTOMIZE_OVERLAY"; then
        success "Deployment applied successfully"
    else
        error "Deployment failed"
        exit 1
    fi

    echo ""
    info "Waiting for deployment rollout..."
    if kubectl rollout status deployment/tradepulse-api -n "$NAMESPACE" --timeout=5m; then
        success "Deployment rolled out successfully"
    else
        error "Rollout failed or timed out"
        info "Check status with: kubectl get pods -n $NAMESPACE"
        exit 1
    fi

    echo ""
    info "Deployment status:"
    kubectl get all -n "$NAMESPACE" -l app.kubernetes.io/name=tradepulse-api

    echo ""
    success "✓ Deployment to $ENVIRONMENT completed successfully!"
    echo ""
    info "Next steps:"
    echo "  - Check pods: kubectl get pods -n $NAMESPACE"
    echo "  - View logs: kubectl logs -n $NAMESPACE deployment/tradepulse-api -f"
    echo "  - Check HPA: kubectl get hpa -n $NAMESPACE"
    echo "  - Port forward: kubectl port-forward -n $NAMESPACE svc/tradepulse-api 8000:80"
fi

echo ""
