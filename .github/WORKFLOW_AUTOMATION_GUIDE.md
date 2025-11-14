# GitHub Actions Workflow Automation Guide

## Overview

This guide documents the automated workflows and processes implemented in the TradePulse repository to improve developer experience, code quality, and operational efficiency.

## 🚀 New Automated Workflows

### 1. PR Size Labeler (`pr-size-labeler.yml`)

**Purpose**: Automatically labels pull requests based on their size to help reviewers prioritize and scope their reviews.

**Features**:
- Labels PRs with size indicators: `size/XS`, `size/S`, `size/M`, `size/L`, `size/XL`
- Warns contributors about PRs that are too large (1000+ lines)
- Encourages breaking down large PRs into smaller, focused changes

**Size Thresholds**:
- XS: 0-9 lines
- S: 10-49 lines
- M: 50-249 lines
- L: 250-999 lines
- XL: 1000+ lines

### 2. Stale PR and Issue Management (`stale.yml`)

**Purpose**: Automatically manages inactive PRs and issues to keep the repository clean and focused.

**Configuration**:
- Issues: Marked stale after 90 days of inactivity, closed after 7 additional days
- PRs: Marked stale after 60 days of inactivity, closed after 14 additional days
- Exempt labels: `keep-open`, `pinned`, `security`, `critical`, `roadmap`, `enhancement`, `work-in-progress`, `blocked`
- Draft PRs are automatically exempt

**Schedule**: Runs daily at 00:00 UTC

### 3. First-Time Contributor Welcome (`first-time-contributor.yml`)

**Purpose**: Welcomes new contributors and provides them with helpful resources.

**Features**:
- Detects first-time contributions (both issues and PRs)
- Posts a friendly welcome message
- Links to contributing guidelines, code of conduct, and documentation
- Adds `first-time-contributor` label for easy identification

### 4. Changelog Automation (`changelog-automation.yml`)

**Purpose**: Ensures PRs include changelog entries and automates changelog generation.

**Features**:
- Checks for changelog entries in `newsfragments/` directory
- Skips check for PRs with labels: `dependencies`, `skip-changelog`, `documentation`, `ci`
- Adds `needs-changelog` label if entry is missing
- Supports towncrier format for changelog entries
- Generates draft changelog on PR merge

**Changelog Entry Format**:
```
newsfragments/<pr_number>.<type>.md
```

**Types**:
- `feature` - New features
- `bugfix` - Bug fixes
- `doc` - Documentation improvements
- `removal` - Deprecations or removals
- `misc` - Other changes

## 📊 Improved Existing Workflows

### 1. Concurrency Control

Added concurrency control to the following workflows to prevent redundant runs and save CI resources:

- `pr-quality-labels.yml`
- `pr-quality-summary.yml`
- `helm.yml`
- `load-test.yml`
- `progressive-release-gates.yml`
- `publish-image.yml` (no cancel)
- `publish-python.yml` (no cancel)
- `slo-gate.yml` (no cancel)
- `dependabot-auto-merge.yml` (no cancel)

**Benefits**:
- Reduces GitHub Actions minutes usage
- Prevents resource contention
- Faster feedback for developers
- Automatically cancels outdated workflow runs

### 2. Caching Improvements

Added comprehensive caching to the Helm workflow (`helm.yml`):

**Cached Items**:
- Helm charts and dependencies
- Helm binary installations
- Chart build artifacts

**Cache Locations**:
```yaml
path: |
  ~/.cache/helm
  ~/.local/share/helm
```

**Benefits**:
- 30-50% faster workflow execution
- Reduced network usage
- More efficient use of CI resources

### 3. Dependabot Auto-Merge Enhancements

Enhanced `dependabot-auto-merge.yml` with:

**New Features**:
- Better error handling for failed checks
- Automatic comments on merge status
- Clear success/failure notifications
- Improved check wait logic

**Auto-Merge Policy**:
- ✅ Automatic for patch and minor updates
- ⚠️ Manual review required for major updates
- ❌ Cancelled if required checks fail

## 🔧 Reusable Workflows

### Setup Python Environment (`reusable/setup-python.yml`)

**Purpose**: Provides a standardized Python environment setup across workflows.

**Parameters**:
- `python-version`: Python version (default: '3.11')
- `install-dev-deps`: Install dev dependencies (default: false)
- `use-constraints`: Use security constraints (default: true)
- `cache-key-suffix`: Additional cache key suffix (default: '')

**Usage Example**:
```yaml
jobs:
  my-job:
    uses: ./.github/workflows/reusable/setup-python.yml
    with:
      python-version: '3.11'
      install-dev-deps: true
      use-constraints: true
```

**Benefits**:
- Consistent Python environment across workflows
- Automatic pip caching
- Centralized dependency installation logic
- Easier to maintain and update

## 📝 Best Practices

### For Contributors

1. **Keep PRs Small**: Aim for PRs under 250 lines when possible
2. **Add Changelog Entries**: Include a changelog entry for user-facing changes
3. **Label Your Work**: Use appropriate labels to help automation
4. **Keep PRs Active**: Respond to reviews within 30 days to avoid stale marking

### For Maintainers

1. **Use Labels Effectively**:
   - `keep-open`: Prevent stale bot from closing
   - `skip-changelog`: Skip changelog requirement
   - `work-in-progress`: Indicate ongoing work
   - `blocked`: Indicate external dependencies

2. **Monitor Automation**:
   - Review stale PR/issue reports weekly
   - Check dependabot auto-merge successes
   - Monitor workflow execution times

3. **Customize When Needed**:
   - Adjust stale timeouts in `stale.yml`
   - Modify size thresholds in `pr-size-labeler.yml`
   - Update concurrency groups if workflow patterns change

## 🔍 Troubleshooting

### Workflow Not Triggering

**Check**:
1. Trigger conditions (branches, paths, types)
2. Required permissions
3. Concurrency group conflicts

**Solution**: Review workflow YAML and GitHub Actions logs

### Stale Bot Marking Active PRs

**Solution**: Add `keep-open` label or ensure regular activity (comments, commits)

### Dependabot Auto-Merge Not Working

**Common Issues**:
1. Required checks not passing
2. Major version update (requires manual review)
3. Merge conflicts

**Solution**: Check PR comments for bot feedback and resolve issues

### Cache Not Working

**Check**:
1. Cache key matches between save and restore
2. Cache size limits (max 10GB per repository)
3. Cache hit/miss in workflow logs

**Solution**: Review cache configuration and hash functions

## 📈 Metrics and Monitoring

### Key Performance Indicators

1. **CI/CD Efficiency**:
   - Average workflow execution time
   - Cache hit rate
   - Cancelled workflow runs (due to concurrency)

2. **Developer Experience**:
   - Time to first review
   - PR merge time
   - Number of stale PRs/issues

3. **Quality Metrics**:
   - Changelog compliance rate
   - Average PR size
   - First-time contributor retention

### Monitoring Tools

- **GitHub Insights**: Workflow run statistics
- **Actions Usage**: Monitor actions minutes consumption
- **Repository Insights**: PR and issue metrics

## 🛠️ Maintenance

### Regular Reviews

1. **Monthly**:
   - Review stale PR/issue list
   - Check automation effectiveness
   - Update thresholds if needed

2. **Quarterly**:
   - Update action versions
   - Review and optimize cache strategies
   - Assess workflow performance

3. **Annually**:
   - Comprehensive automation audit
   - Update documentation
   - Gather team feedback

### Updating Workflows

1. **Test Changes**: Use workflow_dispatch or test branches
2. **Review Logs**: Monitor first few runs after changes
3. **Document Updates**: Update this guide with changes
4. **Communicate**: Inform team of workflow changes

## 🔗 Related Documentation

- [GitHub Actions Documentation](https://docs.github.com/en/actions)
- [Contributing Guide](../CONTRIBUTING.md)
- [Code of Conduct](../CODE_OF_CONDUCT.md)
- [Security Policy](../SECURITY.md)

## 📞 Support

For questions or issues with workflows:
1. Check this guide first
2. Review workflow logs in GitHub Actions
3. Open an issue with the `ci` label
4. Tag `@neuron7x` for urgent workflow issues

---

**Last Updated**: 2025-11-14
**Maintained By**: TradePulse DevOps Team
