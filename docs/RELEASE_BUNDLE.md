# Canonical Release Bundle (REL-006)

> How the GeoSync release capsule is packaged as a git bundle so that a plain
> `git clone` lands on the sealed release — with **no manual ref selection**.

## Problem

Prior release bundles were built with `git bundle create … --all`, capturing
**363 refs** (many stale branch heads). Cloning such a bundle is ambiguous: the
caller must already know which of the 363 refs *is* the release, and a naive
`git clone` can check out an unintended HEAD. A release capsule must be
unambiguous by construction.

## Canonical release ref

| Field | Value |
|-------|-------|
| Tag | `geosync-canonical-8080e4b4` |
| Commit | `8080e4b475efe054901804f25b37b80bd06203f4` (the `Merge … into 'main'` seal) |
| Tree | `9060de4a097ea467f7ab5d52ecb660ba345f671b` |

The tag is the source of truth. The **tree hash is the checkout oracle**: a
correct clean-clone MUST check out tree `9060de4a…`.

## What the bundle contains

The bundle is built with **exactly two named refs** — never `--all`:

```
refs/heads/main                        -> 8080e4b4 (canonical commit)
refs/tags/geosync-canonical-8080e4b4   -> tag object (peels to 8080e4b4)
HEAD                                   -> 8080e4b4 (via symref to refs/heads/main)
```

Because the bundle's `HEAD` resolves to the canonical commit, a plain
`git clone <bundle>` checks out `main` at tree `9060de4a…` directly.

### Why `main` in the capsule is pinned to the seal

The capsule pins `main` to the canonical commit — the sealed release state. The
**live** repository's `main` may have advanced past the seal (in the REL-006
worktree it was at `c5417de`, which does *not* contain `8080e4b4`). That is
expected and correct: the capsule is immutable at the sealed ref, and the tag is
authoritative. `main` inside the bundle is a convenience head so that a plain
clone lands on the release rather than on a detached HEAD.

The build script never mutates the source repository's refs or `HEAD`. It
assembles a throwaway bare repo in `/tmp`, pins `main`/`HEAD` there, and runs
`git bundle create … --all` against *that* pinned repo (where `--all` is exactly
the two canonical refs).

## Building the bundle

```bash
# default output: /tmp/geosync-canonical-geosync-canonical-8080e4b4.bundle
scripts/release/build_canonical_bundle.sh

# explicit output path
scripts/release/build_canonical_bundle.sh /tmp/geosync-release.bundle
```

The script self-verifies the emitted bundle (`git bundle verify`, exact ref set,
`HEAD` resolves to the canonical commit) and fails closed (exit 2) on any
contract violation — missing tag, tree mismatch, or unexpected refs.

> **Size warning:** the bundle is ~150 MB. It is written to `/tmp` by default and
> **must never be committed** into the repository or a worktree.

## Verifying clean-clone behavior (CI smoke)

```bash
python scripts/ci/check_bundle_clone.py
```

This gate (`G-RELEASE-BUNDLE-CLONE`) runs the full pipeline in `/tmp`:

1. build the canonical bundle;
2. **plain** `git clone` it (no `--branch`, no ref selection);
3. assert HEAD tree == `9060de4a097ea467f7ab5d52ecb660ba345f671b`;
4. `git fsck --strict` must exit 0;
5. dangling-object count must be 0;

then it writes the machine-generated receipt and deletes every `/tmp` artifact
(bundle + clone). Exit 2 on any assertion failure.

Flags: `--receipt PATH` (receipt location), `--no-write` (assert only),
`--keep` (retain the `/tmp` workdir for debugging).

## Evidence

- `scripts/release/build_canonical_bundle.sh` — bundle builder (canonical refs only).
- `scripts/ci/check_bundle_clone.py` — build→clone→fsck clean-clone gate.
- `artifacts/release/bundle_clone_receipt.json` — real receipt from an actual run
  (refs included, clone HEAD tree, fsck verdict, `dangling_count: 0`).

## Acceptance (REL-006)

| Criterion | Result |
|-----------|--------|
| `git clone <bundle>` checks out the canonical release directly | PASS — HEAD tree `9060de4a…`, branch `main`, no manual selection |
| `git fsck --strict` | PASS — exit 0 |
| No required commit dangling | PASS — `dangling_count: 0` |
