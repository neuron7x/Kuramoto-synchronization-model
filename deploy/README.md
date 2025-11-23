# Deploy Module

## Overview

The `deploy` module contains deployment configurations, scripts, and infrastructure-as-code for deploying TradePulse to various environments.

## Purpose

- **Deployment Configuration**: Environment-specific configs
- **Infrastructure as Code**: Terraform, Kubernetes manifests
- **Deployment Scripts**: Automated deployment workflows
- **Environment Management**: Dev, staging, production configs

## Key Features

- 🚀 **Automated Deployment**: CI/CD integration
- 🏗️ **Infrastructure as Code**: Terraform modules
- ☸️ **Kubernetes**: K8s manifests and Helm charts
- 🐳 **Docker**: Container configurations
- 🌍 **Multi-Environment**: Support for multiple environments

## Structure

```
deploy/
├── docker/                 # Docker configurations
├── kubernetes/             # K8s manifests
├── terraform/              # Infrastructure as code
├── scripts/               # Deployment scripts
└── environments/          # Environment-specific configs
    ├── dev/
    ├── staging/
    └── production/
```

## Usage Examples

### Docker Deployment

```bash
# Build image
docker build -t tradepulse:latest .

# Run container
docker run -d \
  -p 8000:8000 \
  -e DATABASE_URL=postgresql://... \
  tradepulse:latest
```

### Kubernetes Deployment

```bash
# Deploy to K8s
kubectl apply -f deploy/kubernetes/

# Check status
kubectl get pods -n tradepulse

# View logs
kubectl logs -f deployment/tradepulse -n tradepulse
```

### Terraform Infrastructure

```bash
# Initialize Terraform
cd deploy/terraform
terraform init

# Plan infrastructure
terraform plan -var-file=environments/production.tfvars

# Apply infrastructure
terraform apply -var-file=environments/production.tfvars
```

## Configuration

Environment-specific configurations:

```yaml
# deploy/environments/production/config.yaml
environment: production
replicas: 3
resources:
  cpu: 2
  memory: 4Gi
  
database:
  host: prod-db.example.com
  port: 5432
  
monitoring:
  enabled: true
  prometheus_url: http://prometheus:9090
```

## Related Documentation

- [Deployment Guide](https://docs.tradepulse.io/deployment)
- [Infrastructure Guide](https://docs.tradepulse.io/infrastructure)
- [Security Best Practices](https://docs.tradepulse.io/security)

## License

See [LICENSE](../LICENSE) for licensing information.
