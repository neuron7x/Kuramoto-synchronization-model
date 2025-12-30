# Dependency Security Workflow

## Install (deterministic + constrained)

- Always install Python dependencies with the security constraint file and the locked manifest:

  ```bash
  pip install -c constraints/security.txt -r sbom/combined-requirements.txt
  pip install -c constraints/security.txt -r requirements-dev.lock  # when dev tooling is needed
  ```

- Never install directly from `requirements.txt` or `pyproject.toml` in CI/CD or production paths.

## Bump pins safely

1. Update `constraints/security.txt` with the vetted version (e.g., from pip-audit/OSV/Dependabot).
2. Regenerate locks to capture the new pins:

   ```bash
   python -m pip install --upgrade pip-tools
   pip-compile --constraint=constraints/security.txt --no-annotate --output-file=requirements.lock --strip-extras requirements.txt
   pip-compile --constraint=constraints/security.txt --no-annotate --output-file=requirements-dev.lock --strip-extras requirements-dev.txt
   cp requirements.lock sbom/combined-requirements.txt
   ```

3. Commit the updated constraint + lock files together.

## Validate before merging

Run the security gates locally (mirrors CI):

```bash
python scripts/security/check_dependency_drift.py --output artifacts/security/dependency-drift.json
pip-audit --desc --format json --output artifacts/security/pip-audit.json --severity HIGH --severity CRITICAL -r sbom/combined-requirements.txt
make lint
make test
```

Both reports (`artifacts/security/dependency-drift.json`, `artifacts/security/pip-audit.json`) should exist and contain no HIGH/CRITICAL findings.
