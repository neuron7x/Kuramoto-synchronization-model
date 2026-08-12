# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for the CI permission & untrusted-PR boundary gate (SEC-011).

POSITIVE: the real ``.github/workflows`` tree passes the checker (exit 0, every
workflow has an explicit permissions block, no unsafe pull_request_target).

NEGATIVE (the malicious-PR model):
  * a ``pull_request_target`` workflow that checks out the PR head AND has a
    ``secrets.*`` value in an env → flagged UNSAFE_PRT_CHECKOUT, exit 1;
  * a workflow with no top-level ``permissions:`` block → flagged
    MISSING_PERMISSIONS, exit 1.

Plus: write-all default, unjustified write scope, and fail-closed parse error.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REAL_WORKFLOWS = ROOT / ".github/workflows"


def _load_gate():
    # Load by path — tests/ci helper tests are independent of repo-level
    # sys.path bootstrapping (see tests/ci/pytest.ini).
    src = ROOT / "scripts/ci/check_ci_permissions.py"
    spec = importlib.util.spec_from_file_location("check_ci_permissions", src)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


gate = _load_gate()


def _write(dir_: Path, name: str, text: str) -> Path:
    dir_.mkdir(parents=True, exist_ok=True)
    path = dir_ / name
    path.write_text(text, encoding="utf-8")
    return path


# --------------------------------------------------------------------------- #
# POSITIVE: the hardened real tree passes.
# --------------------------------------------------------------------------- #
def test_positive_real_tree_passes() -> None:
    rc = gate.main(["--workflows", str(REAL_WORKFLOWS), "--quiet"])
    assert rc == gate.EXIT_OK

    report = gate.audit_dir(REAL_WORKFLOWS)
    assert report["status"] == "PASS", report["workflows_flagged"]
    assert report["workflows_flagged"] == 0
    assert report["workflows_audited"] >= 60
    # Every workflow has an explicit permissions block.
    assert all(w["has_top_level_permissions"] for w in report["workflows"])
    # No workflow uses pull_request_target at all.
    assert not any(w["uses_pull_request_target"] for w in report["workflows"])


# --------------------------------------------------------------------------- #
# NEGATIVE 1: pull_request_target + PR-head checkout + secrets in env.
# --------------------------------------------------------------------------- #
_PWN_REQUEST = """\
name: Pwn Request
on:
  pull_request_target:
    branches: [main]
permissions:
  contents: read
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@0000000000000000000000000000000000000000
        with:
          ref: ${{ github.event.pull_request.head.sha }}
      - name: Build untrusted PR code with a secret in scope
        env:
          NPM_TOKEN: ${{ secrets.NPM_TOKEN }}
        run: ./ci/build.sh
"""


def test_negative_pull_request_target_pwn_request_flagged(tmp_path: Path) -> None:
    wf = tmp_path / "wf"
    _write(wf, "pwn.yml", _PWN_REQUEST)
    rc = gate.main(["--workflows", str(wf), "--quiet"])
    assert rc == gate.EXIT_FLAGGED

    report = gate.audit_dir(wf)
    assert report["status"] == "FLAGGED"
    assert report["workflows_flagged"] == 1
    (w,) = report["workflows"]
    assert w["uses_pull_request_target"] is True
    assert w["checks_out_pr_head"] is True
    assert "NPM_TOKEN" in w["explicit_secret_refs"]
    codes = {f["code"] for f in w["flags"] if f["level"] == gate.FATAL}
    assert "UNSAFE_PRT_CHECKOUT" in codes


# --------------------------------------------------------------------------- #
# NEGATIVE 2: no top-level permissions block.
# --------------------------------------------------------------------------- #
_NO_PERMISSIONS = """\
name: No Permissions
on:
  pull_request:
    branches: [main]
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - run: echo hi
"""


def test_negative_missing_permissions_flagged(tmp_path: Path) -> None:
    wf = tmp_path / "wf"
    _write(wf, "no_perms.yml", _NO_PERMISSIONS)
    rc = gate.main(["--workflows", str(wf), "--quiet"])
    assert rc == gate.EXIT_FLAGGED

    report = gate.audit_dir(wf)
    (w,) = report["workflows"]
    assert w["has_top_level_permissions"] is False
    codes = {f["code"] for f in w["flags"] if f["level"] == gate.FATAL}
    assert "MISSING_PERMISSIONS" in codes


# --------------------------------------------------------------------------- #
# NEGATIVE 3: write-all default is fatal.
# --------------------------------------------------------------------------- #
_WRITE_ALL = """\
name: Write All
on: [push]
permissions: write-all
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - run: echo hi
"""


def test_negative_write_all_flagged(tmp_path: Path) -> None:
    wf = tmp_path / "wf"
    _write(wf, "write_all.yml", _WRITE_ALL)
    rc = gate.main(["--workflows", str(wf), "--quiet"])
    assert rc == gate.EXIT_FLAGGED

    report = gate.audit_dir(wf)
    (w,) = report["workflows"]
    codes = {f["code"] for f in w["flags"] if f["level"] == gate.FATAL}
    assert "WRITE_ALL_DEFAULT" in codes


# --------------------------------------------------------------------------- #
# NEGATIVE 4: an unexplained write scope is fatal (keeps the default honest).
# --------------------------------------------------------------------------- #
_UNJUSTIFIED_WRITE = """\
name: Rogue Write
on: [push]
permissions:
  contents: write
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - run: echo hi
"""


def test_negative_unjustified_write_scope_flagged(tmp_path: Path) -> None:
    wf = tmp_path / "wf"
    _write(wf, "rogue.yml", _UNJUSTIFIED_WRITE)
    rc = gate.main(["--workflows", str(wf), "--quiet"])
    assert rc == gate.EXIT_FLAGGED

    report = gate.audit_dir(wf)
    (w,) = report["workflows"]
    assert w["top_level_write_scopes"] == ["contents"]
    codes = {f["code"] for f in w["flags"] if f["level"] == gate.FATAL}
    assert "UNJUSTIFIED_WRITE_SCOPE" in codes


# --------------------------------------------------------------------------- #
# SAFE VARIANT: pull_request_target WITHOUT a PR-head checkout is not the pwn
# pattern (e.g. labelling a PR from the base ref). Must NOT be flagged fatal.
# --------------------------------------------------------------------------- #
_PRT_NO_CHECKOUT = """\
name: Label PR
on:
  pull_request_target:
    types: [opened]
permissions:
  contents: read
  pull-requests: read
jobs:
  triage:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@0000000000000000000000000000000000000000
      - run: echo "operate on base ref only"
"""


def test_prt_without_pr_head_checkout_not_fatal(tmp_path: Path) -> None:
    wf = tmp_path / "wf"
    _write(wf, "label.yml", _PRT_NO_CHECKOUT)
    report = gate.audit_dir(wf)
    (w,) = report["workflows"]
    assert w["uses_pull_request_target"] is True
    assert w["checks_out_pr_head"] is False
    codes = {f["code"] for f in w["flags"] if f["level"] == gate.FATAL}
    assert "UNSAFE_PRT_CHECKOUT" not in codes
    assert w["status"] == "PASS"


# --------------------------------------------------------------------------- #
# Use / mention: merely NAMING pull_request_target in a comment is not using it.
# --------------------------------------------------------------------------- #
_MENTION_ONLY = """\
# This workflow forbids pull_request_target and checks secrets policy.
name: Policy Mention
on:
  pull_request:
    branches: [main]
permissions:
  contents: read
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - run: echo "no pull_request_target trigger here"
"""


def test_mention_of_pull_request_target_not_flagged(tmp_path: Path) -> None:
    wf = tmp_path / "wf"
    _write(wf, "mention.yml", _MENTION_ONLY)
    report = gate.audit_dir(wf)
    (w,) = report["workflows"]
    assert w["uses_pull_request_target"] is False
    assert w["status"] == "PASS"


# --------------------------------------------------------------------------- #
# Fail-closed: an unparseable workflow errors (exit 2), never silently passes.
# --------------------------------------------------------------------------- #
def test_fail_closed_on_unparseable_workflow(tmp_path: Path) -> None:
    wf = tmp_path / "wf"
    _write(wf, "broken.yml", "name: [unterminated\n  : : :\n")
    rc = gate.main(["--workflows", str(wf), "--quiet"])
    assert rc == gate.EXIT_ERROR
    report = gate.audit_dir(wf)
    assert report["status"] == "ERROR"
    assert report["parse_errors"]


# --------------------------------------------------------------------------- #
# DS-06 [HIGH]: GitHub Actions runs BOTH *.yml and *.yaml. Auditing only *.yml
# left an identical .yaml twin of the pwn-request pattern completely unaudited.
# The malicious .yaml MUST now be audited and FLAGGED; a benign .yaml twin must
# still be audited and PASS (proves the extension is audited, not just flagged).
# --------------------------------------------------------------------------- #
_PWN_REQUEST_YAML = _PWN_REQUEST  # byte-identical content, .yaml extension

_BENIGN_YAML = """\
name: Benign Yaml
on:
  pull_request:
    branches: [main]
permissions:
  contents: read
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - run: echo hi
"""


def test_ds06_yaml_extension_pwn_request_flagged(tmp_path: Path) -> None:
    wf = tmp_path / "wf"
    _write(wf, "pwn.yaml", _PWN_REQUEST_YAML)
    rc = gate.main(["--workflows", str(wf), "--quiet"])
    assert rc == gate.EXIT_FLAGGED

    report = gate.audit_dir(wf)
    assert report["workflows_audited"] == 1  # the .yaml WAS audited
    assert report["status"] == "FLAGGED"
    (w,) = report["workflows"]
    assert w["uses_pull_request_target"] is True
    assert w["checks_out_pr_head"] is True
    codes = {f["code"] for f in w["flags"] if f["level"] == gate.FATAL}
    assert "UNSAFE_PRT_CHECKOUT" in codes


def test_ds06_benign_yaml_extension_audited_and_passes(tmp_path: Path) -> None:
    wf = tmp_path / "wf"
    _write(wf, "benign.yaml", _BENIGN_YAML)
    rc = gate.main(["--workflows", str(wf), "--quiet"])
    assert rc == gate.EXIT_OK

    report = gate.audit_dir(wf)
    assert report["workflows_audited"] == 1  # non-vacuous: .yaml was audited
    assert report["status"] == "PASS"


# --------------------------------------------------------------------------- #
# DS-07 [HIGH]: a job self-granting `permissions: write-all` (the STRING form,
# which `_write_scopes` reduces to {}) under a least-privilege top-level block.
# Previously PASS (fatal_count 0) — the job silently held every write scope.
# Malicious job-level write-all MUST be FLAGGED WRITE_ALL_DEFAULT; a benign twin
# that grants the job `permissions: read-all` (read-only) must still PASS.
# --------------------------------------------------------------------------- #
_JOB_WRITE_ALL = """\
name: Job Write All
on: [push]
permissions:
  contents: read
jobs:
  build:
    runs-on: ubuntu-latest
    permissions: write-all
    steps:
      - run: echo hi
"""

_JOB_READ_ALL = """\
name: Job Read All
on: [push]
permissions:
  contents: read
jobs:
  build:
    runs-on: ubuntu-latest
    permissions: read-all
    steps:
      - run: echo hi
"""


def test_ds07_job_level_write_all_flagged(tmp_path: Path) -> None:
    wf = tmp_path / "wf"
    _write(wf, "job_write_all.yml", _JOB_WRITE_ALL)
    rc = gate.main(["--workflows", str(wf), "--quiet"])
    assert rc == gate.EXIT_FLAGGED

    report = gate.audit_dir(wf)
    (w,) = report["workflows"]
    assert w["fatal_count"] >= 1
    codes = {f["code"] for f in w["flags"] if f["level"] == gate.FATAL}
    assert "WRITE_ALL_DEFAULT" in codes


def test_ds07_job_level_read_all_not_flagged(tmp_path: Path) -> None:
    wf = tmp_path / "wf"
    _write(wf, "job_read_all.yml", _JOB_READ_ALL)
    rc = gate.main(["--workflows", str(wf), "--quiet"])
    assert rc == gate.EXIT_OK

    report = gate.audit_dir(wf)
    (w,) = report["workflows"]
    codes = {f["code"] for f in w["flags"] if f["level"] == gate.FATAL}
    assert "WRITE_ALL_DEFAULT" not in codes
    assert w["status"] == "PASS"


# --------------------------------------------------------------------------- #
# DS-08 [MED]: PR-head checkout reached WITHOUT a checkout `with.ref` literal.
# (a) a run-step `git fetch origin refs/pull/N/head && git checkout FETCH_HEAD`;
# (b) env indirection: env.PRREF = PR head, then `ref: ${{ env.PRREF }}`.
# Both previously PASS (checks_out_pr_head:False) on a pull_request_target +
# secrets workflow. Both MUST now FLAG UNSAFE_PRT_CHECKOUT; benign twins that
# fetch a normal branch / hold a safe ref in env must still PASS.
# --------------------------------------------------------------------------- #
_PWN_RUN_FETCH = """\
name: Pwn Run Fetch
on:
  pull_request_target:
    branches: [main]
permissions:
  contents: read
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@0000000000000000000000000000000000000000
      - name: Manually fetch and run the untrusted PR head
        env:
          NPM_TOKEN: ${{ secrets.NPM_TOKEN }}
        run: |
          git fetch origin refs/pull/${{ github.event.number }}/head
          git checkout FETCH_HEAD
          ./ci/build.sh
"""

_PWN_ENV_INDIRECT = """\
name: Pwn Env Indirect
on:
  pull_request_target:
    branches: [main]
permissions:
  contents: read
env:
  PRREF: ${{ github.event.pull_request.head.sha }}
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@0000000000000000000000000000000000000000
        with:
          ref: ${{ env.PRREF }}
      - name: Build untrusted PR code with a secret in scope
        env:
          NPM_TOKEN: ${{ secrets.NPM_TOKEN }}
        run: ./ci/build.sh
"""

_BENIGN_RUN_FETCH = """\
name: Benign Run Fetch
on:
  pull_request_target:
    branches: [main]
permissions:
  contents: read
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@0000000000000000000000000000000000000000
      - name: Fetch the base branch only (no PR head)
        run: |
          git fetch origin main
          git log --oneline -1
"""

_BENIGN_ENV_INDIRECT = """\
name: Benign Env Indirect
on:
  pull_request_target:
    branches: [main]
permissions:
  contents: read
env:
  SAFEREF: main
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@0000000000000000000000000000000000000000
        with:
          ref: ${{ env.SAFEREF }}
      - run: echo "operate on base ref only"
"""


def test_ds08_run_step_fetch_pr_head_flagged(tmp_path: Path) -> None:
    wf = tmp_path / "wf"
    _write(wf, "run_fetch.yml", _PWN_RUN_FETCH)
    rc = gate.main(["--workflows", str(wf), "--quiet"])
    assert rc == gate.EXIT_FLAGGED

    report = gate.audit_dir(wf)
    (w,) = report["workflows"]
    assert w["uses_pull_request_target"] is True
    assert w["checks_out_pr_head"] is True
    codes = {f["code"] for f in w["flags"] if f["level"] == gate.FATAL}
    assert "UNSAFE_PRT_CHECKOUT" in codes


def test_ds08_env_indirection_pr_head_flagged(tmp_path: Path) -> None:
    wf = tmp_path / "wf"
    _write(wf, "env_indirect.yml", _PWN_ENV_INDIRECT)
    rc = gate.main(["--workflows", str(wf), "--quiet"])
    assert rc == gate.EXIT_FLAGGED

    report = gate.audit_dir(wf)
    (w,) = report["workflows"]
    assert w["uses_pull_request_target"] is True
    assert w["checks_out_pr_head"] is True
    codes = {f["code"] for f in w["flags"] if f["level"] == gate.FATAL}
    assert "UNSAFE_PRT_CHECKOUT" in codes


def test_ds08_benign_base_branch_fetch_not_flagged(tmp_path: Path) -> None:
    wf = tmp_path / "wf"
    _write(wf, "benign_fetch.yml", _BENIGN_RUN_FETCH)
    report = gate.audit_dir(wf)
    (w,) = report["workflows"]
    assert w["uses_pull_request_target"] is True
    assert w["checks_out_pr_head"] is False
    codes = {f["code"] for f in w["flags"] if f["level"] == gate.FATAL}
    assert "UNSAFE_PRT_CHECKOUT" not in codes
    assert w["status"] == "PASS"


def test_ds08_benign_env_safe_ref_not_flagged(tmp_path: Path) -> None:
    wf = tmp_path / "wf"
    _write(wf, "benign_env.yml", _BENIGN_ENV_INDIRECT)
    report = gate.audit_dir(wf)
    (w,) = report["workflows"]
    assert w["uses_pull_request_target"] is True
    assert w["checks_out_pr_head"] is False
    codes = {f["code"] for f in w["flags"] if f["level"] == gate.FATAL}
    assert "UNSAFE_PRT_CHECKOUT" not in codes
    assert w["status"] == "PASS"


# --------------------------------------------------------------------------- #
# Report writing.
# --------------------------------------------------------------------------- #
def test_report_written_to_disk(tmp_path: Path) -> None:
    out = tmp_path / "sub" / "report.json"
    gate.main(["--workflows", str(REAL_WORKFLOWS), "--report", str(out), "--quiet"])
    assert out.exists()
    import json

    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["task"] == "SEC-011"
    assert payload["status"] == "PASS"
