# Environment Setup Guide

This guide provides step-by-step instructions for setting up the TradePulse development environment locally or in a container.

---

## Table of Contents

- [Prerequisites](#prerequisites)
- [Quick Start (TL;DR)](#quick-start-tldr)
- [Local Setup](#local-setup)
  - [1. Clone the Repository](#1-clone-the-repository)
  - [2. Create Virtual Environment](#2-create-virtual-environment)
  - [3. Install Dependencies](#3-install-dependencies)
  - [4. Configure Environment Variables](#4-configure-environment-variables)
  - [5. Verify Installation](#5-verify-installation)
- [Docker Setup](#docker-setup)
  - [1. Prerequisites](#1-prerequisites)
  - [2. Configure Environment Variables](#2-configure-environment-variables)
  - [3. Start Services](#3-start-services)
  - [4. Verify Services](#4-verify-services)
- [Environment Variables Reference](#environment-variables-reference)
- [Development Tools Setup](#development-tools-setup)
- [Troubleshooting](#troubleshooting)

---

## Prerequisites

### Required Software

| Software | Version | Purpose |
|----------|---------|---------|
| **Python** | 3.11–3.12 | Main runtime |
| **Git** | 2.30+ | Version control |
| **pip** | Latest | Package management |

### Optional (for full development)

| Software | Version | Purpose |
|----------|---------|---------|
| **Docker** | 20.10+ | Containerization |
| **Docker Compose** | 2.0+ | Container orchestration |
| **Go** | 1.22+ | Go services |
| **Node.js** | 18+ | Web dashboard |
| **CUDA** | 11.8+ | GPU acceleration |

### Platform-Specific Requirements

**Linux (Ubuntu/Debian):**
```bash
sudo apt-get update
sudo apt-get install -y python3-dev python3-venv build-essential libffi-dev
```

**macOS:**
```bash
xcode-select --install
```

**Windows:**
- Use [WSL2](https://learn.microsoft.com/en-us/windows/wsl/install) with Ubuntu 22.04 (recommended)
- Or install [Build Tools for Visual Studio](https://visualstudio.microsoft.com/visual-cpp-build-tools/)

---

## Quick Start (TL;DR)

For experienced developers who want to get started immediately:

```bash
# Clone and enter directory
git clone https://github.com/neuron7x/TradePulse.git && cd TradePulse

# Create and activate virtual environment
python -m venv .venv && source .venv/bin/activate

# Install dependencies
pip install --upgrade pip && pip install -r requirements.lock

# Copy and configure environment variables
cp .env.example .env
# Edit .env with your settings (especially secrets)

# Verify installation
python -c "from core.indicators.kuramoto import compute_phase; print('✅ Setup complete!')"
```

For Docker:
```bash
cp .env.example .env
# Edit .env with secrets
docker compose up -d
```

---

## Local Setup

### 1. Clone the Repository

```bash
git clone https://github.com/neuron7x/TradePulse.git
cd TradePulse
```

### 2. Create Virtual Environment

TradePulse uses a Python virtual environment to isolate dependencies.

**Linux/macOS:**
```bash
# Create virtual environment
python -m venv .venv

# Activate virtual environment
source .venv/bin/activate
```

**Windows (PowerShell):**
```powershell
# Create virtual environment
python -m venv .venv

# Activate virtual environment
.\.venv\Scripts\Activate.ps1
```

**Windows (Command Prompt):**
```cmd
# Create virtual environment
python -m venv .venv

# Activate virtual environment
.venv\Scripts\activate.bat
```

> **Tip:** You can also use the automated bootstrap script:
> ```bash
> python -m scripts bootstrap --include-dev --pre-commit
> ```

### 3. Install Dependencies

```bash
# Upgrade pip to latest version
python -m pip install --upgrade pip wheel setuptools

# Install core runtime dependencies (locked versions)
pip install -r requirements.lock

# For development (includes testing, linting tools)
pip install -r requirements-dev.lock
```

**Optional extras:**
```bash
# Market & broker connectors (Binance, Alpaca, Polygon)
pip install ".[connectors]"

# GPU acceleration (requires CUDA toolkit)
pip install ".[gpu]"

# Documentation tools
pip install ".[docs]"

# All development extras
pip install ".[dev]"
```

### 4. Configure Environment Variables

TradePulse uses environment variables for configuration. A template is provided in `.env.example`.

**Step 1: Copy the template**
```bash
cp .env.example .env
```

**Step 2: Edit the `.env` file**

Open `.env` in your preferred editor and configure the following sections:

#### Required Settings

```bash
# Application environment
TRADEPULSE_ENV=development
LOG_LEVEL=INFO

# Security: Generate secure secrets (REQUIRED)
# Use this command to generate secrets:
# python -c "import secrets; print(secrets.token_hex(32))"
TRADEPULSE_AUDIT_SECRET=<generate_secure_secret_minimum_16_chars>
TRADEPULSE_RBAC_AUDIT_SECRET=<generate_secure_secret_minimum_16_chars>
SECRET_KEY=<generate_secure_secret>
JWT_SECRET=<generate_secure_secret>
```

#### Database Configuration (if using PostgreSQL)

```bash
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_USER=tradepulse
POSTGRES_PASSWORD=<your_secure_password>
POSTGRES_DB=tradepulse
```

#### Exchange API Keys (for live trading)

```bash
# Binance (optional)
BINANCE_API_KEY=<your_api_key>
BINANCE_API_SECRET=<your_api_secret>
BINANCE_TESTNET=true

# Other exchanges...
```

> **Security Warning:** Never commit `.env` to version control! The `.gitignore` file already excludes it.

**Step 3: Generate secure secrets**

Use Python to generate cryptographically secure secrets:

```bash
# Generate a secure secret
python -c "import secrets; print(secrets.token_hex(32))"

# Or generate multiple secrets at once
python -c "import secrets; [print(f'Secret {i+1}: {secrets.token_hex(32)}') for i in range(4)]"
```

### 5. Verify Installation

```bash
# Test basic imports
python -c "from core.indicators.kuramoto import compute_phase; print('✅ Core imports OK')"

# Run quick tests
pytest tests/unit -q

# Run CLI command
python -m interfaces.cli --help
```

---

## Docker Setup

### 1. Prerequisites

Ensure Docker and Docker Compose are installed:

```bash
# Check Docker version
docker --version  # Should be 20.10+

# Check Docker Compose version
docker compose version  # Should be 2.0+
```

### 2. Configure Environment Variables

**Step 1: Create `.env` file**
```bash
cp .env.example .env
```

**Step 2: Generate and set required secrets**
```bash
# Generate secrets (run each command and copy output to .env)
python -c "import secrets; print('TRADEPULSE_AUDIT_SECRET=' + secrets.token_hex(32))"
python -c "import secrets; print('TRADEPULSE_RBAC_AUDIT_SECRET=' + secrets.token_hex(32))"
```

**Step 3: Edit `.env` with the generated secrets and your configuration**

### 3. Start Services

```bash
# Start all services in background
docker compose up -d

# View logs
docker compose logs -f

# Start specific services only
docker compose up -d tradepulse prometheus
```

### 4. Verify Services

```bash
# Check running containers
docker compose ps

# Test TradePulse service
curl -k https://localhost:8000/health

# Access services:
# - TradePulse API: https://localhost:8000
# - Prometheus: http://localhost:9090
# - Kibana: http://localhost:5601
```

### Docker Commands Reference

```bash
# Stop all services
docker compose stop

# Stop and remove containers
docker compose down

# Stop, remove containers and volumes (⚠️ deletes data)
docker compose down -v

# Rebuild and restart
docker compose up -d --build

# View logs for specific service
docker compose logs -f tradepulse

# Execute command in container
docker compose exec tradepulse python -m interfaces.cli --help
```

---

## Environment Variables Reference

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `TRADEPULSE_ENV` | Yes | `development` | Environment: `development`, `staging`, `production` |
| `LOG_LEVEL` | No | `INFO` | Logging level: `DEBUG`, `INFO`, `WARNING`, `ERROR` |
| `TRADEPULSE_AUDIT_SECRET` | Yes | — | Secret for signing audit records (min 16 chars) |
| `TRADEPULSE_RBAC_AUDIT_SECRET` | Yes | — | Secret for RBAC audit (min 16 chars) |
| `SECRET_KEY` | Yes | — | Application secret key |
| `JWT_SECRET` | Yes | — | JWT token signing secret |
| `POSTGRES_HOST` | No | `localhost` | PostgreSQL host |
| `POSTGRES_PORT` | No | `5432` | PostgreSQL port |
| `POSTGRES_USER` | No | `tradepulse` | PostgreSQL username |
| `POSTGRES_PASSWORD` | Yes | — | PostgreSQL password |
| `POSTGRES_DB` | No | `tradepulse` | PostgreSQL database name |
| `REDIS_HOST` | No | `localhost` | Redis host |
| `REDIS_PORT` | No | `6379` | Redis port |
| `PORT` | No | `8000` | Application port |

See `.env.example` for the complete list of available variables.

---

## Development Tools Setup

### Install Pre-commit Hooks

```bash
# Install pre-commit
pip install pre-commit

# Set up hooks
pre-commit install

# Run hooks manually on all files
pre-commit run --all-files
```

### IDE Configuration

**VS Code:**
1. Install Python extension
2. Select interpreter: `.venv/bin/python`
3. Recommended extensions:
   - Python
   - Pylance
   - Ruff
   - Docker

**PyCharm:**
1. Open project folder
2. Configure interpreter: Project Settings → Python Interpreter → Add → Existing Environment → `.venv/bin/python`

---

## Troubleshooting

### Common Issues

#### "ModuleNotFoundError: No module named 'core'"

**Solution:** Install the project in editable mode:
```bash
pip install -e .
```

#### Virtual environment not activating

**Solution:** Ensure you're using the correct activation command for your shell:
```bash
# Bash/Zsh
source .venv/bin/activate

# Fish
source .venv/bin/activate.fish

# PowerShell
.\.venv\Scripts\Activate.ps1
```

#### Docker services fail to start

**Solution:** Check that required environment variables are set:
```bash
# Verify secrets are in .env
grep -E "(TRADEPULSE_AUDIT_SECRET|TRADEPULSE_RBAC_AUDIT_SECRET)" .env

# Check Docker logs
docker compose logs tradepulse
```

#### Permission denied errors on Linux

**Solution:**
```bash
# Fix file ownership
sudo chown -R $USER:$USER .

# Or add user to docker group
sudo usermod -aG docker $USER
# Log out and back in for changes to take effect
```

#### NumPy/SciPy installation errors

**Solution:**
```bash
# Clear pip cache
rm -rf ~/.cache/pip

# Upgrade pip tools
python -m pip install --upgrade pip setuptools wheel

# Retry installation
pip install -r requirements.lock
```

### Getting Help

- 📖 Check [docs/troubleshooting.md](docs/troubleshooting.md) for more solutions
- 💬 Ask in [GitHub Discussions](https://github.com/neuron7x/TradePulse/discussions)
- 🐛 Report issues on [GitHub Issues](https://github.com/neuron7x/TradePulse/issues)

---

## Next Steps

After setting up your environment:

1. **Run tests:** `pytest tests/ -v`
2. **Explore documentation:** `docs/quickstart.md`
3. **Try the CLI:** `python -m interfaces.cli analyze --help`
4. **Read contributing guide:** `CONTRIBUTING.md`

---

**Last Updated:** 2025-12-05
