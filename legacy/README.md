# Legacy Code and Artifacts Directory

This directory contains code, configurations, and scripts that are no longer actively used in the TradePulse system but are preserved for historical reference and potential future reuse.

## Structure

```
legacy/
├── code/       # Python modules with no active imports or references
├── config/     # Configuration files that have been superseded
├── scripts/    # Utility scripts no longer called by CI/Makefile
└── README.md   # This file
```

## Purpose

Files are moved here when they:
- Have no active imports or function calls in the codebase
- Are not referenced in tests, CI workflows, or Makefile
- Are not mentioned in primary documentation (README, ARCHITECTURE, TESTING, SECURITY)
- Have been superseded by newer implementations

## Retention Policy

Legacy files are kept indefinitely because they:
- Provide historical context about system evolution
- May contain algorithms or approaches useful for future features
- Document past implementation decisions
- Preserve institutional knowledge

## Using Legacy Code

**⚠️ WARNING**: Code in this directory is not maintained and may:
- Use outdated dependencies or APIs
- Not follow current coding standards
- Lack test coverage
- Have security vulnerabilities

If you need functionality from a legacy module:
1. Review the code carefully for compatibility
2. Update dependencies and APIs as needed
3. Add comprehensive tests
4. Run security scans
5. Consider reimplementing rather than reusing directly

## File Naming Convention

Files retain their original names to preserve git history tracking via `git mv`.
Use `git log --follow legacy/code/<filename>` to see the complete history.

## Related Directories

- `docs/archive/` - Legacy documentation and task completion reports
- `docs/legacy/` - Superseded technical documentation (if exists)

## Index

### Moved on 2025-12-12 (Phase 2 Deep Cleanup)

**Code Modules** (no active references):
- `core/metrics/lyapunov.py` → `legacy/code/lyapunov.py`
  - Reason: No imports found, Lyapunov analysis not used in current system
  
- `runtime/fractal_sync.py` → `legacy/code/fractal_sync.py`
  - Reason: No references, fractal synchronization not implemented
  
- `runtime/filters/vlpo_core_filter/visualization/plot_filter.py` → `legacy/code/plot_filter.py`
  - Reason: Visualization module not used

**Scripts** (not called by CI/Makefile/docs):
- `scripts/backtest_agent.py` → `legacy/scripts/backtest_agent.py`
- `scripts/capacity_sweep.py` → `legacy/scripts/capacity_sweep.py`
- `scripts/make_synth.py` → `legacy/scripts/make_synth.py`
- `scripts/run_golden_path_perf.py` → `legacy/scripts/run_golden_path_perf.py`
- `scripts/run_walkforward.py` → `legacy/scripts/run_walkforward.py`
- `scripts/run_walkforward_parallel.py` → `legacy/scripts/run_walkforward_parallel.py`
- `scripts/train_agent.py` → `legacy/scripts/train_agent.py`

All files moved with `git mv` to preserve complete history.
