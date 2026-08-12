<!-- SPDX-License-Identifier: MIT -->
# Hermetic CPU Container (ENV-005)

A reproducible, digest-pinned, non-root container that can execute GeoSync
integrity gates offline, with a read-only root filesystem. It closes the
"works-on-my-machine" gap for the release gates: the same image, byte-for-byte,
runs the gates in CI and locally.

- **Dockerfile:** [`Dockerfile.repro`](../Dockerfile.repro)
- **Builder:** [`scripts/ci/build_hermetic_image.sh`](../scripts/ci/build_hermetic_image.sh)
- **Policy gate:** [`scripts/ci/check_hermetic_image.py`](../scripts/ci/check_hermetic_image.py) (G-HERMETIC-IMAGE)
- **Test:** [`tests/ci/test_hermetic_image.py`](../tests/ci/test_hermetic_image.py)
- **Provenance:** [`artifacts/env/image_digest.json`](../artifacts/env/image_digest.json)
- **Scan report:** [`artifacts/env/image_scan_report.json`](../artifacts/env/image_scan_report.json)

## Hermetic guarantees

The gate `G-HERMETIC-IMAGE` statically enforces each of these on `Dockerfile.repro`:

| Guarantee | How it is enforced |
| --- | --- |
| Base pinned by **digest** | `FROM python:3.12-slim@sha256:423ed6…` — an immutable content digest, never a mutable tag. |
| **Non-root** execution | A dedicated `geosync` user (uid/gid 10001) is the effective `USER`. |
| No runtime package mutation | `apt` appears **only** in the build layer and its lists are removed in the same layer; there is no `apt-get upgrade` and no `pip install --upgrade`; `CMD`/`ENTRYPOINT` never invoke a package manager. |
| **Hashed** dependency install | `pip install --require-hashes` over a fully pinned (`==`) transitive closure — every artifact must match a recorded `sha256` or the build fails closed. |
| Deterministic **locale** | `LANG=LC_ALL=C.UTF-8` (ships with glibc; no locale-gen needed). |
| Deterministic **timezone** | `TZ=UTC`, with `/etc/localtime` linked to `UTC`. |
| Reproducible timestamps | `ARG SOURCE_DATE_EPOCH` (default `0`), recorded in `image_digest.json`. |

## Build

```bash
scripts/ci/build_hermetic_image.sh          # build + digest capture + scan
scripts/ci/build_hermetic_image.sh --no-scan
```

The script builds `geosync-hermetic:repro`, writes the resolved image id / base
digest / build args to `artifacts/env/image_digest.json`, runs a vulnerability
scan into `artifacts/env/image_scan_report.json`, then prunes dangling images
and build cache to protect the disk budget.

## Run a gate inside the container (read-only)

The repo is **mounted read-only** — never copied into the image — so the image
stays source-agnostic and `MANIFEST.sha256` / `INVENTORY.json` are never
embedded.

```bash
docker run --rm --read-only \
  --tmpfs /tmp:rw,size=64m \
  --user "$(id -u):$(id -g)" \
  -v "$PWD":/repo:ro \
  geosync-hermetic:repro \
  scripts/ci/check_capsule_schema.py
```

- `--read-only` makes the container root filesystem immutable; the only writable
  surface is the explicit `--tmpfs /tmp`.
- `-v "$PWD":/repo:ro` mounts the working tree read-only.
- `--user "$(id -u):$(id -g)"` is needed **only** because this repo's working
  tree is group-readable but not world-readable (mode `0660/0770`); it maps the
  process to the invoking (non-root) user so it can read the mount. The image's
  baked-in default identity remains the non-root `geosync` (uid 10001) — verify
  with `docker run --rm geosync-hermetic:repro -c "import os;print(os.getuid())"`
  → `10001`.

The gate executed as the acceptance witness is `check_capsule_schema.py`
(G-CAPSULE-SCHEMA): a pure-Python, git-independent integrity gate that validates
every committed reproducible-capsule manifest against its JSON Schema. It
returns exit 0 inside the read-only container.

> Note: gates that shell out to `git` (e.g. `check_root_manifest.py`) are **not**
> run through a bare read-only mount here, because this worktree's `.git` is a
> file pointing outside the mount (`gitdir: …/GeoSync/.git/worktrees/…`). Running
> those in-container requires additionally mounting the parent git dir; the
> capsule-schema gate is the self-contained witness.

## Vulnerability scan & acceptance policy

The scan (trivy, severity `CRITICAL,HIGH`, vuln scanner) is post-processed into
an **acceptance envelope** (`image_scan_report.json`, schema
`geosync.env.image_scan/v1`):

- A CVE with **no upstream fix** (empty `FixedVersion`; Debian status `affected`
  / `fix_deferred`) is recorded as **ACCEPTED** — it is inherited from the pinned
  `python:3.12-slim` (debian trixie) base and cannot be remediated at scan time.
  These packages (`perl-base`, `util-linux`, `ncurses`, `gzip`, …) are not
  reachable through the pure-Python integrity gate, and the container runs
  non-root, read-only, and offline.
- A CVE that **has a fix** is **ACTIONABLE** and flips the report `verdict` to
  `FAIL` (fail-closed). Remediation is to re-pin the base image digest to a
  patched build.

At the recorded build the report verdict is **PASS**: `accepted_unfixable = 22`,
`actionable_fixable = 0` (0 critical/high **unaccepted**). Re-run the builder
after a base bump; when Debian ships fixes, they become actionable and the gate
turns them RED until the digest is re-pinned.

If neither `trivy` nor `grype` is installed, the builder records
`{"scanner_absent": true}` honestly instead of fabricating a clean report.

## Full-suite image (deferred, disk-bound)

This **CORE** image installs only the integrity-gate tooling (`pytest`,
`PyYAML`, `jsonschema`) and their fully-hashed transitive closure — enough to
run the critical gates and prove the hermetic pattern end-to-end.

The **full-suite** image uses the *same* `Dockerfile.repro` pattern with the
complete `--require-hashes requirements.lock`. That build is deferred here
because `requirements.lock` pulls multi-GB `torch` + NVIDIA CUDA wheels that
exceed the current disk budget (~a few GB free on `/home`). To produce it,
swap the embedded `hermetic-requirements.txt` heredoc for a `COPY
requirements.lock` + `pip install --require-hashes -r requirements.lock` on a
host with sufficient disk; every other guarantee is unchanged.
