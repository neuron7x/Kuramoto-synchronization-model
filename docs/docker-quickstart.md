# Docker Quick Start Guide

Get TradePulse running with Docker in minutes.

---

## Prerequisites

- **Docker** 20.10 or higher
- **Docker Compose** 2.0 or higher
- 4 GB RAM available
- 10 GB disk space

### Install Docker

**Linux:**
```bash
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
sudo usermod -aG docker $USER
```

**macOS:**
Download [Docker Desktop for Mac](https://www.docker.com/products/docker-desktop)

**Windows:**
Download [Docker Desktop for Windows](https://www.docker.com/products/docker-desktop)

---

## Quick Start

### 1. Clone Repository

```bash
git clone https://github.com/neuron7x/TradePulse.git
cd TradePulse
```

### 2. Prepare Environment Variables

TradePulse requires audit secrets for signing audit logs and RBAC audit events. Generate strong secrets (64 hexadecimal characters or longer) and store them in a `.env` file before starting Docker Compose:

```bash
# Generate cryptographically secure secrets
python - <<'PY'
import secrets
print('TRADEPULSE_AUDIT_SECRET=' + secrets.token_hex(32))
print('TRADEPULSE_RBAC_AUDIT_SECRET=' + secrets.token_hex(32))
PY

# Save the output in .env together with any other settings you need
```

### 3. Start Services

```bash
# Start all services
docker compose --env-file .env up -d

# View logs
docker compose logs -f
```

> ℹ️ Docker Compose automatically reads a `.env` file from the project root. Passing `--env-file .env` makes it explicit that the generated secrets should be loaded before the containers start.

The `tradepulse` service defined in `docker-compose.yml` consumes the `.env` file, so `TRADEPULSE_AUDIT_SECRET` and `TRADEPULSE_RBAC_AUDIT_SECRET` are injected into the container environment. You can verify they are present with:

```bash
docker compose exec tradepulse env | grep TRADEPULSE_.*AUDIT_SECRET
```

Services started:
- **TradePulse**: Main application
- **Prometheus**: Metrics collection (port 9090)
- **Grafana**: Dashboards (port 3000)
- **PostgreSQL**: Database (port 5432)

### 4. Verify Services

```bash
# Check running containers
docker compose ps

# Should show:
# tradepulse-app      running
# tradepulse-prometheus running
# tradepulse-grafana   running
# tradepulse-db        running
```

### 5. Access Services

**Grafana Dashboard:**
- URL: http://localhost:3000
- Username: `admin`
- Password: `admin` (change on first login)

**Prometheus:**
- URL: http://localhost:9090

**TradePulse API:**
- URL: http://localhost:8000

---

## Using Docker Compose

### Start Services

```bash
# Start in foreground
docker compose up

# Start in background
docker compose up -d

# Start specific service
docker compose up -d prometheus
```

### Stop Services

```bash
# Stop all services
docker compose stop

# Stop specific service
docker compose stop grafana

# Stop and remove containers
docker compose down

# Stop and remove volumes (⚠️ deletes data)
docker compose down -v
```

### View Logs

```bash
# All services
docker compose logs -f

# Specific service
docker compose logs -f tradepulse

# Last 100 lines
docker compose logs --tail=100 tradepulse
```

### Restart Services

```bash
# Restart all
docker compose restart

# Restart specific service
docker compose restart tradepulse
```

---

## Running TradePulse Commands

### Execute Commands in Container

```bash
# Analyze data
docker compose exec tradepulse python -m interfaces.cli analyze --csv /data/sample.csv

# Run backtest
docker compose exec tradepulse python -m interfaces.cli backtest --csv /data/sample.csv

# Run tests
docker compose exec tradepulse pytest tests/

# Open shell
docker compose exec tradepulse /bin/bash
```

### Using Docker Run

```bash
# One-off command
docker compose run --rm tradepulse python -m interfaces.cli analyze --csv /data/sample.csv

# Interactive shell
docker compose run --rm tradepulse /bin/bash
```

---

## Configuration

### Environment Variables

Create `.env` file in project root. Be sure to include the audit secrets you generated earlier so the application can start successfully:

```bash
# .env
POSTGRES_USER=tradepulse
POSTGRES_PASSWORD=secure_password
POSTGRES_DB=tradepulse

# Exchange API keys
BINANCE_API_KEY=your_api_key
BINANCE_API_SECRET=your_api_secret

# TradePulse settings
TRADEPULSE_ENV=production
TRADEPULSE_LOG_LEVEL=INFO
TRADEPULSE_AUDIT_SECRET=replace_with_output_from_secrets_generator
TRADEPULSE_RBAC_AUDIT_SECRET=replace_with_output_from_secrets_generator
```

Load environment variables:
```bash
docker compose --env-file .env up -d
```

### Volume Mounts

Mount local directories for data and logs:

```yaml
# docker-compose.yml
services:
  tradepulse:
    volumes:
      - ./data:/data           # Data directory
      - ./logs:/logs           # Log files
      - ./configs:/configs     # Configuration files
```

### Custom Configuration

Override docker-compose.yml:

```yaml
# docker-compose.override.yml
services:
  tradepulse:
    environment:
      - LOG_LEVEL=DEBUG
    ports:
      - "8001:8000"  # Different port
```

---

## Docker Compose File

### Basic Configuration

```yaml
# docker-compose.yml
version: '3.8'

services:
  tradepulse:
    build: .
    container_name: tradepulse-app
    ports:
      - "8000:8000"
    volumes:
      - ./data:/data
      - ./logs:/logs
    environment:
      - PYTHONUNBUFFERED=1
      - TRADEPULSE_ENV=production
    depends_on:
      - db
      - prometheus
    restart: unless-stopped

  db:
    image: postgres:15
    container_name: tradepulse-db
    ports:
      - "5432:5432"
    environment:
      - POSTGRES_USER=tradepulse
      - POSTGRES_PASSWORD=tradepulse
      - POSTGRES_DB=tradepulse
    volumes:
      - postgres_data:/var/lib/postgresql/data
    restart: unless-stopped

  prometheus:
    image: prom/prometheus:latest
    container_name: tradepulse-prometheus
    ports:
      - "9090:9090"
    volumes:
      - ./prometheus.yml:/etc/prometheus/prometheus.yml
      - prometheus_data:/prometheus
    command:
      - '--config.file=/etc/prometheus/prometheus.yml'
      - '--storage.tsdb.path=/prometheus'
    restart: unless-stopped

  grafana:
    image: grafana/grafana:latest
    container_name: tradepulse-grafana
    ports:
      - "3000:3000"
    environment:
      - GF_SECURITY_ADMIN_PASSWORD=admin
    volumes:
      - grafana_data:/var/lib/grafana
      - ./grafana/dashboards:/etc/grafana/provisioning/dashboards
    depends_on:
      - prometheus
    restart: unless-stopped

volumes:
  postgres_data:
  prometheus_data:
  grafana_data:
```

---

## Dockerfile

### Multi-stage Build

```dockerfile
# Dockerfile
FROM python:3.12-slim as builder

WORKDIR /app

# Install dependencies
COPY requirements.lock .
RUN pip install --user --no-cache-dir -r requirements.lock

# Final stage
FROM python:3.12-slim

WORKDIR /app

# Copy Python dependencies
COPY --from=builder /root/.local /root/.local

# Copy application
COPY . .

# Add to PATH
ENV PATH=/root/.local/bin:$PATH

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD python -c "import requests; requests.get('http://localhost:8000/health')" || exit 1

# Run application
CMD ["python", "-m", "interfaces.cli", "live", "--source", "csv", "--path", "/data/sample.csv"]
```

### Building Image

```bash
# Build image
docker build -t tradepulse:latest .

# Build with tag
docker build -t tradepulse:v1.0.0 .

# Build without cache
docker build --no-cache -t tradepulse:latest .
```

---

## Development with Docker

### Live Code Reloading

Mount source code as volume:

```yaml
# docker-compose.dev.yml
services:
  tradepulse:
    volumes:
      - .:/app  # Mount source code
    command: python -m interfaces.cli live --reload
```

Start with development config:
```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up
```

### Running Tests

```bash
# Run all tests
docker compose exec tradepulse pytest tests/

# Run with coverage
docker compose exec tradepulse pytest tests/ \
  --cov=core --cov=backtest --cov=execution \
  --cov-config=configs/quality/critical_surface.coveragerc \
  --cov-report=html

# Run specific test
docker compose exec tradepulse pytest tests/unit/test_indicators.py
```

### Debugging

```yaml
# docker-compose.debug.yml
services:
  tradepulse:
    ports:
      - "5678:5678"  # Debugger port
    command: python -m debugpy --listen 0.0.0.0:5678 --wait-for-client -m interfaces.cli
```

Attach debugger from VS Code or PyCharm.

---

## Production Deployment

### Environment-specific Configs

**Development:**
```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up
```

**Staging:**
```bash
docker compose -f docker-compose.yml -f docker-compose.staging.yml up
```

**Production:**
```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

### Resource Limits

```yaml
services:
  tradepulse:
    deploy:
      resources:
        limits:
          cpus: '2.0'
          memory: 4G
        reservations:
          cpus: '1.0'
          memory: 2G
```

### Health Checks

```yaml
services:
  tradepulse:
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s
```

### Logging

```yaml
services:
  tradepulse:
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"
```

---

## Troubleshooting

### Containers Won't Start

```bash
# Check logs
docker compose logs tradepulse

# Check system resources
docker system df

# Clean up old containers
docker system prune -a
```

### Port Already in Use

```bash
# Find process using port
lsof -i :8000

# Or use different port
docker compose up -d --force-recreate
```

### Permission Denied

```bash
# Fix ownership
sudo chown -R $USER:$USER .

# Or run as current user
docker compose run --user $(id -u):$(id -g) tradepulse
```

### Out of Disk Space

```bash
# Clean up Docker
docker system prune -a --volumes

# Check usage
docker system df -v
```

---

## Advanced Features

### Docker Networking

```yaml
services:
  tradepulse:
    networks:
      - frontend
      - backend

networks:
  frontend:
  backend:
    internal: true
```

### Secrets Management

```yaml
services:
  tradepulse:
    secrets:
      - db_password
      - api_key

secrets:
  db_password:
    file: ./secrets/db_password.txt
  api_key:
    file: ./secrets/api_key.txt
```

### Multi-container Scaling

```bash
# Scale service
docker compose up -d --scale tradepulse=3

# Load balancing required for multiple instances
```

---

## Useful Commands

```bash
# View container stats
docker stats

# Inspect container
docker inspect tradepulse-app

# Copy files to/from container
docker cp data.csv tradepulse-app:/data/
docker cp tradepulse-app:/logs/ ./logs/

# Execute shell command
docker compose exec tradepulse ls -la /data

# Remove all stopped containers
docker container prune

# Remove unused images
docker image prune -a

# Remove unused volumes
docker volume prune
```

---

## Summary

You've learned how to:
- ✅ Start TradePulse with Docker
- ✅ Use Docker Compose commands
- ✅ Configure services
- ✅ Run commands in containers
- ✅ Debug and troubleshoot
- ✅ Deploy to production

**Next Steps:**
- Customize `docker-compose.yml` for your needs
- Set up environment variables
- Configure monitoring dashboards
- Deploy to cloud (AWS, GCP, Azure)

---

## Resources

- [Docker Documentation](https://docs.docker.com/)
- [Docker Compose Documentation](https://docs.docker.com/compose/)
- [Best Practices](https://docs.docker.com/develop/dev-best-practices/)

---

**Last Updated**: 2025-01-01
