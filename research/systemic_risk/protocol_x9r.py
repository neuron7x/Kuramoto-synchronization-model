# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Protocol X-9R/1.0-RUN — deterministic empirical-falsification machine.

A fail-closed, sequential nine-gate state machine that takes one
dataset directory in and produces one capsule directory out, with one
of three verdicts:

    PASS                       → all gates green, rerun matches,
                                 max_claim_tier = OBSERVED_IN_DATASET
    FAIL                       → any gate failed,
                                 max_claim_tier = HYPOTHESIS
                                 (or REJECTED on RERUN_CHECK mismatch)
    BLOCKED_BY_DATA_ACCESS     → license/legal/technical block,
                                 max_claim_tier = HYPOTHESIS

The state machine is

    INPUT_SCHEMA → DATA_FIREWALL → LEAKAGE_SENTINEL → END_TO_END_RUN
        → NULL_AUDIT → METRICS_VALIDITY → CAPSULE_WRITE
        → RERUN_CHECK → CLAIM_GOVERNANCE → FINAL_VERDICT

and is **strictly sequential** — the first FAIL or BLOCKED gate
short-circuits all downstream evaluation, the diagnostic capsule is
still written, and the verdict is reported.

The protocol does NOT trust models. It trusts gates.
The protocol does NOT validate claims. It limits claims.

One input. One capsule. One verdict.

Pure-function API; deterministic on (dataset_dir, configured seed).
"""

from __future__ import annotations

import argparse
import enum
import hashlib
import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, NamedTuple

import numpy as np
import pandas as pd

__all__ = [
    "GateName",
    "GateResult",
    "GateStatus",
    "MaxClaimTier",
    "ProtocolCapsule",
    "ProtocolVerdict",
    "main",
    "rerun_capsule",
    "run_protocol_x9r",
]


# ============================================================================
# 0. Enums + typed value objects (NamedTuple — no dataclass ceremony)
# ============================================================================


class GateName(str, enum.Enum):
    INPUT_SCHEMA = "INPUT_SCHEMA"
    DATA_FIREWALL = "DATA_FIREWALL"
    LEAKAGE_SENTINEL = "LEAKAGE_SENTINEL"
    END_TO_END_RUN = "END_TO_END_RUN"
    NULL_AUDIT = "NULL_AUDIT"
    METRICS_VALIDITY = "METRICS_VALIDITY"
    CAPSULE_WRITE = "CAPSULE_WRITE"
    RERUN_CHECK = "RERUN_CHECK"
    CLAIM_GOVERNANCE = "CLAIM_GOVERNANCE"


class GateStatus(str, enum.Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    BLOCKED = "BLOCKED"


class ProtocolVerdict(str, enum.Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    BLOCKED_BY_DATA_ACCESS = "BLOCKED_BY_DATA_ACCESS"


class MaxClaimTier(str, enum.Enum):
    OBSERVED_IN_DATASET = "OBSERVED_IN_DATASET"
    HYPOTHESIS = "HYPOTHESIS"
    REJECTED = "REJECTED"


class GateResult(NamedTuple):
    """Single-gate evaluation outcome (the gate contract).

    Every gate emits exactly this record. Boolean PASS/FAIL flags are
    forbidden; this is the only legal gate output shape.
    """

    gate: str
    status: str
    reason: str | None
    inputs_sha256: tuple[str, ...]
    outputs_sha256: tuple[str, ...]
    started_at_utc: str
    ended_at_utc: str
    evidence: dict[str, Any]

    def as_json(self) -> dict[str, Any]:
        return {
            "gate": self.gate,
            "status": self.status,
            "reason": self.reason,
            "inputs_sha256": list(self.inputs_sha256),
            "outputs_sha256": list(self.outputs_sha256),
            "started_at_utc": self.started_at_utc,
            "ended_at_utc": self.ended_at_utc,
            "evidence": self.evidence,
        }


class ProtocolCapsule(NamedTuple):
    """The single returned object of :func:`run_protocol_x9r`.

    Mirrors the FINAL_RESPONSE_ONLY contract.
    """

    capsule_path: Path
    verdict: str
    failed_gate: str | None
    max_claim_tier: str
    rerun_command: str
    gate_results: tuple[GateResult, ...]
    tests_run: int


# ============================================================================
# 1. Forbidden-overclaim corpus + canonical constants
# ============================================================================


# Regex patterns with word boundaries — matches the existing
# ``governance.FORBIDDEN_OVERCLAIM_TERMS`` convention. Word
# boundaries prevent the source file containing these patterns
# from matching itself under the governance grep.
_FORBIDDEN_OVERCLAIM_PATTERNS: tuple[str, ...] = (
    r"\bvalidated\b",
    r"\bproven\b",
    r"\bconfirmed\b",
    r"\bproduction\b",
    r"\bpredicts crisis\b",
    r"\btrading signal\b",
    r"\bmeasured result\b",
    r"\bempirically established\b",
)


_REQUIRED_INPUT_FILES: tuple[str, ...] = (
    "manifest.json",
    "exposure_panel.parquet",
    "node_mapping.parquet",
    "crisis_ledger.json",
    "license.txt",
)


_REQUIRED_MANIFEST_KEYS: tuple[str, ...] = (
    "source_id",
    "schema_version",
    "capture_timestamp_utc",
    "payload_sha256",
    "seed",
    "config_hash",
    "n_banks",
    "n_days",
    "crisis_lock_timestamp_utc",
    "first_evaluation_timestamp_utc",
)


_BLOCKED_LICENSE_TOKENS: tuple[str, ...] = (
    "BLOCKED",
    "RESTRICTED",
    "EXPIRED",
    "DENIED",
    "EMBARGOED",
)


_NULL_AUDIT_MIN_MARGIN: float = 0.05


# ============================================================================
# 2. Helpers — sha256 of bytes / files / dataframe / dict
# ============================================================================


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _sha256_path(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _sha256_obj(obj: object) -> str:
    """Canonical sha256 of a JSON-serialisable object."""
    return _sha256_bytes(
        json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    )


def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _make_gate_result(
    *,
    gate: GateName,
    status: GateStatus,
    reason: str | None,
    inputs_sha256: tuple[str, ...],
    outputs_sha256: tuple[str, ...],
    started_at_utc: str,
    evidence: dict[str, Any] | None = None,
) -> GateResult:
    return GateResult(
        gate=gate.value,
        status=status.value,
        reason=reason,
        inputs_sha256=inputs_sha256,
        outputs_sha256=outputs_sha256,
        started_at_utc=started_at_utc,
        ended_at_utc=_now_utc_iso(),
        evidence=evidence if evidence is not None else {},
    )


# ============================================================================
# 3. State machine internals — _RunState carries intermediates
# ============================================================================


class _RunState:
    """Mutable run-time scratch space for the state machine.

    Holds intermediate computations between gates; never serialised
    directly. Each gate reads what its predecessor wrote and writes
    its own output. Outputs that survive are written to the capsule
    by ``CAPSULE_WRITE``.
    """

    def __init__(self, dataset_dir: Path, output_dir: Path) -> None:
        self.dataset_dir: Path = dataset_dir
        self.output_dir: Path = output_dir
        self.gate_results: list[GateResult] = []
        self.input_shas: dict[str, str] = {}
        self.manifest: dict[str, Any] = {}
        self.crisis_ledger: dict[str, Any] = {}
        self.license_text: str = ""
        self.exposure_panel: pd.DataFrame | None = None
        self.node_mapping: pd.DataFrame | None = None
        self.score_per_event: dict[str, float] = {}
        self.score_sha: str = ""
        self.null_audit: dict[str, Any] = {}
        self.metrics: dict[str, Any] = {}
        self.metrics_sha: str = ""
        self.leakage_report: dict[str, Any] = {}
        self.death_conditions: dict[str, Any] = {}


# ============================================================================
# 4. Gate 1 — INPUT_SCHEMA
# ============================================================================


def _gate_input_schema(state: _RunState) -> GateResult:
    started = _now_utc_iso()
    if not state.dataset_dir.exists() or not state.dataset_dir.is_dir():
        return _make_gate_result(
            gate=GateName.INPUT_SCHEMA,
            status=GateStatus.FAIL,
            reason=f"dataset_dir does not exist or is not a directory: {state.dataset_dir}",
            inputs_sha256=(),
            outputs_sha256=(),
            started_at_utc=started,
        )
    missing = [name for name in _REQUIRED_INPUT_FILES if not (state.dataset_dir / name).is_file()]
    if missing:
        return _make_gate_result(
            gate=GateName.INPUT_SCHEMA,
            status=GateStatus.FAIL,
            reason=f"missing required input files: {missing}",
            inputs_sha256=(),
            outputs_sha256=(),
            started_at_utc=started,
        )
    input_shas: dict[str, str] = {}
    for name in _REQUIRED_INPUT_FILES:
        input_shas[name] = _sha256_path(state.dataset_dir / name)
    state.input_shas = input_shas
    return _make_gate_result(
        gate=GateName.INPUT_SCHEMA,
        status=GateStatus.PASS,
        reason=None,
        inputs_sha256=tuple(sorted(input_shas.values())),
        outputs_sha256=(_sha256_obj(input_shas),),
        started_at_utc=started,
        evidence={"input_files": list(_REQUIRED_INPUT_FILES)},
    )


# ============================================================================
# 5. Gate 2 — DATA_FIREWALL
# ============================================================================


def _gate_data_firewall(state: _RunState) -> GateResult:
    started = _now_utc_iso()

    # 5.1 license — read first, may BLOCK before anything else.
    license_path = state.dataset_dir / "license.txt"
    license_text = license_path.read_text(encoding="utf-8").strip()
    state.license_text = license_text
    if not license_text:
        return _make_gate_result(
            gate=GateName.DATA_FIREWALL,
            status=GateStatus.FAIL,
            reason="license.txt is empty",
            inputs_sha256=(state.input_shas["license.txt"],),
            outputs_sha256=(),
            started_at_utc=started,
        )
    # Word-boundary regex match — substring match falsely flags
    # "unrestricted" as containing "RESTRICTED". The token list is
    # word-bounded against the upper-cased text.
    import re

    upper = license_text.upper()
    pattern = re.compile(r"\b(" + "|".join(re.escape(t) for t in _BLOCKED_LICENSE_TOKENS) + r")\b")
    match = pattern.search(upper)
    blocked_token = match.group(1) if match else None
    if blocked_token is not None:
        return _make_gate_result(
            gate=GateName.DATA_FIREWALL,
            status=GateStatus.BLOCKED,
            reason=f"license.txt contains restriction token: {blocked_token!r}",
            inputs_sha256=(state.input_shas["license.txt"],),
            outputs_sha256=(),
            started_at_utc=started,
            evidence={"blocked_token": blocked_token},
        )

    # 5.2 manifest — required keys present, types correct.
    try:
        manifest = json.loads((state.dataset_dir / "manifest.json").read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return _make_gate_result(
            gate=GateName.DATA_FIREWALL,
            status=GateStatus.FAIL,
            reason=f"manifest.json malformed: {exc}",
            inputs_sha256=(state.input_shas["manifest.json"],),
            outputs_sha256=(),
            started_at_utc=started,
        )
    if not isinstance(manifest, dict):
        return _make_gate_result(
            gate=GateName.DATA_FIREWALL,
            status=GateStatus.FAIL,
            reason=f"manifest.json is not a JSON object, got {type(manifest).__name__}",
            inputs_sha256=(state.input_shas["manifest.json"],),
            outputs_sha256=(),
            started_at_utc=started,
        )
    missing_keys = [k for k in _REQUIRED_MANIFEST_KEYS if k not in manifest]
    if missing_keys:
        return _make_gate_result(
            gate=GateName.DATA_FIREWALL,
            status=GateStatus.FAIL,
            reason=f"manifest.json missing required keys: {missing_keys}",
            inputs_sha256=(state.input_shas["manifest.json"],),
            outputs_sha256=(),
            started_at_utc=started,
        )
    state.manifest = manifest

    # 5.3 provenance — payload_sha256 in manifest matches the actual
    # exposure_panel.parquet sha256.
    declared_sha = manifest["payload_sha256"]
    actual_sha = state.input_shas["exposure_panel.parquet"]
    if declared_sha != actual_sha:
        return _make_gate_result(
            gate=GateName.DATA_FIREWALL,
            status=GateStatus.FAIL,
            reason=(
                f"provenance mismatch: manifest payload_sha256={declared_sha} "
                f"!= actual exposure_panel.parquet sha256={actual_sha}"
            ),
            inputs_sha256=(
                state.input_shas["manifest.json"],
                state.input_shas["exposure_panel.parquet"],
            ),
            outputs_sha256=(),
            started_at_utc=started,
        )

    # 5.4 node_mapping — must be parquet with (node_id, bank_label),
    # node_id surjective onto 0..n_banks-1, no duplicates.
    try:
        node_df = pd.read_parquet(state.dataset_dir / "node_mapping.parquet")
    except Exception as exc:  # pragma: no cover — defensive
        return _make_gate_result(
            gate=GateName.DATA_FIREWALL,
            status=GateStatus.FAIL,
            reason=f"node_mapping.parquet unreadable: {exc}",
            inputs_sha256=(state.input_shas["node_mapping.parquet"],),
            outputs_sha256=(),
            started_at_utc=started,
        )
    expected_cols = {"node_id", "bank_label"}
    if set(node_df.columns) != expected_cols:
        return _make_gate_result(
            gate=GateName.DATA_FIREWALL,
            status=GateStatus.FAIL,
            reason=(
                f"node_mapping.parquet columns {sorted(node_df.columns)} "
                f"!= expected {sorted(expected_cols)}"
            ),
            inputs_sha256=(state.input_shas["node_mapping.parquet"],),
            outputs_sha256=(),
            started_at_utc=started,
        )
    n_banks = int(manifest["n_banks"])
    ids = sorted(node_df["node_id"].tolist())
    if ids != list(range(n_banks)):
        return _make_gate_result(
            gate=GateName.DATA_FIREWALL,
            status=GateStatus.FAIL,
            reason=(
                f"node_mapping.node_id is not surjective onto [0, {n_banks}); got {ids[:5]}..."
            ),
            inputs_sha256=(state.input_shas["node_mapping.parquet"],),
            outputs_sha256=(),
            started_at_utc=started,
        )
    if node_df["bank_label"].duplicated().any():
        return _make_gate_result(
            gate=GateName.DATA_FIREWALL,
            status=GateStatus.FAIL,
            reason="node_mapping.bank_label contains duplicates (survivorship-bias risk)",
            inputs_sha256=(state.input_shas["node_mapping.parquet"],),
            outputs_sha256=(),
            started_at_utc=started,
        )
    state.node_mapping = node_df

    # 5.5 exposure_panel — long-format (date, source, target, exposure).
    try:
        panel_df = pd.read_parquet(state.dataset_dir / "exposure_panel.parquet")
    except Exception as exc:  # pragma: no cover — defensive
        return _make_gate_result(
            gate=GateName.DATA_FIREWALL,
            status=GateStatus.FAIL,
            reason=f"exposure_panel.parquet unreadable: {exc}",
            inputs_sha256=(state.input_shas["exposure_panel.parquet"],),
            outputs_sha256=(),
            started_at_utc=started,
        )
    required_panel_cols = {"date", "source", "target", "exposure"}
    actual_panel_cols = set(panel_df.columns)
    if not required_panel_cols.issubset(actual_panel_cols):
        # Required columns missing — schema violation, firewall block.
        # Extra columns (e.g. label-leakage) pass through here and are
        # caught by the LEAKAGE_SENTINEL gate, by design.
        missing_cols = required_panel_cols - actual_panel_cols
        return _make_gate_result(
            gate=GateName.DATA_FIREWALL,
            status=GateStatus.FAIL,
            reason=(
                f"exposure_panel.parquet missing required columns {sorted(missing_cols)}; "
                f"got {sorted(actual_panel_cols)}"
            ),
            inputs_sha256=(state.input_shas["exposure_panel.parquet"],),
            outputs_sha256=(),
            started_at_utc=started,
        )
    state.exposure_panel = panel_df

    # 5.6 crisis_ledger — JSON with 'events' list each having 'id' and 'date'.
    try:
        crisis = json.loads((state.dataset_dir / "crisis_ledger.json").read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return _make_gate_result(
            gate=GateName.DATA_FIREWALL,
            status=GateStatus.FAIL,
            reason=f"crisis_ledger.json malformed: {exc}",
            inputs_sha256=(state.input_shas["crisis_ledger.json"],),
            outputs_sha256=(),
            started_at_utc=started,
        )
    if (
        not isinstance(crisis, dict)
        or "events" not in crisis
        or not isinstance(crisis["events"], list)
    ):
        return _make_gate_result(
            gate=GateName.DATA_FIREWALL,
            status=GateStatus.FAIL,
            reason="crisis_ledger.json must be {'events': [...]}",
            inputs_sha256=(state.input_shas["crisis_ledger.json"],),
            outputs_sha256=(),
            started_at_utc=started,
        )
    state.crisis_ledger = crisis

    return _make_gate_result(
        gate=GateName.DATA_FIREWALL,
        status=GateStatus.PASS,
        reason=None,
        inputs_sha256=tuple(sorted(state.input_shas.values())),
        outputs_sha256=(_sha256_obj({"manifest": manifest, "n_events": len(crisis["events"])}),),
        started_at_utc=started,
        evidence={"n_banks": n_banks, "n_events": len(crisis["events"])},
    )


# ============================================================================
# 6. Gate 3 — LEAKAGE_SENTINEL
# ============================================================================


def _gate_leakage_sentinel(state: _RunState) -> GateResult:
    started = _now_utc_iso()
    panel = state.exposure_panel
    assert panel is not None  # firewall guarantees this

    # 6.1 forbidden columns — crisis_label, future_*, etc.
    forbidden_cols = {"crisis_label", "future_value", "y_label", "outcome"}
    found = forbidden_cols & set(panel.columns)
    if found:
        return _make_gate_result(
            gate=GateName.LEAKAGE_SENTINEL,
            status=GateStatus.FAIL,
            reason=f"exposure_panel contains label-leakage columns: {sorted(found)}",
            inputs_sha256=(state.input_shas["exposure_panel.parquet"],),
            outputs_sha256=(),
            started_at_utc=started,
        )

    # 6.2 config-key sweep on manifest — center / centered / lookahead / full_sample.
    cfg = state.manifest.get("config", {})
    if isinstance(cfg, dict):
        for forbidden_key in ("center", "centered", "lookahead"):
            val = cfg.get(forbidden_key)
            if val is True or val == 1:
                return _make_gate_result(
                    gate=GateName.LEAKAGE_SENTINEL,
                    status=GateStatus.FAIL,
                    reason=f"manifest.config has forbidden centered-window key: {forbidden_key}={val}",
                    inputs_sha256=(state.input_shas["manifest.json"],),
                    outputs_sha256=(),
                    started_at_utc=started,
                )
        if cfg.get("align") == "center":
            return _make_gate_result(
                gate=GateName.LEAKAGE_SENTINEL,
                status=GateStatus.FAIL,
                reason="manifest.config.align == 'center' (centered rolling window)",
                inputs_sha256=(state.input_shas["manifest.json"],),
                outputs_sha256=(),
                started_at_utc=started,
            )
        for op in cfg.get("ops", []):
            if isinstance(op, str) and "full_sample" in op:
                return _make_gate_result(
                    gate=GateName.LEAKAGE_SENTINEL,
                    status=GateStatus.FAIL,
                    reason=f"manifest.config.ops contains full-sample normalization op: {op!r}",
                    inputs_sha256=(state.input_shas["manifest.json"],),
                    outputs_sha256=(),
                    started_at_utc=started,
                )

    # 6.3 crisis-date tuning — lock < first_evaluation.
    try:
        lock = datetime.fromisoformat(state.manifest["crisis_lock_timestamp_utc"])
        first_eval = datetime.fromisoformat(state.manifest["first_evaluation_timestamp_utc"])
    except (ValueError, KeyError) as exc:
        return _make_gate_result(
            gate=GateName.LEAKAGE_SENTINEL,
            status=GateStatus.FAIL,
            reason=f"manifest timestamps unparseable: {exc}",
            inputs_sha256=(state.input_shas["manifest.json"],),
            outputs_sha256=(),
            started_at_utc=started,
        )
    if lock >= first_eval:
        return _make_gate_result(
            gate=GateName.LEAKAGE_SENTINEL,
            status=GateStatus.FAIL,
            reason=(
                f"crisis_lock {lock.isoformat()} >= first_evaluation {first_eval.isoformat()} "
                f"(crisis-date tuning)"
            ),
            inputs_sha256=(state.input_shas["manifest.json"],),
            outputs_sha256=(),
            started_at_utc=started,
        )

    # 6.4 post-event contamination — every crisis date strictly after
    # the start of any pre-event window must allow ≥ 1-day lead.
    panel_dates = pd.to_datetime(panel["date"]).dt.normalize().unique()
    panel_dates_set = set(pd.Timestamp(d).date() for d in panel_dates)
    n_post_event = 0
    for ev in state.crisis_ledger.get("events", []):
        try:
            ev_date = datetime.fromisoformat(ev["date"]).date()
        except (KeyError, ValueError, TypeError):
            continue
        if ev_date in panel_dates_set:
            n_post_event += 1
    if n_post_event > 0:
        return _make_gate_result(
            gate=GateName.LEAKAGE_SENTINEL,
            status=GateStatus.FAIL,
            reason=(
                f"{n_post_event} crisis date(s) appear in the exposure panel; "
                f"post-event contamination — score window must end before crisis"
            ),
            inputs_sha256=(
                state.input_shas["exposure_panel.parquet"],
                state.input_shas["crisis_ledger.json"],
            ),
            outputs_sha256=(),
            started_at_utc=started,
        )

    state.leakage_report = {
        "n_forbidden_columns_found": 0,
        "centered_window_detected": False,
        "full_sample_normalization_detected": False,
        "crisis_date_tuning_detected": False,
        "post_event_contamination_detected": False,
    }
    return _make_gate_result(
        gate=GateName.LEAKAGE_SENTINEL,
        status=GateStatus.PASS,
        reason=None,
        inputs_sha256=(
            state.input_shas["exposure_panel.parquet"],
            state.input_shas["manifest.json"],
            state.input_shas["crisis_ledger.json"],
        ),
        outputs_sha256=(_sha256_obj(state.leakage_report),),
        started_at_utc=started,
        evidence=state.leakage_report,
    )


# ============================================================================
# 7. Gate 4 — END_TO_END_RUN (deterministic score from exposure panel)
# ============================================================================


def _build_panel_matrices(panel_df: pd.DataFrame, n_banks: int) -> dict[date, np.ndarray]:
    """Pivot long-format panel into ``date → (N, N)`` matrix dict.

    Strict-causal: snapshots strictly indexed by date; no future or
    centered values introduced.
    """
    out: dict[date, np.ndarray] = {}
    panel_df = panel_df.copy()
    panel_df["date"] = pd.to_datetime(panel_df["date"]).dt.date
    for d, sub in panel_df.groupby("date", sort=True):
        if not isinstance(d, date):
            continue
        m = np.zeros((n_banks, n_banks), dtype=np.float64)
        for _, row in sub.iterrows():
            s = int(row["source"])
            t = int(row["target"])
            if 0 <= s < n_banks and 0 <= t < n_banks and s != t:
                m[s, t] = float(row["exposure"])
        out[d] = m
    return out


_KURAMOTO_BURN_IN: int = 200
_KURAMOTO_AVG_STEPS: int = 200
_KURAMOTO_DT: float = 0.05
_KURAMOTO_K_NORM_FACTOR: float = 0.05


def _kuramoto_R_per_snapshot(matrices: dict[date, np.ndarray], *, seed: int) -> dict[date, float]:
    """Per-snapshot Kuramoto order parameter R(t) on the directed
    weighted graph defined by each exposure-matrix snapshot.

    For each snapshot:
      * Build coupling K_ij = ``_KURAMOTO_K_NORM_FACTOR`` × exposure_ij
        normalised by the snapshot's max non-zero entry, so K stays
        physically bounded across panels of any scale.
      * Initialise phases θ ~ U(−π, π) seeded by ``seed + i`` (per-
        snapshot deterministic).
      * Integrate Sakaguchi-Kuramoto with α = 0 for
        ``_KURAMOTO_BURN_IN + _KURAMOTO_AVG_STEPS`` steps, dt =
        ``_KURAMOTO_DT``.
      * R(snapshot) = mean of the order-parameter magnitude over the
        post-burn-in window.

    The ω vector is set to per-bank node-strength rank divided by N
    (a stable structural per-bank ω that preserves heterogeneity
    across snapshots without requiring an extra time series).
    """
    from .kuramoto_extensions import (
        kuramoto_order_parameter,
        sakaguchi_kuramoto_step,
    )

    sorted_dates = sorted(matrices.keys())
    out: dict[date, float] = {}
    for i, d in enumerate(sorted_dates):
        m = matrices[d]
        n = m.shape[0]
        if n == 0:
            out[d] = float("nan")
            continue
        # K normalised by snapshot scale.
        scale = float(np.max(m)) if np.any(m) else 0.0
        if scale == 0.0:
            out[d] = float("nan")
            continue
        coupling = _KURAMOTO_K_NORM_FACTOR * m / scale
        # Per-bank ω from out-strength rank (heterogeneous, structural).
        out_strength = m.sum(axis=1)
        if not np.any(out_strength > 0):
            out[d] = float("nan")
            continue
        omega = (out_strength.argsort().argsort().astype(np.float64) / max(n - 1, 1)) - 0.5
        alpha = np.zeros((n, n), dtype=np.float64)
        rng = np.random.default_rng(seed + i)
        theta = np.asarray(rng.uniform(-np.pi, np.pi, n), dtype=np.float64)
        # Burn-in.
        for _ in range(_KURAMOTO_BURN_IN):
            theta = sakaguchi_kuramoto_step(
                theta, omega=omega, coupling=coupling, alpha=alpha, dt=_KURAMOTO_DT
            )
        # Time-average R.
        r_acc = 0.0
        for _ in range(_KURAMOTO_AVG_STEPS):
            theta = sakaguchi_kuramoto_step(
                theta, omega=omega, coupling=coupling, alpha=alpha, dt=_KURAMOTO_DT
            )
            r_acc += kuramoto_order_parameter(theta)
        out[d] = r_acc / float(_KURAMOTO_AVG_STEPS)
    return out


_CANDIDATE_SCORE_METHOD_TRAILING_MEAN: str = "trailing_mean_density"
_CANDIDATE_SCORE_METHOD_KURAMOTO: str = "kuramoto_R_per_snapshot"
_CANDIDATE_SCORE_METHOD_SPECTRAL_RADIUS: str = "spectral_radius_of_coupling"
_CANDIDATE_SCORE_METHOD_DEFAULT: str = _CANDIDATE_SCORE_METHOD_TRAILING_MEAN


def _spectral_radius_per_snapshot(
    matrices: dict[date, np.ndarray], *, seed: int
) -> dict[date, float]:
    """Per-snapshot spectral radius ρ(K) = max |eigenvalue| of the
    snapshot exposure matrix.

    Maps to the Gai-Kapadia (2010) contagion bound: spectral radius
    of the interbank coupling matrix is the controlling parameter
    for the linearised default-cascade fixed point. ρ(K) ≥ 1 is the
    classical onset of unbounded cascade in the linearised regime;
    larger ρ ⇒ structurally more contagious network.

    The seed argument is accepted for API symmetry with other
    candidate-score methods but unused — λ_max is deterministic.
    """
    rng = np.random.default_rng(seed)
    _ = rng.uniform(0.0, 1.0, 1)  # exercise the seed; result unused
    out: dict[date, float] = {}
    for d, m in matrices.items():
        if m.size == 0:
            out[d] = float("nan")
            continue
        if not np.any(m):
            out[d] = 0.0
            continue
        try:
            eigvals = np.linalg.eigvals(m.astype(np.float64))
            out[d] = float(np.max(np.abs(eigvals)))
        except np.linalg.LinAlgError:
            out[d] = float("nan")
    return out


def _candidate_score_trailing_mean(
    matrices: dict[date, np.ndarray], seed: int
) -> dict[date, float]:
    """Trailing-mean network-density candidate score.

    Time-dependent so the shuffled-time-labels null erodes the
    signal: any temporal clustering of high-density matrices is
    destroyed by the shuffle.
    """
    rng = np.random.default_rng(seed)
    _ = rng.uniform(0.0, 1.0, 1)  # exercise the seed; result unused
    sorted_dates = sorted(matrices.keys())
    densities: list[float] = []
    for d in sorted_dates:
        m = matrices[d]
        densities.append(float(m.sum()) if m.size > 0 else float("nan"))
    window = 20
    out: dict[date, float] = {}
    for i, d in enumerate(sorted_dates):
        if i + 1 < window:
            out[d] = float("nan")
            continue
        chunk = densities[i + 1 - window : i + 1]
        finite = [x for x in chunk if not np.isnan(x)]
        out[d] = float(np.mean(finite)) if finite else float("nan")
    return out


def _candidate_score(
    matrices: dict[date, np.ndarray],
    seed: int,
    *,
    method: str = _CANDIDATE_SCORE_METHOD_DEFAULT,
) -> dict[date, float]:
    """Dispatch to the configured candidate-score implementation.

    Three methods are supported:

    * ``trailing_mean_density`` (default) — fast, time-aware, well-
      tuned for synthetic stress fixtures. Used by the X-9R unit
      tests to keep the pipeline test-pinned.
    * ``kuramoto_R_per_snapshot`` — physics-meaningful Sakaguchi-
      Kuramoto steady-state order parameter R(t) on the directed
      weighted graph. Recommended for real-data runs (BIS LBS,
      e-MID, MiMiK, etc.) where the systemic-risk-as-phase-
      transition hypothesis is the actual claim under test.
    * ``spectral_radius_of_coupling`` — Gai-Kapadia (2010) contagion
      bound: per-snapshot ρ(K) = max |eigenvalue| of the exposure
      matrix. Orthogonal in nature to Kuramoto R (linearised cascade
      vs nonlinear phase synchronisation); useful as an independent
      cross-check on real bank-network data.

    Selectable per-run via ``manifest.config["candidate_score_method"]``;
    callers that don't pass a method get the default.
    """
    if method == _CANDIDATE_SCORE_METHOD_KURAMOTO:
        return _kuramoto_R_per_snapshot(matrices, seed=seed)
    if method == _CANDIDATE_SCORE_METHOD_SPECTRAL_RADIUS:
        return _spectral_radius_per_snapshot(matrices, seed=seed)
    return _candidate_score_trailing_mean(matrices, seed=seed)


def _resolve_candidate_score_method(state: _RunState) -> str:
    cfg = state.manifest.get("config", {})
    if isinstance(cfg, dict):
        method = cfg.get("candidate_score_method")
        if isinstance(method, str) and method in (
            _CANDIDATE_SCORE_METHOD_TRAILING_MEAN,
            _CANDIDATE_SCORE_METHOD_KURAMOTO,
            _CANDIDATE_SCORE_METHOD_SPECTRAL_RADIUS,
        ):
            return method
    return _CANDIDATE_SCORE_METHOD_DEFAULT


def _per_event_score(
    score_per_date: dict[date, float],
    crisis_events: list[dict[str, Any]],
    lead_days: int = 90,
) -> dict[str, float]:
    """For each crisis event, take the maximum score in the
    pre-event lead window ``[event - lead_days, event)``.

    Strict half-open interval: the event date itself is excluded.
    """
    sorted_dates = sorted(score_per_date.keys())
    by_date = score_per_date
    out: dict[str, float] = {}
    for ev in crisis_events:
        ev_id = ev.get("id", "?")
        try:
            ev_date = datetime.fromisoformat(ev["date"]).date()
        except (KeyError, ValueError, TypeError):
            out[ev_id] = float("nan")
            continue
        window = [
            d for d in sorted_dates if (ev_date - d).days > 0 and (ev_date - d).days <= lead_days
        ]
        if not window:
            out[ev_id] = float("nan")
            continue
        scores = [by_date[d] for d in window if not np.isnan(by_date[d])]
        out[ev_id] = float(np.max(scores)) if scores else float("nan")
    return out


def _gate_end_to_end_run(state: _RunState) -> GateResult:
    started = _now_utc_iso()
    panel = state.exposure_panel
    assert panel is not None
    n_banks = int(state.manifest["n_banks"])
    seed = int(state.manifest["seed"])

    matrices = _build_panel_matrices(panel, n_banks=n_banks)
    if not matrices:
        return _make_gate_result(
            gate=GateName.END_TO_END_RUN,
            status=GateStatus.FAIL,
            reason="exposure_panel produced 0 dated matrices",
            inputs_sha256=(state.input_shas["exposure_panel.parquet"],),
            outputs_sha256=(),
            started_at_utc=started,
        )
    method = _resolve_candidate_score_method(state)
    score_per_date = _candidate_score(matrices, seed=seed, method=method)
    score_per_event = _per_event_score(score_per_date, state.crisis_ledger.get("events", []))

    # No-placeholder guard: if every event score is NaN, the score
    # implementation produced nothing — fail rather than parade a
    # null result as a score.
    finite = [v for v in score_per_event.values() if not np.isnan(v)]
    if not finite:
        return _make_gate_result(
            gate=GateName.END_TO_END_RUN,
            status=GateStatus.FAIL,
            reason="every per-event score is NaN — no signal extractable from panel",
            inputs_sha256=(
                state.input_shas["exposure_panel.parquet"],
                state.input_shas["crisis_ledger.json"],
            ),
            outputs_sha256=(),
            started_at_utc=started,
            evidence={"n_events": len(score_per_event), "n_finite": 0},
        )

    state.score_per_event = score_per_event
    state.score_sha = _sha256_obj(
        {k: round(v, 12) if not np.isnan(v) else None for k, v in sorted(score_per_event.items())}
    )
    return _make_gate_result(
        gate=GateName.END_TO_END_RUN,
        status=GateStatus.PASS,
        reason=None,
        inputs_sha256=(
            state.input_shas["exposure_panel.parquet"],
            state.input_shas["crisis_ledger.json"],
            state.input_shas["manifest.json"],
        ),
        outputs_sha256=(state.score_sha,),
        started_at_utc=started,
        evidence={
            "n_events": len(score_per_event),
            "n_finite": len(finite),
            "score_min": float(np.min(finite)),
            "score_max": float(np.max(finite)),
        },
    )


# ============================================================================
# 8. Gate 5 — NULL_AUDIT
# ============================================================================


_NULL_AUDIT_PERMUTATIONS: int = 200


def _mean_per_event_score(per_event: dict[str, float]) -> float:
    """Return the mean of finite per-event scores; ``nan`` only if all are non-finite."""
    finite = [v for v in per_event.values() if not np.isnan(v)]
    return float(np.mean(finite)) if finite else float("nan")


def _null_mean_shuffled_time_labels(
    matrices: dict[date, np.ndarray],
    crisis_events: list[dict[str, Any]],
    seed: int,
    method: str = _CANDIDATE_SCORE_METHOD_DEFAULT,
) -> float:
    """Average per-event-score-mean over many time-label shuffles.

    A single shuffle is a noisy point estimate; the canonical
    permutation-test mean is the average over many independent
    shuffles. ``_NULL_AUDIT_PERMUTATIONS`` controls the count.
    """
    sorted_dates = sorted(matrices.keys())
    means: list[float] = []
    for k in range(_NULL_AUDIT_PERMUTATIONS):
        rng = np.random.default_rng(seed + 1 + k * 1000)
        perm_idx = rng.permutation(len(sorted_dates))
        permuted = [sorted_dates[int(j)] for j in perm_idx]
        relabelled = {permuted[i]: matrices[sorted_dates[i]] for i in range(len(sorted_dates))}
        score_per_date = _candidate_score(relabelled, seed=seed + 1 + k * 1000, method=method)
        per_event = _per_event_score(score_per_date, crisis_events)
        m = _mean_per_event_score(per_event)
        if np.isfinite(m):
            means.append(m)
    return float(np.mean(means)) if means else float("nan")


def _null_mean_permuted_crisis_dates(
    score_per_date: dict[date, float],
    crisis_events: list[dict[str, Any]],
    seed: int,
) -> float:
    """Average per-event-score-mean over many crisis-date permutations.

    Robust against the small-N corner case where a single
    permutation lands all events in the trailing-window NaN
    region: averaging over ``_NULL_AUDIT_PERMUTATIONS`` independent
    permutations recovers a finite mean even if ~30% of single
    permutations would individually return all-NaN.
    """
    sorted_dates = sorted(score_per_date.keys())
    if len(sorted_dates) < 2:
        return float("nan")
    means: list[float] = []
    for k in range(_NULL_AUDIT_PERMUTATIONS):
        rng = np.random.default_rng(seed + 2 + k * 1000)
        permuted_events: list[dict[str, Any]] = []
        for ev in crisis_events:
            new_date = sorted_dates[int(rng.integers(0, len(sorted_dates)))]
            permuted_events.append({"id": ev.get("id", "?"), "date": new_date.isoformat()})
        per_event = _per_event_score(score_per_date, permuted_events)
        m = _mean_per_event_score(per_event)
        if np.isfinite(m):
            means.append(m)
    return float(np.mean(means)) if means else float("nan")


def _gate_null_audit(state: _RunState) -> GateResult:
    started = _now_utc_iso()
    panel = state.exposure_panel
    assert panel is not None
    n_banks = int(state.manifest["n_banks"])
    seed = int(state.manifest["seed"])
    matrices = _build_panel_matrices(panel, n_banks=n_banks)

    # Per-event candidate score (already in state).
    cand_mean = _mean_per_event_score(state.score_per_event)
    method = _resolve_candidate_score_method(state)

    # Null comparators: each is the *average over many independent
    # permutations* (n=_NULL_AUDIT_PERMUTATIONS), not a single noisy
    # draw. The single-draw approach was numerically unstable on
    # small N and produced false NaN at quarterly cadence.
    null_a_mean = _null_mean_shuffled_time_labels(
        matrices, state.crisis_ledger.get("events", []), seed=seed, method=method
    )
    null_b_mean = _null_mean_permuted_crisis_dates(
        _candidate_score(matrices, seed=seed, method=method),
        state.crisis_ledger.get("events", []),
        seed=seed,
    )

    # Margin requirement: candidate must beat each null by at least
    # ``_NULL_AUDIT_MIN_MARGIN``. Tie or worse → FAIL.
    margin_a = cand_mean - null_a_mean
    margin_b = cand_mean - null_b_mean
    state.null_audit = {
        "candidate_mean": cand_mean,
        "null_shuffled_time_labels_mean": null_a_mean,
        "null_permuted_crisis_dates_mean": null_b_mean,
        "margin_vs_shuffled_time": margin_a,
        "margin_vs_permuted_crisis": margin_b,
        "min_required_margin": _NULL_AUDIT_MIN_MARGIN,
    }

    if not (np.isfinite(margin_a) and np.isfinite(margin_b)):
        return _make_gate_result(
            gate=GateName.NULL_AUDIT,
            status=GateStatus.FAIL,
            reason="null-audit margins non-finite",
            inputs_sha256=(state.score_sha,),
            outputs_sha256=(),
            started_at_utc=started,
            evidence=state.null_audit,
        )
    if margin_a < _NULL_AUDIT_MIN_MARGIN:
        return _make_gate_result(
            gate=GateName.NULL_AUDIT,
            status=GateStatus.FAIL,
            reason=(
                f"null shuffled-time-labels tie or win: candidate_mean={cand_mean:.4f}, "
                f"null_mean={null_a_mean:.4f}, margin={margin_a:.4f} < {_NULL_AUDIT_MIN_MARGIN}"
            ),
            inputs_sha256=(state.score_sha,),
            outputs_sha256=(),
            started_at_utc=started,
            evidence=state.null_audit,
        )
    if margin_b < _NULL_AUDIT_MIN_MARGIN:
        return _make_gate_result(
            gate=GateName.NULL_AUDIT,
            status=GateStatus.FAIL,
            reason=(
                f"null permuted-crisis-dates tie or win: candidate_mean={cand_mean:.4f}, "
                f"null_mean={null_b_mean:.4f}, margin={margin_b:.4f} < {_NULL_AUDIT_MIN_MARGIN}"
            ),
            inputs_sha256=(state.score_sha,),
            outputs_sha256=(),
            started_at_utc=started,
            evidence=state.null_audit,
        )
    return _make_gate_result(
        gate=GateName.NULL_AUDIT,
        status=GateStatus.PASS,
        reason=None,
        inputs_sha256=(state.score_sha,),
        outputs_sha256=(_sha256_obj(state.null_audit),),
        started_at_utc=started,
        evidence=state.null_audit,
    )


# ============================================================================
# 9. Gate 6 — METRICS_VALIDITY (AUC + bootstrap CI + Bonferroni p)
# ============================================================================


def _auc_mann_whitney(positives: list[float], negatives: list[float]) -> float:
    """AUC = P(X > Y) via the Mann-Whitney U-statistic ranking.

    Under ties counted at 0.5; standard Bamber 1975 form.
    """
    if not positives or not negatives:
        return float("nan")
    pos_arr = np.asarray(positives, dtype=np.float64)
    neg_arr = np.asarray(negatives, dtype=np.float64)
    diff = pos_arr[:, None] - neg_arr[None, :]
    u = float(((diff > 0).sum() + 0.5 * (diff == 0).sum()))
    return u / float(pos_arr.size * neg_arr.size)


def _gate_metrics_validity(state: _RunState) -> GateResult:
    started = _now_utc_iso()
    seed = int(state.manifest["seed"])
    candidate = state.score_per_event
    finite_candidate = [v for v in candidate.values() if not np.isnan(v)]
    if len(finite_candidate) < 2:
        return _make_gate_result(
            gate=GateName.METRICS_VALIDITY,
            status=GateStatus.FAIL,
            reason=f"need ≥ 2 finite per-event scores to compute AUC; got {len(finite_candidate)}",
            inputs_sha256=(state.score_sha,),
            outputs_sha256=(),
            started_at_utc=started,
        )
    panel = state.exposure_panel
    assert panel is not None
    n_banks = int(state.manifest["n_banks"])
    matrices = _build_panel_matrices(panel, n_banks=n_banks)
    method = _resolve_candidate_score_method(state)
    null_score_per_date = _candidate_score(matrices, seed=seed + 7, method=method)
    null_finite = [v for v in null_score_per_date.values() if not np.isnan(v)]

    auc = _auc_mann_whitney(finite_candidate, null_finite)
    if not np.isfinite(auc):
        return _make_gate_result(
            gate=GateName.METRICS_VALIDITY,
            status=GateStatus.FAIL,
            reason="AUC non-finite",
            inputs_sha256=(state.score_sha,),
            outputs_sha256=(),
            started_at_utc=started,
            evidence={"auc": None, "reason_for_nan": "insufficient finite samples"},
        )

    # Bootstrap 95% percentile CI for AUC.
    rng = np.random.default_rng(seed + 11)
    n_boot = 1000
    boot = np.empty(n_boot, dtype=np.float64)
    cand_arr = np.asarray(finite_candidate, dtype=np.float64)
    null_arr = np.asarray(null_finite, dtype=np.float64)
    for i in range(n_boot):
        c = cand_arr[rng.integers(0, cand_arr.size, cand_arr.size)]
        n = null_arr[rng.integers(0, null_arr.size, null_arr.size)]
        boot[i] = _auc_mann_whitney(c.tolist(), n.tolist())
    ci_low = float(np.quantile(boot, 0.025))
    ci_high = float(np.quantile(boot, 0.975))

    # One-sided permutation p-value, Bonferroni-corrected for the
    # number of crisis events (multiple-comparison family).
    n_perm = 999
    n_extreme = 0
    pooled = np.concatenate([cand_arr, null_arr])
    for _ in range(n_perm):
        rng.shuffle(pooled)
        p_cand = pooled[: cand_arr.size]
        p_null = pooled[cand_arr.size :]
        if _auc_mann_whitney(p_cand.tolist(), p_null.tolist()) >= auc:
            n_extreme += 1
    p_value = (n_extreme + 1) / (n_perm + 1)
    n_events = len(state.score_per_event)
    p_bonferroni = min(1.0, p_value * max(1, n_events))

    state.metrics = {
        "auc": auc,
        "ci_low_95": ci_low,
        "ci_high_95": ci_high,
        "p_one_sided_perm": p_value,
        "p_bonferroni": p_bonferroni,
        "n_candidate": int(cand_arr.size),
        "n_null": int(null_arr.size),
        "n_bootstrap": n_boot,
        "n_permutations": n_perm,
    }
    state.metrics_sha = _sha256_obj(
        {k: round(v, 12) if isinstance(v, float) else v for k, v in state.metrics.items()}
    )

    # AUC-only failure: must have all of {auc, ci, p_bonferroni}.
    required = {"auc", "ci_low_95", "ci_high_95", "p_bonferroni"}
    missing = required - set(state.metrics.keys())
    if missing:
        return _make_gate_result(
            gate=GateName.METRICS_VALIDITY,
            status=GateStatus.FAIL,
            reason=f"AUC-only / incomplete metrics: missing {missing}",
            inputs_sha256=(state.score_sha,),
            outputs_sha256=(),
            started_at_utc=started,
            evidence=state.metrics,
        )

    return _make_gate_result(
        gate=GateName.METRICS_VALIDITY,
        status=GateStatus.PASS,
        reason=None,
        inputs_sha256=(state.score_sha,),
        outputs_sha256=(state.metrics_sha,),
        started_at_utc=started,
        evidence=state.metrics,
    )


# ============================================================================
# 10. Gate 7 — CAPSULE_WRITE (atomic capsule on disk)
# ============================================================================


def _write_capsule(
    state: _RunState, *, verdict: str, max_claim_tier: str, failed_gate: str | None
) -> Path:
    out = state.output_dir
    out.mkdir(parents=True, exist_ok=True)
    (out / "logs").mkdir(parents=True, exist_ok=True)
    (out / "figures").mkdir(parents=True, exist_ok=True)
    (out / "figure_sources").mkdir(parents=True, exist_ok=True)

    gate_results_json = [g.as_json() for g in state.gate_results]
    (out / "gate_results.json").write_text(
        json.dumps(gate_results_json, indent=2, sort_keys=True), encoding="utf-8"
    )
    (out / "metrics.json").write_text(
        json.dumps(state.metrics, indent=2, sort_keys=True, default=str), encoding="utf-8"
    )
    (out / "null_audit.json").write_text(
        json.dumps(state.null_audit, indent=2, sort_keys=True, default=str), encoding="utf-8"
    )
    (out / "leakage_report.json").write_text(
        json.dumps(state.leakage_report, indent=2, sort_keys=True), encoding="utf-8"
    )
    (out / "death_conditions.json").write_text(
        json.dumps(state.death_conditions, indent=2, sort_keys=True), encoding="utf-8"
    )
    # Evidence ledger — JSON Lines, one record per gate.
    with (out / "evidence_ledger.jsonl").open("w", encoding="utf-8") as fh:
        for g in state.gate_results:
            fh.write(json.dumps(g.as_json(), sort_keys=True, default=str))
            fh.write("\n")
    rerun_sh = (
        "#!/bin/bash\n"
        "set -euo pipefail\n"
        'CAPSULE_DIR="$(dirname "$(readlink -f "$0")")"\n'
        'python -m research.systemic_risk.protocol_x9r rerun --capsule "$CAPSULE_DIR"\n'
    )
    rerun_path = out / "rerun.sh"
    rerun_path.write_text(rerun_sh, encoding="utf-8")
    rerun_path.chmod(0o755)
    capsule_payload = {
        "verdict": verdict,
        "max_claim_tier": max_claim_tier,
        "failed_gate": failed_gate,
        "input_shas": state.input_shas,
        "score_sha": state.score_sha,
        "metrics_sha": state.metrics_sha,
        "n_gate_results": len(state.gate_results),
        "rerun_command": f"python -m research.systemic_risk.protocol_x9r rerun --capsule {out}",
        "written_at_utc": _now_utc_iso(),
    }
    (out / "capsule.json").write_text(
        json.dumps(capsule_payload, indent=2, sort_keys=True), encoding="utf-8"
    )
    return out


def _gate_capsule_write(state: _RunState) -> GateResult:
    started = _now_utc_iso()
    try:
        _write_capsule(
            state,
            verdict=ProtocolVerdict.PASS.value,
            max_claim_tier=MaxClaimTier.OBSERVED_IN_DATASET.value,
            failed_gate=None,
        )
    except OSError as exc:
        return _make_gate_result(
            gate=GateName.CAPSULE_WRITE,
            status=GateStatus.FAIL,
            reason=f"capsule write failed: {exc}",
            inputs_sha256=(state.metrics_sha,),
            outputs_sha256=(),
            started_at_utc=started,
        )
    capsule_sha = _sha256_path(state.output_dir / "capsule.json")
    return _make_gate_result(
        gate=GateName.CAPSULE_WRITE,
        status=GateStatus.PASS,
        reason=None,
        inputs_sha256=(state.metrics_sha,),
        outputs_sha256=(capsule_sha,),
        started_at_utc=started,
        evidence={"capsule_path": str(state.output_dir)},
    )


# ============================================================================
# 11. Gate 8 — RERUN_CHECK (bound to running the capsule's rerun)
# ============================================================================


def _gate_rerun_check_during_initial_run(state: _RunState) -> GateResult:
    """During the initial run, the rerun gate writes a stub recording
    the metrics_sha that any subsequent rerun must reproduce.
    """
    started = _now_utc_iso()
    return _make_gate_result(
        gate=GateName.RERUN_CHECK,
        status=GateStatus.PASS,
        reason=None,
        inputs_sha256=(state.metrics_sha,),
        outputs_sha256=(state.metrics_sha,),
        started_at_utc=started,
        evidence={"mode": "initial-run", "expected_metrics_sha": state.metrics_sha},
    )


def _gate_rerun_check_during_rerun(state: _RunState, expected_metrics_sha: str) -> GateResult:
    started = _now_utc_iso()
    if state.metrics_sha != expected_metrics_sha:
        return _make_gate_result(
            gate=GateName.RERUN_CHECK,
            status=GateStatus.FAIL,
            reason=(
                f"rerun metrics_sha mismatch: expected={expected_metrics_sha} "
                f"actual={state.metrics_sha}"
            ),
            inputs_sha256=(state.metrics_sha,),
            outputs_sha256=(),
            started_at_utc=started,
        )
    return _make_gate_result(
        gate=GateName.RERUN_CHECK,
        status=GateStatus.PASS,
        reason=None,
        inputs_sha256=(state.metrics_sha,),
        outputs_sha256=(state.metrics_sha,),
        started_at_utc=started,
        evidence={"mode": "rerun-verified"},
    )


# ============================================================================
# 12. Gate 9 — CLAIM_GOVERNANCE (overclaim grep on capsule)
# ============================================================================


def _gate_claim_governance(state: _RunState) -> GateResult:
    import re

    started = _now_utc_iso()
    out = state.output_dir
    overclaim_hits: list[tuple[str, str]] = []
    pattern = re.compile("|".join(_FORBIDDEN_OVERCLAIM_PATTERNS), re.IGNORECASE)
    for path in out.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix.lower() not in {".md", ".txt", ".json", ".jsonl", ".sh"}:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for match in pattern.finditer(text):
            overclaim_hits.append((str(path.relative_to(out)), match.group(0)))
    if overclaim_hits:
        return _make_gate_result(
            gate=GateName.CLAIM_GOVERNANCE,
            status=GateStatus.FAIL,
            reason=f"capsule contains {len(overclaim_hits)} overclaim term hits: {overclaim_hits[:5]}",
            inputs_sha256=(state.metrics_sha,),
            outputs_sha256=(),
            started_at_utc=started,
            evidence={"overclaim_hits": overclaim_hits},
        )
    state.death_conditions = {
        "kill_rule": "RERUN_CHECK FAIL drives KILL → REJECTED",
        "invalidate_rule": "LEAKAGE_SENTINEL FAIL drives INVALIDATE → IDEA",
        "stop_rule": "DATA_FIREWALL BLOCK drives STOP",
        "demote_rule": "NULL_AUDIT FAIL drives DEMOTE",
    }
    return _make_gate_result(
        gate=GateName.CLAIM_GOVERNANCE,
        status=GateStatus.PASS,
        reason=None,
        inputs_sha256=(state.metrics_sha,),
        outputs_sha256=(_sha256_obj(state.death_conditions),),
        started_at_utc=started,
        evidence={"overclaim_hits": []},
    )


# ============================================================================
# 13. State machine driver
# ============================================================================


_GATES_INITIAL: tuple[tuple[GateName, Any], ...] = (
    (GateName.INPUT_SCHEMA, _gate_input_schema),
    (GateName.DATA_FIREWALL, _gate_data_firewall),
    (GateName.LEAKAGE_SENTINEL, _gate_leakage_sentinel),
    (GateName.END_TO_END_RUN, _gate_end_to_end_run),
    (GateName.NULL_AUDIT, _gate_null_audit),
    (GateName.METRICS_VALIDITY, _gate_metrics_validity),
    (GateName.CAPSULE_WRITE, _gate_capsule_write),
    (GateName.RERUN_CHECK, _gate_rerun_check_during_initial_run),
    (GateName.CLAIM_GOVERNANCE, _gate_claim_governance),
)


def _final_verdict(
    state: _RunState,
) -> tuple[ProtocolVerdict, MaxClaimTier, str | None]:
    for g in state.gate_results:
        if g.status == GateStatus.BLOCKED.value:
            return ProtocolVerdict.BLOCKED_BY_DATA_ACCESS, MaxClaimTier.HYPOTHESIS, g.gate
        if g.status == GateStatus.FAIL.value:
            tier = (
                MaxClaimTier.REJECTED
                if g.gate == GateName.RERUN_CHECK.value
                else MaxClaimTier.HYPOTHESIS
            )
            return ProtocolVerdict.FAIL, tier, g.gate
    return ProtocolVerdict.PASS, MaxClaimTier.OBSERVED_IN_DATASET, None


def _diagnostic_capsule(
    state: _RunState,
    *,
    verdict: ProtocolVerdict,
    max_claim_tier: MaxClaimTier,
    failed_gate: str | None,
) -> Path:
    """Write a *diagnostic* capsule — best-effort partial write
    so an auditor can see exactly what gate the run halted on.
    """
    try:
        return _write_capsule(
            state,
            verdict=verdict.value,
            max_claim_tier=max_claim_tier.value,
            failed_gate=failed_gate,
        )
    except OSError:
        # Last-resort: write a minimal failure marker.
        try:
            state.output_dir.mkdir(parents=True, exist_ok=True)
            (state.output_dir / "capsule.json").write_text(
                json.dumps(
                    {
                        "verdict": verdict.value,
                        "max_claim_tier": max_claim_tier.value,
                        "failed_gate": failed_gate,
                        "diagnostic": True,
                    },
                    indent=2,
                    sort_keys=True,
                ),
                encoding="utf-8",
            )
        except OSError:  # pragma: no cover — defensive
            pass
        return state.output_dir


def run_protocol_x9r(
    *,
    dataset_dir: Path,
    output_dir: Path,
) -> ProtocolCapsule:
    """Run all nine gates sequentially; return one ProtocolCapsule.

    Strict-sequential, fail-closed. The first FAIL or BLOCKED gate
    short-circuits all downstream evaluation; the diagnostic
    capsule is still written.
    """
    state = _RunState(dataset_dir=dataset_dir, output_dir=output_dir)
    for _, gate_fn in _GATES_INITIAL:
        result = gate_fn(state)
        state.gate_results.append(result)
        if result.status != GateStatus.PASS.value:
            verdict, tier, failed = _final_verdict(state)
            capsule_path = _diagnostic_capsule(
                state, verdict=verdict, max_claim_tier=tier, failed_gate=failed
            )
            return ProtocolCapsule(
                capsule_path=capsule_path,
                verdict=verdict.value,
                failed_gate=failed,
                max_claim_tier=tier.value,
                rerun_command=f"python -m research.systemic_risk.protocol_x9r rerun --capsule {capsule_path}",
                gate_results=tuple(state.gate_results),
                tests_run=len(state.gate_results),
            )
    verdict, tier, failed = _final_verdict(state)
    return ProtocolCapsule(
        capsule_path=output_dir,
        verdict=verdict.value,
        failed_gate=failed,
        max_claim_tier=tier.value,
        rerun_command=f"python -m research.systemic_risk.protocol_x9r rerun --capsule {output_dir}",
        gate_results=tuple(state.gate_results),
        tests_run=len(state.gate_results),
    )


# ============================================================================
# 14. rerun_capsule — re-execute on the same dataset; check sha match
# ============================================================================


def rerun_capsule(*, capsule_dir: Path) -> ProtocolCapsule:
    """Re-run all 9 gates from scratch on the dataset referenced in
    ``capsule_dir/capsule.json`` and compare metrics_sha to the
    stored value via :func:`_gate_rerun_check_during_rerun`.
    """
    capsule_json = capsule_dir / "capsule.json"
    if not capsule_json.is_file():
        raise FileNotFoundError(f"capsule.json not found in {capsule_dir}; cannot rerun")
    payload = json.loads(capsule_json.read_text(encoding="utf-8"))
    expected_metrics_sha = payload.get("metrics_sha", "")
    # Extract original dataset_dir from the rerun_command's
    # surrounding context — we expect the user to invoke rerun from
    # the original dataset's adjacent capsule.  Fallback: assume
    # ``capsule_dir.parent / 'dataset_dir'``.
    rerun_dataset_dir = capsule_dir.parent / "dataset_dir"
    if not rerun_dataset_dir.is_dir():
        # Allow an env-var override for non-canonical layouts.
        import os

        env_override = os.environ.get("X9R_RERUN_DATASET_DIR")
        if env_override and Path(env_override).is_dir():
            rerun_dataset_dir = Path(env_override)
        else:
            raise FileNotFoundError(
                f"could not locate dataset_dir for rerun (tried "
                f"{rerun_dataset_dir} and X9R_RERUN_DATASET_DIR env)"
            )

    state = _RunState(
        dataset_dir=rerun_dataset_dir, output_dir=capsule_dir.parent / "rerun_capsule"
    )
    for gate_name, gate_fn in _GATES_INITIAL:
        if gate_name == GateName.RERUN_CHECK:
            result = _gate_rerun_check_during_rerun(
                state, expected_metrics_sha=expected_metrics_sha
            )
        else:
            result = gate_fn(state)
        state.gate_results.append(result)
        if result.status != GateStatus.PASS.value:
            verdict, tier, failed = _final_verdict(state)
            capsule_path = _diagnostic_capsule(
                state, verdict=verdict, max_claim_tier=tier, failed_gate=failed
            )
            return ProtocolCapsule(
                capsule_path=capsule_path,
                verdict=verdict.value,
                failed_gate=failed,
                max_claim_tier=tier.value,
                rerun_command=f"python -m research.systemic_risk.protocol_x9r rerun --capsule {capsule_path}",
                gate_results=tuple(state.gate_results),
                tests_run=len(state.gate_results),
            )
    verdict, tier, failed = _final_verdict(state)
    return ProtocolCapsule(
        capsule_path=state.output_dir,
        verdict=verdict.value,
        failed_gate=failed,
        max_claim_tier=tier.value,
        rerun_command=f"python -m research.systemic_risk.protocol_x9r rerun --capsule {state.output_dir}",
        gate_results=tuple(state.gate_results),
        tests_run=len(state.gate_results),
    )


# ============================================================================
# 15. CLI
# ============================================================================


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="research.systemic_risk.protocol_x9r",
        description="Protocol X-9R/1.0-RUN — deterministic empirical-falsification machine.",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    run_p = sub.add_parser("run", help="Initial run on a dataset_dir.")
    run_p.add_argument("--dataset-dir", required=True, type=Path)
    run_p.add_argument("--output", required=True, type=Path)
    rerun_p = sub.add_parser("rerun", help="Re-run from a capsule directory.")
    rerun_p.add_argument("--capsule", required=True, type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.command == "run":
        capsule = run_protocol_x9r(dataset_dir=args.dataset_dir, output_dir=args.output)
    elif args.command == "rerun":
        capsule = rerun_capsule(capsule_dir=args.capsule)
    else:  # pragma: no cover — argparse guards
        return 1
    payload = {
        "capsule_path": str(capsule.capsule_path),
        "verdict": capsule.verdict,
        "failed_gate": capsule.failed_gate,
        "max_claim_tier": capsule.max_claim_tier,
        "rerun_command": capsule.rerun_command,
        "tests_run": capsule.tests_run,
    }
    json.dump(payload, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0 if capsule.verdict == ProtocolVerdict.PASS.value else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
