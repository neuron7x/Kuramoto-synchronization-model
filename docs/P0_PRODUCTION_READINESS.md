# P0 Production Readiness Implementation

This document describes the P0 (Priority Zero) production readiness features implemented for TradePulse before large-scale production deployment.

## Overview

The P0 initiative ensures TradePulse meets enterprise-grade production requirements with:

1. ✅ Git tag-based versioning with setuptools_scm
2. ✅ Helm deployment charts with security hardening
3. ✅ Multi-language security scanning (CodeQL, Semgrep)
4. ✅ SBOM generation and signing
5. ✅ Enhanced secret scanning
6. ✅ Dependency pinning enforcement
7. ✅ Kubernetes runtime security policies
8. ✅ SLO gates with automatic rollback

## 1. Version Management

### Implementation

**setuptools_scm** is configured to derive version from git tags, providing a single source of truth for version information.

**Configuration**: `pyproject.toml`
```toml
[build-system]
requires = ["setuptools>=69", "setuptools_scm>=8", "wheel"]

[tool.setuptools_scm]
version_file = "src/_version.py"
fallback_version = "0.1.0"
```

**Usage**:
```bash
# Create a release tag
git tag -a v1.0.0 -m "Release 1.0.0"

# Version is automatically derived
python -m setuptools_scm
# Output: 1.0.0

# Development builds include commit info
# Output: 1.0.0.dev42+g1234567
```

**CI Gate**: `.github/workflows/version-gate.yml`
- Fails PR if version doesn't match latest tag
- Allows development versions (with .dev suffix)
- Enforces exact match for release builds

**Benefits**:
- Single source of truth (git tags)
- Automatic version bumping
- Traceable releases
- No manual version file updates

## 2. Helm Deployment Charts

### Structure

```
deploy/helm/tradepulse/
├── Chart.yaml              # Umbrella chart
├── values.yaml             # Global configuration
└── charts/
    ├── sandbox/            # Sandbox service
    ├── admin/              # Admin interface
    └── observability/      # Monitoring stack
```

### Security Features

**Pod Security Context**:
```yaml
securityContext:
  runAsNonRoot: true
  runAsUser: 1000
  fsGroup: 1000
  seccompProfile:
    type: RuntimeDefault

containerSecurityContext:
  allowPrivilegeEscalation: false
  readOnlyRootFilesystem: true
  capabilities:
    drop: [ALL]
```

**Network Policies**:
- East-west traffic control
- Ingress: namespace + monitoring only
- Egress: DNS, services, OTEL collector

**Resource Management**:
- CPU/memory requests and limits
- Horizontal Pod Autoscaler (HPA)
- Pod Disruption Budget (PDB)

**Observability**:
- ServiceMonitor for Prometheus
- OpenTelemetry integration
- Metrics endpoints

### CI Testing

**Workflow**: `.github/workflows/helm.yml`

Tests include:
1. **Helm lint**: Validates chart structure
2. **Template validation**: kubeval checks manifests
3. **Kind smoke test**: Full deployment in kind cluster
4. **Security scans**: Kubescape and Polaris

### Usage

```bash
# Install complete stack
helm install tradepulse ./deploy/helm/tradepulse \
  --namespace tradepulse \
  --create-namespace

# Upgrade
helm upgrade tradepulse ./deploy/helm/tradepulse

# Uninstall
helm uninstall tradepulse -n tradepulse
```

See `deploy/helm/README.md` for detailed documentation.

## 3. Security Scanning

### CodeQL (Python)

**Workflow**: `.github/workflows/security.yml`

- **Language**: Python
- **Queries**: security-extended
- **Upload**: SARIF to GitHub Security tab
- **Blocking**: Manual review of critical/high findings

### Semgrep (Multi-language)

**Workflow**: `.github/workflows/semgrep.yml`

- **Languages**: Python, TypeScript, Rust, Go
- **Rules**: `--config auto` (community rules)
- **Severity**: ERROR and WARNING
- **Blocking**: Critical/high severity findings fail PR

### Configuration

Semgrep runs automatically on:
- Push to main/develop
- All pull requests
- Weekly schedule (Monday 00:00 UTC)

## 4. SBOM and Supply Chain

### SBOM Generation

**Workflow**: `.github/workflows/sbom.yml`

Generates Software Bill of Materials in two formats:
- **CycloneDX JSON**: Machine-readable
- **CycloneDX XML**: Human-readable

### Signing with Cosign

**Implementation**:
```bash
# Sign SBOM (keyless)
cosign sign-blob --yes \
  --bundle sbom/cyclonedx-sbom.json.bundle \
  sbom/cyclonedx-sbom.json

# Verify signature
cosign verify-blob \
  --bundle sbom/cyclonedx-sbom.json.bundle \
  sbom/cyclonedx-sbom.json
```

### CI Gates

- ✅ SBOM must be generated for all images
- ✅ SBOM must be signed with cosign
- ✅ SBOM age must be <24 hours
- ✅ Signature verification must pass

## 5. Secret Scanning

### Tools

1. **detect-secrets**: Baseline scanning
2. **Gitleaks**: Git history scanning
3. **TruffleHog**: High-entropy secret detection

### Integration

**Pre-commit**: `.pre-commit-config.yaml`
```yaml
- repo: https://github.com/Yelp/detect-secrets
  hooks:
    - id: detect-secrets
      args: ["--baseline", ".secrets.baseline"]

- repo: https://github.com/gitleaks/gitleaks
  hooks:
    - id: gitleaks
```

**CI**: `.github/workflows/security.yml`
```yaml
- name: Run Gitleaks
  uses: gitleaks/gitleaks-action@v2

- name: Run TruffleHog
  uses: trufflesecurity/trufflehog@main
  with:
    extra_args: --only-verified
```

### Baseline Management

Update baseline when adding intentional test secrets:
```bash
detect-secrets scan --baseline .secrets.baseline
```

## 6. Dependency Pinning

### Python

**Tool**: pip-compile

**Files**:
- `requirements.txt`: High-level dependencies
- `requirements.lock`: Pinned versions (generated)
- `requirements-dev.txt`: Development dependencies
- `requirements-dev.lock`: Pinned dev versions (generated)

**Update**:
```bash
pip-compile --upgrade --output-file=requirements.lock requirements.txt
pip-compile --upgrade --output-file=requirements-dev.lock requirements-dev.txt
```

### Node.js

**File**: `ui/dashboard/package-lock.json`

**Update**:
```bash
cd ui/dashboard
npm install
```

### Rust

**File**: `rust/tradepulse-accel/Cargo.lock`

**Update**:
```bash
cd rust/tradepulse-accel
cargo update
```

### Go

**File**: `go.sum`

**Update**:
```bash
go mod tidy
```

### CI Gate

**Workflow**: `.github/workflows/dependency-pinning.yml`

Enforces:
- ✅ `requirements.lock` exists and contains pinned versions
- ✅ `requirements-dev.lock` exists
- ✅ `package-lock.json` exists for Node.js projects
- ✅ `Cargo.lock` exists for Rust projects
- ✅ `go.sum` exists for Go projects

## 7. Kubernetes Runtime Policies

### Security Standards

**Pod Security Admission**:
```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: tradepulse
  labels:
    pod-security.kubernetes.io/enforce: baseline
    pod-security.kubernetes.io/audit: restricted
    pod-security.kubernetes.io/warn: restricted
```

**Security Context** (applied to all pods):
- `runAsNonRoot: true`
- `runAsUser: 1000`
- `fsGroup: 1000`
- `seccompProfile: RuntimeDefault`
- `allowPrivilegeEscalation: false`
- `readOnlyRootFilesystem: true`
- `capabilities.drop: [ALL]`

### Network Policies

Implemented for all services:
- Ingress from namespace and monitoring only
- Egress to DNS, namespace services, and OTEL collector

### Resource Management

All containers have:
```yaml
resources:
  requests:
    cpu: 100m
    memory: 256Mi
  limits:
    cpu: 1000m
    memory: 1Gi
```

### CI Validation

**Tools**:
- **Kubescape**: NSA/MITRE frameworks
- **Polaris**: Best practices validation

**Workflow**: `.github/workflows/helm.yml`
```yaml
- name: Run Kubescape scan
  uses: kubescape/github-action@v3
  with:
    frameworks: "nsa,mitre"
    failedThreshold: 30
    severityThreshold: high
```

## 8. SLO Gates and Auto-Rollback

### SLO Thresholds

**Configuration**:
```yaml
slo:
  errorBudget: 0.001          # 99.9% uptime
  latencyP99Threshold: 500     # milliseconds
  errorRateThreshold: 0.01     # 1%
  minCanaryDuration: 15        # minutes
```

### Canary Evaluation

**Workflow**: `.github/workflows/slo-gate.yml`

**Process**:
1. Deploy canary version
2. Wait minimum duration (15 minutes)
3. Query Prometheus for metrics:
   - Error rate
   - P99 latency
   - Availability
   - Request rate
4. Evaluate against SLO thresholds
5. Promote or rollback

### Auto-Rollback

**Triggers**:
- Error rate exceeds 1%
- P99 latency exceeds 500ms
- Availability below 99.9%

**Actions**:
1. Execute `kubectl rollout undo`
2. Scale canary to 0 replicas
3. Notify via GitHub comment
4. Fail workflow

### Promotion

If all SLO checks pass:
1. Update production deployment with canary image
2. Wait for rollout completion
3. Scale down canary
4. Notify success

### Metrics Collection

**Prometheus Queries**:
```promql
# Error rate
rate(http_requests_total{service="...",status=~"5.."}[5m])
/ rate(http_requests_total{service="..."}[5m])

# P99 latency
histogram_quantile(0.99,
  rate(http_request_duration_seconds_bucket{service="..."}[5m]))

# Availability
avg_over_time(up{service="..."}[15m])
```

## CI/CD Integration

All P0 features are integrated into CI/CD:

```
Pull Request
├── version-gate.yml         ✓ Version matches tag
├── dependency-pinning.yml   ✓ Dependencies pinned
├── security.yml             ✓ Secrets, CodeQL, dependencies
├── semgrep.yml              ✓ Multi-language security
├── sbom.yml                 ✓ SBOM generation & signing
└── helm.yml                 ✓ Chart validation & security

Push to main/develop
├── All PR checks
├── SBOM signing (not on PR)
└── Container image builds

Release (tag)
└── slo-gate.yml             ✓ Canary evaluation & rollback
```

## Best Practices

### Versioning

1. Use semantic versioning (vX.Y.Z)
2. Create annotated tags: `git tag -a v1.0.0 -m "Release 1.0.0"`
3. Push tags: `git push --tags`

### Helm Charts

1. Always lint before committing: `helm lint deploy/helm/tradepulse`
2. Test in kind cluster before PR
3. Update chart version in `Chart.yaml` for changes
4. Document configuration changes in `values.yaml`

### Security

1. Run pre-commit hooks: `pre-commit run --all-files`
2. Review security scan results in PR
3. Update `.secrets.baseline` when adding test secrets
4. Keep dependencies up-to-date

### Dependencies

1. Update lock files when changing dependencies
2. Test builds with lock files to ensure reproducibility
3. Review security advisories for dependencies

### Deployments

1. Use canary deployments for major changes
2. Monitor SLO metrics during canary evaluation
3. Have rollback plan ready
4. Document changes in release notes

## Monitoring and Observability

### Metrics

**Prometheus ServiceMonitor** scrapes:
- `/metrics` endpoint on port 9090
- Interval: 30s
- Timeout: 10s

### Tracing

**OpenTelemetry Collector**:
- Endpoint: `http://otel-collector:4317`
- Protocols: gRPC (4317), HTTP (4318)
- Exporters: Prometheus, logging

### Dashboards

Grafana dashboards (when enabled):
- Service metrics
- SLO tracking
- Error rates and latency
- Resource utilization

## Troubleshooting

### Version mismatch in CI

**Problem**: Version gate fails

**Solution**:
```bash
# Check current version
python -m setuptools_scm

# Create matching tag
git tag -a vX.Y.Z -m "Release X.Y.Z"
git push --tags
```

### Helm chart fails to deploy

**Problem**: Pod security violations

**Solution**: Check security context in `values.yaml` and ensure:
- User is non-root (UID 1000)
- Read-only root filesystem
- No privileged escalation

### SBOM signing fails

**Problem**: cosign verification fails

**Solution**: Check that:
- SBOM file exists
- Bundle file is present
- Using keyless signing (default)

### Canary rollback triggered

**Problem**: SLO violation

**Solution**:
1. Check Prometheus metrics
2. Review application logs
3. Investigate root cause
4. Fix issues
5. Redeploy

## References

- [setuptools_scm documentation](https://setuptools-scm.readthedocs.io/)
- [Helm documentation](https://helm.sh/docs/)
- [CodeQL documentation](https://codeql.github.com/docs/)
- [Semgrep documentation](https://semgrep.dev/docs/)
- [Cosign documentation](https://docs.sigstore.dev/cosign/overview/)
- [Kubernetes Pod Security Standards](https://kubernetes.io/docs/concepts/security/pod-security-standards/)
- [SLO/SLI Best Practices](https://sre.google/workbook/implementing-slos/)
