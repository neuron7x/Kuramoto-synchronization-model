# Deploy Directory Changelog

All notable changes to the deployment configurations will be documented in this file.

## [Unreleased]

### Added
- Comprehensive README.md with quick start guides and troubleshooting
- NetworkPolicy resources for enhanced security (deny-all default + allow rules)
- ResourceQuota and LimitRange for staging and production namespaces
- Ingress configuration with TLS, mTLS, rate limiting, and security headers
- Environment-specific ingress patches (staging and production)
- Validation script (`scripts/validate.sh`) for pre-deployment checks
- Deployment script (`scripts/deploy.sh`) with dry-run support
- Secrets creation helper script (`scripts/create-secrets.sh`)
- Enhanced Prometheus configuration with Kubernetes service discovery examples
- Expanded chaos engineering scenarios (network partition, CPU stress, pod failure)
- Local configuration files for logging addon (filebeat.yml, logstash.conf)

### Changed
- Fixed kustomize configuration to reference local config files instead of parent directories
- Updated logging addon kustomization to use local config directory
- Fixed ClusterRoleBinding namespace reference in filebeat RBAC
- Improved chaos.yml with multiple failure scenarios and deadlines
- Enhanced prometheus.yml with better documentation and K8s SD examples
- Updated base kustomization.yaml to include NetworkPolicy and Ingress resources
- Updated namespace kustomizations to include ResourceQuota

### Removed
- Duplicate namespace YAML files in `kustomize/namespaces/` (kept only in subdirectories)
- Problematic replacements configuration in logging addon kustomization

### Fixed
- Kustomize security violation: files now within allowed directory structure
- Missing namespace in ClusterRoleBinding (now uses environment-specific value)
- All kustomize overlays now build successfully (staging: 22 resources, production: 23 resources)

## [Previous] - Before Improvements

### Existing Configuration
- Base Kubernetes manifests (deployment, service, serviceaccount)
- Kustomize overlays for staging and production
- PodDisruptionBudget for high availability
- HorizontalPodAutoscaler with custom metrics
- Logging addon with Filebeat and Logstash
- Database backup CronJob for TimescaleDB
- Chaos Mesh workflow for resilience testing
- K6 load test script for HPA validation
- Basic Prometheus scrape configuration

---

For deployment instructions, see [README.md](README.md).
For general project changes, see [../CHANGELOG.md](../CHANGELOG.md).
