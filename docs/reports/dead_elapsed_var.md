# Dead local removal — `elapsed` in SerotoninController

Date: 2026-06-10 · Branch: `fix/dead-elapsed-var`

`SerotoninController.get_performance_stats()` assigned
`elapsed = self._last_step_time` and never used it — the returned dict reports a
hardcoded `avg_step_time_ms` approximation. Removed.

This is the **single** CodeQL `py/unused-local-variable` finding (#195) that the
project's enforced linter (`ruff` F841) *also* flags as genuinely unused. Every
other CodeQL unused-import / unused-variable / unused-global finding is a false
positive against ruff (TYPE_CHECKING string annotations, `__all__` re-exports,
conditional rebinds, augmented assignments) and was dismissed with that
justification during the board triage.

Verification: `ruff check --select F841` clean · `black --check` clean ·
`mypy --strict` clean · serotonin test suite green.
