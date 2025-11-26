"""Local model and experiment registry utilities.

This module provides a small, file-backed registry for experiment runs.  The
registry stores training parameters, metrics, and rich artifact metadata for
each run while automatically deriving audit trails that make it simple to
inspect how hyperparameters and outcomes evolved across iterations.

The design favours readability and explicitness: records are represented with
Pydantic models for type safety, and metadata is stored as JSON alongside the
materialised artifacts.  This keeps the registry self-contained and portable
while enabling deterministic reproduction of previous results.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from threading import RLock
from typing import Any, Dict, Iterable, Iterator, List, Mapping
from uuid import uuid4

from pydantic import BaseModel, Field

__all__ = [
    "ArtifactSpec",
    "AuditChange",
    "AuditDelta",
    "AuditTrail",
    "ExperimentRun",
    "ModelRegistry",
]


@dataclass(slots=True)
class ArtifactSpec:
    """User-supplied description of an artifact to persist in the registry."""

    path: Path
    name: str | None = None
    kind: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def resolved_name(self) -> str:
        """Return the concrete name that should be used when storing the artifact."""

        candidate = self.name or self.path.name
        if not candidate:
            raise ValueError("Artifact name must not be empty")

        candidate_path = Path(candidate)
        if candidate_path.is_absolute():
            raise ValueError(
                f"Artifact name '{candidate}' must not be an absolute path"
            )

        normalised = candidate_path.name
        if normalised in {"", ".", ".."}:
            raise ValueError(f"Artifact name '{candidate}' is not valid")

        if normalised != candidate:
            raise ValueError(
                f"Artifact name '{candidate}' must not contain path separators or parent traversals"
            )

        return normalised


class ArtifactRecord(BaseModel):
    """Metadata describing a stored artifact."""

    name: str
    stored_path: Path
    original_path: Path
    checksum: str
    kind: str | None = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(tz=timezone.utc))

    def absolute_path(self, base_dir: Path) -> Path:
        """Resolve the absolute path of the stored artifact on disk."""

        return base_dir / self.stored_path


class AuditChange(BaseModel):
    """Represents a single change entry in an audit diff."""

    key: str
    previous: Any
    current: Any


class AuditDelta(BaseModel):
    """Group of additions, removals, and updates for a mapping-like structure."""

    added: Dict[str, Any] = Field(default_factory=dict)
    removed: Dict[str, Any] = Field(default_factory=dict)
    changed: List[AuditChange] = Field(default_factory=list)

    def is_empty(self) -> bool:
        """Return ``True`` when no changes are recorded."""

        return not (self.added or self.removed or self.changed)


class AuditTrail(BaseModel):
    """Audit information comparing the run with a previous reference run."""

    reference_run_id: str | None = None
    hyperparameters: AuditDelta | None = None
    metrics: AuditDelta | None = None


class ExperimentRun(BaseModel):
    """Immutable record capturing the outcome of a single experiment run."""

    id: str
    experiment: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(tz=timezone.utc))
    parameters: Dict[str, Any] = Field(default_factory=dict)
    metrics: Dict[str, Any] = Field(default_factory=dict)
    artifacts: List[ArtifactRecord] = Field(default_factory=list)
    tags: List[str] = Field(default_factory=list)
    notes: str | None = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    audit: AuditTrail = Field(default_factory=AuditTrail)

    model_config = {"frozen": True}

    def reproduction_bundle(self, base_dir: Path) -> Dict[str, Any]:
        """Build a structured bundle with everything needed to reproduce the run."""

        artifacts = [
            {
                "name": artifact.name,
                "path": str(artifact.absolute_path(base_dir)),
                "checksum": artifact.checksum,
                "kind": artifact.kind,
            }
            for artifact in self.artifacts
        ]
        return {
            "experiment": self.experiment,
            "run_id": self.id,
            "created_at": self.created_at.isoformat(),
            "parameters": self.parameters,
            "metrics": self.metrics,
            "artifacts": artifacts,
            "tags": self.tags,
            "notes": self.notes,
            "metadata": self.metadata,
        }


class RegistryIndex(BaseModel):
    """Compact lookup structure that maps run ids to their metadata on disk."""

    experiments: Dict[str, List[str]] = Field(default_factory=dict)
    runs: Dict[str, str] = Field(default_factory=dict)

    def register(self, run: ExperimentRun, metadata_path: Path) -> None:
        entries = self.experiments.setdefault(run.experiment, [])
        entries.append(run.id)
        self.runs[run.id] = str(metadata_path)

    def list_runs(self, experiment: str) -> List[str]:
        return list(self.experiments.get(experiment, ()))


class ModelRegistry:
    """A minimal, file-backed registry for experiments and model artifacts."""

    def __init__(self, base_dir: Path) -> None:
        self._base_dir = Path(base_dir).expanduser().resolve()
        self._experiments_dir = self._base_dir / "experiments"
        self._index_path = self._base_dir / "index.json"
        self._lock = RLock()
        self._ensure_structure()

    @property
    def base_dir(self) -> Path:
        return self._base_dir

    def register_run(
        self,
        experiment: str,
        *,
        parameters: Mapping[str, Any],
        metrics: Mapping[str, Any] | None = None,
        artifacts: Iterable[ArtifactSpec | Path | tuple[str, Path]] = (),
        tags: Iterable[str] = (),
        notes: str | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> ExperimentRun:
        """Persist a new experiment run in the registry."""

        run_id = uuid4().hex
        run_dir = self._experiments_dir / experiment / run_id
        with self._lock:
            run_dir.mkdir(parents=True, exist_ok=False)
            stored_artifacts = list(self._store_artifacts(run_dir, artifacts))
            metrics_payload = _normalise_mapping(metrics or {})
            parameters_payload = _normalise_mapping(parameters)
            metadata_payload = _normalise_mapping(metadata or {})
            tags_payload = sorted(set(tags))

            previous_run = self._load_latest_run(experiment)
            audit_trail = self._build_audit(
                previous_run, parameters_payload, metrics_payload
            )

            run = ExperimentRun(
                id=run_id,
                experiment=experiment,
                parameters=parameters_payload,
                metrics=metrics_payload,
                artifacts=stored_artifacts,
                tags=tags_payload,
                notes=notes,
                metadata=metadata_payload,
                audit=audit_trail,
            )

            metadata_path = run_dir / "run.json"
            metadata_path.write_text(
                run.model_dump_json(indent=2, exclude_none=True, by_alias=True)
            )

            index = self._load_index()
            relative_metadata_path = metadata_path.relative_to(self._base_dir)
            index.register(run, relative_metadata_path)
            self._save_index(index)
            return run

    def get_run(self, run_id: str) -> ExperimentRun:
        """Retrieve a specific run by its identifier."""

        with self._lock:
            index = self._load_index()
            relative = index.runs.get(run_id)
            if relative is None:
                raise KeyError(f"Run '{run_id}' is not present in the registry")
            metadata_path = self._base_dir / Path(relative)
            if not metadata_path.exists():
                raise FileNotFoundError(
                    f"Metadata for run '{run_id}' is missing: {metadata_path}"
                )
            return ExperimentRun.model_validate_json(metadata_path.read_text())

    def list_experiments(self) -> List[str]:
        """Return the names of all experiments known to the registry."""

        with self._lock:
            index = self._load_index()
            return sorted(index.experiments.keys())

    def history(self, experiment: str) -> List[ExperimentRun]:
        """Return all runs for an experiment ordered chronologically."""

        with self._lock:
            index = self._load_index()
            run_ids = index.list_runs(experiment)
            runs = [self.get_run(run_id) for run_id in run_ids]
            return sorted(runs, key=lambda run: run.created_at)

    def latest_run(self, experiment: str) -> ExperimentRun | None:
        """Return the latest run for the experiment, if any."""

        with self._lock:
            index = self._load_index()
            run_ids = index.list_runs(experiment)
            if not run_ids:
                return None
            return self.get_run(run_ids[-1])

    def reproduction_plan(self, run_id: str) -> Dict[str, Any]:
        """Convenience wrapper around :meth:`ExperimentRun.reproduction_bundle`."""

        run = self.get_run(run_id)
        return run.reproduction_bundle(self._base_dir)

    def _store_artifacts(
        self, run_dir: Path, artifacts: Iterable[ArtifactSpec | Path | tuple[str, Path]]
    ) -> Iterator[ArtifactRecord]:
        artifact_dir = run_dir / "artifacts"
        artifact_dir.mkdir(parents=True, exist_ok=True)
        for spec in self._normalise_artifacts(artifacts):
            if not spec.path.exists():
                raise FileNotFoundError(f"Artifact '{spec.path}' does not exist")
            resolved_name = spec.resolved_name()
            target = artifact_dir / resolved_name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(spec.path, target)
            checksum = _file_checksum(target)
            yield ArtifactRecord(
                name=resolved_name,
                stored_path=target.relative_to(self._base_dir),
                original_path=spec.path.resolve(),
                checksum=checksum,
                kind=spec.kind,
                metadata=dict(spec.metadata),
            )

    def _normalise_artifacts(
        self, artifacts: Iterable[ArtifactSpec | Path | tuple[str, Path]]
    ) -> Iterator[ArtifactSpec]:
        for item in artifacts:
            if isinstance(item, ArtifactSpec):
                yield item
            elif isinstance(item, tuple):
                name, path = item
                yield ArtifactSpec(path=Path(path), name=name)
            else:
                yield ArtifactSpec(path=Path(item))

    def _load_index(self) -> RegistryIndex:
        if not self._index_path.exists():
            return RegistryIndex()
        return RegistryIndex.model_validate_json(self._index_path.read_text())

    def _save_index(self, index: RegistryIndex) -> None:
        self._index_path.write_text(index.model_dump_json(indent=2))

    def _ensure_structure(self) -> None:
        self._experiments_dir.mkdir(parents=True, exist_ok=True)
        if not self._index_path.exists():
            self._save_index(RegistryIndex())

    def _load_latest_run(self, experiment: str) -> ExperimentRun | None:
        index = self._load_index()
        run_ids = index.list_runs(experiment)
        if not run_ids:
            return None
        return self.get_run(run_ids[-1])

    def _build_audit(
        self,
        previous: ExperimentRun | None,
        parameters: Mapping[str, Any],
        metrics: Mapping[str, Any],
    ) -> AuditTrail:
        if previous is None:
            return AuditTrail(reference_run_id=None)
        parameter_delta = _diff_mappings(parameters, previous.parameters)
        metric_delta = _diff_mappings(metrics, previous.metrics)
        return AuditTrail(
            reference_run_id=previous.id,
            hyperparameters=None if parameter_delta.is_empty() else parameter_delta,
            metrics=None if metric_delta.is_empty() else metric_delta,
        )


def _normalise_mapping(mapping: Mapping[str, Any]) -> Dict[str, Any]:
    """Recursively convert a mapping into a JSON-serialisable dictionary."""

    def _coerce(value: Any) -> Any:
        if isinstance(value, Mapping):
            return {str(k): _coerce(v) for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            return [_coerce(item) for item in value]
        if isinstance(value, Path):
            return str(value)
        if isinstance(value, (datetime,)):
            return value.isoformat()
        return value

    return {str(key): _coerce(val) for key, val in mapping.items()}


def _flatten_mapping(mapping: Mapping[str, Any], *, prefix: str = "") -> Dict[str, Any]:
    flat: Dict[str, Any] = {}
    for key, value in mapping.items():
        path = f"{prefix}.{key}" if prefix else str(key)
        if isinstance(value, Mapping):
            flat.update(_flatten_mapping(value, prefix=path))
        else:
            flat[path] = value
    return flat


def _diff_mappings(
    current: Mapping[str, Any], previous: Mapping[str, Any]
) -> AuditDelta:
    current_flat = _flatten_mapping(current)
    previous_flat = _flatten_mapping(previous)

    added = {k: current_flat[k] for k in current_flat.keys() - previous_flat.keys()}
    removed = {k: previous_flat[k] for k in previous_flat.keys() - current_flat.keys()}
    changed = [
        AuditChange(key=key, previous=previous_flat[key], current=current_flat[key])
        for key in current_flat.keys() & previous_flat.keys()
        if not _values_equal(current_flat[key], previous_flat[key])
    ]
    return AuditDelta(added=added, removed=removed, changed=changed)


def _values_equal(first: Any, second: Any) -> bool:
    if isinstance(first, float) and isinstance(second, float):
        return abs(first - second) <= 1e-12
    return first == second


def _file_checksum(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(4096), b""):
            digest.update(chunk)
    return digest.hexdigest()
