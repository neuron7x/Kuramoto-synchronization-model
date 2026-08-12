# Version Policy — Single Source of Truth (SSOT)

**Status:** enforced (REL-008) · **Gate:** `scripts/ci/check_version_ssot.py` ·
**Tests:** `tests/ci/test_version_ssot.py`

GeoSync declares its version string **once** and reconciles every other
version-bound surface to that single value. Drift between surfaces is a
supply-chain and provenance hazard (a wheel that reports a different version
than the citation metadata, or a changelog that names a version no tag backs);
this policy makes such drift a hard CI failure.

## 1. The canonical source

The canonical current version lives in the repository-root **`VERSION`** file:

```
1.1.0
```

Nothing else *invents* a version. `VERSION` is the value the gate reads and the
value every other surface must match.

## 2. Bound surfaces (enforced, fail-closed)

`scripts/ci/check_version_ssot.py` reads the canonical value from `VERSION` and
asserts the identical string on each of:

| Surface | Location | Role |
| --- | --- | --- |
| **VERSION** | repo root | canonical SSOT (source of truth) |
| **CITATION.cff `version`** | top level | academic / citation metadata |
| **CITATION.cff `preferred-citation.version`** | nested | preferred-citation metadata |
| **`fallback_version`** | `pyproject.toml` → `[tool.setuptools_scm]` | wheel / CLI `--version` derivation fallback |
| **CHANGELOG heading** | `CHANGELOG.md` | a `## [<version>]` release section must exist |

Any mismatch, missing surface, empty/malformed `VERSION`, or unreadable file
returns a non-zero exit code. There is no "best effort" — the gate fails closed.

## 3. How the wheel / CLI version is derived (and the true source)

The distribution version is **dynamic** (`pyproject.toml` → `dynamic =
["version", ...]`) and produced by **setuptools_scm**:

```toml
[tool.setuptools_scm]
version_file = "src/_version.py"   # generated at build time — DO NOT hand-edit
fallback_version = "1.1.0"
```

- On a normal build, setuptools_scm derives the version **from the git tag**.
  It considers only PEP 440-style tags, so the release tag must be
  `v<version>` (e.g. **`v1.1.0`**). That tag is the *true* dynamic source of the
  wheel version and of `src/_version.py` (which is generated, git-ignored, and
  must never be edited by hand).
- When **no version tag is reachable from `HEAD`** (shallow CI checkout, an
  untagged working branch, or — as on the current `remediation/wave3-p0` branch
  — a `v1.1.0` tag that lives on a divergent commit not in HEAD's ancestry),
  setuptools_scm falls back to **`fallback_version`**. That is why
  `fallback_version` is an SSOT-bound surface: on such branches it, not the tag,
  governs the wheel version, so it must equal `VERSION`.

**Image tags** derive from the same string: container / release images are
tagged `geosync:<version>` (== the `v<version>` git tag == `VERSION`). Publish
workflows must read the version from `VERSION` (or `git describe`), never
hard-code it.

## 4. Releasing a new version — the reconciliation ritual

To cut version `X.Y.Z`, change the string in **all** declared surfaces in one
commit, then tag:

1. `VERSION` → `X.Y.Z`
2. `CITATION.cff` → `version: X.Y.Z` **and** `preferred-citation.version: "X.Y.Z"`
   (also update `date-released`).
3. `pyproject.toml` → `[tool.setuptools_scm] fallback_version = "X.Y.Z"`.
4. `CHANGELOG.md` → add a `## [X.Y.Z] - <date>` release heading above the
   previous entries. **Never rewrite historical entries.**
5. Run `python scripts/ci/check_version_ssot.py` — must exit 0.
6. Commit, then tag the release commit: `git tag vX.Y.Z && git push --tags`.
   The tag is what setuptools_scm reads for the published wheel.

The tag and the files must always agree; the gate enforces the file side, and
the tag is the authoritative side for the built artifact.

## 5. Historical versions

`CHANGELOG.md` preserves prior version headings verbatim for provenance. The
`2.x.y` entries are a **legacy imported history** that predates this SSOT and
uses a numbering scheme inconsistent with the current release tags
(`v1.0.0`, `v1.1.0`); they are clearly marked historical in the changelog and
are **not** the current version. The gate ignores non-canonical headings — it
only requires that a heading for the *current* canonical version exists.

## 6. Honest residuals

- **Tag ↔ HEAD divergence.** On `remediation/wave3-p0` the `v1.1.0` tag is not an
  ancestor of `HEAD`, so a build here derives its version from `fallback_version`,
  not the tag. This is expected and documented; the fallback is pinned to the
  SSOT so the wheel still reports `1.1.0`. When the release is cut on the
  mainline, `v1.1.0` (or the next tag) must sit on the release commit.
- **`src/_version.py` is generated**, not tracked as an SSOT surface. It is a
  build artifact of setuptools_scm and must never be hand-edited; the gate does
  not read it (checking a generated file would test the build tool, not the
  declaration).
- **Changelog numbering legacy.** The historical `2.x.y` block is numerically
  higher than the current `1.1.0`. This is a known artifact of an earlier import
  and is retained rather than rewritten, per the "preserve history" rule.
