# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Typed model for ``.claude/commit_acceptors/*.yaml``.

A commit acceptor binds a code change to a falsifiable promise: the
diff scope (allowed / forbidden paths), required Python symbols,
expected signal, an inverse-falsifier probe, and a rollback path. The
``tools/commit_acceptor/validate_commit_acceptor.py`` validator
consumes one acceptor per changed file and enforces:

* every changed code file appears in some acceptor's ``changed_files``;
* no file imports from a forbidden path (per
  ``commit_acceptor_policy.yaml::forbidden_import_patterns``);
* the falsifier exits non-zero only when the invariant is violated.

The Pydantic v2 model below mirrors the YAML shape verbatim.
``extra='forbid'`` guards against schema drift; loaders raise
``pydantic.ValidationError`` on any mistyped field.
"""

from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Any

import yaml
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    ValidationError,
    field_validator,
)
from typing_extensions import Annotated

# Acceptor IDs use a relaxed pattern compared to claim IDs: existing
# canonical files include uppercase prefixes (e.g. "T2b-stuart-landau-es")
# from the physics-law naming convention. The lowercase-only ledger
# constraint is preserved on ClaimEntry; acceptor IDs accept any
# alphanumeric segments separated by dashes.
ACCEPTOR_ID_PATTERN = r"^[A-Za-z0-9]+(?:-[A-Za-z0-9]+)*$"
AcceptorId = Annotated[str, StringConstraints(pattern=ACCEPTOR_ID_PATTERN, min_length=1)]


class Status(str, Enum):
    """Acceptor lifecycle status.

    ACTIVE        — currently enforced.
    DRAFT         — author iterating; gate is permissive.
    VERIFIED      — landed and the falsifier has fired at least once.
    REJECTED      — superseded; kept as audit trail.
    """

    ACTIVE = "ACTIVE"
    DRAFT = "DRAFT"
    VERIFIED = "VERIFIED"
    REJECTED = "REJECTED"


class ClaimType(str, Enum):
    """Maps the acceptor to a policy file-count cap.

    ``commit_acceptor_policy.yaml::max_changed_files_by_claim_type``
    enforces a per-type ceiling so a 50-file refactor cannot ship
    under ``correctness`` (cap 12) without explicit re-classification.
    """

    CORRECTNESS = "correctness"
    DETERMINISM = "determinism"
    FAIL_CLOSED = "fail_closed"
    SECURITY = "security"
    PERFORMANCE = "performance"
    GOVERNANCE = "governance"
    REFACTOR = "refactor"
    DOCUMENTATION = "documentation"
    CHORE = "chore"


class MemoryUpdateType(str, Enum):
    APPEND = "append"
    REPLACE = "replace"
    NONE = "none"


class ChangedFile(BaseModel):
    """One entry under ``diff_scope.changed_files:``.

    Schema is ``{path, sha256?}`` per the acceptor template: ``sha256`` is an
    optional content pin (used by VERIFIED acceptors; absent/None for DRAFT).
    """

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    path: str = Field(min_length=1)
    sha256: str | None = None


class DiffScope(BaseModel):
    """The set of paths the acceptor binds.

    ``changed_files``     — every file the PR is allowed to modify; the
                            validator rejects any modified file outside
                            this list (or another acceptor's list).
    ``forbidden_paths``   — extra path-prefix denylist on top of the
                            global policy. Any modified file under one
                            of these prefixes is rejected.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    changed_files: tuple[ChangedFile, ...] = Field(min_length=1)
    forbidden_paths: tuple[str, ...] = Field(default_factory=tuple)


class AcceptorFalsifier(BaseModel):
    """Inverse probe: the acceptor's invariant is broken iff this exits 0.

    Distinct from the claim-ledger ``Falsifier`` (which points at a
    pytest node). An acceptor falsifier is a one-shot shell command;
    its non-zero exit means the invariant holds. Used by
    ``compute_fps_audit`` and the local pre-PR loop.
    """

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    command: str = Field(min_length=1)
    description: str = Field(min_length=1)


class EvidenceEntry(BaseModel):
    """Optional evidence attachment under ``evidence:``."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    path: str = Field(min_length=1)
    sha256: str | None = None


class CommitAcceptor(BaseModel):
    """Top-level shape of one acceptor YAML file.

    Field-by-field mirror of the on-disk format. The ``model_config``
    ``extra='forbid'`` guarantees that any unknown top-level key
    raises a structured error rather than being silently dropped.
    """

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    id: AcceptorId
    status: Status
    claim_type: ClaimType
    promise: str = Field(min_length=1)
    diff_scope: DiffScope
    expected_signal: str = Field(min_length=1)
    measurement_command: str = Field(min_length=1)
    signal_artifact: str = Field(min_length=1)
    falsifier: AcceptorFalsifier
    rollback_command: str = Field(min_length=1)
    rollback_verification_command: str = Field(min_length=1)
    memory_update_type: MemoryUpdateType = MemoryUpdateType.APPEND
    ledger_path: str = Field(min_length=1)
    report_path: str = Field(min_length=1)
    required_python_symbols: tuple[str, ...] = Field(default_factory=tuple)
    evidence: tuple[EvidenceEntry, ...] = Field(default_factory=tuple)

    @field_validator("required_python_symbols", mode="before")
    @classmethod
    def _reject_mapping_symbol_form(cls, value: Any) -> Any:
        # Forward-proof against the most common authoring drift: a list of
        # ``{module: ..., symbol: ...}`` mappings instead of canonical
        # ``file::symbol`` strings. Pydantic's native error for this is the
        # opaque ``Input should be a valid string`` — which once cost a
        # 46-minute coverage lane to diagnose (stale run 27294986826).
        # We intercept the structured form *before* coercion and re-emit a
        # message that names the canonical shape, so the next drift fails
        # legibly in seconds. Fail-closed: we do NOT silently normalize —
        # one canonical on-disk form is the invariant.
        if isinstance(value, (list, tuple)):
            for i, item in enumerate(value):
                if isinstance(item, dict):
                    module = item.get("module", "<module>")
                    symbol = item.get("symbol", "<symbol>")
                    raise ValueError(
                        f"required_python_symbols.{i} is a mapping "
                        f"{{module, symbol}}; the canonical form is a single "
                        f'"file::symbol" string. Replace with '
                        f'"{module}::{symbol}".'
                    )
        return value

    @field_validator("required_python_symbols")
    @classmethod
    def _symbol_shape(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        # Accept either pytest-style file::symbol or a bare qualified name
        # (e.g. ``module.ClassName``). The historical corpus contains
        # both forms; the AST audit in validate_commit_acceptor.py handles
        # them uniformly via attribute lookup.
        for sym in value:
            if not sym or sym.isspace():
                raise ValueError(f"required_python_symbol entry must be non-empty, got {sym!r}")
        return value

    @property
    def changed_paths(self) -> tuple[str, ...]:
        return tuple(cf.path for cf in self.diff_scope.changed_files)


def load_commit_acceptor(path: str | Path) -> CommitAcceptor:
    """Parse + validate one acceptor YAML file."""
    raw: Any = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"{path}: top-level must be a mapping, got {type(raw).__name__}")
    try:
        return CommitAcceptor.model_validate(raw)
    except ValidationError as exc:
        # Name the offending file in the message itself; pydantic's default
        # surfaces only the field path, leaving the operator to grep across
        # 200+ acceptors to find which file drifted.
        raise ValueError(f"{path}: invalid commit acceptor: {exc}") from exc


def load_all_commit_acceptors(directory: str | Path) -> tuple[CommitAcceptor, ...]:
    """Load every ``*.yaml`` under ``directory`` (deterministic order)."""
    root = Path(directory)
    if not root.is_dir():
        raise NotADirectoryError(root)
    acceptors: list[CommitAcceptor] = []
    for yaml_path in sorted(root.glob("*.yaml")):
        acceptors.append(load_commit_acceptor(yaml_path))
    seen: set[str] = set()
    for acc in acceptors:
        if acc.id in seen:
            raise ValueError(f"duplicate acceptor id: {acc.id}")
        seen.add(acc.id)
    return tuple(acceptors)


__all__ = [
    "AcceptorFalsifier",
    "ChangedFile",
    "ClaimType",
    "CommitAcceptor",
    "DiffScope",
    "EvidenceEntry",
    "MemoryUpdateType",
    "Status",
    "load_all_commit_acceptors",
    "load_commit_acceptor",
]
