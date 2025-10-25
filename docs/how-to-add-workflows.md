# How to Add or Extend GitHub Workflows

TradePulse relies on GitHub Actions to orchestrate CI checks, security scans, and delivery automation. Use the following process to add a new workflow or extend an existing one while maintaining consistency across the repository.

## 1. Decide where the job belongs

- Add project-wide automation under `.github/workflows/`.
- For reusable job definitions, prefer composite actions stored in `.github/actions/`.
- Group related functionality into a single workflow file unless separation simplifies permissions or runtime constraints.

## 2. Start from a proven template

- Copy an existing workflow that matches the toolchain you need (Python, Docker, etc.).
- Update the `name`, triggers under the `on:` section, and job identifier to reflect the purpose of the new workflow.
- Keep `workflow_dispatch` as an optional trigger whenever manual reruns are helpful for maintainers.

## 3. Apply repository standards

- Pin third-party actions to their major versions (`@v4`, `@v6`, …) to inherit security patches automatically.
- Run automation on `ubuntu-latest` unless the job requires a specific runner.
- Request the minimum necessary permissions per job to honour GitHub's principle of least privilege.
- Prefer Python 3.11 for scripts unless an explicit toolchain demands a different version; specify it via `actions/setup-python`.

## 4. Validate locally when possible

- Use `act` with the provided `.actrc` presets to dry-run workflow logic.
- For Docker-heavy workflows, exercise `docker build` locally with the same build arguments the workflow will use.
- Where secrets are required, inject them via environment variables in `act` rather than storing them on disk.

## 5. Document the change

- Summarise the purpose of the workflow in `docs/final-summary.md` or the most relevant README.
- If the workflow introduces new contributor expectations, update `TESTING.md` or related guides accordingly.
- Capture any follow-up tasks in the backlog so the team can iterate on the automation.

Following these steps keeps the automation suite coherent, secure, and easy for new contributors to understand.
