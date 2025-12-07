# Changelog

All notable changes to TradePulse are documented in this file.

Format follows [Keep a Changelog](https://keepachangelog.com/) and [Semantic Versioning](https://semver.org/).

This file is automatically updated via [Towncrier](https://towncrier.readthedocs.io/).
Add change fragments to `newsfragments/` for each Pull Request.

<!-- towncrier release notes start -->

## [Unreleased]

### 🚀 Features
- DOC PR COPILOT v2: LLM-based documentation agent for automated documentation review and patch generation in Pull Requests.
- Agent configuration system in `.github/agents/` with system prompts, integration guides, and examples.
- 4C Principles documentation (Clarity, Conciseness, Correctness, Consistency) for documentation standards.
- Comprehensive API documentation (`docs/API.md`) with Python, CLI, and HTTP endpoint references.
- Release readiness assessment with comprehensive quality gates and metrics

### ⚡ Performance
- Refactored cache key normalisation to use deterministic `repr` tuples, improving synthetic throughput by ~19%.
- Benchmarks show 48-74% performance improvements over baseline across core indicators

### 🧹 Maintenance
- Hardened Release Drafter automation (v6 workflow, semantic version resolver, metrics summary).
- Repository cleanup: verified all temporary artifacts properly gitignored
- Comprehensive release readiness report (`reports/RELEASE_READINESS_REPORT.md`)

### ✅ Quality Assurance
- 351 core tests passing (100% pass rate)
- 683 source files with zero type errors (mypy)
- Zero critical security vulnerabilities
- 30+ GitHub Actions workflows for comprehensive CI/CD

### ⚠️ Breaking Changes
- Systems with non-deterministic `__repr__` implementations on cache keys should validate behaviour after the cache refactoring.

---

## [2.1.3] - 2025-10-05
### 🚀 Features
- New **CI/CD pipelines**: `ci.yml` (lint/test matrices, concurrency, caches), `pre-commit.yml`, `auto-merge.yml`, `sbom-scan.yml`, `publish-image.yml` (cosign), `data-sanity.yml`.
- Quality management: `benchmarks.yml`, `integration.yml`, `commitlint.yml`, `pr-labeler.yml`, `todo.yml`.
- Contract validation: `buf.yml` (lint+breaking), `gen-drift.yml` (+ Makefile `generate`).

### 🧹 Maintenance
- Updated `.pre-commit-config.yaml` (black, ruff, prettier, buf hooks).
- Adapted JS gateway (`domains/platform/gateway`) for lint job.

---

## [2.1.2] - 2025-10-05

### 🚀 Features
- Pre-commit config (`.pre-commit-config.yaml`), pytest config (`pytest.ini`).
- GitHub templates: issue/PR, labeler, dependabot, release-drafter.
- CI workflows: release-drafter, codeql, lint, test-matrix, docs-build, deploy, infra-check.
- Automation scripts expansion (`scripts/*`).
- Process templates: `.gitattributes`, `CODEOWNERS`, `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`.

### 📝 Documentation
- Clarified documentation on Fractal Modular Architecture (FPM-A).

---

## [2.1.1] - 2025-10-05

### 🚀 Features
- Integrated professional project artifacts: `.gitattributes`, `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, `CHANGELOG.md`, `CODEOWNERS`.
- Added Python package `scripts` with unified CLI (`python -m scripts`).

### 🔐 Security
- Unified file line endings via `.gitattributes`.

---

## [2.1.0] - 2025-10-05

### 🚀 Features
- **FPM-A Integration**: Fractal units, dependency graphs, cyclomatic complexity metrics, CI gates.

---

## [2.0.0] - 2025-10-05

### 🚀 Features
- Initial TradePulse skeleton: protobuf contracts, Python/Next.js scaffolding, infrastructure files.

---

## [0.1.0] - 2025-10-05 — Initial Public Preview

### 🚀 Features
- **Core Indicators**: Kuramoto oscillators, Ricci flow curvature, Shannon entropy, Hurst exponent, 50+ technical indicators.
- **Market Phase Detection**: Five-phase classification (CHAOTIC, PROTO_EMERGENT, STRONG_EMERGENT, TRANSITION, POST_EMERGENT).
- **TradePulseCompositeEngine**: High-level API combining Kuramoto synchronization with Ricci flow geometry.
- **Event-Driven Backtest Engine**: Walk-forward testing, Monte Carlo simulation, transaction cost modeling.
- **CLI Interface**: `analyze`, `backtest`, `live` commands with JSON output and tracing.
- **Streamlit Dashboard**: Interactive market analysis and visualization.
- **Fractal Modular Architecture (FPM-A)**: Clean domain separation with ports/adapters pattern.

### 📝 Documentation
- README with quickstart, feature overview, and architecture diagrams.
- MkDocs documentation site structure.
- API reference, quickstart guide, deployment docs.

### 🔐 Security
- CodeQL scanning, SBOM generation, secret detection.
- Security framework aligned with NIST SP 800-53 and ISO 27001.

### 🐛 Fixes
- Filled template placeholders in CLI/scripts.
- Synchronized versioning and configs.

### ⚠️ Known Limitations
- Live trading is in beta; test thoroughly in paper mode before production.
- Web dashboard is in early preview (alpha).
- Some advanced indicators require optional dependencies (`pip install ".[neuro_advanced]"`).

---

[Unreleased]: https://github.com/neuron7x/TradePulse/compare/v2.1.3...HEAD
[2.1.3]: https://github.com/neuron7x/TradePulse/compare/v2.1.2...v2.1.3
[2.1.2]: https://github.com/neuron7x/TradePulse/compare/v2.1.1...v2.1.2
[2.1.1]: https://github.com/neuron7x/TradePulse/compare/v2.1.0...v2.1.1
[2.1.0]: https://github.com/neuron7x/TradePulse/compare/v2.0.0...v2.1.0
[2.0.0]: https://github.com/neuron7x/TradePulse/compare/v0.1.0...v2.0.0
[0.1.0]: https://github.com/neuron7x/TradePulse/releases/tag/v0.1.0
