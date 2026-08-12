# Unicode (Non-ASCII) Tracked-Path Policy

Status: enforced (CI gate + packaging tests)
Audit finding: #1 — Unicode filename portability
Task: REL-007

## Scope

The repository tracks documents with non-ASCII (Cyrillic) filenames, e.g.
`docs/operations/СТАН_РОЗВИТКУ_ПРОЄКТУ.md`. Release packaging uses
`git archive`. This policy defines how such paths MUST be encoded so that the
archive, checkout, and internal links remain portable on Linux.

Enumerate every tracked non-ASCII path with:

```
git -c core.quotePath=false ls-files | grep -P '[^\x00-\x7F]'
```

(`git ls-files` quotes non-ASCII bytes as octal escapes by default; disable
`core.quotePath` to see the real UTF-8 name.)

## The actual defect vs. the display artifact

There are two distinct things that get conflated:

1. **Display artifact (NOT a defect).** `git archive --format=zip HEAD` stores
   the filename as its raw UTF-8 bytes AND sets the zip "language encoding" flag
   (general-purpose bit 11, `0x800`). Any conformant extractor — Python
   `zipfile`, `bsdtar`, `unzip` built with UTF-8 support — reproduces the exact
   name. Some **legacy `unzip` builds ignore that flag** and render the octets
   as `#U0421#U0422...`. The archived bytes are correct; only the extractor's
   display is wrong. **This does not require a rename.** Verify with a
   UTF-8-honoring extractor:

   ```python
   import io, subprocess, zipfile
   z = subprocess.run(["git","archive","--format=zip","HEAD"],
                      capture_output=True).stdout
   names = zipfile.ZipFile(io.BytesIO(z)).namelist()
   assert "docs/operations/СТАН_РОЗВИТКУ_ПРОЄКТУ.md" in names
   ```

   or `bsdtar tf archive.zip`.

2. **Genuine portability bug: NFD (decomposed) names.** NFC and NFD forms render
   identically but are **different byte sequences**. A macOS-authored path can
   be stored decomposed (e.g. `Й` as `U+0418 U+0306` instead of `U+0419`);
   internal Markdown links written in NFC then fail to match, and Linux tooling
   sees a different filename. This IS a defect and MUST be fixed.

## Policy (normative)

Every tracked non-ASCII path MUST:

1. Be **NFC-normalized**: `unicodedata.normalize('NFC', name) == name`.
2. **Resolve on disk** in the working tree.
3. Survive a `git archive --format=zip HEAD` round-trip **byte-identical**, with
   the zip UTF-8 flag (`0x800`) set.
4. Be referenced by internal links/paths only in its exact NFC form; every such
   reference MUST resolve to an existing file.

Renames of a tracked non-ASCII file are done with care: they must preserve the
NFC form, update every internal reference, and re-run the gate + tests. Do not
rename to "fix" the `#U` display artifact — that is not a byte-level problem.

## Enforcement

- **Gate:** `scripts/ci/check_unicode_paths.py` — fail-closed
  (`exit 0` = clean, `exit 1` = violation, `exit 2` = environment error).
  Checks NFC, on-disk resolution, archive byte-identity, and broken references.
- **Tests:** `tests/packaging/test_unicode_paths.py` — POSITIVE (the real
  tracked path survives `git archive` → `zipfile` extraction byte-identical and
  is NFC; references resolve) and NEGATIVE (a synthetic NFD name is rejected by
  the NFC check; the gate returns `exit 1`).
- **Receipt:** `artifacts/release/unicode_archive_receipt.json` — recorded NFC
  status, UTF-8 bytes, archive round-trip result, and verdict at a pinned
  `git HEAD`.

## Current state (finding #1 disposition)

`docs/operations/СТАН_РОЗВИТКУ_ПРОЄКТУ.md` is **already NFC-normalized** — the
Ukrainian Cyrillic base letters used here have no canonical decomposition, so
NFC == NFD == the tracked bytes. It survives the `git archive` → zip round-trip
byte-identical with the UTF-8 flag set. **The reported `#U...` symptom is a
legacy-extractor display artifact, not a corruption; no rename is required.**
The gate exists to keep it that way and to fail-close on any future NFD path.
