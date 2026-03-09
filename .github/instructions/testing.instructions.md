# Testing instructions
- Use pytest markers: `fast`, `slow`, `crypto`, `exchange`, `replay`, `risk`, `security`, `integration`, `performance`, `contract`.
- Route tests by touched paths and run fast-lane checks on PR.
- Keep replay deterministic and fail fast for security/risk/execution regressions.
- Enforce coverage on critical paths (`execution`, `application/security`, `application/runtime`, `application/api`).
