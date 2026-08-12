# Fake-Closure Advisory Scanner

`tools/governance/check_fake_closure_claims.py`

## Why

> An issue is closed only by a matching source-level mechanism + tests + CI +
> ledger. A green test suite over a partial guard does not satisfy a
> non-waivable requirement. A test/fixture-only PR must say `Refs #N`, never
> `Closes #N`.

Canonical regression: **PR #1140** declared `Closes #1109` while being
test/fixture-only — the full `SecondOrderStabilityAudit` object that #1109
requires was never built. The closing keyword auto-closed a still-incomplete
issue (`FAKE_CLOSURE`). #1109 has since been reopened and #1140 downgraded to
`Refs #1109`.

## What it does

Given a PR body and the bodies of the issues it closes, it returns one state:

| State | Meaning |
|-------|---------|
| `PASS` | Closure claims are consistent with satisfied issue requirements. |
| `ADVISORY_FAIL` | A `Closes #N` references an issue with unchecked non-waivable requirements. **Does not block merge.** |
| `UNKNOWN` | An issue body was unavailable or its requirement structure is unverifiable (e.g. a non-waivable declaration in prose with no checklist). Never silently upgraded to `PASS`. |
| `OUT_OF_SCOPE` | No closing keyword in the PR body — nothing to verify. |

## Detection heuristic (deliberately high-precision)

1. **Closure keywords** (`close[sd]`, `fix(es|ed)`, `resolve[sd]`) `#N`, case-insensitive. Keywords inside fenced/inline **code spans are ignored** — GitHub ignores them too, and correction notes routinely quote `` `Closes #N` ``.
2. **Bare `Refs #N`** is never a closure claim → out of scope.
3. An unchecked GFM item `- [ ]` is treated as a **hard requirement** when either:
   - the issue contains an explicit `non-waivable` declaration (the *only* global promoter), or
   - the item text itself carries a per-item qualifier (`required:`, `acceptance:`, `source-level`, `release-blocking`, `evidence-bearing`, `same-sha ci`, `must `, …).
4. A normal checklist with no such markers does **not** fail (false-positive guard).

## Known limitations (report survival paths, not victories)

- **Prose-lane overreach is NOT detected.** #1143 declares `Closes #1096`, but FP-1 is only Lane A of the 5-lane #1096 epic. #1096 expresses its lanes as prose/headers with **zero GFM checkboxes**, so the checkbox heuristic returns `PASS`. This is a real **false negative**: the scanner's scope is *checklist-bearing* issues. Multi-lane epics need either checkbox-per-lane in the issue or human review.
- **Diff-vs-requirement matching is not performed.** The scanner reads the *claim surface* (PR body + issue checklist), not whether the diff actually implements each requirement. It catches the #1109 class (issue visibly incomplete), not a PR that checks a box without landing the mechanism.
- **`UNKNOWN` is common for closed/legacy issues** whose bodies lack a machine-readable checklist. This is intended: better honest `UNKNOWN` than false `PASS`.

## Usage

```bash
# Live (advisory; always exits 0):
python tools/governance/check_fake_closure_claims.py --pr 1140

# Offline (CI-free, deterministic):
python tools/governance/check_fake_closure_claims.py \
  --body-file pr_body.md --issue-file issue_1109.md
```

## Advisory CI (enable when ready — intentionally NOT added yet)

This phase ships the tool + tests + ledger only. Wiring CI is deferred so the
scanner can be calibrated first. To enable a **non-blocking** advisory check,
add `.github/workflows/fake-closure-advisory.yml`:

```yaml
name: Fake Closure Advisory
on: [pull_request]
permissions:
  contents: read
  pull-requests: read
jobs:
  fake-closure-advisory:
    runs-on: ubuntu-latest
    continue-on-error: true   # ADVISORY: never blocks merge
    steps:
      - uses: actions/checkout@v6
      - uses: actions/setup-python@v6
        with: { python-version: "3.12" }
      - env: { GH_TOKEN: ${{ github.token }} }
        run: python tools/governance/check_fake_closure_claims.py --pr ${{ github.event.pull_request.number }} | tee fake_closure.json
      - uses: actions/upload-artifact@v4
        with: { name: fake-closure-report, path: fake_closure.json }
```

## Promotion policy (advisory → required)

Do **not** make this a required blocking gate until all hold:

- ≥ 10 real PR bodies scanned and recorded in the closure ledger;
- zero known false **negatives** on non-waivable closure cases;
- false-**positive** rate < 5%;
- ambiguous cases return `UNKNOWN`, never `FAIL`;
- repo owner explicitly approves required mode.
