# SPDX-License-Identifier: MIT

# === FPM-A (Fractal Project Method) integration ===
.PHONY: fpma-graph fpma-check lock build-package publish-package clean-dist \
	test\:fast test\:all test\:heavy lint lint\:python lint\:go
fpma-graph:
	python -m scripts fpma graph

fpma-check:
	python -m scripts fpma check

.PHONY: lint lint\:python lint\:go
lint: lint\:python lint\:go

lint\:python:
	python -m flake8
	python -m mypy --config-file=mypy.ini

lint\:go:
	golangci-lint run ./...

.PHONY: lock
lock:
	python -m pip install --upgrade pip
	python -m pip install pip-tools
	pip-compile --resolver=backtracking --strip-extras --no-annotate \
	    --constraint constraints/security.txt \
	    --output-file=requirements.lock requirements.txt
	pip-compile --resolver=backtracking --strip-extras --no-annotate \
	    --constraint constraints/security.txt \
	    --output-file=requirements-dev.lock requirements-dev.txt

.PHONY: build-package
build-package: clean-dist
	python -m build --sdist --wheel --outdir dist

.PHONY: publish-package
publish-package: build-package
	twine check dist/*
	twine upload dist/*

.PHONY: clean-dist
clean-dist:
	rm -rf dist build *.egg-info

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
.PHONY: mutation-test
mutation-test:
	mutmut run --use-coverage
	python -m tools.mutation.kill_rate_guard --threshold 0.8
	mutmut results

.PHONY: sbom supply-chain-verify dependencies-check
sbom:
	python -m scripts supply-chain generate-sbom --include-dev --output sbom/cyclonedx-sbom.json

supply-chain-verify:
	python -m scripts supply-chain verify --include-dev

dependencies-check:
	python -m tools.dependencies.check_alignment

.PHONY: security-audit
security-audit:
	python scripts/dependency_audit.py --requirement requirements.txt --requirement requirements-dev.txt

.PHONY: test\:fast-sanity test\:fast-suite
test\:fast-sanity:
	pytest -q markets/orderbook/tests
	pytest -q analytics/tests/test_runner_safety.py
	pytest -q markets/vpin/tests/test_core.py
	pytest -q scripts/tests/test_api_management.py

test\:fast-suite:
	pytest tests/ -m "not slow and not heavy_math and not nightly"

.PHONY: test\:fast
test\:fast: test\:fast-suite

.PHONY: test\:all
test\:all:
	pytest tests/ \
		--cov=core --cov=backtest --cov=execution \
		--cov-config=configs/quality/critical_surface.coveragerc \
		--cov-report=term-missing --cov-report=xml
	python -m tools.coverage.guardrail \
		--config configs/quality/critical_surface.toml \
		--coverage coverage.xml

.PHONY: test\:heavy
test\:heavy:
	pytest tests/ -m "slow or heavy_math or nightly"

