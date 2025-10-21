from __future__ import annotations

"""Generator for Alembic migration templates."""

from typing import Any

from ..runtime.fingerprint import stable_hash
from .template import TemplateGenerator
from .base import GenerationRequest


class MigrationGenerator(TemplateGenerator):
    def build_context(self, request: GenerationRequest) -> dict[str, Any]:
        metadata = dict(request.metadata)
        fingerprint = stable_hash([str(sorted(request.sources.items()))])[:12]
        metadata.setdefault("revision_id", fingerprint)
        metadata.setdefault("down_revision", None)
        metadata.setdefault("branch_labels", None)
        metadata.setdefault("depends_on", None)
        return {"metadata": metadata}
