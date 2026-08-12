# Installation Guide

This guide covers environment prerequisites, supported platforms, and the recommended workflows for installing GeoSync.

## Prerequisites

Before installing GeoSync, make sure you have the following tools available:

- **Python 3.11–3.13** with `pip` and `venv` modules.
- **Git** for cloning the repository and tracking updates.
- **Build essentials** for native extensions:
  - Linux: `build-essential`, `python3-dev`, and `libffi-dev`.
  - macOS: Xcode Command Line Tools (`xcode-select --install`).
  - Windows: [Build Tools for Visual Studio](https://visualstudio.microsoft.com/visual-cpp-build-tools/) or install inside WSL2.
- **CMake 3.21+** (GPU extras rely on compiled components).
- **CUDA 11.8+** drivers if you plan to enable GPU acceleration.

Optional but recommended:

- **Poetry or pip-tools** if you manage custom dependency sets.
- **Docker** to run the bundled docker-compose stack.

## Automated bootstrap

The fastest way to prepare a development machine is via the consolidated
automation CLI:

```bash
python -m scripts bootstrap --include-dev --pre-commit --frontend --extras connectors gpu
```

The command will create ``.venv`` (or reuse it when present), install the locked
Python dependencies, wire ``pre-commit`` git hooks, and install the dashboard
frontend packages. Use ``--help`` for the full option matrix including custom
virtualenv paths, optional extras, and frontend controls.

## Supported Platforms

GeoSync is continuously tested on Linux (Ubuntu 22.04) and macOS (13+). Windows users should run inside WSL2 with Ubuntu 22.04 or newer to match the supported dependency toolchain. Native Windows execution is possible but not part of the automated CI matrix.

> ℹ️ Keep your Python minor version aligned with the published lock files (`requirements.lock`, `requirements-dev.lock`).

## Creating an Isolated Environment

We recommend using `venv` to avoid dependency conflicts.

```bash
# Clone the repository
git clone https://github.com/neuron7xLab/GeoSync.git
cd GeoSync

# Create a virtual environment
python -m venv .venv
source .venv/bin/activate  # Windows (PowerShell): .\.venv\Scripts\Activate.ps1

# Upgrade pip tooling
python -m pip install --upgrade pip wheel setuptools

# Install the core runtime dependencies
pip install -r requirements.lock

# Install developer tooling if you plan to run tests or type checks
pip install -r requirements-dev.lock
```

When you finish working, deactivate the environment with `deactivate`.

## Optional Extras

GeoSync exposes optional extras to keep the base installation lean. Install only what you need:

```bash
# Broker and market data connectors
pip install ".[connectors]"

# GPU acceleration backends (requires CUDA toolkit and compatible drivers)
pip install ".[gpu]"
```

You can combine extras: `pip install ".[connectors,gpu]"`.

## Local TLS Development Certificates

GeoSync expects development TLS material in `configs/tls/dev/`. Private keys (`*.key.pem`) are **never** committed and must be generated locally.

Recommended workflow (from the repository root):

```bash
make generate-dev-certs
```

Manual workflow (OpenSSL wrapper script):

```bash
cd configs/tls/dev
./generate_certs.sh
```

If you suspect a leak or need a fresh set, delete the dev artifacts and regenerate:

```bash
rm -f configs/tls/dev/*.key.pem configs/tls/dev/*.pem
make generate-dev-certs
```

See `configs/tls/dev/README.md` for certificate details, expiration notes, and troubleshooting.

## Troubleshooting

### Native dependency build failures

1. Ensure a compiler toolchain is installed (see prerequisites above).
2. Reinstall the latest `pip`, `setuptools`, and `wheel`: `python -m pip install --upgrade pip setuptools wheel`.
3. On macOS with Apple Silicon, set `export ARCHFLAGS="-arch arm64"` before installing native dependencies.

### NumPy / SciPy install errors

- Verify that you are using Python 3.11 or newer.
- Remove existing build caches: `rm -rf ~/.cache/pip`.
- If the issue persists, install prebuilt wheels: `pip install numpy==1.26.*` before running the main install.

### GPU extras fail to detect CUDA

- Confirm `nvidia-smi` reports the expected driver version.
- Check that `CUDA_HOME` points to your CUDA installation.
- Install the matching cuDNN package if your GPU backend requires it.

### SSL or proxy errors when downloading packages

- Set `PIP_INDEX_URL` or `PIP_NO_VERIFY` according to your corporate proxy policy.
- Download `requirements.lock` dependencies via an internal mirror if outbound internet is restricted.

Still blocked? File an issue with the error logs and your OS/Python version so the team can assist.
