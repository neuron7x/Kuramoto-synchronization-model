# TradePulse Helm Charts

This directory contains Helm charts for deploying TradePulse to Kubernetes.

## Structure

```
deploy/helm/tradepulse/
├── Chart.yaml              # Umbrella chart definition
├── values.yaml             # Default configuration values
└── charts/
    ├── sandbox/            # Sandbox service subchart
    ├── admin/              # Admin service subchart
    └── observability/      # Observability stack subchart
```

## Prerequisites

- Kubernetes 1.24+
- Helm 3.14+
- cert-manager (for TLS certificates)
- Prometheus Operator (optional, for ServiceMonitors)

## Quick Start

### Install the complete stack

```bash
# Add Prometheus community charts (for observability dependencies)
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo update

# Create namespace with Pod Security labels
kubectl create namespace tradepulse
kubectl label namespace tradepulse \
  pod-security.kubernetes.io/enforce=baseline \
  pod-security.kubernetes.io/audit=restricted \
  pod-security.kubernetes.io/warn=restricted

# Install TradePulse
helm install tradepulse ./deploy/helm/tradepulse \
  --namespace tradepulse \
  --values ./deploy/helm/tradepulse/values.yaml
```

### Install with custom values

```bash
helm install tradepulse ./deploy/helm/tradepulse \
  --namespace tradepulse \
  --set sandbox.replicaCount=3 \
  --set sandbox.resources.limits.memory=2Gi \
  --set global.otel.enabled=true
```

### Upgrade existing deployment

```bash
helm upgrade tradepulse ./deploy/helm/tradepulse \
  --namespace tradepulse \
  --values ./deploy/helm/tradepulse/values.yaml
```

## Configuration

### Global Settings

The `global` section in `values.yaml` contains settings that apply to all subcharts:

- **Security Context**: Pod and container security settings (runAsNonRoot, seccomp, etc.)
- **OpenTelemetry**: Distributed tracing and metrics configuration
- **Network Policies**: East-west traffic control
- **Pod Security**: Admission control levels

### Service-Specific Settings

Each service (sandbox, admin) has its own configuration section:

- **Replicas**: Number of pod replicas
- **Resources**: CPU and memory requests/limits
- **Autoscaling**: HPA configuration (min/max replicas, target utilization)
- **Pod Disruption Budget**: Availability guarantees during disruptions
- **Service Monitor**: Prometheus scraping configuration

### Observability Stack

The observability subchart deploys:

- **OpenTelemetry Collector**: Receives, processes, and exports telemetry data
- **Prometheus**: (optional) Metrics collection and storage
- **Grafana**: (optional) Metrics visualization

## Security Features

### Pod Security

All pods run with restricted security contexts:

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
    drop:
      - ALL
```

### Network Policies

Network policies control traffic between services:

- Ingress: Only from within namespace and monitoring
- Egress: DNS, namespace services, and OTEL collector

### Resource Limits

All containers have CPU and memory limits to prevent resource exhaustion.

## High Availability

### Horizontal Pod Autoscaling (HPA)

Automatically scales pods based on CPU and memory utilization:

```yaml
autoscaling:
  enabled: true
  minReplicas: 2
  maxReplicas: 10
  targetCPUUtilizationPercentage: 70
  targetMemoryUtilizationPercentage: 80
```

### Pod Disruption Budget (PDB)

Ensures minimum availability during cluster operations:

```yaml
podDisruptionBudget:
  enabled: true
  minAvailable: 1
```

## Monitoring

### Service Monitors

Prometheus ServiceMonitor resources are created for each service:

```yaml
serviceMonitor:
  enabled: true
  interval: 30s
  scrapeTimeout: 10s
```

### SLO Configuration

Service Level Objectives are defined in the global configuration:

```yaml
slo:
  enabled: true
  errorBudget: 0.001  # 99.9% uptime
  latencyP99Threshold: 500  # milliseconds
```

## Testing

### Lint Charts

```bash
helm lint deploy/helm/tradepulse
```

### Template and Validate

```bash
helm template tradepulse deploy/helm/tradepulse --output-dir /tmp/helm-output
kubeval --strict /tmp/helm-output/**/*.yaml
```

### Deploy to Kind

```bash
# Create kind cluster
kind create cluster --name tradepulse-test

# Install
helm install tradepulse ./deploy/helm/tradepulse \
  --namespace tradepulse \
  --create-namespace \
  --set observability.enabled=false

# Verify
kubectl get all -n tradepulse
```

## Uninstall

```bash
helm uninstall tradepulse --namespace tradepulse
kubectl delete namespace tradepulse
```

## CI/CD Integration

The charts are automatically tested in CI:

1. **Lint**: `helm lint` validates chart structure
2. **Template**: Charts are rendered and validated with kubeval
3. **Kind Smoke Test**: Full deployment test in kind cluster
4. **Security Scan**: Kubescape and Polaris scan for security issues

See `.github/workflows/helm.yml` for details.

## Troubleshooting

### Pods not starting

Check pod security context:

```bash
kubectl describe pod <pod-name> -n tradepulse
kubectl logs <pod-name> -n tradepulse
```

### Network connectivity issues

Check network policies:

```bash
kubectl get networkpolicies -n tradepulse
kubectl describe networkpolicy <policy-name> -n tradepulse
```

### Resource limits

Check if pods are being OOMKilled:

```bash
kubectl get events -n tradepulse --sort-by='.lastTimestamp'
```

## Contributing

When modifying charts:

1. Update version in `Chart.yaml`
2. Document changes in chart `README.md`
3. Run `helm lint` locally
4. Test in kind cluster
5. Submit PR (CI will run full validation)
