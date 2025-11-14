# GitHub Actions Workflows - Release Gate System

This directory contains the CI/CD workflows that implement the TradePulse release gate system, inspired by dopamine-based reinforcement learning mechanisms (TD(0) RPE, DDM, Go/No-Go).

## Workflow Overview

### Core Quality Gates

#### 1. `ci.yml` - Main CI Pipeline
**Triggers:** PR to any branch, push to main
**Purpose:** Comprehensive testing with coverage and mutation testing gates

**Jobs:**
- `test-coverage` (sharded 1-3): Runs tests with coverage tracking
- `coverage-aggregate`: Combines coverage and enforces 98% threshold
- `mutation-testing-gate`: Runs mutation testing and enforces 90% kill rate
- `publish-containers`: Builds and publishes Docker images (main/develop only)

**Requirements:**
- ✅ Code coverage ≥ 98%
- ✅ Mutation kill rate ≥ 90%
- ✅ All tests passing

#### 2. `coverage.yml` - Coverage Tracking
**Triggers:** PR to main/develop, push to main/develop
**Purpose:** Test coverage validation and reporting

**Requirements:**
- ✅ Coverage ≥ 98%
- Uploads to Codecov if token configured

#### 3. `mutation-testing.yml` - Mutation Testing
**Triggers:** PR to main/develop when code changes
**Purpose:** Validates test quality through mutation testing

**Features:**
- Runs mutmut on core, backtest, execution modules
- Posts detailed mutation results to PR
- Enforces 90% kill rate threshold
- Uploads mutation reports as artifacts

### PR Management

#### 4. `pr-release-gate.yml` - Quality & Risk Assessment
**Triggers:** PR opened/synchronized
**Purpose:** Comprehensive quality assessment and risk scoring

**Features:**
- Runs quick coverage check
- Samples mutation testing on changed files
- Calculates risk score based on:
  - Coverage gap (up to 40 points)
  - Mutation gap (up to 40 points)
  - Critical files modified (up to 20 points)
  - PR size >500 lines (10 points)
- Applies risk labels: `risk: low`, `risk: medium`, `risk: high`
- Posts comprehensive quality report
- Blocks merge if quality gates fail

#### 5. `pr-quality-labels.yml` - Auto-Labeling
**Triggers:** PR opened/synchronized
**Purpose:** Automatically applies quality-related labels

**Labels Applied:**
- `test-needed`: No test files modified
- `missing-coverage`: Coverage below threshold
- `risk: low/medium/high`: Risk assessment
- `quality-gate-failed`: Quality requirements not met
- `needs-mutation-testing`: Mutation testing required

#### 6. `merge-guard.yml` - Merge Protection
**Triggers:** PR opened/synchronized/labeled
**Purpose:** Final check before merge is allowed

**Features:**
- Validates all required checks passed
- Blocks merge if `quality-gate-failed` label present
- Posts merge status to PR
- Provides actionable next steps

#### 7. `pr-quality-summary.yml` - Aggregated Reports
**Triggers:** After CI workflows complete
**Purpose:** Posts comprehensive quality summary

**Features:**
- Downloads artifacts from completed workflows
- Aggregates coverage and mutation metrics
- Posts summary table to PR
- Links to detailed workflow runs

### Other Workflows

#### `enterprise-cicd.yml`
Full enterprise deployment pipeline with:
- Quality gates
- Unit and integration tests
- Container building and signing
- Infrastructure planning
- Canary deployments
- Progressive rollouts
- Automated rollback

## Quality Requirements

### Coverage (98%)
All critical modules (`core/`, `backtest/`, `execution/`) must maintain 98% line coverage.

**Local check:**
```bash
pytest tests/ --cov=core --cov=backtest --cov=execution --cov-fail-under=98
```

### Mutation Testing (90%)
Test suite must kill at least 90% of mutants to ensure test quality.

**Local check:**
```bash
mutmut run --paths-to-mutate=core,backtest,execution --tests-dir=tests
python -m tools.mutation.kill_rate_guard --threshold=0.9
```

## Risk Levels

### 🟢 Low Risk (0-24 points)
- Standard review process
- Automated checks sufficient
- Can be merged by any team member with approval

### 🟡 Medium Risk (25-49 points)
- Requires careful review
- Multiple approvals recommended
- Should have comprehensive testing

### 🔴 High Risk (50+ points)
- **Requires senior review**
- Extensive testing mandatory
- Phased rollout recommended
- Consider feature flags

## PR Labels

### Quality Labels
- `quality-gate-failed` (🔴): Quality requirements not met - **merge blocked**
- `missing-coverage` (🟠): Coverage below threshold
- `test-needed` (🔴): Tests must be added or updated
- `needs-mutation-testing` (🟠): Mutation testing required

### Risk Labels
- `risk: low` (🟢): Low risk, standard process
- `risk: medium` (🟡): Medium risk, careful review needed
- `risk: high` (🔴): High risk, senior review required

## Artifacts

All workflows generate artifacts for review:

### Coverage Reports
- `coverage.xml`: Cobertura format
- `coverage_html/`: Browsable HTML report

### Mutation Reports
- `mutation_summary.json`: Metrics in JSON
- `.mutmut-cache`: Full mutation cache
- `html/`: Browsable mutation report

### Quality Reports
- `quality-gate-reports`: Combined quality metrics

## Branch Protection

To enforce these gates, configure branch protection on `main`:

### Required Status Checks
- ✅ `Aggregate coverage & enforce guardrail`
- ✅ `Mutation Testing Gate (90% kill rate)`
- ✅ `Merge Guard Quality Check`

### Additional Settings
- ✅ Require pull request reviews (1 for standard, 2 for high-risk)
- ✅ Require conversation resolution
- ❌ Do not allow bypassing settings

## Troubleshooting

### Coverage Below 98%
1. Run locally: `pytest --cov-report=term-missing`
2. Identify uncovered lines
3. Add tests for uncovered code paths
4. Push changes to re-trigger checks

### Mutation Kill Rate Below 90%
1. Run locally: `mutmut run`
2. Review survivors: `mutmut show`
3. Improve tests to detect mutations
4. Re-run to verify
5. Push changes

### Quality Gate Blocking Merge
1. Check PR comments for specific failures
2. Review workflow logs
3. Fix identified issues
4. Push changes - checks re-run automatically

### High Risk Label Applied
1. Review risk factors in PR comment
2. Consider breaking into smaller PRs
3. Ensure comprehensive test coverage
4. Request senior review
5. Risk is informational only - doesn't block if quality gates pass

## Local Development

Before pushing:

```bash
# Run tests with coverage
pytest tests/ --cov=core --cov=backtest --cov=execution --cov-fail-under=98

# Run mutation testing (slower, optional)
mutmut run --paths-to-mutate=core,backtest,execution --tests-dir=tests
python -m tools.mutation.kill_rate_guard --threshold=0.9

# Run linters
ruff check .
black --check .
mypy

# Push if all pass
git push origin your-branch
```

## Best Practices for Workflow Development

### Heredoc Syntax in Workflows

When using heredocs (e.g., for inline Python scripts) in GitHub Actions workflows, follow these guidelines to prevent syntax errors:

**✅ Correct: Use `<<-` with tab indentation**
```yaml
- name: Run inline script
  run: |
    python <<-'PY' "$arg1" "$arg2"
    	import sys
    	print(sys.argv[1])
    	PY
```

**❌ Incorrect: Using `<<` with space-indented closing marker**
```yaml
- name: Run inline script
  run: |
    python <<'PY' "$arg1" "$arg2"
      import sys
      print(sys.argv[1])
      PY  # Shell won't recognize this as delimiter!
```

**Key Rules:**
1. Use `<<-` operator (not `<<`) to allow indented closing markers
2. Use **tabs** (not spaces) for indentation within heredoc content when using `<<-`
3. The closing marker (e.g., `PY`) must be indented with tabs to match the content
4. This maintains both YAML validity and bash heredoc syntax correctness

**Why This Matters:**
- `<<` requires closing marker at column 0 (no indentation), which breaks YAML
- `<<-` allows tab-indented closing markers, working within YAML's structure
- Spaces don't work with `<<-` - only tabs are stripped

### YAML Validation

Always validate workflow YAML before committing:

```bash
# Validate single workflow
python -c "import yaml; yaml.safe_load(open('.github/workflows/your-workflow.yml'))"

# Validate all workflows
find .github/workflows -name "*.yml" -exec python -c "import yaml; yaml.safe_load(open('{}'))" \; -print
```

### Testing Workflows Locally

Use [act](https://github.com/nektos/act) to test workflows locally:

```bash
# Install act
curl https://raw.githubusercontent.com/nektos/act/master/install.sh | sudo bash

# Run a specific workflow
act -W .github/workflows/ci.yml

# Run with specific event
act pull_request -W .github/workflows/pr-quality-summary.yml
```

## References

- [Release Gates Documentation](../../docs/RELEASE_GATES.md)
- [Operations Guide](../../docs/OPERATIONS.md)
- [Testing Guide](../../TESTING.md)
- [Bash Heredoc Documentation](https://tldp.org/LDP/abs/html/here-docs.html)

---

**Last Updated:** 2025-11-14
**Version:** 1.1.0
