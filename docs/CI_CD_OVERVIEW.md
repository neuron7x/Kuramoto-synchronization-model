# CI/CD Overview — TradePulse

> **TL;DR:** Nothing breaks `main` — CI/CD strictly validates lint, tests, coverage, security, and build.

## Principles

1. **Never disable tests/lint** — fix the issue, don't work around it.
2. **One pipeline = clear set of checks** — no Frankenstein monsters.
3. **Reproducibility, speed, predictability** — local = CI.

---

## Quality Gates (What Blocks Merge)

| Gate | Threshold | Enforced By | Action on Failure |
|------|-----------|-------------|-------------------|
| **Code Coverage** | ≥ 98% | `tests.yml` | ❌ Blocks merge, adds `missing-coverage` label |
| **Mutation Kill Rate** | ≥ 90% | `ci.yml` | ❌ Blocks merge |
| **Lint (ruff/black/mypy)** | No errors | `tests.yml` | ❌ Blocks merge |
| **Security Scan** | No critical CVEs | `security.yml` | ❌ Blocks merge for critical, ⚠️ warns for high |
| **Tests** | All pass | `tests.yml` | ❌ Blocks merge |

---

## Workflow Structure

### Stage 1: Lint + Static Analysis (`tests.yml`)
- **ruff** — Python linter (fast, modern)
- **black** — Code formatter check
- **mypy** — Type checking
- **slotscheck** — `__slots__` validation for core modules
- **detect-secrets** — Secrets detection in code
- **shellcheck/shfmt** — Shell script linting

### Stage 2: Unit Tests (`tests.yml`)
- Runs all `tests/` with pytest
- Coverage: `core/`, `backtest/`, `execution/`
- Parallel execution with xdist
- Property-based tests with Hypothesis

### Stage 3: Integration/E2E Tests (`tests.yml`, `e2e-integration.yml`)
- Integration tests in `tests/integration/`
- E2E tests in `tests/e2e/`
- UI tests with Playwright (on `ui/` changes)

### Stage 4: Security Checks (`security.yml`)
- **Bandit** — SAST for Python
- **pip-audit/Safety** — Dependency vulnerability scan
- **Trivy/Grype** — Container image scan
- **CodeQL** — GitHub security analysis (Python, JS, Go)
- **detect-secrets** — Hardcoded secrets detection

### Stage 5: Build Artifacts (`ci.yml`, `enterprise-cicd.yml`)
- Docker images → ghcr.io
- Multi-arch builds (linux/amd64, linux/arm64)
- Image signing with Cosign
- SLSA provenance generation

---

## Основні Workflow Files

| Workflow | Trigger | Purpose |
|----------|---------|---------|
| `tests.yml` | PR, push to main/develop | Lint, tests, coverage |
| `ci.yml` | push to main | Coverage aggregation, mutation testing, container publish |
| `security.yml` | push, weekly schedule | Security scans (SAST, dependencies, containers) |
| `enterprise-cicd.yml` | push to main, manual | Full enterprise pipeline with deployment |
| `e2e-integration.yml` | PR (on specific paths) | E2E/integration tests |
| `ci-hardening.yml` | PR on workflows, weekly | Workflow security audit |
| `pr-release-gate.yml` | PR to main/develop | Risk assessment and labeling |

---

## Як запустити локально

### Повний lint check
```bash
# Pre-commit (all hooks)
pre-commit run --all-files

# Individual tools
python -m ruff check .
python -m black --check .
python -m mypy
python -m slotscheck --module core --module backtest --module execution
```

### Tests з coverage
```bash
# Fast unit tests
make test:fast

# All tests with coverage
make test:all

# Specific test suite
pytest tests/unit -v --cov=core --cov-report=term-missing
```

### Coverage check (98% threshold)
```bash
pytest tests/ \
  --cov=core --cov=backtest --cov=execution \
  --cov-fail-under=98 \
  --cov-report=term-missing
```

### Mutation testing (90% kill rate)
```bash
make mutation-test
# or
mutmut run --paths-to-mutate=core,backtest,execution --tests-dir=tests
python -m tools.mutation.kill_rate_guard --threshold=0.9
```

### Security scans
```bash
# Bandit SAST
python -m bandit -r core backtest execution -ll

# Dependency audit
python scripts/dependency_audit.py --requirement requirements.txt
```

### Docker build
```bash
docker build -t tradepulse:local .
```

---

## Debugging CI Failures

### "Coverage below 98%"
1. Check `coverage.xml` artifact in workflow run
2. Identify uncovered lines: `pytest --cov-report=html`
3. Add tests for uncovered code
4. Verify locally: `pytest --cov-fail-under=98`

### "Mutation kill rate below 90%"
1. Download `mutation_summary.json` artifact
2. Run locally: `mutmut results`
3. Review surviving mutants: `mutmut show <id>`
4. Add tests that would catch the mutations

### "Lint failures"
1. Run `pre-commit run --all-files` locally
2. Auto-fix with: `ruff check . --fix && black .`
3. Manual fix for mypy type errors

### "Security scan failed"
1. Check workflow logs for specific CVE/vulnerability
2. For dependencies: update in `requirements*.txt`
3. For container: update base image or fix Dockerfile
4. For code: address Bandit/CodeQL findings

### "Tests failing"
1. Download JUnit XML artifacts
2. Run failing tests locally with verbose: `pytest tests/path/to/test.py -v`
3. Check for flaky tests: `pytest --reruns=3`

---

## Branch Protection

### Required for `main`
- ✅ Tests (Python 3.11) — passing
- ✅ Lint & Type Check — passing
- ✅ Web Frontend Lint & Type Check — passing (if UI changes)
- ✅ Security Tests — passing
- ✅ Code review — at least 1 approval

### Recommended Settings
```yaml
# Branch protection rules for main
required_status_checks:
  strict: true
  contexts:
    - "Tests (Python 3.11)"
    - "Lint & Type Check (Python 3.11)"
    - "Security Tests (Python 3.11)"
    - "Web Frontend Lint & Type Check"
required_pull_request_reviews:
  required_approving_review_count: 1
  dismiss_stale_reviews: true
  require_code_owner_reviews: true
restrictions:
  users: []
  teams: []
enforce_admins: true
```

---

## PR Labels (Auto-applied)

| Label | Meaning | Action |
|-------|---------|--------|
| `risk: low` 🟢 | Standard review | Normal merge process |
| `risk: medium` 🟡 | Careful review needed | Additional scrutiny |
| `risk: high` 🔴 | Senior review required | Must have senior approval |
| `missing-coverage` | Coverage below threshold | Add tests before merge |
| `quality-gate-failed` | Quality checks failed | Fix issues before merge |

---

## Artifacts

CI generates these artifacts for every run:

| Artifact | Contents | Retention |
|----------|----------|-----------|
| `coverage-reports-*` | `coverage.xml`, HTML report | 30 days |
| `junit-test-results-*` | JUnit XML reports | 30 days |
| `pytest-html-reports-*` | HTML test reports | 30 days |
| `security-reports` | Bandit, SAST, DAST reports | 30 days |
| `benchmark-reports` | Performance benchmarks | 30 days |
| `mutation-test-results` | Mutmut results, kill rate | 30 days |

---

## Nightly/Scheduled Jobs

| Schedule | Workflow | Purpose |
|----------|----------|---------|
| Weekly (Mon 00:00 UTC) | `security.yml` | Full security scan |
| Weekly (Mon 03:00 UTC) | `ci-hardening.yml` | Workflow security audit |

---

## Related Documentation

- [Release Process](RELEASE_PROCESS.md) — How to create releases
- [Security Reports Guide](SECURITY_REPORTS_GUIDE.md) — Reading and responding to security reports
- [Release Gates](RELEASE_GATES.md) — Quality gate thresholds
- [Quality Gates](quality_gates.md) — Automated governance
- [Workflow README](../.github/workflows/README.md) — Detailed workflow documentation

---

## Contact

- **CI/CD Issues:** Create issue with `ci` or `build` label
- **Security Concerns:** Use private security advisory process
- **Emergency:** See `docs/runbook_kill_switch_failover.md`

---

*Last updated: 2025-12*
