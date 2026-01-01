---
owner: platform@tradepulse
review_cadence: quarterly
last_reviewed: 2026-01-01
---

# Scripts

This directory hosts the consolidated command line tooling for TradePulse.
All commands are exposed through the Python module `scripts.cli`, which can be
invoked with `python -m scripts` from the repository root.  The CLI provides
consistent logging, deterministic defaults and optional environment variable
loading so that workflows behave identically across Linux, macOS and Windows.

## Quick start

```bash
python -m scripts --help
python -m scripts bootstrap --include-dev --frontend --pre-commit
python -m scripts lint --verbose
python -m scripts test --pytest-args -k smoke
python -m scripts gen-proto
python -m scripts dev-up
python -m scripts dev-down
python -m scripts fpma graph
python -m scripts sanity --dry-run
make test:fast   # Skip slow/nightly/heavy suites
make test:all    # Full coverage-enabled suite
make test:heavy  # Only heavy/slow/nightly suites
```

### Logging controls

Use `--verbose` (repeatable) to increase logging verbosity and `--quiet`
(repeatable) to reduce noise.  Timestamps are always emitted in ISO 8601 format
using UTC to avoid timezone ambiguity.

### Environment variables

Scripts load configuration from `scripts/.env` when present.  Secrets should not
be committed to the repository; copy [`scripts/.env.example`](./.env.example)
and provide your own values locally.  The loader never echoes variable values to
avoid leaking credentials.

### Deterministic behaviour

On startup the CLI configures the locale and random seeds to deterministic
defaults.  This keeps tool output stable across machines, which in turn
simplifies debugging and makes regression tests easier to reproduce.

## Modules

Each top-level command is implemented in a dedicated module under
[`scripts/commands`](./commands).  The modules provide reusable functions that
can be imported from unit tests or other automation code.

### Environment bootstrap automation

Use the ``bootstrap`` command to provision a fully configured development
environment in minutes. It creates (or refreshes) a virtualenv, installs the
locked dependency sets, applies optional extras, configures ``pre-commit`` git
hooks, and can install the dashboard frontend dependencies when requested. For
new contributors or scientists who simply want to validate the stack end-to-end,
``--verify`` runs lightweight health checks after installation and ``--smoke-test``
executes a tiny sample CSV analysis so you immediately know the pipeline works.

```bash
python -m scripts bootstrap \
  --include-dev \
  --pre-commit \
  --frontend \
  --extras connectors gpu \
  --verify \
  --smoke-test
```

Key options:

- ``--venv-path`` controls where the virtual environment is created (default
  ``.venv``).
- ``--include-dev`` installs tooling from ``requirements-dev.lock``.
- ``--extras`` installs optional extras defined in ``pyproject.toml``.
- ``--pre-commit`` installs and wires git hooks.
- ``--frontend`` installs dependencies for ``ui/dashboard`` using the available
  Node package manager.

### Sanity cleanup automation

The `sanity` command orchestrates repository hygiene tasks such as removing
temporary build artefacts, regenerating managed sections of `.gitignore`,
producing inventories for scripts and configuration files, synchronising
Makefile targets into a generated `Justfile`, and collecting metadata about
packages, licences, templates, and directory layouts.  By default it performs
destructive actions such as deleting cache directories; use `--dry-run` to
preview changes and `--archive-legacy` to create tarball archives for legacy or
deprecated directories that are discovered during the run.

## Standalone Scripts

### Data Utilities

- **[data_sanity.py](README_data_sanity.md)** - Perform sanity checks on CSV data files
- **[gen_synth_amm_data.py](README_gen_synth_amm_data.md)** - Generate synthetic AMM data for testing
- **[generate_sample_ohlcv.py](README_generate_sample_ohlcv.md)** - Generate comprehensive OHLCV sample data for testing
- **[resilient_data_sync.py](README_resilient_data_sync.md)** - Resilient data synchronization with retry logic
- **[resilient_data_sync.sh](README_resilient_data_sync_sh.md)** - Bash version of resilient sync with comprehensive error handling

### Configuration & Schema

- **[export_tradepulse_schema.py](README_export_tradepulse_schema.md)** - Export TradePulse configuration JSON schema

### Analysis & Testing

- **[integrate_kuramoto_ricci.py](README_integrate_kuramoto_ricci.md)** - Run Kuramoto-Ricci composite integration pipeline
- **[smoke_e2e.py](README_smoke_e2e.md)** - Nightly smoke end-to-end pipeline for integration testing
- **[dependency_audit.py](README_dependency_audit.md)** - Audit Python dependencies for security vulnerabilities

Each script has detailed documentation in its respective README file linked above.

## Script Standards

All scripts in this directory follow these standards:

### Python Scripts

- **Shebang**: `#!/usr/bin/env python3` for executable scripts
- **License**: SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary header
- **Imports**: `from __future__ import annotations` for Python 3.11+
- **Type hints**: Full typing annotations on all functions
- **CLI**: argparse or typer with comprehensive help text
- **Logging**: Structured logging with logging module
- **Exit codes**: Proper exit codes (0=success, non-zero=failure)
- **Docstrings**: Module, function, and class docstrings
- **Error handling**: Comprehensive exception handling
- **Testing**: Unit tests in `scripts/tests/`

### Bash Scripts

- **Shebang**: `#!/usr/bin/env bash`
- **Safety**: `set -euo pipefail` at the top
- **Trap handlers**: Cleanup on EXIT, INT, TERM
- **Shellcheck**: Pass shellcheck validation
- **POSIX compatibility**: Avoid bash-specific features where possible
- **Structured logging**: JSON or structured output
- **Error handling**: Clear error messages and exit codes

### Common Requirements

- **Cross-platform**: Work on Linux, macOS, and Windows (Python)
- **Idempotency**: Safe to run multiple times
- **Atomicity**: Use temporary files and atomic operations
- **Resource limits**: Respect CPU, memory, and time constraints
- **Configuration**: Use .env or YAML for settings
- **Documentation**: README with CLI examples and use cases
- **Testing**: Comprehensive test coverage

## Testing

Run all script tests:

```bash
python -m pytest scripts/tests/ -v
```

Run specific test file:

```bash
python -m pytest scripts/tests/test_gen_synth_amm_data.py -v
```

## Linting and Formatting

Format all scripts:

```bash
python -m black scripts/
python -m ruff check scripts/ --fix
```

Lint bash scripts:

```bash
shellcheck scripts/*.sh
```

## CI Integration

Scripts are integrated into CI workflows:

- **Nightly smoke tests**: `smoke_e2e.py` runs nightly
- **Security audits**: `dependency_audit.py` checks for vulnerabilities
- **Data validation**: `data_sanity.py` validates CSV files
- **Pre-commit hooks**: Black, ruff, shellcheck, mypy

## Contributing

When adding new scripts:

1. Follow the script standards above
2. Add comprehensive tests to `scripts/tests/`
3. Create a README_scriptname.md with documentation
4. Update this README with a link to the new script
5. Ensure cross-platform compatibility
6. Add type hints and docstrings
7. Pass linting and formatting checks

## License

All scripts in this directory are licensed under the TradePulse Proprietary License Agreement (TPLA). See the [LICENSE](../LICENSE) file for details.

