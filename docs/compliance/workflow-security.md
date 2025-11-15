# GitHub Actions Workflow Security Policy

**Version:** 1.0  
**Effective Date:** 2025-11-15  
**Last Updated:** 2025-11-15

## Purpose

This document defines security requirements for GitHub Actions workflows in the TradePulse repository. The policy is enforced through automated OPA (Open Policy Agent) checks that run on every pull request.

## Security Levels

### HIGH/CRITICAL Issues (DENY - Blocks PR)

The following security issues will cause the workflow security check to **FAIL** and block PR merges:

#### 1. Excessive Permissions
- ❌ **DENY:** `permissions: write-all` or broad write permissions without justification
- ❌ **DENY:** `GITHUB_TOKEN` with write permissions when read-only is sufficient
- ✅ **ALLOW:** Minimal permissions explicitly scoped to required access level

**Example - BAD:**
```yaml
permissions: write-all
```

**Example - GOOD:**
```yaml
permissions:
  contents: read
  pull-requests: write
```

#### 2. Unsafe pull_request_target Usage
- ❌ **DENY:** `pull_request_target` with code execution from untrusted PR
- ❌ **DENY:** `pull_request_target` with `actions/checkout` of PR head without isolation
- ✅ **ALLOW:** `pull_request_target` only for read-only analysis or with proper isolation

**Rationale:** `pull_request_target` runs in the context of the base branch with access to secrets, making it dangerous if executing code from the PR.

**Example - BAD:**
```yaml
on:
  pull_request_target:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v5
        with:
          ref: ${{ github.event.pull_request.head.ref }}
      - run: npm install && npm test  # Executes PR code with repo secrets!
```

**Example - GOOD:**
```yaml
on:
  pull_request:  # Use pull_request instead
    branches: [main]
```

#### 3. Unpinned Actions in Security-Sensitive Workflows
- ❌ **DENY:** Actions using branch names (`@main`, `@v1`) in workflows that handle secrets or write access
- ✅ **ALLOW:** Actions pinned to specific SHA (`@a1b2c3d...`) or version tags (`@v1.2.3`)

**Example - BAD:**
```yaml
- uses: actions/checkout@main  # Unpinned to branch
```

**Example - GOOD:**
```yaml
- uses: actions/checkout@v5  # Pinned to major version
# OR
- uses: actions/checkout@8ade135a41bc03ea155e62e844d188df1ea18608  # Pinned to SHA
```

### MEDIUM/LOW Issues (WARN - Does not block)

The following issues generate warnings but do not block PR merges. They should be addressed over time:

#### 1. Missing Permissions Block
- ⚠️ **WARN:** No `permissions:` block specified (defaults to write)
- ✅ **RECOMMENDED:** Always specify `permissions:` explicitly

#### 2. Missing Timeout
- ⚠️ **WARN:** No `timeout-minutes` specified for jobs
- ✅ **RECOMMENDED:** Set reasonable timeout (e.g., 30 minutes for tests)

#### 3. Missing Concurrency Control
- ⚠️ **WARN:** No `concurrency` block with `cancel-in-progress`
- ✅ **RECOMMENDED:** Cancel redundant workflow runs to save resources

**Example - RECOMMENDED:**
```yaml
concurrency:
  group: ${{ github.workflow }}-${{ github.event.pull_request.number || github.ref }}
  cancel-in-progress: true
```

## Enforcement Process

### Automated Checks

Every PR that modifies `.github/workflows/*.yml` files triggers the OPA security policy enforcement workflow:

1. **Scan:** All workflow files are scanned against security policies
2. **Evaluate:** Issues are classified as HIGH/CRITICAL (deny) or MEDIUM/LOW (warn)
3. **Report:** Results are posted as a PR comment with detailed findings
4. **Decision:**
   - If any HIGH/CRITICAL issues: Workflow **FAILS**, PR is blocked
   - If only MEDIUM/LOW issues: Workflow **PASSES** with warnings

### Manual Review

For complex cases where the automated check generates false positives:

1. Add a comment in the workflow file explaining why the pattern is safe
2. Request review from a workflow security expert
3. If approved, add an exception to the OPA policy

## Common Patterns

### Secure Workflow Template

```yaml
name: Example Secure Workflow

# Minimal, explicit permissions
permissions:
  contents: read
  pull-requests: write

# Use pull_request, not pull_request_target
on:
  pull_request:
    branches: [main, develop]

# Add concurrency control
concurrency:
  group: ${{ github.workflow }}-${{ github.event.pull_request.number || github.ref }}
  cancel-in-progress: true

jobs:
  secure-job:
    runs-on: ubuntu-latest
    timeout-minutes: 30  # Reasonable timeout
    
    steps:
      # Pin actions to specific versions
      - name: Checkout code
        uses: actions/checkout@v5
      
      # Minimal permissions for each step
      - name: Run tests
        run: npm test
```

### When pull_request_target is Necessary

Use `pull_request_target` only for:
- Posting comments/labels on PRs from forks (requires write access)
- Read-only analysis that doesn't execute PR code

**Safe pattern:**
```yaml
on:
  pull_request_target:
    types: [opened, synchronize]

permissions:
  pull-requests: write  # Only what's needed
  contents: read

jobs:
  comment:
    runs-on: ubuntu-latest
    steps:
      # Do NOT checkout the PR head
      - name: Comment on PR
        uses: actions/github-script@v7
        with:
          script: |
            // Safe: Only reads PR metadata, doesn't execute PR code
            github.rest.issues.createComment({
              owner: context.repo.owner,
              repo: context.repo.repo,
              issue_number: context.payload.pull_request.number,
              body: 'Thank you for your contribution!'
            })
```

## Baseline and Exceptions

### Current Baseline

As of 2025-11-15, the following workflows have been audited and meet security standards:
- (This section will be updated as workflows are hardened)

### Known Exceptions

No exceptions currently documented. Any new exceptions must be approved by the security team.

## References

- [GitHub Actions Security Best Practices](https://docs.github.com/en/actions/security-guides/security-hardening-for-github-actions)
- [GitHub Security Lab: Keeping your GitHub Actions secure](https://securitylab.github.com/research/github-actions-preventing-pwn-requests/)
- [OpenSSF Scorecard - Token Permissions](https://github.com/ossf/scorecard/blob/main/docs/checks.md#token-permissions)

## Incident Response

If a workflow security issue is discovered in production:

1. Create a security advisory via GitHub Security tab
2. Notify the security team immediately
3. Disable the affected workflow if necessary
4. Create a fix PR with priority review
5. Document the incident in SECURITY_FIXES.md

## Version History

| Version | Date       | Changes                                      |
|---------|------------|----------------------------------------------|
| 1.0     | 2025-11-15 | Initial workflow security policy             |

---

*For questions about this policy, contact the security team via security@tradepulse.local or GitHub issues with the `security` label.*
