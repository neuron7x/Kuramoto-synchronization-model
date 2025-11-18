# CI/CD Integration Guide for Code Quality

This guide provides GitHub Actions workflows for maintaining the code quality standards established by the technical debt elimination PR.

## Quick Start

Add these workflows to `.github/workflows/` directory:

### 1. Code Quality Check (`code-quality.yml`)

```yaml
name: Code Quality

on:
  pull_request:
    branches: [main, develop]
  push:
    branches: [main, develop]

jobs:
  code-quality:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'
          cache: 'pip'
      
      - name: Install dependencies
        run: |
          pip install ruff black
      
      - name: Check code formatting with black
        run: |
          black --check --line-length 100 --target-version py311 .
      
      - name: Lint with ruff
        run: |
          ruff check . --select F,E --output-format github
      
      - name: Check for critical issues
        run: |
          # Fail if any F or E errors found
          ruff check . --select F,E --quiet || exit 1
```

### 2. Auto-Format on Commit (`auto-format.yml`)

```yaml
name: Auto-Format

on:
  pull_request:
    types: [opened, synchronize]

jobs:
  format:
    runs-on: ubuntu-latest
    permissions:
      contents: write
      pull-requests: write
    
    steps:
      - uses: actions/checkout@v4
        with:
          ref: ${{ github.head_ref }}
          token: ${{ secrets.GITHUB_TOKEN }}
      
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      
      - name: Install formatters
        run: pip install black ruff
      
      - name: Run black formatter
        run: black --line-length 100 --target-version py311 .
      
      - name: Run ruff auto-fix
        run: ruff check . --select F,E --fix
      
      - name: Commit changes
        run: |
          git config --local user.email "github-actions[bot]@users.noreply.github.com"
          git config --local user.name "github-actions[bot]"
          git add -A
          git diff --staged --quiet || git commit -m "style: auto-format code with black and ruff"
          git push
```

### 3. Quality Gate (`quality-gate.yml`)

```yaml
name: Quality Gate

on:
  pull_request:
    branches: [main]

jobs:
  quality-gate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
      
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'
          cache: 'pip'
      
      - name: Install tools
        run: |
          pip install ruff black pytest pytest-cov
      
      - name: Check code quality
        id: quality
        run: |
          ERROR_COUNT=$(ruff check . --select F,E --quiet 2>&1 | wc -l)
          echo "errors=$ERROR_COUNT" >> $GITHUB_OUTPUT
          
          if [ $ERROR_COUNT -gt 0 ]; then
            echo "❌ Quality gate FAILED: $ERROR_COUNT errors found"
            exit 1
          else
            echo "✅ Quality gate PASSED: 0 errors"
          fi
      
      - name: Run tests
        run: |
          pytest tests/ -v --tb=short
      
      - name: Comment PR
        if: always()
        uses: actions/github-script@v7
        with:
          script: |
            const errors = '${{ steps.quality.outputs.errors }}';
            const status = errors === '0' ? '✅ PASSED' : '❌ FAILED';
            const body = `## Quality Gate ${status}\n\n**Errors Found**: ${errors}\n\nAll code must pass quality checks before merging.`;
            
            github.rest.issues.createComment({
              issue_number: context.issue.number,
              owner: context.repo.owner,
              repo: context.repo.repo,
              body: body
            });
```

## Pre-commit Hooks

Install pre-commit hooks to catch issues before committing:

```bash
# Install pre-commit
pip install pre-commit

# Install the git hooks
pre-commit install

# Run manually on all files
pre-commit run --all-files
```

## VS Code Integration

Add to `.vscode/settings.json`:

```json
{
  "python.formatting.provider": "black",
  "python.formatting.blackArgs": [
    "--line-length",
    "100",
    "--target-version",
    "py311"
  ],
  "python.linting.enabled": true,
  "python.linting.ruffEnabled": true,
  "python.linting.ruffArgs": [
    "--select",
    "F,E"
  ],
  "editor.formatOnSave": true,
  "editor.codeActionsOnSave": {
    "source.fixAll": true,
    "source.organizeImports": true
  }
}
```

## PyCharm/IntelliJ Integration

1. **Black formatter**:
   - Settings → Tools → External Tools
   - Add new tool: black
   - Program: `black`
   - Arguments: `--line-length 100 $FilePath$`

2. **Ruff linter**:
   - Settings → Tools → External Tools
   - Add new tool: ruff
   - Program: `ruff`
   - Arguments: `check $FilePath$ --select F,E`

## Maintenance

### Weekly Quality Report

Add to `.github/workflows/weekly-quality.yml`:

```yaml
name: Weekly Quality Report

on:
  schedule:
    - cron: '0 0 * * 1'  # Every Monday at midnight
  workflow_dispatch:

jobs:
  quality-report:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      
      - name: Install tools
        run: pip install ruff
      
      - name: Generate report
        run: |
          echo "# Weekly Code Quality Report" > report.md
          echo "" >> report.md
          echo "**Date**: $(date)" >> report.md
          echo "" >> report.md
          echo "## Error Summary" >> report.md
          ruff check . --select F,E --statistics >> report.md
      
      - name: Create issue
        uses: actions/github-script@v7
        with:
          script: |
            const fs = require('fs');
            const report = fs.readFileSync('report.md', 'utf8');
            
            github.rest.issues.create({
              owner: context.repo.owner,
              repo: context.repo.repo,
              title: `Weekly Code Quality Report - ${new Date().toISOString().split('T')[0]}`,
              body: report,
              labels: ['quality', 'metrics']
            });
```

## Metrics Dashboard

Track code quality over time:

```bash
# Save baseline
ruff check . --select F,E --statistics > quality-baseline.txt

# Compare later
ruff check . --select F,E --statistics > quality-current.txt
diff quality-baseline.txt quality-current.txt
```

## Enforcement Policies

### Branch Protection Rules

Configure on GitHub:
1. Navigate to Settings → Branches
2. Add rule for `main` branch:
   - ✅ Require status checks to pass
   - ✅ Require branches to be up to date
   - Required checks: `code-quality`, `quality-gate`
   - ✅ Require linear history
   - ✅ Do not allow bypassing

### CODEOWNERS

Add to `.github/CODEOWNERS`:

```
# Code quality standards
.pre-commit-config.yaml @tech-leads
pyproject.toml @tech-leads
ruff.toml @tech-leads
```

## Troubleshooting

### Common Issues

1. **Black and ruff conflict**:
   - Ensure ruff is configured to respect black's line length
   - Add to `pyproject.toml`:
     ```toml
     [tool.ruff]
     line-length = 100
     ```

2. **Pre-commit slow**:
   - Use `pre-commit run --hook-stage manual` for manual runs
   - Configure hooks to run only on changed files

3. **CI/CD timeout**:
   - Cache pip dependencies with `actions/setup-python@v5`
   - Use `actions/cache` for ruff cache

## Support

For questions or issues:
1. Check existing GitHub issues
2. Review PR #[PR_NUMBER] for context
3. Contact @tech-leads team

---

**Maintained by**: Platform Engineering Team
**Last Updated**: 2025-11-18
**Related PR**: copilot/remove-technical-debt
