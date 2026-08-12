# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Loader and well-formedness validator for ``physics_contracts/market_limits.yaml``.

The market-limits contract states the boundary under which GeoSync's geometric
and dynamical descriptors (Kuramoto, Ricci, topology, thermo) may be interpreted
as statements about real markets at all. This module loads that contract and
exposes a fail-closed validator so a witness test can assert the contract stays
well-formed and aligned with the canonical claim-tier vocabulary.

It asserts nothing new about markets; it only makes the limits machine-checkable.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError as exc:  # pragma: no cover - plumbed by env, not tests
    raise RuntimeError("market_limits requires PyYAML. Install via `pip install pyyaml`.") from exc

_CONTRACT_PATH = Path(__file__).resolve().parents[2] / "physics_contracts" / "market_limits.yaml"

REQUIRED_FIELDS: tuple[str, ...] = (
    "limit_id",
    "mathematical_object",
    "market_interpretation",
    "valid_when",
    "invalid_when",
    "witness_required",
    "falsifier_required",
    "forbidden_claims",
    "max_claim_tier_violated",
)

# A promotion-relevant limit is one whose `invalid_when` could otherwise let a
# real-data claim advance a claim tier. Such a limit's named falsifier is not a
# falsifier unless it can actually be run, so it MUST carry an EXECUTABLE
# falsifier: either a runnable `falsifier_command` (command / pytest node id) or
# a `falsifier_artifact_path` (a path to a frozen result artifact). The contract
# load fails closed when a promotion-relevant limit declares neither. Non-
# promotion limits keep the prior behavior (no executable falsifier required).

# The four pre-registered nulls a falsifier_required entry must name. Mirrors
# ``tools/research/ricci_preregistration_guard.REQUIRED_NULLS`` so the contract
# cannot drift to a falsifier that the prereg pipeline does not run.
KNOWN_FALSIFIERS: frozenset[str] = frozenset(
    {"permutation_null", "lag_sweep_no_future_data", "cost_model", "multi_session_replay"}
)


@dataclass(frozen=True)
class MarketLimit:
    """A single market approximation limit drawn from the contract."""

    limit_id: str
    mathematical_object: str
    market_interpretation: str
    valid_when: tuple[str, ...]
    invalid_when: tuple[str, ...]
    witness_required: str
    falsifier_required: str
    forbidden_claims: tuple[str, ...]
    max_claim_tier_violated: str
    promotion_relevant: bool = False
    falsifier_command: str | None = None
    falsifier_artifact_path: str | None = None

    @property
    def has_executable_falsifier(self) -> bool:
        """True iff this limit names a runnable falsifier command or artifact."""
        return bool(self.falsifier_command) or bool(self.falsifier_artifact_path)


@dataclass(frozen=True)
class MarketLimitsContract:
    """The loaded contract: claim-tier vocabulary plus the limit entries."""

    version: int
    claim_tiers: tuple[str, ...]
    limits: tuple[MarketLimit, ...]

    def by_id(self, limit_id: str) -> MarketLimit | None:
        for limit in self.limits:
            if limit.limit_id == limit_id:
                return limit
        return None


def _as_str_tuple(value: Any) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError(f"expected a list[str], got {value!r}")
    return tuple(value)


def _as_optional_nonblank_str(value: Any, *, field: str, limit_id: str) -> str | None:
    """Coerce an optional executable-falsifier field; reject blank/non-str."""
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"limit {limit_id!r}: {field} must be a non-blank string, got {value!r}")
    return value


def load_contract(path: Path | None = None) -> MarketLimitsContract:
    """Load and parse the market-limits contract, fail-closed on shape errors."""
    contract_path = path or _CONTRACT_PATH
    raw: Any = yaml.safe_load(contract_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("market_limits.yaml must parse to a mapping")

    version = raw.get("version")
    if not isinstance(version, int):
        raise ValueError("market_limits.yaml requires an integer `version`")

    claim_tiers = _as_str_tuple(raw.get("claim_tiers"))
    raw_limits = raw.get("limits")
    if not isinstance(raw_limits, list) or not raw_limits:
        raise ValueError("market_limits.yaml requires a non-empty `limits` list")

    limits: list[MarketLimit] = []
    for entry in raw_limits:
        if not isinstance(entry, dict):
            raise ValueError(f"each limit must be a mapping, got {entry!r}")
        missing = [field for field in REQUIRED_FIELDS if field not in entry]
        if missing:
            raise ValueError(
                f"limit {entry.get('limit_id', '<unknown>')!r} missing fields: {missing}"
            )
        limit_id = str(entry["limit_id"])

        promotion_relevant_raw = entry.get("promotion_relevant", False)
        if not isinstance(promotion_relevant_raw, bool):
            raise ValueError(
                f"limit {limit_id!r}: promotion_relevant must be a bool, "
                f"got {promotion_relevant_raw!r}"
            )
        falsifier_command = _as_optional_nonblank_str(
            entry.get("falsifier_command"), field="falsifier_command", limit_id=limit_id
        )
        falsifier_artifact_path = _as_optional_nonblank_str(
            entry.get("falsifier_artifact_path"),
            field="falsifier_artifact_path",
            limit_id=limit_id,
        )

        # Fail-closed: a named falsifier is not a falsifier unless it can be run.
        # A promotion-relevant limit must carry an executable falsifier path.
        if promotion_relevant_raw and not (falsifier_command or falsifier_artifact_path):
            raise ValueError(
                f"limit {limit_id!r} is promotion_relevant but declares neither "
                f"falsifier_command nor falsifier_artifact_path: its required falsifier "
                f"{str(entry['falsifier_required'])!r} is not executable/locatable"
            )

        limits.append(
            MarketLimit(
                limit_id=limit_id,
                mathematical_object=str(entry["mathematical_object"]),
                market_interpretation=str(entry["market_interpretation"]),
                valid_when=_as_str_tuple(entry["valid_when"]),
                invalid_when=_as_str_tuple(entry["invalid_when"]),
                witness_required=str(entry["witness_required"]),
                falsifier_required=str(entry["falsifier_required"]),
                forbidden_claims=_as_str_tuple(entry["forbidden_claims"]),
                max_claim_tier_violated=str(entry["max_claim_tier_violated"]),
                promotion_relevant=promotion_relevant_raw,
                falsifier_command=falsifier_command,
                falsifier_artifact_path=falsifier_artifact_path,
            )
        )

    return MarketLimitsContract(
        version=version,
        claim_tiers=claim_tiers,
        limits=tuple(limits),
    )
