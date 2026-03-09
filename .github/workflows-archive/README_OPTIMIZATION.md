# GitHub Actions Optimization Quick Reference

> **For Developers:** How to leverage workflow optimizations in TradePulse

## TL;DR - What Changed?

🚀 **Workflows are now 25-80% faster** thanks to aggressive caching!

### Key Improvements
- **Dependency installation:** 2-3 min → 30-60 sec (70-80% faster on cache hit)
- **PR feedback time:** Faster initial results from lint and tests
- **Storage costs:** Reduced by 50% with shorter artifact retention
- **Cache hit rates:** 80-95% for common operations

## For PR Authors

### What You'll Notice
1. **Faster CI runs** - Especially on subsequent pushes to the same PR
2. **Quicker feedback** - Lint and test results arrive sooner
3. **Consistent performance** - Cache hits make runs more predictable

### When Caches Miss
Caches will rebuild when you:
- Update `requirements.txt` or `requirements-dev.txt`
- Modify `constraints/security.txt`
- Change `.pre-commit-config.yaml`
- Update `go.mod` or `go.sum`

This is expected and ensures you always test with the latest dependencies.

### Artifacts
Test artifacts are now retained for **7 days** instead of 30. This is sufficient for:
- Debugging test failures
- Reviewing coverage reports
- Analyzing benchmark results

Download artifacts promptly if you need them for later reference.

## For Workflow Maintainers

### Caching Pattern

All optimized workflows follow this pattern:

```yaml
- name: Set up Python
  uses: actions/setup-python@v6
  with:
    python-version: '3.11'
    cache: 'pip'
    cache-dependency-path: |
      requirements.txt
      requirements.lock
      requirements-dev.txt
      requirements-dev.lock
      constraints/security.txt

- name: Cache Python packages  # Additional pip cache
  uses: actions/cache@v4
  with:
    path: ~/.cache/pip
    key: pip-{context}-${{ runner.os }}-py3.11-${{ hashFiles('requirements*.txt', 'requirements*.lock', 'constraints/security.txt') }}
    restore-keys: |
      pip-{context}-${{ runner.os }}-py3.11-

- name: Cache Python virtual environment  # Best for repeated installations
  uses: actions/cache@v4
  id: venv-cache
  with:
    path: .venv
    key: venv-{context}-${{ runner.os }}-py${{ matrix.python-version }}-${{ hashFiles('requirements*.txt', 'requirements*.lock', 'constraints/security.txt') }}
    restore-keys: |
      venv-{context}-${{ runner.os }}-py${{ matrix.python-version }}-

- name: Install dependencies
  if: steps.venv-cache.outputs.cache-hit != 'true'
  run: |
    python -m venv .venv
    .venv/bin/pip install --upgrade pip
    .venv/bin/pip install -r requirements.txt
```

### Cache Key Strategy

1. **Unique per context:** Use descriptive prefixes (`pip-lint-`, `pip-tests-`, etc.)
2. **Hash dependencies:** Include all relevant dependency files
3. **Restore keys:** Enable partial cache hits for faster fallback
4. **Conditional installation:** Skip when venv cache hits

### Artifact Retention

Set appropriate retention based on artifact type:

```yaml
- name: Upload test artifacts
  uses: actions/upload-artifact@v4
  with:
    name: test-results
    path: reports/
    retention-days: 7  # For temporary test/debug artifacts

- name: Upload wheels
  uses: actions/upload-artifact@v4
  with:
    name: wheels
    path: dist/
    retention-days: 14  # For build artifacts

- name: Upload security reports
  uses: actions/upload-artifact@v4
  with:
    name: security-scan
    path: reports/security/
    retention-days: 30  # For compliance/audit artifacts (if needed)
```

### Adding New Workflows

When creating a new workflow with Python dependencies:

1. ✅ Use `actions/setup-python` with `cache: 'pip'`
2. ✅ Add explicit pip cache with `actions/cache@v4`
3. ✅ Consider venv caching for repeated installs (tests, multi-job workflows)
4. ✅ Use conditional installation with `if: steps.cache.outputs.cache-hit != 'true'`
5. ✅ Set appropriate artifact retention
6. ✅ Use descriptive cache key prefixes

Example template:
```yaml
jobs:
  my-job:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v5
      
      - name: Set up Python
        uses: actions/setup-python@v6
        with:
          python-version: '3.11'
          cache: 'pip'
          cache-dependency-path: |
            requirements*.txt
            requirements*.lock
            constraints/security.txt
      
      - name: Cache Python packages
        uses: actions/cache@v4
        with:
          path: ~/.cache/pip
          key: pip-my-job-${{ runner.os }}-py3.11-${{ hashFiles('requirements*.txt') }}
          restore-keys: |
            pip-my-job-${{ runner.os }}-py3.11-
      
      - name: Install dependencies
        run: |
          pip install -r requirements.txt
      
      - name: Run my job
        run: python -m my.module
      
      - name: Upload results
        uses: actions/upload-artifact@v4
        with:
          name: my-results
          path: output/
          retention-days: 7  # Choose appropriate retention
```

## Cache Management

### Viewing Caches
- Go to repository **Settings** → **Actions** → **Caches**
- View cache keys, sizes, and last access times

### Cache Limits
- GitHub has a 10 GB total cache limit per repository
- Least recently used caches are evicted automatically
- Caches older than 7 days are automatically deleted

### Invalidating Caches
Caches auto-invalidate when dependency files change. To manually invalidate:
1. **Change the cache key:** Modify the key prefix or version
2. **Delete via API:** Use GitHub CLI or REST API
3. **Update dependencies:** Touch dependency files to trigger new hash

Example of adding a cache version:
```yaml
key: v2-pip-${{ runner.os }}-${{ hashFiles('requirements.txt') }}
```

### Cache Performance Tips

1. **Use restore-keys wisely:**
   ```yaml
   restore-keys: |
     pip-context-${{ runner.os }}-py3.11-
     pip-context-${{ runner.os }}-
   ```
   This allows partial matches when exact cache misses.

2. **Cache early, cache often:**
   - Cache at the beginning of jobs
   - Use separate caches for different contexts
   - Don't cache generated files or secrets

3. **Monitor cache effectiveness:**
   - Check cache hit rates in workflow logs
   - Look for "Cache restored from key:" messages
   - Adjust keys if hit rates are low

## Troubleshooting

### "Cache not found"
- Normal on first run or after dependency changes
- Check that cache keys are correctly formatted
- Verify dependency files exist at specified paths

### "Restore failed"
- Usually harmless, will build from scratch
- Check cache size limits
- Verify restore-keys are sensible fallbacks

### "Slower than before"
- Cache miss on first run is expected
- Subsequent runs should be faster
- Check workflow logs for cache hit/miss status

### "Dependency conflicts"
- Cached venv might have stale dependencies
- Update dependency files to invalidate cache
- Consider adding lock files to cache key hash

## Performance Monitoring

### Workflow Timing
Check the Actions tab for:
- Total workflow duration
- Time spent in "Set up Python" step
- Time spent in "Install dependencies" step

### Expected Timings

**Before optimization:**
- Dependency install: 2-3 minutes
- Total PR workflow: 45-60 minutes

**After optimization (cache hit):**
- Dependency install: 30-60 seconds
- Total PR workflow: 30-40 minutes

**After optimization (cache miss):**
- Dependency install: 2-3 minutes (same as before)
- Total PR workflow: 40-50 minutes (still better due to other optimizations)

## Questions?

- See [WORKFLOW_OPTIMIZATIONS.md](../../docs/WORKFLOW_OPTIMIZATIONS.md) for detailed docs
- Check [CI_CD_OVERVIEW.md](../../docs/CI_CD_OVERVIEW.md) for overall CI/CD architecture
- Create an issue with the `ci` label for workflow questions

---

*Last updated: 2025-12-10*
