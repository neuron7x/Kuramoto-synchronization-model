#!/usr/bin/env bash
# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
# Helper script to create required Kubernetes secrets for TradePulse

set -euo pipefail

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

info() { echo -e "${BLUE}ℹ${NC} $*"; }
success() { echo -e "${GREEN}✓${NC} $*"; }
warning() { echo -e "${YELLOW}⚠${NC} $*"; }
error() { echo -e "${RED}✗${NC} $*" >&2; }

NAMESPACE="${1:-tradepulse-staging}"
INTERACTIVE="${INTERACTIVE:-true}"

echo "======================================"
echo "  TradePulse Secrets Setup"
echo "======================================"
echo ""
info "Target namespace: $NAMESPACE"
echo ""

# Check if namespace exists
if ! kubectl get namespace "$NAMESPACE" &> /dev/null; then
    warning "Namespace '$NAMESPACE' doesn't exist"
    read -r -p "Create namespace? (yes/no): " create_ns
    if [[ "$create_ns" == "yes" ]]; then
        kubectl create namespace "$NAMESPACE"
        success "Namespace created"
    else
        error "Namespace required. Exiting."
        exit 1
    fi
fi

# Function to prompt for secret value
prompt_secret() {
    local description=$2
    local default_value="${3:-}"
    
    if [[ "$INTERACTIVE" == "true" ]]; then
        read -r -p "$description [$default_value]: " value
        echo "${value:-$default_value}"
    else
        echo "$default_value"
    fi
}

# Create tradepulse-secrets
info "Creating tradepulse-secrets..."
echo ""

# Generate or prompt for audit secret
AUDIT_SECRET=$(openssl rand -base64 32 2>/dev/null || echo "PLEASE_CHANGE_ME_$(date +%s)")
if [[ "$INTERACTIVE" == "true" ]]; then
    echo "Generated audit secret: $AUDIT_SECRET"
    read -r -p "Use generated secret? (yes/no): " use_gen
    if [[ "$use_gen" != "yes" ]]; then
        read -r -p "Enter audit secret: " AUDIT_SECRET
    fi
fi

OAUTH2_ISSUER=$(prompt_secret "OAUTH2_ISSUER" "OAuth2 Issuer URL" "https://auth.example.com")
OAUTH2_AUDIENCE=$(prompt_secret "OAUTH2_AUDIENCE" "OAuth2 Audience" "tradepulse-api")
OAUTH2_JWKS_URI=$(prompt_secret "OAUTH2_JWKS_URI" "OAuth2 JWKS URI" "https://auth.example.com/.well-known/jwks.json")

# Check if secret already exists
if kubectl get secret tradepulse-secrets -n "$NAMESPACE" &> /dev/null; then
    warning "Secret 'tradepulse-secrets' already exists"
    read -r -p "Overwrite? (yes/no): " overwrite
    if [[ "$overwrite" == "yes" ]]; then
        kubectl delete secret tradepulse-secrets -n "$NAMESPACE"
    else
        info "Skipping tradepulse-secrets creation"
        SKIP_APP_SECRETS=true
    fi
fi

if [[ "${SKIP_APP_SECRETS:-false}" != "true" ]]; then
    kubectl create secret generic tradepulse-secrets \
        --namespace="$NAMESPACE" \
        --from-literal=audit-secret="$AUDIT_SECRET" \
        --from-literal=oauth2-issuer="$OAUTH2_ISSUER" \
        --from-literal=oauth2-audience="$OAUTH2_AUDIENCE" \
        --from-literal=oauth2-jwks-uri="$OAUTH2_JWKS_URI"
    
    success "Created tradepulse-secrets"
fi

echo ""

# Create tradepulse-mtls-client
info "Creating tradepulse-mtls-client..."
echo ""

if [[ "$INTERACTIVE" == "true" ]]; then
    read -r -p "Path to client CA certificate (client-ca.pem): " CA_CERT_PATH
    read -r -p "Path to certificate revocation list (client.crl): " CRL_PATH
else
    CA_CERT_PATH="${CA_CERT_PATH:-./certs/client-ca.pem}"
    CRL_PATH="${CRL_PATH:-./certs/client.crl}"
fi

# Check if files exist
if [[ ! -f "$CA_CERT_PATH" ]]; then
    warning "CA certificate not found: $CA_CERT_PATH"
    info "Creating self-signed CA for development..."
    
    # Set restrictive umask for security
    old_umask=$(umask)
    umask 077
    
    mkdir -p /tmp/tradepulse-certs
    openssl req -x509 -newkey rsa:4096 -keyout /tmp/tradepulse-certs/ca-key.pem \
        -out /tmp/tradepulse-certs/client-ca.pem -days 365 -nodes \
        -subj "/CN=TradePulse Dev CA/O=TradePulse/C=US" 2>/dev/null
    
    # Restore original umask
    umask "$old_umask"
    
    CA_CERT_PATH="/tmp/tradepulse-certs/client-ca.pem"
    success "Generated development CA at $CA_CERT_PATH"
    warning "⚠ DO NOT USE IN PRODUCTION"
fi

if [[ ! -f "$CRL_PATH" ]]; then
    warning "CRL not found: $CRL_PATH"
    info "Creating empty CRL for development..."
    
    touch /tmp/tradepulse-certs/client.crl
    CRL_PATH="/tmp/tradepulse-certs/client.crl"
    success "Created empty CRL at $CRL_PATH"
fi

# Check if secret already exists
if kubectl get secret tradepulse-mtls-client -n "$NAMESPACE" &> /dev/null; then
    warning "Secret 'tradepulse-mtls-client' already exists"
    read -r -p "Overwrite? (yes/no): " overwrite
    if [[ "$overwrite" == "yes" ]]; then
        kubectl delete secret tradepulse-mtls-client -n "$NAMESPACE"
    else
        info "Skipping tradepulse-mtls-client creation"
        SKIP_MTLS_SECRET=true
    fi
fi

if [[ "${SKIP_MTLS_SECRET:-false}" != "true" ]]; then
    kubectl create secret generic tradepulse-mtls-client \
        --namespace="$NAMESPACE" \
        --from-file=client-ca.pem="$CA_CERT_PATH" \
        --from-file=client.crl="$CRL_PATH"
    
    success "Created tradepulse-mtls-client"
fi

echo ""

# Create tradepulse-timescale (optional, for backups)
info "Creating tradepulse-timescale (optional, for database backups)..."
echo ""

if [[ "$INTERACTIVE" == "true" ]]; then
    read -r -p "Create TimescaleDB secret? (yes/no): " create_db
else
    create_db="no"
fi

if [[ "$create_db" == "yes" ]]; then
    DB_URL=$(prompt_secret "DATABASE_URL" "TimescaleDB connection URL" "postgresql://user:pass@host:5432/db?sslmode=verify-full")
    
    if kubectl get secret tradepulse-timescale -n "$NAMESPACE" &> /dev/null; then
        warning "Secret 'tradepulse-timescale' already exists"
        read -r -p "Overwrite? (yes/no): " overwrite
        if [[ "$overwrite" == "yes" ]]; then
            kubectl delete secret tradepulse-timescale -n "$NAMESPACE"
        else
            info "Skipping tradepulse-timescale creation"
            SKIP_DB_SECRET=true
        fi
    fi
    
    if [[ "${SKIP_DB_SECRET:-false}" != "true" ]]; then
        kubectl create secret generic tradepulse-timescale \
            --namespace="$NAMESPACE" \
            --from-literal=url="$DB_URL"
        
        success "Created tradepulse-timescale"
    fi
else
    info "Skipping TimescaleDB secret (not required if backups addon is disabled)"
fi

echo ""
echo "======================================"
success "✓ Secrets setup complete!"
echo ""
info "Verify secrets with:"
echo "  kubectl get secrets -n $NAMESPACE"
echo ""
info "View secret details (non-sensitive):"
echo "  kubectl describe secret tradepulse-secrets -n $NAMESPACE"
echo ""
info "Next steps:"
echo "  1. Review the secrets"
echo "  2. Deploy TradePulse: ./deploy/scripts/deploy.sh"
echo ""
