# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary

# ============================================================================
# Standard Entry Points - Use these commands for development
# ============================================================================

.PHONY: help
help:
	@echo "TradePulse Development Commands"
	@echo "================================"
	@echo ""
	@echo "Core Commands:"
	@echo "  make install       - Install all dependencies (dev + runtime)"
	@echo "  make test          - Run core test suite (fast, CI-safe)"
	@echo "  make lint          - Run all linters (Python + Go + shell)"
	@echo "  make format        - Auto-format code (black, isort, ruff)"
	@echo "  make audit         - Run security audits (bandit, pip-audit)"
	@echo "  make clean         - Remove cache files and build artifacts"
	@echo ""
	@echo "Extended Commands:"
	@echo "  make test-coverage - Generate HTML/XML coverage reports"
	@echo "  make test-all      - Run full test suite with coverage"
	@echo "  make test-fast     - Run fast unit tests only"
	@echo "  make test-heavy    - Run slow/heavy tests"
	@echo "  make perf          - Run performance benchmarks"
	@echo "  make e2e           - Run end-to-end smoke tests"
	@echo "  make docs          - Build documentation"
	@echo "  make release       - Helper for local release builds"
	@echo ""
	@echo "Specialized Commands:"
	@echo "  make fpma-check    - Run FPM-A architecture checks"
	@echo "  make mutation-test - Run mutation testing"
	@echo "  make sbom          - Generate SBOM"
	@echo ""

# ============================================================================
# Standard Targets
# ============================================================================

.PHONY: install
install:
	@echo "📦 Installing dependencies..."
	python -m pip install --upgrade pip setuptools wheel
	pip install -c constraints/security.txt -r requirements.txt
	pip install -c constraints/security.txt -r requirements-dev.txt
	@echo "✅ Dependencies installed"

.PHONY: test
test:
	@echo "🧪 Running core test suite..."
	pytest tests/ -m "not slow and not heavy_math and not nightly" -q
	@echo "✅ Tests passed"

.PHONY: lint
lint: lint-python lint-go lint-shell
	@echo "✅ All linters passed"

.PHONY: lint-python
lint-python:
	@echo "🔍 Linting Python code..."
	python -m ruff check .
	python -m flake8
	python -m mypy --config-file=mypy.ini

.PHONY: lint-go
lint-go:
	@echo "🔍 Linting Go code..."
	@if command -v golangci-lint >/dev/null 2>&1; then \
		golangci-lint run ./...; \
	else \
		echo "⚠️  golangci-lint not installed"; \
		echo "    Install: go install github.com/golangci/golangci-lint/cmd/golangci-lint@latest"; \
		echo "    Or via package manager: brew install golangci-lint"; \
		echo "    Skipping Go linting in local development (required in CI)"; \
	fi

.PHONY: lint-shell
lint-shell:
	@echo "🔍 Linting shell scripts..."
	@if command -v shellcheck >/dev/null 2>&1; then \
		find scripts/ -name "*.sh" -type f -exec shellcheck {} +; \
	else \
		echo "⚠️  shellcheck not installed"; \
		echo "    Install: apt-get install shellcheck (Ubuntu/Debian)"; \
		echo "    Or: brew install shellcheck (macOS)"; \
		echo "    Or: https://github.com/koalaman/shellcheck#installing"; \
		echo "    Skipping shell linting in local development (required in CI)"; \
	fi

.PHONY: format
format:
	@echo "✨ Formatting code..."
	python -m ruff check --fix .
	python -m black .
	python -m isort .
	@echo "✅ Code formatted"

.PHONY: audit
audit:
	@echo "🔒 Running security audits..."
	@echo "Note: pip-audit may report vulnerabilities that need review"
	python -m pip_audit -r requirements.txt -r requirements-dev.txt || echo "⚠️  pip-audit found issues - review above output"
	python -m bandit -r core/ backtest/ execution/ src/ -ll -q
	@echo "✅ Security audit complete"

.PHONY: clean
clean:
	@echo "🧹 Cleaning cache and build artifacts..."
	rm -rf .pytest_cache .mypy_cache .ruff_cache __pycache__ .coverage coverage.xml htmlcov/
	rm -rf dist/ build/ *.egg-info
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete
	find . -type f -name ".DS_Store" -delete
	@echo "✅ Cleaned"

# ============================================================================
# Extended Test Targets
# ============================================================================

.PHONY: test-coverage
test-coverage:
	@echo "📊 Generating coverage report..."
	@mkdir -p reports/coverage
	pytest tests/ \
		--cov=core --cov=backtest --cov=execution \
		--cov-report=term-missing \
		--cov-report=html:reports/coverage \
		--cov-report=xml:reports/coverage/coverage.xml \
		-m "not slow and not heavy_math and not nightly"
	@echo "✅ Coverage report generated"
	@echo "📂 HTML report: reports/coverage/index.html"
	@echo "📄 XML report: reports/coverage/coverage.xml"

.PHONY: test-all
test-all:
	@echo "🧪 Running full test suite with coverage..."
	pytest tests/ \
		--cov=core --cov=backtest --cov=execution \
		--cov-config=configs/quality/critical_surface.coveragerc \
		--cov-report=term-missing --cov-report=xml
	python -m tools.coverage.guardrail \
		--config configs/quality/critical_surface.toml \
		--coverage coverage.xml
	@echo "✅ Full test suite passed"

.PHONY: test-fast
test-fast:
	@echo "🧪 Running fast tests..."
	pytest tests/ -m "not slow and not heavy_math and not nightly"
	@echo "✅ Fast tests passed"

.PHONY: test-heavy
test-heavy:
	@echo "🧪 Running heavy tests..."
	pytest tests/ -m "slow or heavy_math or nightly"
	@echo "✅ Heavy tests passed"

.PHONY: perf
perf:
	@echo "⚡ Running performance benchmarks..."
	pytest benchmarks/ --benchmark-only
	@echo "✅ Benchmarks complete"

.PHONY: e2e
e2e:
	@echo "🔄 Running end-to-end tests..."
	pytest tests/smoke -m smoke -q
	@echo "✅ E2E tests passed"

.PHONY: docs
docs:
	@echo "📚 Building documentation..."
	mkdocs build
	@echo "✅ Documentation built"

.PHONY: release
release: clean
	@echo "📦 Building release packages..."
	python -m build --sdist --wheel --outdir dist
	twine check dist/*
	@echo "✅ Release packages built (run 'twine upload dist/*' to publish)"

# ============================================================================
# Specialized Targets (Legacy/Advanced)
# ============================================================================

.PHONY: fpma-graph fpma-check
fpma-graph:
	python -m scripts fpma graph

fpma-check:
	python -m scripts fpma check

.PHONY: lock
lock:
	@echo "🔒 Locking dependencies..."
	python -m pip install --upgrade pip pip-tools
	pip-compile --resolver=backtracking --strip-extras --no-annotate \
	    --constraint constraints/security.txt \
	    --output-file=requirements.lock requirements.txt
	pip-compile --resolver=backtracking --strip-extras --no-annotate \
	    --constraint constraints/security.txt \
	    --output-file=requirements-dev.lock requirements-dev.txt
	@echo "✅ Dependencies locked"

.PHONY: mutation-test
mutation-test:
	@echo "🧬 Running mutation testing..."
	mutmut run --use-coverage
	python -m tools.mutation.kill_rate_guard --threshold 0.8
	mutmut results
	@echo "✅ Mutation testing complete"

.PHONY: sbom
sbom:
	@echo "📋 Generating SBOM..."
	python -m scripts supply-chain generate-sbom --include-dev --output sbom/cyclonedx-sbom.json
	@echo "✅ SBOM generated"

# ============================================================================
# Advanced/Specialized Targets (kept for backward compatibility)
# ============================================================================

.PHONY: generate schema-validate schema-catalog
generate:
	buf generate
	PYTHONPATH=. python tools/schema/generate_event_types.py

schema-validate:
	PYTHONPATH=. python tools/schema/validate_compatibility.py --registry schemas/events

schema-catalog:
	PYTHONPATH=. python tools/schema/render_catalog.py --registry schemas/events --output docs/integrations/event_channels.md

.PHONY: scripts-lint scripts-test scripts-gen-proto scripts-dev-up scripts-dev-down
scripts-lint:
	TRADEPULSE_TWO_FACTOR_SECRET=MFRGGZDFMZTWQ2LK \
	TRADEPULSE_BOOTSTRAP_STRATEGY=lazy \
	python -m scripts lint

scripts-test:
	python -m scripts test

scripts-gen-proto:
	python -m scripts gen-proto

scripts-dev-up:
	python -m scripts dev-up

scripts-dev-down:
	python -m scripts dev-down

.PHONY: docs-lint
docs-lint:
	python -m tools.docs.lint_docs

.PHONY: i18n-validate
i18n-validate:
	python scripts/localization/sync_translations.py

.PHONY: supply-chain-verify dependencies-check
supply-chain-verify:
	python -m scripts supply-chain verify --include-dev

dependencies-check:
	python -m tools.dependencies.check_alignment

.PHONY: security-audit security-test
security-audit:
	python scripts/dependency_audit.py --requirement requirements.txt --requirement requirements-dev.txt

security-test:
	python -m tools.security.sast --fail-on-severity MEDIUM
	python -m tools.security.dast_probe
