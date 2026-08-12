# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Validation and quality controls for search results."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Mapping, Sequence
from urllib.parse import urlparse

from .models import Citation, CompletenessReport, DocumentMetadata, SearchResult


class LinkValidator:
    """Validate outbound citations."""

    def __init__(self, allowed_schemes: Sequence[str] | None = None) -> None:
        self._allowed_schemes = tuple(allowed_schemes or ("http", "https"))

    def is_valid(self, url: str) -> bool:
        parsed = urlparse(url)
        if not parsed.scheme or not parsed.netloc:
            return False
        return parsed.scheme in self._allowed_schemes


class CitationBuilder:
    """Construct citation records from metadata."""

    def __init__(self, link_validator: LinkValidator | None = None) -> None:
        self._link_validator = link_validator or LinkValidator()

    def build(self, metadata: DocumentMetadata) -> Citation | None:
        url = metadata.attributes.get("url") if metadata.attributes else None
        title = (
            metadata.attributes.get("title", metadata.document_id)
            if metadata.attributes
            else metadata.document_id
        )
        if not url or not self._link_validator.is_valid(url):
            return None
        return Citation(
            document_id=metadata.document_id,
            url=url,
            title=title,
            accessed_at=datetime.now(timezone.utc),
        )


class FreshnessPolicy:
    """Score documents by freshness."""

    def __init__(self, half_life_days: float = 30.0) -> None:
        if half_life_days <= 0:
            raise ValueError("half_life_days must be positive")
        self._half_life_days = half_life_days

    def score(
        self, metadata: DocumentMetadata, horizon_days: int | None = None
    ) -> float:
        now = datetime.now(timezone.utc)
        age_days = (now - metadata.updated_at).total_seconds() / 86400
        if horizon_days is not None and age_days > horizon_days:
            return 0.0
        decay = 0.5 ** (age_days / self._half_life_days)
        return float(decay)


class CompletenessController:
    """Assess coverage of search results."""

    def __init__(
        self, required_tags_by_query: Mapping[str, Sequence[str]] | None = None
    ) -> None:
        self._required_tags_by_query = required_tags_by_query or {}

    def evaluate(
        self, query: str, results: Sequence[SearchResult]
    ) -> CompletenessReport:
        required_tags = set(self._required_tags_by_query.get(query, ()))
        present_tags = {tag for result in results for tag in result.metadata.tags}
        missing = sorted(required_tags - present_tags)
        stale = [result.document_id for result in results if result.score <= 0]
        return CompletenessReport(
            total_results=len(results),
            missing_tags=missing,
            stale_results=tuple(stale),
        )
