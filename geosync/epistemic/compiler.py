"""Deterministic structured claim compiler.

Natural-language drafting may be performed by an LLM, but admission semantics
must be emitted as explicit structured fields and validated here.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Tuple

@dataclass(frozen=True, slots=True)
class ClaimContractSpec:
    proposition: str
    population_or_domain: str
    operational_definition: str
    null_hypothesis: str
    alternative_hypotheses: Tuple[str,...]
    effect_criterion: str
    falsification_criterion: str
    required_oracle: str

    def validate(self) -> None:
        fields=(self.proposition,self.population_or_domain,self.operational_definition,
                self.null_hypothesis,self.effect_criterion,self.falsification_criterion,
                self.required_oracle)
        if any(not x.strip() for x in fields): raise ValueError("claim contract fields must be explicit")
        if not self.alternative_hypotheses: raise ValueError("at least one alternative hypothesis required")
        if any(not x.strip() for x in self.alternative_hypotheses): raise ValueError("empty alternative hypothesis")
        if self.null_hypothesis.strip()==self.proposition.strip(): raise ValueError("null cannot equal proposition")
        if self.falsification_criterion.strip()==self.effect_criterion.strip():
            raise ValueError("effect and falsification criteria must be independently stated")

def compile_structured_claim(**kwargs: object) -> ClaimContractSpec:
    spec=ClaimContractSpec(**kwargs)  # type: ignore[arg-type]
    spec.validate(); return spec
