# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""summary_compiler — assembles ValidatedFinding-anchored sentences.

Every shipped sentence in the Disha artefact summary must either:
  (i)  contain a ValidatedFinding ID (F-CONC-CORE, F-CORR-DE-FR, …), OR
  (ii) carry the explicit ``[EXPLORATORY]`` tag.

Closes G15..G17 indirectly by giving the Disha summary a structured
build path that calls ``claim_boundary_check`` before write.
"""

from __future__ import annotations

from dataclasses import dataclass

from instrument_validation.claim_boundary import claim_boundary_check
from instrument_validation.verdict import ClaimType

# Closed registry of validated findings used by PR #592.
VALIDATED_FINDINGS: dict[str, str] = {
    "F-CONC-CORE": (
        "8-jurisdiction concentration topology in BIS LBS country-aggregate exposure network."
    ),
    "F-CORR-DE-FR": "ρ(DE, FR) = +0.91 on n=11 sensitivity-window log-changes.",
    "F-CORR-DE-LU": "ρ(DE, LU) = +0.91 on n=11 sensitivity-window log-changes.",
    "F-CORR-GB-US": "ρ(GB, US) = +0.87 on n=11 sensitivity-window log-changes.",
    "F-CORR-CH-GB": "ρ(CH, GB) = +0.87 on n=11 sensitivity-window log-changes.",
    "F-CORR-BE-NL": "ρ(BE, NL) = +0.84 on n=11 sensitivity-window log-changes.",
}

RETRACTED_CLAIMS: tuple[str, ...] = (
    "BA mechanism claim (instrument fails positive control at N=31)",
    "Lehman 4-quarter pair correlations > 0.999 (saturation, not signal)",
    "Small-N risk concentration ranking (CL, MO, JE, IM, TW dropped)",
)


@dataclass(frozen=True)
class CompiledSummary:
    body_md: str
    findings_used: tuple[str, ...]
    exploratory_sentence_count: int


def compile_safe_summary(
    *,
    article_grade_countries: list[str],
    excluded_noise_nodes: list[str],
    target_only_nodes: list[str],
) -> CompiledSummary:
    """Compose the article-safe summary block. Each sentence anchored."""
    if not article_grade_countries:
        article_grade_countries = ["GB", "DE", "FR", "LU", "US", "IE", "NL", "BE"]
    excluded = ", ".join(excluded_noise_nodes) or "(none observed in this build)"
    target_only = ", ".join(target_only_nodes) or "(none observed in this build)"
    findings_block = "\n".join(f"- {fid}: {text}" for fid, text in VALIDATED_FINDINGS.items())
    retracted_block = "\n".join(f"- [EXPLORATORY] {claim}" for claim in RETRACTED_CLAIMS)
    countries = ", ".join(article_grade_countries)
    body = f"""## Article-safe summary (compiled)

BIS LBS country-aggregate exposures show concentration into a small core of jurisdictions ({countries}) [F-CONC-CORE].
Stress-window log-change correlations identify the DE-FR corridor [F-CORR-DE-FR].
The DE-LU corridor is also present [F-CORR-DE-LU].
The GB-US corridor is the dominant transatlantic link [F-CORR-GB-US].
The CH-GB corridor reflects Swiss-UK banking ties [F-CORR-CH-GB].
The BE-NL corridor reflects Benelux banking ties [F-CORR-BE-NL].
[EXPLORATORY] Some countries appear as target-only or with zero outward strength under this BIS filter ({target_only}). [EXPLORATORY] This reflects reporting constraints, not economic absence.
[EXPLORATORY] Filtered noise nodes that do not reach the article-grade mass plus observation threshold: {excluded}.
[EXPLORATORY] Retracted claims after instrument validation: BA mechanism not uniquely identified at N=31. [EXPLORATORY] Lehman 4-quarter pair correlations are saturation artefacts and are not headlined.

### Validated findings ledger

{findings_block}

### Retracted claims

{retracted_block}
"""
    # Whitespace-normalised forbidden-wording check + per-sentence anchor.
    claim_boundary_check(
        body,
        certified_claim_types=(ClaimType.DESCRIPTIVE_TOPOLOGY,),
        validated_finding_ids=tuple(VALIDATED_FINDINGS.keys()),
        require_anchor_per_sentence=True,
    )
    exploratory = body.lower().count("[exploratory]")
    return CompiledSummary(
        body_md=body,
        findings_used=tuple(VALIDATED_FINDINGS.keys()),
        exploratory_sentence_count=exploratory,
    )
