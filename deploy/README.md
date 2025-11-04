# TradePulse Deployment Configuration

This directory contains Kubernetes deployment configurations and related infrastructure for TradePulse. The deployment manifests support both simple kubectl-based deployments and advanced Kustomize overlays for staging and production environments.

## Directory Structure

```
deploy/
├── README.md                          # This file
├── tradepulse-deployment.yaml         # Standalone Kubernetes deployment
├── tradepulse-service.yaml            # Standalone Kubernetes service & PDB
├── tradepulse-serviceaccount.yaml     # Standalone Kubernetes service account
├── prometheus.yml                     # Prometheus scrape configuration
├── chaos/                             # Chaos engineering experiments
│   └── chaos.yml                      # Chaos Mesh workflow definitions
├── loadtests/                         # Load testing scripts
│   └── hpa-k6.js                      # K6 load test for HPA validation
└── kustomize/                         # Kustomize-based deployment
    ├── base/                          # Base configuration for all environments
    │   ├── kustomization.yaml
    │   ├── deployment.yaml
    │   ├── service.yaml
    │   ├── serviceaccount.yaml
    │   ├── pdb.yaml                   # PodDisruptionBudget
    │   └── hpa.yaml                   # HorizontalPodAutoscaler
    ├── overlays/                      # Environment-specific overlays
    │   ├── staging/
    │   │   ├── kustomization.yaml
    │   │   └── patches/               # Staging-specific patches
    │   │       ├── deployment-resources.yaml
    │   │       └── hpa-limits.yaml
    │   └── production/
    │       ├── kustomization.yaml
    │       ├── priorityclass.yaml     # Production priority class
    │       └── patches/               # Production-specific patches
    │           ├── deployment-high-availability.yaml
    │           └── hpa-high-throughput.yaml
    ├── namespaces/                    # Namespace definitions
    │   ├── staging/
    │   │   ├── kustomization.yaml
    │   │   └── namespace.yaml
    │   └── production/
    │       ├── kustomization.yaml
    │       └── namespace.yaml
    └── addons/                        # Optional add-ons
        ├── logging/                   # Logging stack (Filebeat + Logstash)
        │   ├── kustomization.yaml
        │   ├── filebeat-rbac.yaml
        │   ├── filebeat-daemonset.yaml
        │   ├── logstash-deployment.yaml
        │   ├── logstash-service.yaml
        │   └── config/                # Configuration files
        │       ├── filebeat.yml
        │       └── logstash.conf
        └── backups/                   # Database backup jobs
            ├── kustomization.yaml
            ├── persistentvolumeclaim.yaml
            └── timescale-backup-cronjob.yaml
```

## Quick Start

### Option 1: Standalone Deployment (Simple)

Deploy TradePulse directly to your cluster with basic configurations:

```bash
# Create namespace
kubectl create namespace tradepulse

# Create required secrets (see Prerequisites section)
kubectl create secret generic tradepulse-secrets \
  --namespace tradepulse \
  --from-literal=audit-secret=YOUR_SECRET \
  --from-literal=oauth2-issuer=YOUR_ISSUER \
  --from-literal=oauth2-audience=YOUR_AUDIENCE \
  --from-literal=oauth2-jwks-uri=YOUR_JWKS_URI

kubectl create secret generic tradepulse-mtls-client \
  --namespace tradepulse \
  --from-file=client-ca.pem=path/to/ca.pem \
  --from-file=client.crl=path/to/client.crl

# Deploy the application
kubectl apply -f deploy/tradepulse-serviceaccount.yaml -n tradepulse
kubectl apply -f deploy/tradepulse-deployment.yaml -n tradepulse
kubectl apply -f deploy/tradepulse-service.yaml -n tradepulse

# Verify deployment
kubectl rollout status deployment/tradepulse-api -n tradepulse
kubectl get pods -n tradepulse
```

### Option 2: Kustomize Deployment (Recommended)

Deploy using environment-specific overlays that include logging and backup addons:

#### Staging Environment

```bash
# Validate the configuration
kubectl kustomize deploy/kustomize/overlays/staging

# Apply staging configuration
kubectl apply -k deploy/kustomize/overlays/staging

# Monitor rollout
kubectl rollout status deployment/tradepulse-api -n tradepulse-staging

# Check all resources
kubectl get all -n tradepulse-staging
```

#### Production Environment

```bash
# Validate the configuration
kubectl kustomize deploy/kustomize/overlays/production

# Apply production configuration (requires namespace approval in CI/CD)
kubectl apply -k deploy/kustomize/overlays/production

# Monitor rollout
kubectl rollout status deployment/tradepulse-api -n tradepulse-production

# Verify high-availability setup
kubectl get pods -n tradepulse-production -o wide
kubectl get hpa -n tradepulse-production
```

## Prerequisites

### Required Secrets

The deployment references the following Kubernetes secrets that must be created before applying manifests:

1. **`tradepulse-secrets`**: Application secrets
   - `audit-secret`: Secret key for audit log signing
   - `oauth2-issuer`: OAuth2 issuer URL
   - `oauth2-audience`: OAuth2 audience
   - `oauth2-jwks-uri`: OAuth2 JWKS endpoint

2. **`tradepulse-mtls-client`**: mTLS certificates
   - `client-ca.pem`: Client CA certificate bundle
   - `client.crl`: Certificate revocation list

3. **`tradepulse-timescale`** (optional, for backups addon):
   - `url`: TimescaleDB connection URL

### Creating Secrets

Using `kubectl`:

```bash
kubectl create secret generic tradepulse-secrets \
  --from-literal=audit-secret="$(openssl rand -base64 32)" \
  --from-literal=oauth2-issuer="https://your-idp.com" \
  --from-literal=oauth2-audience="tradepulse-api" \
  --from-literal=oauth2-jwks-uri="https://your-idp.com/.well-known/jwks.json"

kubectl create secret generic tradepulse-mtls-client \
  --from-file=client-ca.pem=./tls/ca.pem \
  --from-file=client.crl=./tls/revocation.crl
```

Using external secret management (recommended for production):

```bash
# Example with AWS Secrets Manager
kubectl apply -f - <<EOF
apiVersion: external-secrets.io/v1beta1
kind: ExternalSecret
metadata:
  name: tradepulse-secrets
spec:
  refreshInterval: 1h
  secretStoreRef:
    name: aws-secrets-manager
    kind: SecretStore
  target:
    name: tradepulse-secrets
  data:
    - secretKey: audit-secret
      remoteRef:
        key: tradepulse/prod/audit-secret
    # ... additional keys
EOF
```

## Configuration Details

### Base Configuration

The base configuration in `kustomize/base/` defines:

- **Deployment**: 3 replicas with rolling update strategy
- **Security**: Non-root user, read-only filesystem, dropped capabilities
- **Resources**: 250m CPU / 512Mi memory requests, 1 CPU / 1Gi limits
- **Probes**: Liveness, readiness, and startup probes on `/health` endpoint
- **Service**: ClusterIP exposing HTTP (port 80) and metrics (port 8001)
- **PodDisruptionBudget**: Minimum 2 pods available during disruptions
- **HorizontalPodAutoscaler**: Scale 3-12 replicas based on CPU (60%), memory (70%), and custom metrics

### Staging Overlay

Staging environment (`kustomize/overlays/staging/`) includes:

- **Namespace**: `tradepulse-staging`
- **Replicas**: 3 pods
- **Resources**: Same as base (250m CPU / 512Mi memory)
- **HPA**: 2-6 replicas with moderate scaling policies
- **Topology**: Spread across zones with soft anti-affinity
- **Image Tag**: `staging`
- **Add-ons**: Logging stack and database backups

### Production Overlay

Production environment (`kustomize/overlays/production/`) includes:

- **Namespace**: `tradepulse-production`
- **Replicas**: 5 pods
- **Resources**: 750m CPU / 1Gi memory requests, 2 CPU / 2Gi limits
- **HPA**: 6-24 replicas with aggressive scaling policies
- **Priority**: `tradepulse-critical` PriorityClass (prevents eviction)
- **Topology**: Strict anti-affinity across zones and nodes
- **Node Selection**: Production-labeled nodes with taints
- **Rate Limiting**: 1200 TPS
- **Image Tag**: `stable`
- **Add-ons**: Logging stack and database backups
- **Monitoring**: Prometheus scraping enabled

## Observability

### Monitoring

The deployment exposes metrics on port 8001:

```bash
# Port-forward to access metrics
kubectl port-forward -n tradepulse-staging svc/tradepulse-api 8001:8001

# View metrics
curl http://localhost:8001/metrics
```

Configure Prometheus to scrape the metrics endpoint using `deploy/prometheus.yml`:

```yaml
global:
  scrape_interval: 15s
scrape_configs:
  - job_name: 'nfpro'
    static_configs:
      - targets: ['tradepulse-api:8001']
```

### Logging

The optional logging addon deploys:

- **Filebeat**: DaemonSet collecting container logs from all nodes
- **Logstash**: Processing and forwarding logs to Elasticsearch
- **Configuration**: Automatically filters TradePulse application logs

Enable logging by including it in your overlay (already included in staging/production):

```yaml
resources:
  - ../../addons/logging
```

View logs:

```bash
# View application logs
kubectl logs -n tradepulse-staging deployment/tradepulse-api -f

# View Filebeat logs
kubectl logs -n tradepulse-staging daemonset/filebeat -f

# View Logstash logs
kubectl logs -n tradepulse-staging deployment/logstash -f
```

## Horizontal Pod Autoscaling

The HPA configuration scales based on:

1. **CPU Utilization**: Target 60%
2. **Memory Utilization**: Target 70%
3. **Custom Metrics**:
   - `tradepulse_signal_to_fill_latency_quantiles_seconds` (p95 < 400ms)
   - `tradepulse_orders_queue_depth` (avg < 80)

For custom metrics to work, you need to deploy:
- Prometheus Adapter or similar custom metrics provider
- Configure the adapter to expose TradePulse metrics

Test HPA behavior:

```bash
# Run load test
cd deploy/loadtests
k6 run --env TRADEPULSE_BASE_URL=http://your-service hpa-k6.js

# Watch HPA scaling
kubectl get hpa -n tradepulse-staging -w

# Check scaling events
kubectl describe hpa tradepulse-api -n tradepulse-staging
```

## Database Backups

The optional backups addon creates a daily CronJob to backup TimescaleDB:

- **Schedule**: 2:00 AM daily
- **Retention**: 35 days
- **Archive After**: 14 days
- **Storage**: 200Gi PersistentVolumeClaim

Configure backup by creating the required secret:

```bash
kubectl create secret generic tradepulse-timescale \
  --from-literal=url="postgresql://user:pass@host:5432/db?sslmode=verify-full"
```

Monitor backups:

```bash
# List backup jobs
kubectl get cronjobs -n tradepulse-staging

# View backup logs
kubectl logs -n tradepulse-staging job/timescale-backup-XXXXX
```

## Chaos Engineering

The chaos testing configuration (`chaos/chaos.yml`) defines a Chaos Mesh workflow that:

1. Injects 250ms network latency for 5 minutes
2. Kills 30% of matching engine pods with 10s grace period for 10 minutes
3. Verifies observability metrics stay within SLO (drawdown < 2%)

Run chaos experiments (requires Chaos Mesh):

```bash
# Install Chaos Mesh (one-time setup)
kubectl apply -f https://mirrors.chaos-mesh.org/latest/crd.yaml
kubectl apply -f https://mirrors.chaos-mesh.org/latest/chaos-mesh.yaml

# Create chaos testing namespace
kubectl create namespace chaos-testing

# Run the chaos workflow
kubectl apply -f deploy/chaos/chaos.yml

# Monitor the workflow
kubectl get workflow -n chaos-testing
kubectl describe workflow tradepulse-chaos-suite -n chaos-testing
```

## Load Testing

The `loadtests/hpa-k6.js` script validates:

- Service remains responsive under load
- Auto-scaling behaves correctly
- Latency SLOs are met (p95 < 400ms)
- Error rate stays below 1%

Load test stages:
1. Ramp-up: 2 minutes to 50 VUs
2. Plateau 1: 8 minutes at 200 VUs
3. Peak: 6 minutes at 400 VUs
4. Cool-down: 5 minutes back to 50 VUs
5. Completion: 3 minutes to 0 VUs

Run load test:

```bash
cd deploy/loadtests

# Against staging
k6 run --env TRADEPULSE_BASE_URL=http://tradepulse-api.tradepulse-staging.svc.cluster.local hpa-k6.js

# Against production (with custom SLO)
k6 run \
  --env TRADEPULSE_BASE_URL=http://tradepulse-api.tradepulse-production.svc.cluster.local \
  --env TRADEPULSE_LATENCY_SLO_MS=300 \
  hpa-k6.js
```

## Troubleshooting

### Deployment Issues

Check pod status:
```bash
kubectl get pods -n tradepulse-staging
kubectl describe pod <pod-name> -n tradepulse-staging
kubectl logs <pod-name> -n tradepulse-staging
```

Common issues:

1. **ImagePullBackOff**: Check image tag and registry access
2. **CrashLoopBackOff**: Check logs for application errors
3. **Pending**: Check node resources and PodDisruptionBudget
4. **Secret not found**: Ensure all required secrets are created

### HPA Not Scaling

```bash
# Check HPA status
kubectl get hpa -n tradepulse-staging
kubectl describe hpa tradepulse-api -n tradepulse-staging

# Check metrics server
kubectl top nodes
kubectl top pods -n tradepulse-staging

# For custom metrics, check metrics adapter
kubectl get apiservices | grep metrics
```

### Networking Issues

```bash
# Test service connectivity (using pinned version for reproducibility)
kubectl run -it --rm debug --image=nicolaka/netshoot:v0.11 --restart=Never -- /bin/bash
> curl http://tradepulse-api.tradepulse-staging.svc.cluster.local/health

# Check service endpoints
kubectl get endpoints tradepulse-api -n tradepulse-staging
```

## Best Practices

1. **Always validate before applying**:
   ```bash
   kubectl kustomize deploy/kustomize/overlays/staging | kubectl apply --dry-run=client -f -
   ```

2. **Use resource limits**: Prevent resource exhaustion
3. **Enable PodDisruptionBudget**: Maintain availability during updates
4. **Configure health probes**: Enable Kubernetes self-healing
5. **Use namespaces**: Isolate environments
6. **Rotate secrets regularly**: Update secrets and restart pods
7. **Monitor resource usage**: Adjust requests/limits based on actual usage
8. **Test in staging first**: Validate changes before production
9. **Use version pinning**: Specify image tags instead of `latest`
10. **Enable security contexts**: Run as non-root, drop capabilities

## Related Documentation

- [Main Deployment Guide](../DEPLOYMENT.md) - Comprehensive deployment documentation
- [Architecture Overview](../docs/architecture/system_overview.md) - System architecture
- [Contributing Guide](../CONTRIBUTING.md) - Development guidelines
- [Security Policy](../SECURITY.md) - Security best practices

## Support

For issues or questions:
- Open an issue on GitHub
- Review existing documentation in the `docs/` directory
- Check the main README.md for project overview
