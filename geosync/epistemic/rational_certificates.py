"""Exact rational proof objects for distributionally robust quorum bounds.

A certificate contains both:
1. a primal joint distribution attaining an event probability; and
2. a dual affine majorant proving no compatible joint distribution can exceed it.

Verification uses only fractions and exhaustive binary states. It does not trust
SciPy, floating-point solver tolerances, or an independence assumption.
"""
from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from itertools import product
from typing import Mapping


def _f(value: str | int | Fraction) -> Fraction:
    return value if isinstance(value, Fraction) else Fraction(value)


def _bits(key: str, n: int) -> tuple[int, ...]:
    if len(key) != n or any(ch not in "01" for ch in key):
        raise ValueError(f"invalid state {key!r} for n={n}")
    return tuple(int(ch) for ch in key)


@dataclass(frozen=True, slots=True)
class RationalQuorumCertificate:
    certificate_id: str
    evaluator_ids: tuple[str, ...]
    required_support: int
    event: str
    marginals: tuple[str, ...]
    joint_mass: Mapping[str, str]
    dual_intercept: str
    dual_coefficients: tuple[str, ...]
    optimum: str

    def as_dict(self) -> dict[str, object]:
        return {
            "certificate_id": self.certificate_id,
            "evaluator_ids": list(self.evaluator_ids),
            "required_support": self.required_support,
            "event": self.event,
            "marginals": list(self.marginals),
            "joint_mass": dict(sorted(self.joint_mass.items())),
            "dual_intercept": self.dual_intercept,
            "dual_coefficients": list(self.dual_coefficients),
            "optimum": self.optimum,
        }


@dataclass(frozen=True, slots=True)
class CertificateVerification:
    valid: bool
    primal_valid: bool
    dual_valid: bool
    strong_duality: bool
    primal_objective: str
    dual_objective: str
    reason: str

    def as_dict(self) -> dict[str, object]:
        return {
            "valid": self.valid,
            "primal_valid": self.primal_valid,
            "dual_valid": self.dual_valid,
            "strong_duality": self.strong_duality,
            "primal_objective": self.primal_objective,
            "dual_objective": self.dual_objective,
            "reason": self.reason,
        }


def event_indicator(event: str, bits: tuple[int, ...], required_support: int) -> int:
    support = sum(bits)
    if event == "UNSAFE_PROMOTION":
        return int(support >= required_support)
    if event == "FALSE_BLOCK":
        return int(support < required_support)
    raise ValueError(f"unsupported event: {event}")


def verify_rational_certificate(cert: RationalQuorumCertificate) -> CertificateVerification:
    n = len(cert.evaluator_ids)
    if len(cert.marginals) != n or len(cert.dual_coefficients) != n:
        return CertificateVerification(False, False, False, False, "0", "0", "dimension mismatch")
    if not 1 <= cert.required_support <= n:
        return CertificateVerification(False, False, False, False, "0", "0", "invalid quorum")

    marginals = tuple(_f(x) for x in cert.marginals)
    optimum = _f(cert.optimum)
    masses = {key: _f(value) for key, value in cert.joint_mass.items()}
    all_states = tuple(product((0, 1), repeat=n))

    primal_valid = all(value >= 0 for value in masses.values())
    primal_valid &= sum(masses.values(), Fraction(0)) == 1
    calculated_marginals = []
    primal_objective = Fraction(0)
    for index in range(n):
        calculated_marginals.append(
            sum(
                mass
                for key, mass in masses.items()
                if _bits(key, n)[index] == 1
            )
        )
    primal_valid &= tuple(calculated_marginals) == marginals
    for key, mass in masses.items():
        bits = _bits(key, n)
        primal_objective += mass * event_indicator(cert.event, bits, cert.required_support)
    primal_valid &= primal_objective == optimum

    intercept = _f(cert.dual_intercept)
    coefficients = tuple(_f(x) for x in cert.dual_coefficients)
    dual_valid = True
    for bits in all_states:
        affine = intercept + sum(c * bit for c, bit in zip(coefficients, bits, strict=True))
        indicator = event_indicator(cert.event, bits, cert.required_support)
        if affine < indicator:
            dual_valid = False
            break
    dual_objective = intercept + sum(c * p for c, p in zip(coefficients, marginals, strict=True))
    dual_valid &= dual_objective == optimum

    strong_duality = primal_objective == dual_objective == optimum
    valid = primal_valid and dual_valid and strong_duality
    reason = (
        "exact primal witness and dual majorant coincide"
        if valid
        else "certificate failed exact rational verification"
    )
    return CertificateVerification(
        valid=valid,
        primal_valid=primal_valid,
        dual_valid=dual_valid,
        strong_duality=strong_duality,
        primal_objective=str(primal_objective),
        dual_objective=str(dual_objective),
        reason=reason,
    )


def iteration_006_certificates() -> tuple[RationalQuorumCertificate, RationalQuorumCertificate]:
    evaluator_ids = (
        "LLaMA-3.3-70B-Instruct::standard",
        "Claude-Opus-4-6::aggressive",
        "GPT-5.4-Mini::aggressive",
    )
    unsafe = RationalQuorumCertificate(
        certificate_id="iter006-best-triplet-unsafe-max",
        evaluator_ids=evaluator_ids,
        required_support=2,
        event="UNSAFE_PROMOTION",
        # FP marginals: 0.980, 0.278, 0.000
        marginals=("49/50", "139/500", "0"),
        # Explicit compatible joint distribution attaining 0.278.
        joint_mass={"000": "1/50", "100": "351/500", "110": "139/500"},
        # 1{sum Xi>=2} <= X2 + X3 for every binary state.
        dual_intercept="0",
        dual_coefficients=("0", "1", "1"),
        optimum="139/500",
    )
    false_block = RationalQuorumCertificate(
        certificate_id="iter006-best-triplet-false-block-max",
        evaluator_ids=evaluator_ids,
        required_support=2,
        event="FALSE_BLOCK",
        # TP marginals: 0.994, 0.664, 0.002
        marginals=("497/500", "83/125", "1/500"),
        # Explicit compatible joint distribution attaining 0.342.
        joint_mass={"010": "3/500", "100": "42/125", "110": "82/125", "111": "1/500"},
        # 1{sum Xi<2} <= 2 - X1 - X2 for every binary state.
        dual_intercept="2",
        dual_coefficients=("-1", "-1", "0"),
        optimum="171/500",
    )
    return unsafe, false_block
