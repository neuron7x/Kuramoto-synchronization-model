# GitHub Actions Automation - Quick Reference

> Quick guide to automated features in TradePulse repository

## 🏷️ PR Labels (Automatic)

### Size Labels
Automatically added based on lines changed:
- `size/XS` - 0-9 lines
- `size/S` - 10-49 lines
- `size/M` - 50-249 lines
- `size/L` - 250-999 lines
- `size/XL` - 1000+ lines

### Quality Labels
- `test-needed` - No test files modified
- `missing-coverage` - Coverage below threshold
- `needs-changelog` - Changelog entry missing
- `first-time-contributor` - First contribution

### Risk Labels (Manual)
- `risk: low` - Standard review
- `risk: medium` - Careful review
- `risk: high` - Senior review required

## 🤖 Automated Actions

### On PR Open
1. ✅ Size label added
2. ✅ Test coverage check
3. ✅ Changelog entry check
4. ✅ First-time contributor welcome (if applicable)

### On PR Update
1. ✅ Labels refreshed
2. ✅ Checks re-run
3. ✅ Old workflow runs cancelled (concurrency)

### Daily (00:00 UTC)
1. ✅ Stale PRs marked (60 days inactive)
2. ✅ Stale issues marked (90 days inactive)
3. ✅ Closed after warning period (7-14 days)

### On Dependabot PR
1. ✅ Auto-rebase on base branch
2. ✅ Wait for checks
3. ✅ Auto-merge if patch/minor + checks pass
4. ✅ Comment if manual review needed

## 🛑 How to Skip Automation

### Skip Changelog Check
Add label: `skip-changelog`

**Use cases**: Dependencies, docs-only, CI changes

### Keep PR/Issue Open
Add label: `keep-open`

**Use cases**: Ongoing work, blocked by external factors

### Skip Specific Workflows
Use `[skip ci]` in commit message (not recommended)

## 📝 Changelog Entry Format

**Location**: `newsfragments/`

**Filename**: `<pr_number>.<type>.md`

**Types**:
- `feature` - New functionality
- `bugfix` - Bug fixes
- `doc` - Documentation
- `removal` - Deprecations
- `misc` - Other changes

**Example**: `newsfragments/1234.feature.md`

**Content**: 1-2 sentence description of the change

## 🔄 Workflow Concurrency

Workflows automatically cancel outdated runs when:
- New commit pushed to PR
- PR rebased/updated
- Another workflow triggered for same context

**Exceptions**: Release workflows (no auto-cancel)

## ⚡ Cache Usage

Automatically cached:
- **Python**: pip packages (setup-python action)
- **Helm**: charts and dependencies
- **Go**: modules (in relevant workflows)
- **Node**: npm packages (in frontend workflows)

Cache invalidates when dependencies change.

## 🎯 Best Practices

### For Contributors
- ✅ Keep PRs under 250 lines when possible
- ✅ Add changelog entry for user-facing changes
- ✅ Include tests with code changes
- ✅ Respond to reviews within 30 days

### For Reviewers
- ✅ Use size labels to prioritize reviews
- ✅ Check automation comments
- ✅ Verify required labels present
- ✅ Add `keep-open` if work ongoing

### For Maintainers
- ✅ Review stale reports weekly
- ✅ Monitor workflow success rates
- ✅ Update automation thresholds as needed
- ✅ Keep documentation current

## 🔧 Common Issues & Solutions

### Issue: Workflow not triggering
**Check**:
1. File paths match trigger conditions
2. Branch matches trigger branches
3. Required permissions granted

### Issue: Stale bot marking active PR
**Solution**: Add `keep-open` label

### Issue: Dependabot not auto-merging
**Check**:
1. All required checks passing?
2. Major version update? (needs manual review)
3. Merge conflicts?

### Issue: Changelog check failing
**Solutions**:
1. Add entry to `newsfragments/`
2. Add `skip-changelog` label if not needed

### Issue: Cache not working
**Check**:
1. Cache key valid?
2. Dependencies changed?
3. Check workflow logs for cache hit/miss

## 📊 Monitoring

### Workflow Dashboard
Go to: **Actions** tab → Select workflow → View runs

### PR Status
Check comment from automation bots on PR

### Stale Items
Weekly report in **Actions** → **Stale** workflow

### Dependabot
**Insights** → **Dependency graph** → **Dependabot**

## 🆘 Getting Help

1. Check this guide first
2. Review [WORKFLOW_AUTOMATION_GUIDE.md](.github/WORKFLOW_AUTOMATION_GUIDE.md)
3. Check workflow logs in **Actions** tab
4. Open issue with `ci` label
5. Tag `@neuron7x` for urgent issues

## 📚 Related Docs

- [Full Automation Guide](.github/WORKFLOW_AUTOMATION_GUIDE.md)
- [Status Badges](.github/WORKFLOW_STATUS_BADGES.md)
- [Contributing Guide](../CONTRIBUTING.md)
- [Code of Conduct](../CODE_OF_CONDUCT.md)

## 🆕 Recent Updates

**2025-11-14**: Initial automation improvements
- Added 4 new automation workflows
- Added concurrency control to 9 workflows
- Added caching to Helm workflows
- Enhanced Dependabot auto-merge
- Created comprehensive documentation

---

**Quick Links**:
- [All Workflows](../../actions)
- [Open PRs](../../pulls)
- [Open Issues](../../issues)
- [Discussions](../../discussions)

**Last Updated**: 2025-11-14
