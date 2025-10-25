# Testing Recommendations

Consistent testing habits keep TradePulse stable and resilient. Use the checklist below to choose the right level of coverage before opening a pull request.

## 1. Quick feedback (under 2 minutes)

- Run `pre-commit run --all-files` to lint, format, and enforce security policies defined in the shared configuration.
- Execute targeted unit tests with `pytest tests/<module>` for any package you touched.
- For Rust or Go components, run `cargo test -p <crate>` or `go test ./...` within the corresponding workspace.

## 2. Full local validation (under 10 minutes)

- Install Python dependencies via `pip install -r requirements-dev.txt` using Python 3.11.
- Run `pytest` from the repository root to execute the comprehensive test suite.
- Build the Docker image locally with `docker build -t tradepulse:local .` to catch integration issues early.

## 3. CI parity checks

- Use `act pull_request -W .github/workflows/pre-commit-validation.yml` to emulate the pre-commit workflow.
- Trigger the requirements verification locally with:
  ```bash
  pip install "pip-tools>=7.4.1"
  pip-compile --no-annotate --resolver=backtracking --output-file=requirements.lock --strip-extras --constraint constraints/security.txt requirements.txt
  pip-compile --no-annotate --resolver=backtracking --output-file=requirements-dev.lock --strip-extras --constraint constraints/security.txt requirements-dev.txt
  git diff --stat requirements.lock requirements-dev.lock
  ```
- For Docker builds, mirror the CI command: `docker build --file Dockerfile --tag tradepulse:ci .`.

## 4. When to request additional reviews

- Changes impacting regulatory reporting, security-sensitive paths, or market connectivity require an additional maintainer review.
- Updates to infrastructure or deployment scripts should involve the DevOps rotation for environment-specific validation.
- If automated checks fail intermittently, include logs in the pull request to help reviewers reproduce the issue.

Adhering to these recommendations ensures contributions remain high quality and predictable for the rest of the team.
