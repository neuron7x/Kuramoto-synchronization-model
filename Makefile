# SPDX-License-Identifier: MIT

# ----------------------------------------------------------------------------
# Tool resolution — prefer the project venv when it exists so CI and local
# developers invoke the same interpreter/pytest. Fall back to bare ``python`` /
# ``pytest`` on PATH when the venv is absent (fresh clones, nix shells, etc.).
# ----------------------------------------------------------------------------
PYTHON := $(shell if [ -x .venv/bin/python ]; then echo .venv/bin/python; else echo python; fi)
PYTEST := $(shell if [ -x .venv/bin/pytest ]; then echo .venv/bin/pytest; else echo pytest; fi)
# Interpreter used to build the hermetic clean venv for the MFN release gate.
MFN_RELEASE_PYTHON ?= python3.12
# Pin the timestamp so the MFN evidence bundle is byte-reproducible by default.
SOURCE_DATE_EPOCH ?= 1700000000
export SOURCE_DATE_EPOCH

# ============================================================================
# Standard Entry Points - Use these commands for development
# ============================================================================

.PHONY: help
help:
	@echo "GeoSync Development Commands"
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
	@echo "  make formal-verify - Run formal Z3 invariant and coherence proofs"
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

.PHONY: eval-tick
eval-tick:
	@echo "📊 Running cross-asset Kuramoto shadow evaluator (persisting to results/shadow_live.json)..."
	@mkdir -p results
	@$(PYTHON) scripts/evaluate_cross_asset_kuramoto_shadow.py | tee results/shadow_live.json >/dev/null
	@test -s results/shadow_live.json || { echo "❌ results/shadow_live.json not produced or empty"; exit 1; }
	@echo "✅ shadow_live.json refreshed at $$(stat -c %Y results/shadow_live.json)"

.PHONY: code-quality
code-quality:
	@echo "🔎 Code-hygiene ratchets (fail-closed, monotone-down)..."
	python -m compileall -q scripts/ci/check_code_hygiene.py scripts/ci/check_skip_ratchet.py
	python scripts/ci/check_import_architecture.py
	python scripts/ci/check_code_hygiene.py
	python scripts/ci/check_skip_ratchet.py
	python scripts/ci/check_debt_baseline_monotonic.py
	@echo "✅ Code-quality ratchets held"

.PHONY: mutation-ratchet
mutation-ratchet:
	@echo "🧬 Mutation-kill ratchet (re-probes claim-critical physics on change)..."
	python scripts/ci/check_mutation_kill_ratchet.py --base-ref origin/main
	@echo "✅ Mutation-kill ratchet held"

.PHONY: mutation-enrol-discover mutation-enrol-probe
mutation-enrol-discover:
	@echo "🔎 Discovering unenrolled 1:1 module<->test pairs (trace: where coverage is thin)..."
	python tools/mutation_enrol.py discover --limit $(or $(LIMIT),10) --max-sites $(or $(MAX_SITES),16)
mutation-enrol-probe:
	@echo "🧬 Probing PAIRS serially (tree-restoring); enrol CLEAN with: python tools/mutation_enrol.py enrol --report <json> --apply"
	python tools/mutation_enrol.py probe --pairs $(PAIRS) --json $(or $(OUT),artifacts/mutation_enrol/trace.json)

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
	python scripts/check_cns_ontology_usage.py
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
	@echo "🔒 Running security audits (fail-closed)..."
	python scripts/dependency_audit.py --requirement sbom/combined-requirements.txt --requirement requirements-dev.lock
	python -m bandit -r core/ backtest/ execution/ src/ -ll -q
	@echo "✅ Security audit complete"

.PHONY: deps-audit
deps-audit:
	@echo "🔒 Auditing Python dependencies for known vulnerabilities (fail-closed)..."
	python scripts/dependency_audit.py --requirement requirements.lock --requirement requirements-dev.lock --extra-arg=--desc
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

.PHONY: verify
verify:
	@echo "🔎 Deterministic PR-gate mirror (changeset vs origin/main)..."
	python scripts/ci/verify_changeset.py $(if $(BASE),--base-ref $(BASE),)

.PHONY: gates-all
gates-all:
	@echo "🌀 Whole-tree gate meta-ratchet (every check_* gate vs full tree)..."
	python scripts/ci/run_all_gates.py

.PHONY: signal
signal:
	@echo "📟 Operator-attention signals (graded bands over governed metrics)..."
	python scripts/ci/emit_metric_signals.py

.PHONY: install-hooks
install-hooks:
	@git config core.hooksPath .githooks && echo "✅ git hooks enabled (.githooks) — pre-push runs the gate meta-ratchet"

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
		--cov=core --cov=backtest --cov=execution --cov=geosync \
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
		--cov=core --cov=backtest --cov=execution --cov=geosync \
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
		--cov=core --cov=backtest --cov=execution --cov=geosync \
		--cov-branch \
		--cov-report=xml --cov-report=term-missing --cov-report=html:coverage_html \
		--cov-fail-under=98 \
		--junitxml=reports/full-test-suite.xml \
		--html=reports/full-test-suite-report.html --self-contained-html
	@echo "✅ Full test suite passed with 98% coverage"

# --------------------------------------------------------------------------- #
# Coverage Intelligence Gate (single coverage authority, 90% release gate).
# coverage-baseline : measure the full production surface + emit evidence.
# coverage-90       : enforce the release gate + critical surface (fail closed).
# coverage-next     : print the prioritized list of missing tests.
# --------------------------------------------------------------------------- #
.PHONY: coverage-baseline
# Co-located test suites that physically live under a production package
# (so pytest's top-level `tests/` root never collects them) yet exercise real
# release surface — analytics/regime/fpma/signals, core/neuro, neural_controller,
# orderbook. They are run as a SECOND, --cov-append invocation rather than being
# appended to the `tests/` argument list: under --import-mode=importlib several
# share a basename with files under tests/ (test_core.py, test_engine.py, ...),
# and a single combined collection raises "import file mismatch". Two isolated
# collection roots accumulate into one .coverage file with zero collisions.
# The canonical junit.xml is written by the `tests/` run (it carries the gated
# claim falsifiers); the co-located run writes its own junit to avoid clobbering.
COLOCATED_TESTS := core/neuro/tests analytics/tests analytics/fpma/tests \
	analytics/regime/tests analytics/signals/tests markets/orderbook/tests \
	geosync/neural_controller/tests

coverage-baseline:
	@echo "📊 Measuring full production surface (release_90 profile)..."
	@mkdir -p reports/coverage
	# An enforcement gate must COMPLETE — a release gate that never finishes
	# silently stops enforcing, the exact "covered everywhere that never ran"
	# vacuum this gate exists to prevent.
	#
	# Run SERIALLY. The serial full-surface measurement (~18k tests, ~94 min of
	# CPU) overran the old 50-min CI cap (run 27866729780: the measure step was
	# killed before it enforced); the fix is a recalibrated job timeout (see
	# coverage-intelligence.yml), NOT parallelism. A `-n auto` attempt surfaced
	# xdist-ONLY failures the vacuum had hidden (pytest-benchmark loses timing
	# under xdist; module-scoped logging tests fail by cross-worker ordering) —
	# artifacts of parallel execution, not real regressions. Serial keeps the
	# measured surface and the 90% threshold exactly as enforced and surfaces
	# only real failures. A total hang fails closed via the job-level cap.
	pytest tests/ \
		-m "not flaky and not nightly" \
		--cov-config=configs/quality/release_90.coveragerc \
		--cov --cov-branch \
		--cov-report= \
		--junitxml=reports/coverage/junit.xml
	pytest $(COLOCATED_TESTS) \
		-m "not flaky and not nightly" \
		--cov-config=configs/quality/release_90.coveragerc \
		--cov --cov-append --cov-branch \
		--cov-report=xml:reports/coverage/coverage.xml \
		--cov-report=html:htmlcov \
		--junitxml=reports/coverage/junit_colocated.xml
	python -m tools.coverage.geosync_coverage_intelligence \
		--coverage reports/coverage/coverage.xml \
		--junit reports/coverage/junit.xml \
		--targets configs/quality/coverage_targets.toml \
		--critical configs/quality/critical_surface.toml \
		--claims docs/CLAIMS.yaml \
		--out reports/coverage

.PHONY: coverage-90
coverage-90: coverage-baseline
	@echo "🚦 Enforcing release gate (90%) + critical surface..."
	python -m tools.coverage.geosync_coverage_intelligence \
		--coverage reports/coverage/coverage.xml \
		--junit reports/coverage/junit.xml \
		--targets configs/quality/coverage_targets.toml \
		--critical configs/quality/critical_surface.toml \
		--claims docs/CLAIMS.yaml \
		--out reports/coverage \
		--enforce-release-90 --enforce-critical
	@echo "✅ Release coverage gate satisfied"

.PHONY: coverage-next
coverage-next:
	python -m tools.coverage.geosync_coverage_intelligence \
		--coverage reports/coverage/coverage.xml \
		--junit reports/coverage/junit.xml \
		--targets configs/quality/coverage_targets.toml \
		--critical configs/quality/critical_surface.toml \
		--claims docs/CLAIMS.yaml \
		--out reports/coverage --suggest-tests
	@echo "📂 reports/coverage/next_tests.md"

.PHONY: test-fast
test-fast:
	@echo "🧪 Running fast tests (PR gate, excludes flaky)..."
	pytest tests/ -m "not slow and not heavy_math and not nightly and not flaky"
	@echo "✅ Fast tests passed"

.PHONY: test-heavy
test-heavy:
	@echo "🧪 Running heavy tests..."
	$(PYTEST) tests/ -m "slow or heavy_math or nightly"
	@echo "✅ Heavy tests passed"

.PHONY: perf
perf:
	@echo "⚡ Running performance benchmarks..."
	pytest benchmarks/ --benchmark-only
	@echo "✅ Benchmarks complete"

.PHONY: formal-verify
formal-verify: formal/proof_invariant.py
	@echo "🧠 Running formal verification (invariant + cache coherence)..."
	@if python -c "import z3" >/dev/null 2>&1; then \
		python formal/proof_invariant.py; \
	else \
		echo "SKIP: z3-solver not installed"; \
	fi
	@echo "✅ Formal verification certificates refreshed"

.PHONY: golden-path
golden-path:
	@echo "🎯 GeoSync Golden Path Workflow"
	@echo "===================================="
	@echo ""
	@echo "This demonstrates the complete GeoSync workflow:"
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
	@echo "  • Run full backtest: python examples/neuro_geosync_backtest.py"
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

.PHONY: release-gate
release-gate:
	@echo "🚦 MFN release gate (SOURCE_DATE_EPOCH=$(SOURCE_DATE_EPOCH))..."
	$(PYTHON) -m ruff check geosync/mfn tools/verify_mfn_clean_install.py
	$(PYTHON) -m mypy --strict geosync/mfn tools/verify_mfn_clean_install.py
	$(PYTEST) -q tests/unit/mfn
	$(PYTHON) tools/verify_mfn_clean_install.py \
	    --python $(MFN_RELEASE_PYTHON) \
	    --report artifacts/runs/mfn_product_state.json
	@echo "✅ MFN gate green → artifacts/runs/mfn_product_state.json"
	@echo "ℹ️  full signed release evidence: $(PYTHON) tools/release_evidence_harness.py"

.PHONY: evidence
evidence:
	@echo "🧾 Aggregating claim-governance gates → VERDICT.json ..."
	$(PYTHON) scripts/ci/emit_verdict.py --output artifacts/audit/VERDICT.json
	@echo "✅ release/no-release verdict → artifacts/audit/VERDICT.json"

.PHONY: phd-evidence
phd-evidence:
	@PYTHON=$(PYTHON) bash scripts/ci/phd_evidence.sh

.PHONY: regenerate-evidence
regenerate-evidence:
	@PYTHONPATH=. $(PYTHON) scripts/ci/gen_distinguished_evidence_table.py
	@PYTHONPATH=. $(PYTHON) scripts/ci/gen_law_mechanism_witness_matrix.py
	@PYTHONPATH=. $(PYTHON) scripts/ci/gen_reference_conformance.py
	@PYTHONPATH=. $(PYTHON) scripts/ci/check_physics_law_witness_index.py --write
	@PYTHONPATH=. $(PYTHON) scripts/ci/check_physics_inference_readiness.py --write
	@PYTHONPATH=. $(PYTHON) scripts/generate_claim_hashes.py
	@PYTHONPATH=. $(PYTHON) scripts/generate_claim_graph.py
	@PYTHONPATH=. $(PYTHON) scripts/ci/check_artifact_freshness.py --write
	@echo "regenerated deterministic evidence artifacts + artifacts/.manifest.json"

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
	@ : "$${GEOSYNC_TWO_FACTOR_SECRET:?export GEOSYNC_TWO_FACTOR_SECRET before running scripts-lint}"
	@ : "$${GEOSYNC_BOOTSTRAP_STRATEGY:?export GEOSYNC_BOOTSTRAP_STRATEGY before running scripts-lint}"
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

# ============================================================================
# L2 Ricci cross-sectional edge — demo entry points
# ============================================================================
# ANSI colour helpers (no-op when NO_COLOR is set)
L2_BOLD    := $(shell test -z "$$NO_COLOR" && printf '\033[1m')
L2_DIM     := $(shell test -z "$$NO_COLOR" && printf '\033[2m')
L2_BLUE    := $(shell test -z "$$NO_COLOR" && printf '\033[34m')
L2_GREEN   := $(shell test -z "$$NO_COLOR" && printf '\033[32m')
L2_YELLOW  := $(shell test -z "$$NO_COLOR" && printf '\033[33m')
L2_RESET   := $(shell test -z "$$NO_COLOR" && printf '\033[0m')

L2_DATA_DIR ?= data/binance_l2_perp
L2_PY       := PYTHONPATH=. python
L2_DASHBOARD := results/figures/index.html

define L2_BANNER
	@printf "\n$(L2_BOLD)$(L2_BLUE)==> %s$(L2_RESET)\n$(L2_DIM)%s$(L2_RESET)\n\n" "$(1)" "$(2)"
endef

define L2_CHECK_SUBSTRATE
	@if [ ! -d "$(L2_DATA_DIR)" ]; then \
	    printf "$(L2_YELLOW)[!]$(L2_RESET) L2 substrate missing at $(L2_BOLD)$(L2_DATA_DIR)$(L2_RESET)\n"; \
	    printf "    Override with $(L2_BOLD)L2_DATA_DIR=/path/to/parquets$(L2_RESET) or collect one first.\n"; \
	    exit 2; \
	fi
endef

.PHONY: l2-help l2-demo l2-open l2-figures l2-dashboard l2-smoke l2-deterministic l2-ablations l2-test

## l2-help: list L2 targets with one-liners
l2-help:
	@printf "$(L2_BOLD)L2 Ricci edge — demo targets$(L2_RESET)\n\n"
	@awk '/^## l2-/ {sub(/^## /, ""); split($$0, p, ":"); printf "  $(L2_GREEN)%-18s$(L2_RESET) %s\n", p[1], substr($$0, length(p[1])+3)}' $(MAKEFILE_LIST)
	@printf "\n  Override substrate path: $(L2_BOLD)L2_DATA_DIR=/path/to/parquets make l2-demo$(L2_RESET)\n"
	@printf "  Disable colours:         $(L2_BOLD)NO_COLOR=1 make l2-demo$(L2_RESET)\n\n"

## l2-demo: full pipeline (9 stages) + 5 figures + HTML dashboard (~85 s)
l2-demo:
	$(call L2_BANNER,l2-demo,full 9-stage pipeline + figures + HTML dashboard)
	$(L2_CHECK_SUBSTRATE)
	@$(L2_PY) scripts/run_l2_full_cycle.py --data-dir $(L2_DATA_DIR) --log-level WARNING
	@$(L2_PY) scripts/render_l2_figures.py --log-level WARNING
	@$(L2_PY) scripts/render_l2_dashboard.py --log-level WARNING
	@printf "\n  $(L2_GREEN)✓$(L2_RESET) demo dashboard ready: $(L2_BOLD)$(L2_DASHBOARD)$(L2_RESET)\n"
	@printf "    open with: $(L2_DIM)xdg-open $(L2_DASHBOARD)$(L2_RESET)\n\n"

## l2-open: open the HTML demo dashboard in the default browser (no substrate needed)
l2-open:
	$(call L2_BANNER,l2-open,open $(L2_DASHBOARD) in browser)
	@if [ ! -f "$(L2_DASHBOARD)" ]; then \
	    printf "$(L2_YELLOW)[!]$(L2_RESET) dashboard missing — run $(L2_BOLD)make l2-dashboard$(L2_RESET) first.\n"; \
	    exit 2; \
	fi
	@if command -v xdg-open >/dev/null 2>&1; then xdg-open "$(L2_DASHBOARD)"; \
	elif command -v open >/dev/null 2>&1;     then open "$(L2_DASHBOARD)"; \
	else printf "  $(L2_DIM)no browser-opener found; path is: $(L2_DASHBOARD)$(L2_RESET)\n"; fi
	@printf "  $(L2_GREEN)✓$(L2_RESET) dashboard at $(L2_BOLD)$(L2_DASHBOARD)$(L2_RESET)\n\n"

## l2-figures: re-render fig0-4 from existing results/L2_*.json (fast, no substrate needed)
l2-figures:
	$(call L2_BANNER,l2-figures,re-render fig0-4 from existing results/L2_*.json)
	@$(L2_PY) scripts/render_l2_figures.py --log-level WARNING
	@printf "  $(L2_GREEN)✓$(L2_RESET) results/figures/fig{0..4}_*.png refreshed\n\n"

## l2-dashboard: regenerate the self-contained HTML demo landing page
l2-dashboard:
	$(call L2_BANNER,l2-dashboard,regenerate $(L2_DASHBOARD))
	@$(L2_PY) scripts/render_l2_dashboard.py --log-level WARNING
	@printf "  $(L2_GREEN)✓$(L2_RESET) $(L2_DASHBOARD) refreshed\n\n"

## l2-smoke: single-gate check that the demo is shippable right now
l2-smoke:
	$(call L2_BANNER,l2-smoke,end-to-end demo-readiness gate tests)
	@python -m pytest tests/test_l2_coherence_demo_smoke.py -q

## l2-deterministic: two independent full-cycle runs must be bit-identical
l2-deterministic:
	$(call L2_BANNER,l2-deterministic,bit-identical manifest across two cycle runs)
	$(L2_CHECK_SUBSTRATE)
	@L2_DETERMINISTIC_REPLAY=1 python -m pytest \
	    tests/test_l2_coherence_deterministic_replay.py -q

## l2-ablations: run all 5 ablation / stress axes (hyperparam, symbol, hold, slippage, fee)
l2-ablations:
	$(call L2_BANNER,l2-ablations,5 ablation / stress axes)
	$(L2_CHECK_SUBSTRATE)
	@$(L2_PY) scripts/run_l2_ablation_sensitivity.py --data-dir $(L2_DATA_DIR) --log-level WARNING
	@$(L2_PY) scripts/run_l2_symbol_ablation.py      --data-dir $(L2_DATA_DIR) --log-level WARNING
	@$(L2_PY) scripts/run_l2_hold_ablation.py        --data-dir $(L2_DATA_DIR) --log-level WARNING
	@$(L2_PY) scripts/run_l2_slippage_stress.py      --data-dir $(L2_DATA_DIR) --log-level WARNING
	@$(L2_PY) scripts/run_l2_fee_stress.py           --data-dir $(L2_DATA_DIR) --log-level WARNING
	@printf "\n  $(L2_GREEN)✓$(L2_RESET) all 5 ablation artifacts under results/\n\n"

## l2-test: run every L2 test suite (~40 s, includes ablation + coherence gates)
l2-test:
	$(call L2_BANNER,l2-test,every tests/test_l2_*.py file)
	@python -m pytest tests/test_l2_*.py -q --timeout=60

# ============================================================================
# Evidence Gate (TASK 936) — the single canonical release verification command.
# evidence-gate      : full 13-layer proof (integrity + capsule + claim + coverage).
# evidence-gate-core : layers 1-11 only (sci-core stack, no heavy coverage run).
# ============================================================================
.PHONY: evidence-gate
evidence-gate:
	@bash scripts/ci/evidence_gate.sh

.PHONY: evidence-gate-core
evidence-gate-core:
	@bash scripts/ci/evidence_gate.sh --skip-coverage

## replay-ricci-capsule: credential-free synthetic-negative Ricci replay capsule (no claim promotion)
.PHONY: replay-ricci-capsule
replay-ricci-capsule:
	@python -m pytest tests/research_lines/test_ricci_microstructure_replay_capsule.py -q

# ============================================================================
# ricci_microstructure_v1 — empirical Ollivier-Ricci-on-L2 lane (T3 exploratory)
# Augments PR #1242 with the real-data run + reproducibility gate.
# ============================================================================
RICCI_MANIFEST ?= data/l2_manifest.json
RICCI_CONFIG   ?= configs/research/ricci_microstructure_v1.json
RICCI_SEED     ?= 1337

.PHONY: ricci-capsule
ricci-capsule:
	bash geosync_research/lines/ricci_microstructure_v1/REPRODUCIBILITY_CAPSULE.sh $(RICCI_MANIFEST) $(RICCI_CONFIG) $(RICCI_SEED)

.PHONY: ricci-release-gate
ricci-release-gate:
	@echo "🚦 ricci_microstructure_v1 release gate (locally-verifiable subset)..."
	$(PYTHON) -m ruff check geosync_research tools/research/ricci_microstructure_cli.py
	$(PYTHON) -m mypy --strict geosync_research/lines/ricci_microstructure_v1
	$(PYTEST) -q tests/research_lines/test_ricci_microstructure_v1.py
	$(MAKE) ricci-capsule
	@echo "✅ ricci lane gate green (signed SLSA/cosign provenance runs in CI)"

.PHONY: verify-cognitive-core
verify-cognitive-core: ## Self-verifying cognitive-core meta-gate (one signed verdict)
	PYTHONPATH=. python scripts/ci/verify_cognitive_core.py

# ============================================================================ #
# ⊛ RVG-1 — Repository Verification Gate (additive; see audit/RVG_PROTOCOL.md)
# Namespaced under rvg-* so it never clobbers the existing audit/verify targets.
# ============================================================================ #
RVG_ARTIFACTS := artifacts/rvg
# Audit surface. Defaults to the RVG harness itself (self-consistent, green).
# Widen for a repo-wide audit, e.g. `make rvg RVG_LINT_PATHS=. RVG_MYPY_TARGETS="core src"`.
RVG_TOOLS     := tools/rvg_audit.py tools/rvg_normalize_mutation.py tools/rvg_verify_artifacts.py tools/rvg_assert_verdict.py
RVG_LINT_PATHS   ?= $(RVG_TOOLS) tests/tools/test_rvg_audit.py tests/tools/test_rvg_artifact_verifier.py
RVG_FORMAT_PATHS ?= $(RVG_TOOLS)
RVG_MYPY_TARGETS ?= $(RVG_TOOLS)
# Isolate RVG's self-tests from the repo-wide pytest addopts (-o addopts=): the
# audit must run the same, deterministically, regardless of any --cov/-W/plugin
# flags the repo injects. Never invoke bare `--cov` (expects an argument).
RVG_PYTEST_ARGS  ?= -o addopts= tests/tools/test_rvg_audit.py tests/tools/test_rvg_artifact_verifier.py
RVG_COVERAGERC   ?= audit/rvg.coveragerc
RVG_COMMIT    := $(shell git rev-parse HEAD 2>/dev/null)
RVG_TS        := $(shell date -u +%Y-%m-%dT%H:%M:%SZ)
RVG_PYVER     := $(shell $(PYTHON) -V 2>&1)

.PHONY: rvg rvg-clean rvg-coverage rvg-lint rvg-typecheck rvg-security rvg-sbom rvg-mutation rvg-verify rvg-assert-bootstrap rvg-assert-enforce

rvg-clean:
	rm -rf $(RVG_ARTIFACTS)
	mkdir -p $(RVG_ARTIFACTS)
	$(PYTHON) -V > $(RVG_ARTIFACTS)/python-version.txt

rvg-coverage:
	$(PYTHON) -m coverage run --rcfile=$(RVG_COVERAGERC) \
	  -m pytest --junitxml=$(RVG_ARTIFACTS)/junit.xml $(RVG_PYTEST_ARGS)
	$(PYTHON) -m coverage json --rcfile=$(RVG_COVERAGERC) -o $(RVG_ARTIFACTS)/coverage.json
	$(PYTHON) -m coverage xml  --rcfile=$(RVG_COVERAGERC) -o $(RVG_ARTIFACTS)/coverage.xml
	-$(PYTHON) -m coverage report --rcfile=$(RVG_COVERAGERC)

rvg-lint:
	$(PYTHON) -m ruff check $(RVG_LINT_PATHS) --output-format=json > $(RVG_ARTIFACTS)/ruff.json || true
	# Format-check only the RVG surface: the repo's canonical formatter is black,
	# so `ruff format --check .` would false-fail on black-formatted files.
	$(PYTHON) -m ruff format --check $(RVG_FORMAT_PATHS)

rvg-typecheck:
	$(PYTHON) -m mypy $(RVG_MYPY_TARGETS) --show-error-codes --no-error-summary \
	  > $(RVG_ARTIFACTS)/mypy.txt || true

rvg-security:
	# pip-audit is NEVER masked with `|| true` (repo policy — see
	# tests/ci/test_makefile_audit_fail_closed.py). It writes the JSON report to
	# --output and then exits non-zero when advisories are present. The `-`
	# prefix lets Make continue PAST that findings-exit so the pipeline reaches
	# the verdict — which is RVG's actual fail-closed gate: rvg_audit.py FAILs on
	# high/critical advisories AND on a missing pip-audit.json (absent auditor →
	# missing evidence → FAIL). Nothing goes green while a real finding exists.
	-$(PYTHON) -m pip_audit --format=json --output=$(RVG_ARTIFACTS)/pip-audit.json
	command -v osv-scanner >/dev/null && osv-scanner --format=json --output=$(RVG_ARTIFACTS)/osv.json . || true
	command -v semgrep >/dev/null && semgrep scan --config=p/owasp-top-ten --json > $(RVG_ARTIFACTS)/semgrep.json || true

rvg-sbom:
	# Fail closed: a real CycloneDX SBOM or nothing. The previous empty-components
	# placeholder is NOT a dependency inventory (sbom_present() now rejects it), so
	# masking a missing generator would ship zero supply-chain evidence as "green".
	command -v cyclonedx-py >/dev/null || { echo "rvg-sbom: cyclonedx-py missing (pip install cyclonedx-bom)"; exit 1; }
	cyclonedx-py environment --output-format JSON --output-file $(RVG_ARTIFACTS)/sbom.cdx.json
	test -s $(RVG_ARTIFACTS)/sbom.cdx.json

# Mutation evidence. Three explicit modes — never a fabricated `tool: none` score:
#   real      run mutmut, normalize its results (default; real oracle signal)
#   explicit  pass measured counts via RVG_MUTATION_ARGS (deterministic re-runs)
#   bootstrap emit explicit non-enforcing evidence (no score claimed) — for the
#             bootstrap CI posture where the full repo cannot yet run a campaign
# See audit/RVG_PROTOCOL.md §6.
RVG_MUTATION_MODE    ?= real
RVG_MUTATION_ARGS    ?= --tool mutmut --killed 0 --survived 0
RVG_MUTATION_SUMMARY := $(RVG_ARTIFACTS)/mutmut-results.txt
rvg-mutation:
ifeq ($(RVG_MUTATION_MODE),real)
	command -v mutmut >/dev/null || { echo "rvg-mutation: mutmut missing"; exit 1; }
	-mutmut run
	mutmut results > $(RVG_MUTATION_SUMMARY)
	$(PYTHON) tools/rvg_normalize_mutation.py --from-mutmut $(RVG_MUTATION_SUMMARY) \
	  --out $(RVG_ARTIFACTS)/mutation.json
else ifeq ($(RVG_MUTATION_MODE),explicit)
	$(PYTHON) tools/rvg_normalize_mutation.py $(RVG_MUTATION_ARGS) \
	  --out $(RVG_ARTIFACTS)/mutation.json
else ifeq ($(RVG_MUTATION_MODE),bootstrap)
	$(PYTHON) tools/rvg_normalize_mutation.py --bootstrap-report-only \
	  --out $(RVG_ARTIFACTS)/mutation.json
else
	@echo "rvg-mutation: invalid RVG_MUTATION_MODE=$(RVG_MUTATION_MODE) (real|explicit|bootstrap)"; exit 1
endif

rvg-verify:
	# Bind source + evidence artifacts first so the verdict is hash-provable.
	find src tests pyproject.toml audit tools $(RVG_ARTIFACTS) -type f 2>/dev/null | sort | xargs sha256sum > $(RVG_ARTIFACTS)/audit.hashes
	# `-` prefix: a FAIL verdict (exit 1) must NOT abort the recipe before the
	# manifest is re-bound to include the emitted verdict. Soundness (the re-bind +
	# verifier below) is the blocking step; the PASS/FAIL policy is enforced
	# separately by rvg-assert-bootstrap / rvg-assert-enforce.
	-$(PYTHON) tools/rvg_audit.py \
	  --coverage $(RVG_ARTIFACTS)/coverage.json \
	  --junit $(RVG_ARTIFACTS)/junit.xml \
	  --mutation $(RVG_ARTIFACTS)/mutation.json \
	  --ruff $(RVG_ARTIFACTS)/ruff.json \
	  --mypy $(RVG_ARTIFACTS)/mypy.txt \
	  --pip-audit $(RVG_ARTIFACTS)/pip-audit.json \
	  --sbom $(RVG_ARTIFACTS)/sbom.cdx.json \
	  --thresholds audit/thresholds.json \
	  --hash-manifest $(RVG_ARTIFACTS)/audit.hashes \
	  --repo neuron7xLab/GeoSync --commit "$(RVG_COMMIT)" \
	  --timestamp "$(RVG_TS)" --python-version "$(RVG_PYVER)" \
	  --out-json $(RVG_ARTIFACTS)/RVG_VERDICT.json \
	  --out-md $(RVG_ARTIFACTS)/RVG_VERDICT.md
	# Re-bind to include the emitted verdict itself.
	find src tests pyproject.toml audit tools $(RVG_ARTIFACTS) -type f 2>/dev/null | sort | xargs sha256sum > $(RVG_ARTIFACTS)/audit.hashes
	$(PYTHON) tools/rvg_verify_artifacts.py $(RVG_ARTIFACTS)/RVG_VERDICT.json $(RVG_ARTIFACTS)/audit.hashes audit/schema/verdict.schema.json

# Explicit CI enforcement gates (choose ONE in the workflow — never ambiguous).
rvg-assert-bootstrap:
	$(PYTHON) tools/rvg_assert_verdict.py $(RVG_ARTIFACTS)/RVG_VERDICT.json --mode bootstrap
rvg-assert-enforce:
	$(PYTHON) tools/rvg_assert_verdict.py $(RVG_ARTIFACTS)/RVG_VERDICT.json --mode enforce

rvg: rvg-clean rvg-coverage rvg-lint rvg-typecheck rvg-security rvg-sbom rvg-mutation rvg-verify
