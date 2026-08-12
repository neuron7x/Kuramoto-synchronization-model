# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""L2 Ricci evidence-bearing session protocol — recorder and gate.

The README pins L2 order-book (depth-5) Ricci microstructure at ``HYPOTHESIS``
and forbids promotion until a real depth-5 session with a real data hash,
replay, baseline, null model, falsifier, and negative evidence is recorded.
This tool is the executable counterpart of
``docs/research/l2_ricci_evidence_protocol.md`` and the machine that produces
and checks artifacts against
``schemas/research/l2_ricci_session.schema.json``.

Two surfaces:

* ``--dry-run`` emits a schema-valid *skeleton* (zero hashes,
  ``semantic_validation_status: PLACEHOLDER``) to stdout or ``--out``. The
  skeleton has the right shape but, by construction, is honest about carrying
  no real data — it can never claim evidence.
* ``--artifact PATH`` validates a recorded session for SHAPE (schema) and then
  for PROMOTION-READINESS (the semantic preconditions a real evidence session
  must satisfy). Validation is fail-closed.

The validator never fabricates evidence: a skeleton is always
``PLACEHOLDER`` and is never promotable, and a real artifact is promotable only
when every required provenance, baseline, null, falsifier, replay, and
negative-evidence field is present and consistent.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = ROOT / "schemas" / "research" / "l2_ricci_session.schema.json"
REGISTRY_PATH = ROOT / "config" / "research" / "l2_ricci_registry.yaml"

SCHEMA_ID = "https://schemas.neuron7xlab.org/research/l2_ricci_session.schema.json"
ZERO_SHA256 = "0" * 64
ZERO_GIT_SHA = "0" * 40

#: Falsification axes a promotable session must have attempted. A real
#: depth-5 Ricci evidence claim must show it tried, at minimum, to kill the
#: signal with a null model and with a forward-looking (no-lookahead) check.
REQUIRED_FALSIFICATION_CLAIMS: frozenset[str] = frozenset({"null_model", "lookahead"})

#: Statuses that assert evidentiary weight and therefore demand real inputs.
EVIDENCE_STATUSES: frozenset[str] = frozenset({"PASS"})

#: A replay_command is executable only if it actually invokes the recorder.
#: Anything else (a prose note, a bare path, a placeholder stub) is non-runnable
#: and must instead be honestly flagged replay_blocked.
_EXECUTABLE_REPLAY_PREFIXES: tuple[str, ...] = ("python ", "python3 ")


def _shared_validator() -> Any:
    """Path-load the canonical schema validator (single source of shape rules).

    Reuses ``validate_ricci_artifact_schema`` so this tool and the existing
    Ricci artifact gate share one jsonschema/fallback implementation rather
    than forking a second, drift-prone validator.
    """
    module_path = Path(__file__).resolve().parent / "validate_ricci_artifact_schema.py"
    spec = importlib.util.spec_from_file_location("_l2_ricci_schema_validator", module_path)
    if spec is None or spec.loader is None:  # pragma: no cover - import plumbing
        raise RuntimeError(f"cannot load schema validator at {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _registry_checker() -> Any:
    """Path-load the registry-resolution checker (single source of the rule).

    Reuses ``check_l2_registry_refs.resolve_session_refs`` so this gate and the
    standalone ``check_l2_registry_refs.py`` tool share one resolver rather than
    forking a second, drift-prone copy of the baseline/null/falsifier rule.
    """
    module_path = Path(__file__).resolve().parent / "check_l2_registry_refs.py"
    spec = importlib.util.spec_from_file_location("_l2_ricci_registry_refs", module_path)
    if spec is None or spec.loader is None:  # pragma: no cover - import plumbing
        raise RuntimeError(f"cannot load registry checker at {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def skeleton() -> dict[str, Any]:
    """Return a schema-valid, honestly-placeholder L2 Ricci session skeleton.

    Hashes are zero and ``semantic_validation_status`` is ``PLACEHOLDER`` so the
    skeleton validates against the schema yet is, by construction, barred from
    promotion. It is a fill-in-the-blanks template, not evidence.
    """
    return {
        "conforms_to": SCHEMA_ID,
        "git_sha": ZERO_GIT_SHA,
        "data_sha256": ZERO_SHA256,
        "config_sha256": ZERO_SHA256,
        "venue": "exchange",
        "symbol": "SYMBOL",
        "depth_level": 5,
        "session_start_utc": "1970-01-01T00:00:00Z",
        "session_end_utc": "1970-01-01T00:00:00Z",
        "baseline_id": "baseline_unset",
        "null_model_id": "null_model_unset",
        "falsifier_id": "falsifier_unset",
        "replay_command": "<no real depth-5 capture to recompute; fill in once recorded>",
        "replay_blocked": True,
        "negative_evidence": [
            {
                "claim": "depth-5 Ricci information coefficient survives a null model",
                "outcome": "BLOCKED",
                "detail": (
                    "Placeholder skeleton: no real depth-5 capture is present "
                    "(data_sha256 is zero), so no falsification attempt could run."
                ),
            }
        ],
        "semantic_validation_status": "PLACEHOLDER",
    }


def _parse_z_datetime(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.endswith("Z"):
        return None
    try:
        return datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError:
        return None


def _is_real_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and value != ZERO_SHA256
        and re.fullmatch(r"[0-9a-f]{64}", value) is not None
    )


def _is_real_git_sha(value: object) -> bool:
    return (
        isinstance(value, str)
        and value != ZERO_GIT_SHA
        and re.fullmatch(r"[0-9a-f]{40}", value) is not None
    )


def validate_session_semantics(artifact: dict[str, Any], artifact_path: Path) -> list[str]:
    """Return promotion-readiness errors for a *schema-valid* session artifact.

    Schema validity proves the artifact has the right fields. It cannot stop a
    hand-typed skeleton with zero hashes from claiming ``semantic_validation_status:
    PASS``, nor enforce that the session start precedes its end, nor that the
    declared null/lookahead falsification axes were actually attempted. These are
    the rules that separate a real evidence session from a schema-shaped fake.
    """
    errors: list[str] = []
    status = artifact.get("semantic_validation_status")
    claims_evidence = status in EVIDENCE_STATUSES
    replay_blocked = bool(artifact.get("replay_blocked", False))

    if claims_evidence:
        if not _is_real_git_sha(artifact.get("git_sha")):
            errors.append(
                f"{artifact_path}: git_sha: evidence session requires a real (non-zero) git sha"
            )
        if not _is_real_sha256(artifact.get("data_sha256")):
            errors.append(
                f"{artifact_path}: data_sha256: evidence session requires a real (non-zero) data hash"
            )
        if not _is_real_sha256(artifact.get("config_sha256")):
            errors.append(
                f"{artifact_path}: config_sha256: evidence session requires a real (non-zero) config hash"
            )
        # An evidence session must be replayable: the command has to actually
        # invoke the recorder, and a session that flags its replay as blocked
        # cannot, by definition, be evidence (a blocked replay is not a replay).
        if replay_blocked:
            errors.append(
                f"{artifact_path}: replay_blocked: an evidence session cannot have a blocked replay"
            )
        replay = artifact.get("replay_command")
        if not isinstance(replay, str) or not replay.startswith(_EXECUTABLE_REPLAY_PREFIXES):
            errors.append(
                f"{artifact_path}: replay_command: evidence session requires an executable "
                "'python'/'python3' replay command"
            )
        # baseline / null / falsifier ids must resolve to the reference registry.
        registry = _registry_checker()
        sections = registry.load_registry(REGISTRY_PATH)
        errors.extend(registry.resolve_session_refs(artifact, sections, artifact_path))

    start = _parse_z_datetime(artifact.get("session_start_utc"))
    end = _parse_z_datetime(artifact.get("session_end_utc"))
    if start is not None and end is not None and end < start:
        errors.append(f"{artifact_path}: session_end_utc: must be at or after session_start_utc")

    negative_evidence = artifact.get("negative_evidence")
    if isinstance(negative_evidence, list):
        # Map negative-evidence text to required falsification axes by substring,
        # tolerant of space- or underscore-separated phrasing, so a
        # 'permutation null model' entry satisfies the 'null_model' axis.
        text = " ".join(
            str(entry.get("claim", "")) + " " + str(entry.get("detail", ""))
            for entry in negative_evidence
            if isinstance(entry, dict)
        ).lower()
        normalized = re.sub(r"[\s_]+", "_", text)
        attempted_axes = {axis for axis in REQUIRED_FALSIFICATION_CLAIMS if axis in normalized}
        if claims_evidence:
            missing = REQUIRED_FALSIFICATION_CLAIMS - attempted_axes
            if missing:
                errors.append(
                    f"{artifact_path}: negative_evidence: evidence session is missing required "
                    f"falsification axes: {sorted(missing)}"
                )
            unattacked = all(
                entry.get("outcome") == "BLOCKED"
                for entry in negative_evidence
                if isinstance(entry, dict)
            )
            if unattacked:
                errors.append(
                    f"{artifact_path}: negative_evidence: evidence session cannot consist only of "
                    "BLOCKED attempts (nothing was actually adversarially tested)"
                )

    if status == "PLACEHOLDER":
        # A placeholder is a schema-shaped skeleton with NO real data. A real
        # depth-5 fixture cannot run in placeholder mode: any real provenance
        # hash (data, config, or git) means this is not a placeholder and must
        # be re-labelled PENDING/PASS (or the hash zeroed). This forbids
        # dressing a real-data session as an inert skeleton to dodge the gates.
        if _is_real_sha256(artifact.get("data_sha256")):
            errors.append(
                f"{artifact_path}: semantic_validation_status: a PLACEHOLDER must not carry a real "
                "data hash (label it PENDING/PASS or zero the hash)"
            )
        if _is_real_sha256(artifact.get("config_sha256")):
            errors.append(
                f"{artifact_path}: semantic_validation_status: a PLACEHOLDER must not carry a real "
                "config hash (label it PENDING/PASS or zero the hash)"
            )
        if _is_real_git_sha(artifact.get("git_sha")):
            errors.append(
                f"{artifact_path}: semantic_validation_status: a PLACEHOLDER must not carry a real "
                "git sha (label it PENDING/PASS or zero the sha)"
            )

    # Replay honesty for any non-evidence session: a replay_command that is not
    # an executable recorder invocation must be explicitly flagged
    # replay_blocked. A command that neither runs nor admits it cannot run is a
    # silently-non-runnable command and is rejected.
    if not claims_evidence:
        replay = artifact.get("replay_command")
        executable = isinstance(replay, str) and replay.startswith(_EXECUTABLE_REPLAY_PREFIXES)
        if not executable and not replay_blocked:
            errors.append(
                f"{artifact_path}: replay_command: not an executable 'python'/'python3' command; "
                "set replay_blocked: true to declare it not-yet-runnable"
            )

    return errors


def validate_artifact(artifact_path: Path) -> list[str]:
    """Validate a session artifact for SHAPE (schema) then PROMOTION-READINESS."""
    validator = _shared_validator()
    schema_errors: list[str] = validator.validate_artifact(SCHEMA_PATH, artifact_path)
    if schema_errors:
        return schema_errors
    artifact = _load_json(artifact_path)
    if not isinstance(artifact, dict):  # pragma: no cover - schema already guards this
        return [f"{artifact_path}: <root>: expected object"]
    return validate_session_semantics(artifact, artifact_path)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Emit a schema-valid, honestly-placeholder session skeleton and exit.",
    )
    parser.add_argument(
        "--artifact",
        type=Path,
        default=None,
        help="Validate a recorded session artifact (shape + promotion-readiness).",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="With --dry-run, write the skeleton here instead of stdout.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)

    if args.dry_run:
        payload = skeleton()
        text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
        # Self-check: the emitted skeleton must be schema-valid.
        validator = _shared_validator()
        errors = validator.validate_artifact(SCHEMA_PATH, _SkeletonPath(payload))
        if errors:  # pragma: no cover - guards against schema/skeleton drift
            for error in errors:
                print(error, file=sys.stderr)
            return 1
        if args.out is not None:
            args.out.write_text(text, encoding="utf-8")
            print(f"Wrote schema-valid L2 Ricci session skeleton to {args.out}")
        else:
            sys.stdout.write(text)
        return 0

    if args.artifact is None:
        print(
            "run_l2_ricci_session: provide --dry-run to emit a skeleton or "
            "--artifact PATH to validate a session.",
            file=sys.stderr,
        )
        return 2

    failures = validate_artifact(args.artifact)
    if failures:
        for failure in failures:
            print(failure, file=sys.stderr)
        return 1
    print(f"Validated L2 Ricci session (shape + promotion-readiness): {args.artifact}")
    return 0


class _SkeletonPath:
    """In-memory path-like wrapper so the shared validator can read a dict.

    The shared validator reads artifacts from disk; for the --dry-run
    self-check we hand it the just-built skeleton without touching the
    filesystem by exposing the minimal ``read_text``/``str`` surface it uses.
    """

    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = payload

    def read_text(self, encoding: str = "utf-8") -> str:
        return json.dumps(self._payload)

    def __str__(self) -> str:
        return "<l2-ricci-session-skeleton>"


if __name__ == "__main__":
    raise SystemExit(main())
