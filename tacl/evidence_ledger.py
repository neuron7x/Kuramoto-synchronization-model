# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
# no-bio-claim
"""PNCC evidence ledger — pre-registered hypotheses + immutable claim records.

Status
------
EXPERIMENTAL / opt-in. This is the contract-enforcement module of the
Physics-Native Cognitive Kernel (PNCC). It stores immutable evidence
records (baseline, intervention, n, effect size, 95% confidence
interval, statistical test) keyed to one of five PRE-REGISTERED
hypotheses (HYP-1..HYP-5) about operator-loop latency, error recovery,
scheduling, compute cost, and the combined loop.

No-bio-claim disclaimer
-----------------------
This module makes no claim of a biological optimization, no medical
language, and no causal cognitive-performance assertion. The ledger
records *measurements*; it does NOT validate any human-physiology or
medical assertion. Negative effect sizes are first-class citizens —
recording HYP rejection is the principal use-case (correlation-only,
no causal interpretation).

Invariants
----------
- ``INV-NO-BIO-CLAIM`` (P0, universal): any source/doc emitting
  cognitive-performance language without an associated EvidenceClaim
  AND without a disclaimer phrase from ``allowed_disclaimer_phrases``
  is a contract violation. Falsification axis: AST-grep over
  ``core/``, ``tacl/``, ``runtime/``, ``geosync/`` returns zero
  naked violations.
- ``INV-HPC1`` (universal): seeded reproducibility — ``claim_hash``
  is a deterministic SHA-256 over canonical-JSON of the claim record.
- Validation is fail-closed: missing samples (n < 30), non-finite
  numerics, inverted CI, or out-of-unit-interval p_value all reject.

Source anchors
--------------
- Pre-registration practice: COS Open Science Framework guidelines.
- Effect size convention: Cohen (1988), Lakens (2013).
- Confidence-interval reporting: APA 7 §3.7.

Notes
-----
Persistence is in-memory by default; serialize with ``to_json`` for
durable 90-day evidence-ledger workflows. Single-arm only — no
crossover, no Bayes-factor scoring yet.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import time
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from enum import Enum
from pathlib import Path
from typing import Final, Literal

# INV-CRITICALITY: substrate decision signals tracked alongside evidence.
# Mirrors tacl/dr_free.robust_energy_state and tacl/physics_native_kernel
# KernelDecision.state. Kept as Literal (not Enum) for cross-module type
# unification.
DecisionSignalKind = Literal["NORMAL", "WARNING", "DORMANT"]
_VALID_SIGNAL_VALUES: Final[frozenset[str]] = frozenset({"NORMAL", "WARNING", "DORMANT"})

__all__ = [
    "BioClaimViolation",
    "DecisionSignalKind",
    "EvidenceClaim",
    "EvidenceLedger",
    "EvidenceRegistry",
    "HypothesisId",
    "LedgerEntry",
    "StatTest",
    "claim_canonical_json",
    "claim_hash",
    "scan_source_for_bio_claims",
    "validate_claim",
    "DEFAULT_FORBIDDEN_PATTERNS",
    "DEFAULT_DISCLAIMER_PHRASES",
]


_DEFAULT_HORIZON_DAYS: Final[int] = 90
_MIN_SAMPLE_FLOOR: Final[int] = 30


class HypothesisId(str, Enum):
    """The five pre-registered PNCC hypotheses.

    These identifiers are FROZEN. Adding a hypothesis requires a new
    enum value plus a corresponding entry in ``CANONS.md`` — never
    re-use or re-purpose an existing identifier.
    """

    HYP_1_DECISION_LATENCY = "HYP-1"
    HYP_2_ERROR_RECOVERY = "HYP-2"
    HYP_3_CNS_SCHEDULING = "HYP-3"
    HYP_4_COMPUTE_COST = "HYP-4"
    HYP_5_COMBINED_LOOP = "HYP-5"


@dataclass(frozen=True, slots=True)
class StatTest:
    """Statistical test bundle attached to an EvidenceClaim."""

    test_name: str
    test_statistic: float
    p_value: float
    df: float | None


@dataclass(frozen=True, slots=True)
class EvidenceClaim:
    """Immutable claim record. Hashed for ledger integrity.

    Negative ``effect_size`` values are valid claims and represent
    HYP rejection (e.g. an intervention that was hypothesised to
    reduce latency but in fact increased it). The schema deliberately
    forbids the registry from "soft-deleting" or rewriting claims.
    """

    hypothesis: HypothesisId
    baseline_mean: float
    baseline_std: float
    baseline_n: int
    intervention_mean: float
    intervention_std: float
    intervention_n: int
    effect_size: float
    ci_95_low: float
    ci_95_high: float
    stat_test: StatTest
    registered_at_ns: int
    pre_registered: bool
    notes: str | None = None
    # INV-CRITICALITY (Bak 1996; Langton 1990; Mora-Bialek 2011; Beggs-Plenz 2003).
    # γ = 2·H + 1 (DFA-1 Hurst). Substrate is intelligence-capable iff
    # γ ∈ [1−ε, 1+ε]. Outside the metastable window any non-DORMANT signal
    # is rejected (fail-closed). None ⇒ legacy claim, criticality bypassed.
    substrate_criticality_at_decision: float | None = None
    criticality_window_confirmed: bool = False
    signal: DecisionSignalKind = "NORMAL"


@dataclass(frozen=True, slots=True)
class LedgerEntry:
    """A claim plus its content-addressable hash and append timestamp."""

    claim_hash: str
    claim: EvidenceClaim
    appended_at_ns: int


@dataclass(frozen=True, slots=True)
class EvidenceLedger:
    """Snapshot view of a registry. Use ``EvidenceRegistry`` for mutation."""

    entries: tuple[LedgerEntry, ...]
    horizon_days: int


@dataclass(frozen=True, slots=True)
class BioClaimViolation:
    """A single naked-claim hit returned by ``scan_source_for_bio_claims``."""

    file_path: str
    line_no: int
    snippet: str
    matched_pattern: str


def claim_canonical_json(claim: EvidenceClaim) -> bytes:
    """Canonical JSON encoding for hashing.

    Sort keys, no whitespace, ASCII-safe, finite numerics only.
    """
    payload = _claim_to_canonical_dict(claim)
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def claim_hash(claim: EvidenceClaim) -> str:
    """SHA-256 over canonical-JSON of the claim. INV-HPC1."""
    return hashlib.sha256(claim_canonical_json(claim)).hexdigest()


def validate_claim(
    claim: EvidenceClaim,
    *,
    min_n: int = _MIN_SAMPLE_FLOOR,
) -> tuple[bool, str | None]:
    """Return ``(is_valid, reason_if_invalid)`` per the PNCC floor.

    Checks (fail-closed):

    - ``baseline_n >= min_n`` and ``intervention_n >= min_n``
    - all numeric stats are finite (no NaN/Inf)
    - ``ci_95_low <= ci_95_high``
    - ``p_value`` in ``[0, 1]``
    - non-zero ``baseline_std`` and ``intervention_std`` UNLESS
      ``effect_size == 0`` exactly (a degenerate constant arm is
      only meaningful when also reporting a zero effect)
    """
    if min_n < 1:
        return False, f"min_n must be >= 1, got {min_n}"

    if claim.baseline_n < min_n:
        return (
            False,
            f"baseline_n={claim.baseline_n} < min_n={min_n}",
        )
    if claim.intervention_n < min_n:
        return (
            False,
            f"intervention_n={claim.intervention_n} < min_n={min_n}",
        )

    numerics: tuple[tuple[str, float], ...] = (
        ("baseline_mean", claim.baseline_mean),
        ("baseline_std", claim.baseline_std),
        ("intervention_mean", claim.intervention_mean),
        ("intervention_std", claim.intervention_std),
        ("effect_size", claim.effect_size),
        ("ci_95_low", claim.ci_95_low),
        ("ci_95_high", claim.ci_95_high),
        ("stat_test.test_statistic", claim.stat_test.test_statistic),
        ("stat_test.p_value", claim.stat_test.p_value),
    )
    for name, value in numerics:
        if not math.isfinite(value):
            return False, f"non-finite value for {name}: {value!r}"
    if claim.stat_test.df is not None and not math.isfinite(claim.stat_test.df):
        return False, f"non-finite stat_test.df: {claim.stat_test.df!r}"

    if claim.ci_95_low > claim.ci_95_high:
        return (
            False,
            f"inverted CI: low={claim.ci_95_low} > high={claim.ci_95_high}",
        )

    p_value = claim.stat_test.p_value
    if not (0.0 <= p_value <= 1.0):
        return False, f"p_value={p_value} outside unit interval [0, 1]"

    if claim.baseline_std < 0.0 or claim.intervention_std < 0.0:
        return (
            False,
            f"negative std (baseline={claim.baseline_std}, intervention={claim.intervention_std})",
        )

    if claim.effect_size != 0.0:
        if claim.baseline_std == 0.0 or claim.intervention_std == 0.0:
            return (
                False,
                "zero std with non-zero effect_size is not a meaningful claim "
                f"(baseline_std={claim.baseline_std}, "
                f"intervention_std={claim.intervention_std}, "
                f"effect_size={claim.effect_size})",
            )

    if claim.baseline_n < 1 or claim.intervention_n < 1:
        return False, "n < 1 not permitted"

    # INV-CRITICALITY: when γ is recorded, it must be a finite positive
    # number, and a non-confirmed window forces the claim's signal to
    # DORMANT (fail-closed). γ is None ⇒ legacy claim, no check.
    gamma = claim.substrate_criticality_at_decision
    if gamma is not None:
        if not math.isfinite(gamma):
            return False, f"non-finite substrate_criticality_at_decision: {gamma!r}"
        if gamma <= 0.0:
            return False, f"substrate_criticality_at_decision must be > 0 (γ > 0), got {gamma}"
        if claim.signal not in _VALID_SIGNAL_VALUES:
            return False, f"signal={claim.signal!r} not in {sorted(_VALID_SIGNAL_VALUES)}"
        if not claim.criticality_window_confirmed and claim.signal != "DORMANT":
            return (
                False,
                "INV-CRITICALITY: criticality_window_confirmed=False with "
                f"signal={claim.signal!r}; non-DORMANT signals require an "
                "explicitly confirmed criticality window",
            )

    return True, None


class EvidenceRegistry:
    """In-memory ledger. NOT thread-safe. Persistence via to_json/from_json.

    The registry is append-only: ``register`` validates, hashes, and
    appends. ``query`` returns a tuple snapshot keyed by hypothesis.
    Two registrations of the same claim collapse to a single entry
    (idempotent on content-hash).
    """

    def __init__(self, horizon_days: int = _DEFAULT_HORIZON_DAYS) -> None:
        if horizon_days < 1:
            raise ValueError(f"horizon_days must be >= 1, got {horizon_days}")
        self._horizon_days: Final[int] = horizon_days
        self._entries: list[LedgerEntry] = []
        self._seen_hashes: set[str] = set()

    @property
    def horizon_days(self) -> int:
        return self._horizon_days

    def __len__(self) -> int:
        return len(self._entries)

    def register(self, claim: EvidenceClaim) -> LedgerEntry:
        """Validate, hash, and append. Returns the new ``LedgerEntry``.

        Raises ``ValueError`` if the claim fails ``validate_claim``.
        """
        is_valid, reason = validate_claim(claim)
        if not is_valid:
            raise ValueError(f"EvidenceClaim rejected: {reason}")

        h = claim_hash(claim)
        if h in self._seen_hashes:
            for existing in self._entries:
                if existing.claim_hash == h:
                    return existing

        entry = LedgerEntry(
            claim_hash=h,
            claim=claim,
            appended_at_ns=time.time_ns(),
        )
        self._entries.append(entry)
        self._seen_hashes.add(h)
        return entry

    def query(self, hypothesis: HypothesisId) -> tuple[LedgerEntry, ...]:
        """Return a tuple of all entries for a given hypothesis."""
        return tuple(e for e in self._entries if e.claim.hypothesis is hypothesis)

    def snapshot(self) -> EvidenceLedger:
        return EvidenceLedger(
            entries=tuple(self._entries),
            horizon_days=self._horizon_days,
        )

    def to_json(self) -> str:
        payload: dict[str, object] = {
            "horizon_days": self._horizon_days,
            "entries": [_entry_to_dict(e) for e in self._entries],
        }
        return json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        )

    @classmethod
    def from_json(cls, payload: str) -> EvidenceRegistry:
        raw = json.loads(payload)
        if not isinstance(raw, dict):
            raise ValueError("payload root must be a JSON object")
        horizon = raw.get("horizon_days", _DEFAULT_HORIZON_DAYS)
        if not isinstance(horizon, int):
            raise ValueError(f"horizon_days must be int, got {type(horizon).__name__}")
        entries_raw = raw.get("entries", [])
        if not isinstance(entries_raw, list):
            raise ValueError("entries must be a list")

        registry = cls(horizon_days=horizon)
        for item in entries_raw:
            if not isinstance(item, dict):
                raise ValueError("each entry must be an object")
            entry = _entry_from_dict(item)
            expected = claim_hash(entry.claim)
            if expected != entry.claim_hash:
                raise ValueError(
                    f"claim_hash mismatch on load: expected {expected}, got {entry.claim_hash}"
                )
            registry._entries.append(entry)
            registry._seen_hashes.add(entry.claim_hash)
        return registry


# ---------------------------------------------------------------------------
# AST-grep guard for INV-NO-BIO-CLAIM
# ---------------------------------------------------------------------------


DEFAULT_FORBIDDEN_PATTERNS: Final[tuple[str, ...]] = (
    r"\bimprov\w*\s+(memory|focus|attention|cognition|productivity|brain)\b",
    r"\bboost\w*\s+(memory|focus|attention|cognition|productivity|brain)\b",
    r"\benhanc\w*\s+(memory|focus|attention|cognition|productivity|brain)\b",
    r"\boptim\w*\s+(memory|focus|attention|cognition|the\s+brain)\b",
    # Medical-claim heuristic: ``diagnose|treat`` followed by an object that
    # could be read as a disease/condition/cognitive-state. The bare form
    # ``treat \w+`` from the original spec was too broad — it triggered on
    # generic English ("treat as inclusive", "treat each edge", ...) which
    # are not medical claims. Refinement keeps the spec intent while making
    # the lint usable as a CI gate. Documented in CANONS.md §INV-NO-BIO-CLAIM.
    r"\b(diagnose|treat)\s+(disease|condition|disorder|illness|"
    r"depression|anxiety|adhd|insomnia|fatigue|burnout|"
    r"memory|focus|attention|cognition|the\s+brain|patients?|symptoms?)\b",
    r"\+\s*\d+\s*[-–]\s*\d+\s*%\s+(productivity|cognition|focus)",
    r"\b\d+\s*[xX]\s+(productivity|focus|memory|cognition)\b",
)

DEFAULT_DISCLAIMER_PHRASES: Final[tuple[str, ...]] = (
    "does NOT",
    "make no claim",
    "is NOT a",
    "is not a",
    "no claim of",
    "no causal",
    "correlation-only",
    "no-bio-claim",
    "no medical",
)

_TEST_PATH_SEGMENTS: Final[tuple[str, ...]] = (
    "/tests/",
    "/test/",
)

_EVIDENCE_REFERENCE_TOKENS: Final[tuple[str, ...]] = (
    "EvidenceClaim",
    "HypothesisId",
    "HYP-1",
    "HYP-2",
    "HYP-3",
    "HYP-4",
    "HYP-5",
)

_DEFAULT_REFERENCE_WINDOW: Final[int] = 5


def scan_source_for_bio_claims(
    paths: Iterable[Path],
    *,
    forbidden_patterns: tuple[str, ...] = DEFAULT_FORBIDDEN_PATTERNS,
    allowed_disclaimer_phrases: tuple[str, ...] = DEFAULT_DISCLAIMER_PHRASES,
    reference_window: int = _DEFAULT_REFERENCE_WINDOW,
) -> list[BioClaimViolation]:
    """Scan files for cognitive-performance language without an evidence anchor.

    Skip rules:

    - lines containing any allowed disclaimer phrase (explicit denials)
    - lines whose path is a test file (those tests assert the bans)
    - lines that reference an EvidenceClaim / HypothesisId / HYP-N
      identifier within ``reference_window`` lines (i.e. an associated
      claim is in scope)

    Returns one ``BioClaimViolation`` per (file, line, pattern) triple
    that survives all skips.
    """
    if reference_window < 0:
        raise ValueError(f"reference_window must be >= 0, got {reference_window}")

    compiled = tuple(re.compile(p, re.IGNORECASE) for p in forbidden_patterns)
    raw_patterns = forbidden_patterns
    violations: list[BioClaimViolation] = []

    for path in paths:
        if _is_test_path(path):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        lines = text.splitlines()
        if not lines:
            continue

        for line_no, line in enumerate(lines, start=1):
            if _line_has_disclaimer(line, allowed_disclaimer_phrases):
                continue
            if _line_in_evidence_window(lines, line_no - 1, reference_window):
                continue
            for pattern, raw in zip(compiled, raw_patterns, strict=True):
                m = pattern.search(line)
                if m is None:
                    continue
                violations.append(
                    BioClaimViolation(
                        file_path=str(path),
                        line_no=line_no,
                        snippet=line.strip(),
                        matched_pattern=raw,
                    )
                )
    return violations


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


def _claim_to_canonical_dict(claim: EvidenceClaim) -> dict[str, object]:
    raw = asdict(claim)
    raw["hypothesis"] = claim.hypothesis.value
    return raw


def _entry_to_dict(entry: LedgerEntry) -> dict[str, object]:
    return {
        "claim_hash": entry.claim_hash,
        "appended_at_ns": entry.appended_at_ns,
        "claim": _claim_to_canonical_dict(entry.claim),
    }


def _entry_from_dict(item: dict[str, object]) -> LedgerEntry:
    h = item.get("claim_hash")
    appended_at_ns = item.get("appended_at_ns")
    claim_raw = item.get("claim")
    if not isinstance(h, str):
        raise ValueError("claim_hash must be str")
    if not isinstance(appended_at_ns, int):
        raise ValueError("appended_at_ns must be int")
    if not isinstance(claim_raw, dict):
        raise ValueError("claim must be an object")
    return LedgerEntry(
        claim_hash=h,
        appended_at_ns=appended_at_ns,
        claim=_claim_from_dict(claim_raw),
    )


def _claim_from_dict(raw: dict[str, object]) -> EvidenceClaim:
    hyp_raw = raw.get("hypothesis")
    if not isinstance(hyp_raw, str):
        raise ValueError("hypothesis must be str")
    hypothesis = HypothesisId(hyp_raw)
    stat_raw = raw.get("stat_test")
    if not isinstance(stat_raw, dict):
        raise ValueError("stat_test must be an object")
    stat_test = StatTest(
        test_name=_require_str(stat_raw, "test_name"),
        test_statistic=_require_float(stat_raw, "test_statistic"),
        p_value=_require_float(stat_raw, "p_value"),
        df=_optional_float(stat_raw, "df"),
    )
    notes_raw = raw.get("notes")
    if notes_raw is not None and not isinstance(notes_raw, str):
        raise ValueError("notes must be str or null")
    # INV-CRITICALITY backward-compat: legacy JSON without these fields
    # deserializes with default sentinels; γ=None ⇒ legacy claim.
    sub_crit = _optional_float(raw, "substrate_criticality_at_decision")
    crit_confirmed_raw = raw.get("criticality_window_confirmed", False)
    if not isinstance(crit_confirmed_raw, bool):
        raise ValueError(
            f"criticality_window_confirmed must be bool, got {type(crit_confirmed_raw).__name__}"
        )
    signal_raw = raw.get("signal", "NORMAL")
    if not isinstance(signal_raw, str) or signal_raw not in _VALID_SIGNAL_VALUES:
        raise ValueError(
            f"signal must be one of {sorted(_VALID_SIGNAL_VALUES)}, got {signal_raw!r}"
        )
    return EvidenceClaim(
        hypothesis=hypothesis,
        baseline_mean=_require_float(raw, "baseline_mean"),
        baseline_std=_require_float(raw, "baseline_std"),
        baseline_n=_require_int(raw, "baseline_n"),
        intervention_mean=_require_float(raw, "intervention_mean"),
        intervention_std=_require_float(raw, "intervention_std"),
        intervention_n=_require_int(raw, "intervention_n"),
        effect_size=_require_float(raw, "effect_size"),
        ci_95_low=_require_float(raw, "ci_95_low"),
        ci_95_high=_require_float(raw, "ci_95_high"),
        stat_test=stat_test,
        registered_at_ns=_require_int(raw, "registered_at_ns"),
        pre_registered=_require_bool(raw, "pre_registered"),
        notes=notes_raw,
        substrate_criticality_at_decision=sub_crit,
        criticality_window_confirmed=crit_confirmed_raw,
        signal=signal_raw,  # type: ignore[arg-type]
    )


def _require_str(d: dict[str, object], key: str) -> str:
    v = d.get(key)
    if not isinstance(v, str):
        raise ValueError(f"{key} must be str, got {type(v).__name__}")
    return v


def _require_float(d: dict[str, object], key: str) -> float:
    v = d.get(key)
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        raise ValueError(f"{key} must be number, got {type(v).__name__}")
    return float(v)


def _optional_float(d: dict[str, object], key: str) -> float | None:
    v = d.get(key)
    if v is None:
        return None
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        raise ValueError(f"{key} must be number or null, got {type(v).__name__}")
    return float(v)


def _require_int(d: dict[str, object], key: str) -> int:
    v = d.get(key)
    if isinstance(v, bool) or not isinstance(v, int):
        raise ValueError(f"{key} must be int, got {type(v).__name__}")
    return v


def _require_bool(d: dict[str, object], key: str) -> bool:
    v = d.get(key)
    if not isinstance(v, bool):
        raise ValueError(f"{key} must be bool, got {type(v).__name__}")
    return v


def _is_test_path(path: Path) -> bool:
    s = str(path).replace("\\", "/")
    name = path.name
    if any(seg in s for seg in _TEST_PATH_SEGMENTS):
        return True
    if name.startswith("test_") or name.endswith("_test.py"):
        return True
    return False


def _line_has_disclaimer(line: str, phrases: tuple[str, ...]) -> bool:
    return any(phrase in line for phrase in phrases)


def _line_in_evidence_window(
    lines: list[str],
    idx: int,
    window: int,
) -> bool:
    lo = max(0, idx - window)
    hi = min(len(lines), idx + window + 1)
    for j in range(lo, hi):
        candidate = lines[j]
        for token in _EVIDENCE_REFERENCE_TOKENS:
            if token in candidate:
                return True
    return False
