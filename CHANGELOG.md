# Changelog

All notable changes to GeoSync are documented in this file.

Format follows [Keep a Changelog](https://keepachangelog.com/) and [Semantic Versioning](https://semver.org/).

This file is automatically updated via [Towncrier](https://towncrier.readthedocs.io/).
Add change fragments to `newsfragments/` for each Pull Request.

<!-- towncrier release notes start -->

## [Unreleased]

### 🔬 Physics Kernel
- **57 machine-checkable invariants** across 15 modules (PR #138, #139)
- **67 mathematical witness tests** with INV-* references and 5-field error messages
- **Physics Kernel CI Gate**: self-check + L1-L5 validation + C1/C2 code audit
- **C1/C2 code audit**: 69 → 5 silent clamps (0 physics), 0 undocumented bounds
- **3 physics-law corrections**: RC1, FE2, OMS1 falsified and corrected by witnesses
- **Gradient Constitution** (CLAUDE.md §0): maintenance hierarchy, INV-YV1

### 🧬 New Modules
- **Cryptobiosis** (`core/neuro/cryptobiosis.py`): phase-transition survival, 8 invariants (CB1-CB8)
- **physics_contracts/**: parallel law-catalog with `@law()` decorator and AST validator

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

## [1.1.0] - 2026-07-19

Current released version and the single source of truth for the version string.
The identical `1.1.0` appears in the `VERSION` file, `CITATION.cff`
(`version` + `preferred-citation.version`), the `[tool.setuptools_scm]`
`fallback_version` in `pyproject.toml`, and the release git tag `v1.1.0` from
which the wheel / CLI `--version` derive. Enforced by
`scripts/ci/check_version_ssot.py`; policy in `docs/VERSION_POLICY.md`.

Change fragments accumulated under **[Unreleased]** above ship in this line.

---

<!-- HISTORICAL — legacy imported changelog (pre-SSOT). The 2.x.y entries below
     predate the git-tag / CITATION version SSOT introduced by REL-008 and use a
     numbering scheme inconsistent with the current release tags (v1.0.0,
     v1.1.0). They are PRESERVED VERBATIM for provenance and are NOT the current
     version. Do not treat any 2.x.y heading as the canonical version. -->

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
- Initial GeoSync skeleton: protobuf contracts, Python/Next.js scaffolding, infrastructure files.

---

## [0.1.0] - 2025-10-05 — Initial Public Preview

### 🚀 Features
- **Core Indicators**: Kuramoto oscillators, Ricci flow curvature, Shannon entropy, Hurst exponent, 50+ technical indicators.
- **Market Phase Detection**: Five-phase classification (CHAOTIC, PROTO_EMERGENT, STRONG_EMERGENT, TRANSITION, POST_EMERGENT).
- **GeoSyncCompositeEngine**: High-level API combining Kuramoto synchronization with Ricci flow geometry.
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
- Execution runs in the paper/replay realism harness only; live-venue execution is out of scope and unverified.
- Web dashboard is in early preview (alpha).
- Some advanced indicators require optional dependencies (`pip install ".[neuro_advanced]"`).

---

[Unreleased]: https://github.com/neuron7xLab/GeoSync/compare/v2.1.3...HEAD
[2.1.3]: https://github.com/neuron7xLab/GeoSync/compare/v2.1.2...v2.1.3
[2.1.2]: https://github.com/neuron7xLab/GeoSync/compare/v2.1.1...v2.1.2
[2.1.1]: https://github.com/neuron7xLab/GeoSync/compare/v2.1.0...v2.1.1
[2.1.0]: https://github.com/neuron7xLab/GeoSync/compare/v2.0.0...v2.1.0
[2.0.0]: https://github.com/neuron7xLab/GeoSync/compare/v0.1.0...v2.0.0
[0.1.0]: https://github.com/neuron7xLab/GeoSync/releases/tag/v0.1.0
