# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Claim boundary — whitespace-normalised, certificate-gated.

Closes B4 (forbidden-wording line-break fragility) plus the
generative-mechanism / liquidity-contagion claim families.
Every shipped sentence must map to a ValidatedFinding ID OR carry
the explicit ``[EXPLORATORY]`` tag.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable

from instrument_validation.verdict import ClaimType

FORBIDDEN_UNLESS_CERTIFIED: dict[str, ClaimType] = {
    "preferential attachment": ClaimType.GENERATIVE_MECHANISM,
    "preferential-attachment": ClaimType.GENERATIVE_MECHANISM,
    "scale-free": ClaimType.GENERATIVE_MECHANISM,
    "scale free": ClaimType.GENERATIVE_MECHANISM,
    "ba network": ClaimType.GENERATIVE_MECHANISM,
    "ba-similar": ClaimType.GENERATIVE_MECHANISM,
    "barabasi-albert structure": ClaimType.GENERATIVE_MECHANISM,
    "bank-to-bank exposures": ClaimType.LIQUIDITY_CONTAGION_MODEL,
    "interbank exposures": ClaimType.LIQUIDITY_CONTAGION_MODEL,
    "contagion": ClaimType.LIQUIDITY_CONTAGION_MODEL,
}

_EXPLORATORY_TAG: str = "[EXPLORATORY]"
_SENTENCE_SPLIT: re.Pattern[str] = re.compile(r"(?<=[.!?;])\s+")


@dataclass
class ClaimBoundaryViolation(Exception):
    forbidden_phrases_found: list[tuple[str, ClaimType]] = field(default_factory=list)
    sentences_without_anchor: list[str] = field(default_factory=list)

    def __str__(self) -> str:
        parts: list[str] = []
        if self.forbidden_phrases_found:
            phr = ", ".join(f"{p!r} ({t.value})" for p, t in self.forbidden_phrases_found)
            parts.append(f"forbidden phrases without certificate: {phr}")
        if self.sentences_without_anchor:
            parts.append(
                f"sentences without ValidatedFinding ID or [EXPLORATORY] tag: "
                f"{self.sentences_without_anchor[:5]}{'...' if len(self.sentences_without_anchor) > 5 else ''}"
            )
        return "; ".join(parts) or "ClaimBoundaryViolation"


_UNICODE_DASH_TO_ASCII: dict[int, int] = {
    0x2010: ord("-"),  # hyphen
    0x2011: ord("-"),  # non-breaking hyphen
    0x2012: ord("-"),  # figure dash
    0x2013: ord("-"),  # en-dash
    0x2014: ord("-"),  # em-dash
    0x2015: ord("-"),  # horizontal bar
    0x2212: ord("-"),  # minus sign
}


def normalize_claim_text(text: str) -> str:
    """Lower-case, collapse whitespace, and fold all Unicode dash variants
    to ASCII hyphen so multi-line / typographic phrases still match.

    Iter-4 audit: previously ``preferential—attachment`` (em-dash U+2014)
    bypassed the forbidden-phrase filter because the registry uses ASCII
    hyphens. The fold table covers the seven dash codepoints in common
    typography.
    """
    folded = text.translate(_UNICODE_DASH_TO_ASCII)
    return re.sub(r"\s+", " ", folded.lower()).strip()


def find_forbidden_phrases(text: str) -> list[tuple[str, ClaimType]]:
    norm = normalize_claim_text(text)
    return [
        (phrase, claim_type)
        for phrase, claim_type in FORBIDDEN_UNLESS_CERTIFIED.items()
        if normalize_claim_text(phrase) in norm
    ]


def _split_sentences(text: str) -> list[str]:
    """Conservative sentence split on ., !, ?, ;.

    Skips empty fragments. Bullet-list lines are treated as sentences.
    """
    parts: list[str] = []
    for line in text.splitlines():
        stripped = line.strip().lstrip("-*0123456789.) ")
        if not stripped:
            continue
        if stripped.startswith("#"):
            continue  # markdown header — skipped
        if stripped.startswith(("|", "```", "<!--")):
            continue
        parts.extend(s.strip() for s in _SENTENCE_SPLIT.split(stripped) if s.strip())
    return parts


def claim_boundary_check(
    summary_md: str,
    *,
    certified_claim_types: Iterable[ClaimType] = (),
    validated_finding_ids: Iterable[str] = (),
    require_anchor_per_sentence: bool = True,
) -> None:
    """Raise ``ClaimBoundaryViolation`` if any rule is breached.

    * Phrase rule: every forbidden phrase requires the matching claim
      type in ``certified_claim_types``.
    * Anchor rule: every sentence must contain at least one validated
      finding ID OR the ``[EXPLORATORY]`` tag.
    """
    certs = set(certified_claim_types)
    finding_ids = list(validated_finding_ids)
    hits = find_forbidden_phrases(summary_md)
    forbidden_uncertified = [
        (phrase, claim_type) for phrase, claim_type in hits if claim_type not in certs
    ]
    violations: list[str] = []
    if require_anchor_per_sentence:
        for sentence in _split_sentences(summary_md):
            if _EXPLORATORY_TAG.lower() in sentence.lower():
                continue
            if any(fid in sentence for fid in finding_ids):
                continue
            violations.append(sentence)
    if forbidden_uncertified or violations:
        raise ClaimBoundaryViolation(
            forbidden_phrases_found=forbidden_uncertified,
            sentences_without_anchor=violations,
        )
