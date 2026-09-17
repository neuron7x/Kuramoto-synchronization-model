"""External-label, synthetic-judge stress harness for ECP-AS Iteration 004.

Ground-truth rigor labels are imported from a frozen SoundnessBench slice.
Evaluator errors are synthetic by design and must never be described as actual
LLM benchmark results. Labels are used only for scoring, never as gate inputs.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import itertools
import json
from pathlib import Path
from typing import Iterable, Mapping

from .evaluator_control import EvaluatorObservation, LineageQuorumPolicy
from .models import Claim, Oracle, OracleIndependence


@dataclass(frozen=True, slots=True)
class SoundnessCase:
    pair_id: str
    soundness_score: float
    rigor_bucket: str

    @property
    def sound(self) -> bool:
        return self.rigor_bucket == "high"


@dataclass(frozen=True, slots=True)
class JudgeProfile:
    name: str
    research_family_support_low: float
    research_family_support_high: float
    external_support_low: float
    external_support_high: float
    hidden_common_support_low: float = 0.0
    hidden_common_block_high: float = 0.0
    external_lineage_declared: bool = True


@dataclass(frozen=True, slots=True)
class StressMetrics:
    policy: str
    profile: str
    unsafe_promotion_rate: float
    false_block_rate: float
    balanced_error: float
    low_count: int
    high_count: int

    def as_dict(self) -> dict[str, object]:
        return {
            "policy": self.policy,
            "profile": self.profile,
            "unsafe_promotion_rate": self.unsafe_promotion_rate,
            "false_block_rate": self.false_block_rate,
            "balanced_error": self.balanced_error,
            "low_count": self.low_count,
            "high_count": self.high_count,
        }


def load_soundness_slice(path: str | Path) -> tuple[SoundnessCase, ...]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    rows = tuple(
        SoundnessCase(
            pair_id=str(item["pair_id"]),
            soundness_score=float(item["soundness_score"]),
            rigor_bucket=str(item["rigor_bucket"]),
        )
        for item in payload["cases"]
    )
    if len({row.pair_id for row in rows}) != len(rows):
        raise ValueError("duplicate SoundnessBench pair_id")
    if any(row.rigor_bucket not in {"low", "high"} for row in rows):
        raise ValueError("unexpected rigor bucket")
    return rows


def manifest_digest(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def default_profiles() -> tuple[JudgeProfile, ...]:
    return (
        JudgeProfile(
            name="optimistic_correlated",
            research_family_support_low=0.934,
            research_family_support_high=0.97,
            external_support_low=0.115,
            external_support_high=0.855,
        ),
        JudgeProfile(
            name="balanced_independent",
            research_family_support_low=0.60,
            research_family_support_high=0.90,
            external_support_low=0.08,
            external_support_high=0.90,
        ),
        JudgeProfile(
            name="hidden_common_cause",
            research_family_support_low=0.90,
            research_family_support_high=0.95,
            external_support_low=0.02,
            external_support_high=0.90,
            hidden_common_support_low=0.15,
            hidden_common_block_high=0.08,
        ),
    )


def _bernoulli_outcomes(probabilities: tuple[float, ...]):
    for bits in itertools.product((False, True), repeat=len(probabilities)):
        probability = 1.0
        for bit, p in zip(bits, probabilities, strict=True):
            probability *= p if bit else 1.0 - p
        yield bits, probability


def _oracles(claim_id: str, *, declare_external_lineage: bool = True) -> tuple[Oracle, ...]:
    full = OracleIndependence(True, True, True, True)
    shared = OracleIndependence(True, True, True, True)
    external_ancestors = (
        (frozenset({"ext:A:model", "ext:A:data"}),
         frozenset({"ext:B:model", "ext:B:data"}),
         frozenset({"ext:C:model", "ext:C:data"}))
        if declare_external_lineage
        else (frozenset(), frozenset(), frozenset())
    )
    return (
        Oracle("research:self", claim_id, "r0", shared, frozenset({"research:family"})),
        Oracle("research:sibling", claim_id, "r1", shared, frozenset({"research:family"})),
        Oracle("external:A", claim_id, "e0", full, external_ancestors[0]),
        Oracle("external:B", claim_id, "e1", full, external_ancestors[1]),
        Oracle("external:C", claim_id, "e2", full, external_ancestors[2]),
    )


def _gate_decision(
    claim: Claim,
    bits: tuple[bool, ...],
    *,
    policy: LineageQuorumPolicy,
    declare_external_lineage: bool = True,
) -> bool:
    observations = tuple(
        EvaluatorObservation(oracle, supports)
        for oracle, supports in zip(
            _oracles(claim.claim_id, declare_external_lineage=declare_external_lineage),
            bits,
            strict=True,
        )
    )
    return policy.decide(claim, observations).promoted


def _raw_majority(bits: tuple[bool, ...]) -> bool:
    return sum(bits) >= 3


def _policy_probability(
    *,
    sound: bool,
    profile: JudgeProfile,
    policy_name: str,
    claim: Claim,
    policy: LineageQuorumPolicy,
) -> float:
    family_p = (
        profile.research_family_support_high if sound else profile.research_family_support_low
    )
    ext_p = profile.external_support_high if sound else profile.external_support_low

    # Research-plane agents share one common-mode outcome. This models two
    # nominal agents that are not epistemically independent.
    base = 0.0
    for family_support, family_prob in ((False, 1.0 - family_p), (True, family_p)):
        # Hidden common cause is deliberately absent from declared lineage metadata.
        if sound:
            latent = ((False, 1.0 - profile.hidden_common_block_high),
                      (True, profile.hidden_common_block_high))
        else:
            latent = ((False, 1.0 - profile.hidden_common_support_low),
                      (True, profile.hidden_common_support_low))
        for common_failure, common_prob in latent:
            for ext_bits, ext_prob in _bernoulli_outcomes((ext_p, ext_p, ext_p)):
                if common_failure:
                    ext_bits = (False, False, False) if sound else (True, True, True)
                bits = (family_support, family_support, *ext_bits)
                if policy_name == "raw_majority":
                    promoted = _raw_majority(bits)
                elif policy_name == "ecp_as_lineage_quorum":
                    promoted = _gate_decision(
                        claim,
                        bits,
                        policy=policy,
                        declare_external_lineage=profile.external_lineage_declared,
                    )
                elif policy_name == "strict_external_unanimity":
                    promoted = all(ext_bits)
                else:
                    raise ValueError(f"unknown policy {policy_name}")
                if promoted:
                    base += family_prob * common_prob * ext_prob
    return base


def evaluate_profile(
    cases: Iterable[SoundnessCase],
    profile: JudgeProfile,
    *,
    policies: tuple[str, ...] = (
        "raw_majority", "ecp_as_lineage_quorum", "strict_external_unanimity"
    ),
) -> tuple[StressMetrics, ...]:
    rows = tuple(cases)
    low = tuple(row for row in rows if not row.sound)
    high = tuple(row for row in rows if row.sound)
    gate = LineageQuorumPolicy(min_admissible=3, required_support=2)
    metrics: list[StressMetrics] = []
    for policy_name in policies:
        low_probs = []
        high_probs = []
        for row in low:
            claim = Claim(
                f"soundness:{row.pair_id}", "proposal soundness", "ml-research", "proposal",
                generator_ancestors=frozenset({"research:family"}),
            )
            low_probs.append(
                _policy_probability(
                    sound=False, profile=profile, policy_name=policy_name, claim=claim, policy=gate
                )
            )
        for row in high:
            claim = Claim(
                f"soundness:{row.pair_id}", "proposal soundness", "ml-research", "proposal",
                generator_ancestors=frozenset({"research:family"}),
            )
            promote = _policy_probability(
                sound=True, profile=profile, policy_name=policy_name, claim=claim, policy=gate
            )
            high_probs.append(promote)
        unsafe = sum(low_probs) / len(low_probs) if low_probs else 0.0
        false_block = (
            sum(1.0 - value for value in high_probs) / len(high_probs) if high_probs else 0.0
        )
        metrics.append(
            StressMetrics(
                policy=policy_name,
                profile=profile.name,
                unsafe_promotion_rate=unsafe,
                false_block_rate=false_block,
                balanced_error=(unsafe + false_block) / 2.0,
                low_count=len(low),
                high_count=len(high),
            )
        )
    return tuple(metrics)


def run_stress_suite(cases: Iterable[SoundnessCase]) -> dict[str, object]:
    rows = tuple(cases)
    output: dict[str, object] = {
        "schema": "ecp-as-soundness-control-stress/v1",
        "case_count": len(rows),
        "low_count": sum(not row.sound for row in rows),
        "high_count": sum(row.sound for row in rows),
        "profiles": {},
    }
    for profile in default_profiles():
        output["profiles"][profile.name] = {
            metric.policy: metric.as_dict() for metric in evaluate_profile(rows, profile)
        }
    return output
