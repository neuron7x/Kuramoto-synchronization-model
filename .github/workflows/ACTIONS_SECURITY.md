# GitHub Actions Security - SHA Pinning Guide

## Overview

This document explains why and how we pin GitHub Actions to commit SHAs for supply chain security.

## Why Pin Actions to SHA?

**Security Risk**: Actions pinned to mutable tags (`@v4`, `@main`) can be modified by attackers if the action maintainer's credentials are compromised. This creates a supply chain attack vector.

**Solution**: Pin actions to immutable commit SHAs (40 hex characters). Even if a tag is moved, the SHA remains fixed.

## Current State

- **Total Actions**: ~386
- **Pinned to SHA**: Managed by Dependabot (see .github/dependabot.yml)
- **Allowlist** (not pinned):
  - Local actions: `uses: ./path/to/action`
  - Docker actions: `uses: docker://image:tag`

## Dependabot Automation

We use Dependabot to automate action pinning and updates:

```yaml
# .github/dependabot.yml
- package-ecosystem: "github-actions"
  directory: "/"
  schedule:
    interval: "weekly"
```

**How it works:**
1. Dependabot scans workflows weekly
2. Creates PRs with actions pinned to SHA
3. Adds comment showing the original tag for reference
4. Groups minor/patch updates to reduce noise

**Example PR:**
```yaml
# Before
uses: actions/checkout@v4

# After (Dependabot PR)
uses: actions/checkout@b4ffde65f46336ab88eb53be808477a3936bae11  # v4.1.1
```

## Manual Pinning Process

If you need to pin an action manually:

### Step 1: Find the Commit SHA

```bash
# Method 1: Using git ls-remote
git ls-remote https://github.com/actions/checkout v4

# Method 2: Using GitHub CLI
gh api repos/actions/checkout/git/ref/tags/v4 --jq .object.sha

# Method 3: GitHub web UI
# Go to: https://github.com/actions/checkout/releases/tag/v4
# Click on the commit hash
```

### Step 2: Update the Workflow

```yaml
# Before
uses: actions/checkout@v4

# After
uses: actions/checkout@b4ffde65f46336ab88eb53be808477a3936bae11  # v4.1.1
```

**Best Practice**: Add a comment with the original tag for maintainability.

### Step 3: Verify

```bash
# Run the action pinning guard
bash scripts/guards/action_pinning_guard.sh
```

## CI Enforcement

We enforce SHA pinning in CI with a guard script:

```bash
# scripts/guards/action_pinning_guard.sh
```

This script:
- Scans all workflows for unpinned actions
- Fails CI if any actions use mutable references
- Provides clear remediation steps
- Excludes local and Docker actions from checks

## Maintenance

### Weekly Updates

Dependabot automatically:
- Checks for new action versions
- Creates PRs with updated SHAs
- Groups updates to reduce noise

### Security Alerts

If a pinned action has a security vulnerability:
1. Dependabot creates a security advisory PR
2. Review and merge the PR promptly
3. The guard ensures the fix stays pinned

## Exceptions

**Do NOT pin:**
1. Local actions: `uses: ./.github/actions/my-action`
2. Docker actions: `uses: docker://alpine:3.18`
3. Reusable workflows (they're referenced by commit in the caller)

## Troubleshooting

### "Unpinned action" error in CI

```
❌ FAILURE: Found 3 unpinned GitHub Actions!
.github/workflows/test.yml:15 - actions/checkout@v4
```

**Fix:**
1. Run `bash scripts/guards/action_pinning_guard.sh` locally
2. Follow remediation steps in output
3. Commit and push changes

### Dependabot not creating PRs

**Check:**
1. `.github/dependabot.yml` is present
2. `github-actions` ecosystem is configured
3. Open PRs haven't hit the limit (10)
4. Check Dependabot logs in repository settings

### Wrong SHA used

```bash
# Verify the SHA corresponds to the right tag
git ls-remote https://github.com/actions/checkout | grep <sha>
```

## Security Considerations

### SHA vs Tag

| Aspect | Tag (@v4) | SHA (@abc123...) |
|--------|-----------|------------------|
| Mutable | ✅ Yes | ❌ No |
| Attackable | ✅ Yes | ❌ No |
| Readable | ✅ Yes | ⚠️ Less |
| Updatable | ✅ Easy | ⚠️ Requires automation |

### Threat Model

**Without SHA pinning:**
1. Attacker compromises action maintainer account
2. Attacker force-pushes malicious code to `v4` tag
3. All workflows using `@v4` now run malicious code
4. Supply chain attack succeeds

**With SHA pinning:**
1. Attacker compromises action maintainer account
2. Attacker cannot change commit SHA (immutable)
3. Workflows continue using original, trusted code
4. Supply chain attack fails

### Recommendations

1. **Always pin to SHA** - No exceptions for external actions
2. **Use Dependabot** - Automates the tedious work
3. **Add comments** - Show original tag for reference
4. **Review updates** - Don't blindly merge Dependabot PRs
5. **Monitor advisories** - Subscribe to security alerts

## References

- [GitHub Security Hardening Guide](https://docs.github.com/en/actions/security-guides/security-hardening-for-github-actions)
- [Dependabot for Actions](https://docs.github.com/en/code-security/dependabot/working-with-dependabot/keeping-your-actions-up-to-date-with-dependabot)
- [OpenSSF Scorecard - Pinned-Dependencies](https://github.com/ossf/scorecard/blob/main/docs/checks.md#pinned-dependencies)

## Questions?

- Security team: See SECURITY.md
- CI/CD team: See .github/workflows/README.md
- Dependabot issues: Check repository settings > Code security and analysis
