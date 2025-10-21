# SPDX-License-Identifier: MIT

# === FPM-A (Fractal Project Method) integration ===
.PHONY: fpma-graph fpma-check lock build-package publish-package clean-dist \
        test\:fast test\:all test\:heavy
fpma-graph:
	python -m scripts fpma graph

fpma-check:
	python -m scripts fpma check

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


.PHONY: i18n-validate
i18n-validate:
	python scripts/localization/sync_translations.py
.PHONY: mutation-test
mutation-test:
	mutmut run --use-coverage
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

.PHONY: docker-build docker-scan docker-sign docker-policy docker-all
docker-build:
	./docker/build_and_verify.sh build

docker-scan:
	./docker/build_and_verify.sh scan

docker-sign:
	./docker/build_and_verify.sh sign

docker-policy:
	./docker/build_and_verify.sh policy

docker-all:
	./docker/build_and_verify.sh all

.PHONY: helm-template helm-package helm-test helm-diff
helm-template:
	helm template tradepulse ./deploy/helm/tradepulse --values ./deploy/helm/tradepulse/values.yaml

helm-package:
	helm package ./deploy/helm/tradepulse --destination dist

helm-test:
	helm test tradepulse

helm-diff:
	helm diff upgrade tradepulse ./deploy/helm/tradepulse --values ./deploy/helm/tradepulse/values.yaml || true

.PHONY: policy-test
policy-test:
	./docker/build_and_verify.sh policy

.PHONY: test\:fast
test\:fast:
        pytest tests/ -m "not slow and not heavy_math and not nightly"

.PHONY: test\:all
test\:all:
	pytest tests/ --cov=core --cov=backtest --cov=execution --cov=analytics --cov-branch --cov-report=term-missing

.PHONY: test\:heavy
test\:heavy:
	pytest tests/ -m "slow or heavy_math or nightly"

