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
	@echo "  make install       - Install runtime dependencies only"
	@echo "  make dev-install   - Install all dependencies (dev + runtime)"
	@echo "  make golden-path   - Demo complete workflow (data → analysis → backtest)"
	@echo "  make test          - Run core test suite (fast, CI-safe)"
	@echo "  make lint          - Run all linters (Python + Go + shell)"
	@echo "  make format        - Auto-format code (black, isort, ruff)"
	@echo "  make audit         - Run security audits (bandit, pip-audit)"
	@echo "  make clean         - Remove cache files and build artifacts"
	@echo ""
	@echo "Dependency Management:"
	@echo "  make deps-update   - Regenerate lock files from requirements.txt"
	@echo "  make deps-audit    - Audit dependencies for vulnerabilities"
	@echo "  make guard-python-matrix - Verify Python version consistency"
	@echo "  make clean-deps    - Clean dependency caches"
	@echo ""
	@echo "Extended Commands:"
	@echo "  make test-coverage - Generate HTML/XML coverage reports"
	@echo "  make test-all      - Run full test suite with coverage"
	@echo "  make test-ci-full  - Run full suite with 98% coverage gate (CI match)"
	@echo "  make test-fast     - Run fast unit tests only (PR gate)"
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
	@echo "Calibration Commands:"
	@echo "  make calibrate-list       - List available calibration profiles"
	@echo "  make calibrate-validate   - Validate current configurations"
	@echo "  make calibrate-conservative - Apply conservative profile (low risk)"
	@echo "  make calibrate-balanced   - Apply balanced profile (moderate risk)"
	@echo "  make calibrate-aggressive - Apply aggressive profile (high risk)"
	@echo ""

# ============================================================================
# Standard Targets
# ============================================================================

.PHONY: install
install:
	@echo "📦 Installing runtime dependencies..."
	python -m pip install --upgrade pip setuptools wheel
	pip install -c constraints/security.txt -r requirements.lock
	@echo "✅ Runtime dependencies installed"

.PHONY: dev-install
dev-install:
	@echo "📦 Installing development dependencies..."
	python -m pip install --upgrade pip setuptools wheel
	pip install -c constraints/security.txt -r requirements.lock
	pip install -c constraints/security.txt -r requirements-dev.lock
	@echo "✅ Development dependencies installed"

.PHONY: deps-update
deps-update:
	@echo "🔄 Updating lock files from requirements.txt..."
	@echo "This will regenerate requirements.lock and requirements-dev.lock with pinned versions"
	python -m pip install --upgrade pip-tools
	pip-compile --constraint=constraints/security.txt --no-annotate --output-file=requirements.lock --strip-extras requirements.txt
	pip-compile --constraint=constraints/security.txt --no-annotate --output-file=requirements-dev.lock --strip-extras requirements-dev.txt
	@echo "✅ Lock files updated"
	@echo "⚠️  Review changes with: git diff requirements*.lock"
	@echo "⚠️  Run 'make deps-audit' to check for vulnerabilities"

.PHONY: clean-deps
clean-deps:
	@echo "🧹 Cleaning dependency caches..."
	rm -rf ~/.cache/pip
	rm -rf .eggs/
	find . -name '*.egg-info' -exec rm -rf {} + 2>/dev/null || true
	find . -name '*.egg' -exec rm -f {} + 2>/dev/null || true
	@echo "✅ Dependency caches cleaned"

.PHONY: test
test:
	@echo "🧪 Running fast PR gate tests (matches CI fast-unit-tests)..."
	pytest tests/ -m "not slow and not heavy_math and not nightly and not flaky" -q
	@echo "✅ Tests passed"

.PHONY: lint
lint: lint-python lint-go lint-shell
	@echo "✅ All linters passed"

.PHONY: lint-python
lint-python:
	@echo "🔍 Linting Python code..."
	python -m ruff check .
	python -m flake8
	python scripts/check_namespace_policy.py
	python scripts/check_serotonin_namespace.py
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
	python -m pip_audit -r sbom/combined-requirements.txt -r requirements-dev.lock || echo "⚠️  pip-audit found issues - review above output"
	python -m bandit -r core/ backtest/ execution/ src/ -ll -q
	@echo "✅ Security audit complete"

.PHONY: deps-audit
deps-audit:
	@echo "🔒 Auditing Python dependencies for known vulnerabilities..."
	@echo "Checking runtime dependencies (requirements.lock)..."
	python -m pip_audit -r requirements.lock --desc || true
	@echo ""
	@echo "Checking dev dependencies (requirements-dev.lock)..."
	python -m pip_audit -r requirements-dev.lock --desc || true
	@echo ""
	@echo "✅ Dependency audit complete"
	@echo "📖 See https://pypi.org/project/pip-audit/ for more info"

.PHONY: guard-python-matrix
guard-python-matrix:
	@echo "🐍 Checking Python version consistency..."
	python scripts/check_python_matrix.py
	@echo "✅ Python version matrix is consistent"

.PHONY: arch-validate
arch-validate:
	@echo "🏗️  Running architecture guardrails..."
	python scripts/check_namespace_integrity.py
	python scripts/check_single_entrypoint.py
	python scripts/check_config_single_source.py
	@echo "✅ Architecture guardrails passed"

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

.PHONY: test-ci-full
test-ci-full:
	@echo "🧪 Running full test suite with 98% coverage gate (matches CI)..."
	@mkdir -p reports
	pytest tests/ \
		-m "not flaky" \
		--cov=core --cov=backtest --cov=execution \
		--cov-branch \
		--cov-report=xml --cov-report=term-missing --cov-report=html:coverage_html \
		--cov-fail-under=98 \
		--junitxml=reports/full-test-suite.xml \
		--html=reports/full-test-suite-report.html --self-contained-html
	@echo "✅ Full test suite passed with 98% coverage"

.PHONY: test-fast
test-fast:
	@echo "🧪 Running fast tests (PR gate, excludes flaky)..."
	pytest tests/ -m "not slow and not heavy_math and not nightly and not flaky"
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

.PHONY: golden-path
golden-path:
	@echo "🎯 TradePulse Golden Path Workflow"
	@echo "===================================="
	@echo ""
	@echo "This demonstrates the complete TradePulse workflow:"
	@echo "  1. Data generation (synthetic market data)"
	@echo "  2. Market analysis (regime detection)"
	@echo "  3. Backtest integration (strategy validation)"
	@echo "  4. Results artifact (PnL summary)"
	@echo ""
	@echo "Prerequisites: Run 'make dev-install' first"
	@echo ""
	@echo "Step 1/3: Generating synthetic market data..."
	@PYTHONPATH=. python -c "import numpy as np; import pandas as pd; from examples.quick_start import sample_df; df = sample_df(n=500, seed=42); print('✓ Generated 500 bars of synthetic data')"
	@echo ""
	@echo "Step 2/3: Running market analysis..."
	@PYTHONPATH=. python examples/quick_start.py --seed 42 --num-points 500
	@echo ""
	@echo "Step 3/3: Running backtest integration test..."
	@pytest tests/integration/test_golden_path_backtest.py::TestGoldenPathBasic::test_backtest_produces_valid_result -v --tb=short
	@echo ""
	@echo "✅ Golden Path Complete!"
	@echo ""
	@echo "📊 What was demonstrated:"
	@echo "  • Synthetic data generation with deterministic seed"
	@echo "  • Market regime detection using Kuramoto-Ricci indicators"
	@echo "  • Backtest execution with valid PnL calculation"
	@echo ""
	@echo "📖 Next steps:"
	@echo "  • Try your own data: python examples/quick_start.py --csv your_data.csv"
	@echo "  • Run full backtest: python examples/neuro_trade_pulse_backtest.py"
	@echo "  • View integration tests: pytest tests/integration/test_golden_path_backtest.py -v"
	@echo ""

.PHONY: perf-golden-path
perf-golden-path:
	@echo "⚡ Running golden path performance benchmark..."
	@mkdir -p reports/perf
	pytest tests/perf/test_golden_path_backtest_perf.py -v
	@echo "✅ Golden path performance benchmark complete"
	@echo "📊 Results available at: reports/perf/golden_path_backtest.json"

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
# Calibration Targets
# ============================================================================

.PHONY: calibrate-list
calibrate-list:
	@echo "📊 Available calibration profiles:"
	@python scripts/calibrate_controllers.py --list-profiles

.PHONY: calibrate-validate
calibrate-validate:
	@echo "✓ Validating NAK controller configuration..."
	@python scripts/calibrate_controllers.py --validate nak_controller/conf/nak.yaml
	@echo ""
	@echo "✓ Validating Dopamine controller configuration..."
	@python scripts/calibrate_controllers.py --validate config/dopamine.yaml
	@echo ""
	@echo "✅ All configurations validated"

.PHONY: calibrate-conservative
calibrate-conservative:
	@echo "⚙️  Applying CONSERVATIVE calibration profile..."
	@echo ""
	@python scripts/calibrate_controllers.py --controller nak --profile conservative --output conf/nak/conservative.yaml
	@echo ""
	@python scripts/calibrate_controllers.py --controller dopamine --profile conservative --output config/profiles/conservative_calibrated.yaml
	@echo ""
	@echo "✅ Conservative profile applied. Review conf/nak/conservative.yaml and config/profiles/conservative_calibrated.yaml"

.PHONY: calibrate-balanced
calibrate-balanced:
	@echo "⚙️  Applying BALANCED calibration profile..."
	@echo ""
	@python scripts/calibrate_controllers.py --controller nak --profile balanced --output conf/nak/balanced.yaml
	@echo ""
	@python scripts/calibrate_controllers.py --controller dopamine --profile balanced --output config/profiles/balanced_calibrated.yaml
	@echo ""
	@echo "✅ Balanced profile applied. Review conf/nak/balanced.yaml and config/profiles/balanced_calibrated.yaml"

.PHONY: calibrate-aggressive
calibrate-aggressive:
	@echo "⚙️  Applying AGGRESSIVE calibration profile..."
	@echo ""
	@python scripts/calibrate_controllers.py --controller nak --profile aggressive --output conf/nak/aggressive.yaml
	@echo ""
	@python scripts/calibrate_controllers.py --controller dopamine --profile aggressive --output config/profiles/aggressive_calibrated.yaml
	@echo ""
	@echo "✅ Aggressive profile applied. Review conf/nak/aggressive.yaml and config/profiles/aggressive_calibrated.yaml"

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
	@ : "$${TRADEPULSE_TWO_FACTOR_SECRET:?export TRADEPULSE_TWO_FACTOR_SECRET before running scripts-lint}"
	@ : "$${TRADEPULSE_BOOTSTRAP_STRATEGY:?export TRADEPULSE_BOOTSTRAP_STRATEGY before running scripts-lint}"
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
