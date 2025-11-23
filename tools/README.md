# Tools Module

## Overview

The `tools` module provides utility scripts, development tools, and automation helpers for TradePulse development, testing, and operations. It contains tools for code quality, security analysis, dependency management, and more.

## Purpose

This module offers:

- **Development Tools**: Scripts for common development tasks
- **Code Quality**: Linting, formatting, and type checking utilities
- **Security Analysis**: SAST, dependency scanning, and vulnerability checks
- **Build Tools**: Package building, distribution, and release management
- **Testing Utilities**: Test data generation, mutation testing, and coverage analysis
- **Documentation**: Doc generation and validation tools

## Key Features

- 🔧 **Automation**: Streamline repetitive development tasks
- 🔒 **Security**: Automated security scanning and audit tools
- 📊 **Analytics**: Code metrics and quality reports
- 🧪 **Testing**: Advanced testing utilities and fixtures
- 📝 **Documentation**: Automated doc generation and validation
- 🚀 **CI/CD**: Integration with GitHub Actions and other CI systems

## Module Structure

```
tools/
├── coverage/                    # Coverage analysis and guardrails
├── dependencies/                # Dependency management and checking
├── docs/                       # Documentation generation tools
├── mutation/                   # Mutation testing utilities
├── observability/              # Observability bundle builder
├── release/                    # Release management tools
├── schema/                     # Schema generation and validation
└── security/                   # Security scanning tools (SAST, DAST)
```

## Usage Examples

### Code Quality Checks

```bash
# Run all linters
make lint

# Python linting
make lint:python

# Go linting (if applicable)
make lint:go

# Type checking
mypy --config-file=mypy.ini
```

### Security Scanning

```bash
# Run security audit
make security-audit

# SAST (Static Application Security Testing)
python -m tools.security.sast --fail-on-severity MEDIUM

# DAST probe
python -m tools.security.dast_probe

# Dependency vulnerability check
python scripts/dependency_audit.py --requirement requirements.txt
```

### Testing Tools

```bash
# Mutation testing
make mutation-test

# Coverage guardrails
python -m tools.coverage.guardrail \
    --config configs/quality/critical_surface.toml \
    --coverage coverage.xml

# Generate test fixtures
python -m tools.testing.fixture_generator
```

### Documentation Tools

```bash
# Validate documentation
make docs-lint
python -m tools.docs.lint_docs

# Generate API docs
python -m tools.docs.generate_api_docs

# Build documentation site
mkdocs build
```

### Dependency Management

```bash
# Check dependency alignment
make dependencies-check
python -m tools.dependencies.check_alignment

# Generate SBOM (Software Bill of Materials)
make sbom

# Verify supply chain
make supply-chain-verify
```

## Configuration

Most tools can be configured via project configuration files:

- `pyproject.toml`: Python tools configuration
- `mypy.ini`: Type checking configuration
- `.flake8`: Flake8 linter configuration
- `.golangci.yml`: Go linting configuration

## Related Modules

- [`scripts`](../scripts/README.md): Operational scripts
- [`.github`](../.github/workflows): CI/CD workflows

## Documentation

- [Development Guide](https://docs.tradepulse.io/development)
- [Security Guide](https://docs.tradepulse.io/security)
- [Testing Guide](https://docs.tradepulse.io/testing)

## Contributing

See [CONTRIBUTING.md](../CONTRIBUTING.md) for contribution guidelines.

## License

See [LICENSE](../LICENSE) for licensing information.
