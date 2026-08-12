<!-- Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab) -->
<!-- SPDX-License-Identifier: MIT -->

# Markdown Link Policy (DOC-001)

This repository enforces **internal Markdown link integrity** as a required,
fail-closed CI gate. The gate is implemented by
[`scripts/ci/check_links.py`](../scripts/ci/check_links.py) and asserted by
[`tests/ci/test_links.py`](../tests/ci/test_links.py).

## What the gate checks

Every tracked `*.md` file (`git ls-files '*.md'`) is scanned for:

* **inline links** — `[text](target)`
* **reference-style definitions** — `[label]: target`

Each *relative* link target is classified:

| Class          | Meaning                                                        | Gate effect |
| -------------- | ------------------------------------------------------------- | ----------- |
| `RESOLVED`     | Target file/dir exists relative to the linking file's dir      | pass        |
| `ANCHOR`       | In-document fragment (`#section`)                              | pass (see scope) |
| `EXTERNAL`     | Carries a URL scheme (`http:`, `https:`, `mailto:`, …)         | pass (not fetched) |
| `BROKEN`       | Repo-internal path but the target file is missing             | **fail**    |
| `OUTSIDE-ROOT` | Resolved path escapes the repository root (`../../…`)          | **fail unless allowlisted** |

Links inside fenced code blocks (```` ``` ````/`~~~`) and inline code spans
(`` `…` ``) are ignored. Anchor fragments and `?query` strings are stripped
before existence resolution.

## Rules

1. **Zero broken internal links.** Any `BROKEN` link fails the build. Fix the
   *link* to point at the real file — do **not** create empty stub files, and do
   **not** delete the surrounding prose. If a target was genuinely removed,
   repoint to the closest surviving document.
2. **No un-allowlisted outside-root links.** A link that escapes the repo root
   must be listed in [`link_allowlist.json`](link_allowlist.json) with a human
   rationale, or it fails the build. Prefer converting such links to a proper
   in-repo relative path; allowlist only when the target legitimately lives
   outside the tree.
3. **Root-absolute links are disallowed.** A leading `/` (e.g. `/docs/x.md`)
   resolves as a filesystem-absolute path and will be reported as
   `OUTSIDE-ROOT`. Use a relative path (`../x.md`) instead.
4. **External links are not existence-checked** here. Live-URL checking is
   handled separately by `.github/markdown-link-check-config.json`.

## Outside-root allowlist format

`docs/link_allowlist.json` is read by the checker. Shape:

```json
{
  "outside_root_allowlist": [
    { "file": "<md-relpath>", "target": "<raw-link-target>", "reason": "<why>" }
  ]
}
```

* An entry with `file` allowlists that exact `target` **only** from that file.
* A bare `{ "target": "…", "reason": "…" }` (no `file`) allowlists the target
  from any file.

**Current state:** zero legitimate outside-root links exist in the tree; every
outside-root link found during DOC-001 was an in-repo target written with a
leading slash and was repointed to a relative path. The allowlist therefore
ships with a single inert template row documenting the schema.

## Scope / honest residual

* **Anchor-level checking is out of scope.** The gate verifies that a target
  *file* exists; it does **not** verify that a `#fragment` resolves to a heading
  inside that file. Fragments are accepted as long as the file resolves (or the
  link is a pure in-document `#anchor`, which always passes).
* External URL liveness is not verified by this gate (see rule 4).
* Directory targets (`foo/`) pass when the directory exists.

## Running locally

```bash
python scripts/ci/check_links.py                                   # verify (exit 0 = clean)
python scripts/ci/check_links.py --json artifacts/governance/geosync_link_audit.json
python -m pytest tests/ci/test_links.py -q                         # gate tests
```
