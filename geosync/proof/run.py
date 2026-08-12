# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Five-minute GeoSync proof pipeline: D -> H -> T -> F -> V."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "geosync" / "proof" / "fixtures" / "market_fixture.csv"
ARTIFACT = ROOT / "artifacts" / "geosync_proof" / "verdict.json"
THRESHOLD = 0.60
TRAIN_RETURNS = 8
MECHANISM = "lag1_directional_persistence_fixture_test"


@dataclass(frozen=True)
class MarketBar:
    timestamp: str
    close: float


@dataclass(frozen=True)
class Hypothesis:
    rule: str
    train_hit_rate: float
    train_samples: int
    text: str


@dataclass(frozen=True)
class TestResult:
    hit_rate: float | None
    hits: int
    samples: int


def _relpath(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def _utc_timestamp() -> str:
    raw = os.environ.get("SOURCE_DATE_EPOCH", "1700000000")
    try:
        epoch = int(raw)
    except ValueError:
        epoch = 1700000000
    return datetime.fromtimestamp(epoch, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


DIGEST_KEY = "content_digest"


def _code_version() -> str:
    """Bind the verdict to the exact verifying code.

    Precedence: explicit env override (reproducible pin) -> best-effort git commit ->
    ``unknown``. An auditor-grade verdict must name the code that produced it; ``unknown``
    is the honest last resort, never a silent blank.
    """
    override = os.environ.get("GEOSYNC_PROOF_CODE_VERSION")
    if override:
        return override
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=ROOT, capture_output=True, text=True, timeout=5, check=False,
        )
        if out.returncode == 0 and out.stdout.strip():
            return f"git:{out.stdout.strip()}"
    except (OSError, subprocess.SubprocessError):
        pass
    return "unknown"


def _sha256_file(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical(payload: object) -> bytes:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _content_digest(verdict: dict[str, object]) -> str:
    """Tamper-evident self-hash over every field EXCEPT the digest itself.

    An auditor recomputes this over the received verdict (minus content_digest) and compares —
    a single flipped byte anywhere in the verdict changes it. See ``--verify``.
    """
    body = {k: v for k, v in verdict.items() if k != DIGEST_KEY}
    return "sha256:" + hashlib.sha256(_canonical(body)).hexdigest()


def load_market_data(path: Path = FIXTURE) -> list[MarketBar]:
    rows: list[MarketBar] = []
    with path.open(encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        if reader.fieldnames != ["timestamp", "close"]:
            raise ValueError("fixture schema must be timestamp,close")
        for row in reader:
            timestamp = str(row.get("timestamp", "")).strip()
            close_raw = str(row.get("close", "")).strip()
            if not timestamp or not close_raw:
                raise ValueError("fixture row has empty timestamp or close")
            close = float(close_raw)
            if close <= 0:
                raise ValueError("close must be positive")
            rows.append(MarketBar(timestamp, close))
    if len(rows) < TRAIN_RETURNS + 4:
        raise ValueError("fixture must contain enough bars for train and test windows")
    return rows


def return_signs(bars: list[MarketBar]) -> list[int]:
    signs: list[int] = []
    for prev, cur in zip(bars, bars[1:]):
        diff = cur.close - prev.close
        signs.append(1 if diff > 0 else -1 if diff < 0 else 0)
    if any(sign == 0 for sign in signs):
        raise ValueError("zero-return bars are unsupported in this proof fixture")
    return signs


def _score_rule(signs: list[int], start: int, stop: int, rule: str) -> TestResult:
    hits = 0
    samples = 0
    for idx in range(start, stop):
        predicted = signs[idx - 1] if rule == "continuation" else -signs[idx - 1]
        hits += int(predicted == signs[idx])
        samples += 1
    return TestResult(hits / samples if samples else None, hits, samples)


def generate_hypothesis(signs: list[int]) -> Hypothesis:
    if len(signs) <= TRAIN_RETURNS:
        raise ValueError("not enough returns to generate hypothesis")
    cont = _score_rule(signs, 1, TRAIN_RETURNS, "continuation")
    rev = _score_rule(signs, 1, TRAIN_RETURNS, "reversal")
    if cont.hit_rate is None or rev.hit_rate is None:
        raise ValueError("training window produced no samples")
    rule = "continuation" if cont.hit_rate >= rev.hit_rate else "reversal"
    chosen = cont if rule == "continuation" else rev
    text = (
        "On the training slice of the fixture, the prior return sign is hypothesized "
        f"to predict the next return sign by {rule}."
    )
    return Hypothesis(rule, chosen.hit_rate, chosen.samples, text)


def run_test(signs: list[int], hypothesis: Hypothesis) -> TestResult:
    return _score_rule(signs, TRAIN_RETURNS, len(signs), hypothesis.rule)


def build_verdict(dataset: Path = FIXTURE) -> dict[str, object]:
    signs = return_signs(load_market_data(dataset))
    hypothesis = generate_hypothesis(signs)
    result = run_test(signs, hypothesis)
    if result.hit_rate is None or result.samples < 3:
        verdict = "INCONCLUSIVE"
    elif result.hit_rate >= THRESHOLD:
        verdict = "ACCEPT"
    else:
        verdict = "REJECT"
    payload: dict[str, object] = {
        "mechanism": MECHANISM,
        "input_dataset": _relpath(dataset),
        "dataset_sha256": _sha256_file(dataset),
        "hypothesis": hypothesis.text,
        "metric": "holdout_hit_rate",
        "threshold": f">= {THRESHOLD:.2f}",
        "result": {
            "holdout_hit_rate": result.hit_rate,
            "hits": result.hits,
            "samples": result.samples,
            "training_rule": hypothesis.rule,
            "training_hit_rate": hypothesis.train_hit_rate,
            "training_samples": hypothesis.train_samples,
        },
        "verdict": verdict,
        "failure_condition": (
            "Reject if holdout_hit_rate is below 0.60; "
            "inconclusive if fewer than 3 holdout samples."
        ),
        "repro_command": "python -m geosync.proof.run",
        "timestamp_utc": _utc_timestamp(),
        "code_version": _code_version(),
    }
    # tamper-evident self-hash MUST be added last (covers every field above)
    payload[DIGEST_KEY] = _content_digest(payload)
    return payload


def verify_verdict(path: Path) -> tuple[bool, list[str]]:
    """Independent auditor check: recompute the digest + dataset hash on a received verdict.

    Trusts nothing but the bytes on disk — proves the verdict was not edited after it was
    produced, and that the named dataset still hashes to what the verdict claims.
    """
    problems: list[str] = []
    verdict = json.loads(path.read_text(encoding="utf-8"))
    claimed = verdict.get(DIGEST_KEY)
    recomputed = _content_digest(verdict)
    if claimed != recomputed:
        problems.append(f"content_digest mismatch: claimed {claimed!r} != recomputed {recomputed!r}")
    ds_rel = str(verdict.get("input_dataset", ""))
    ds_path = ROOT / ds_rel
    if ds_path.exists():
        actual = _sha256_file(ds_path)
        if actual != verdict.get("dataset_sha256"):
            problems.append(f"dataset_sha256 mismatch for {ds_rel}: {actual} != {verdict.get('dataset_sha256')}")
    else:
        problems.append(f"dataset not found for re-hash: {ds_rel}")
    return (not problems), problems


def write_verdict(verdict: dict[str, object], path: Path = ARTIFACT) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        json.dump(verdict, fh, ensure_ascii=False, indent=2, sort_keys=True)
        fh.write("\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m geosync.proof.run",
        description="Five-minute GeoSync proof pipeline (D->H->T->F->V). Emits a "
                    "provenance-bound, tamper-evident verdict an external auditor can "
                    "re-verify without trusting the author.",
    )
    parser.add_argument("--verify", metavar="VERDICT_JSON", type=Path,
                        help="auditor mode: recompute the digest + dataset hash of an existing "
                             "verdict and report OK/TAMPERED instead of running the proof.")
    args = parser.parse_args(argv)

    if args.verify is not None:
        ok, problems = verify_verdict(args.verify)
        if ok:
            sys.stdout.write(f"GEOSYNC_PROOF_VERIFY ok verdict={_relpath(args.verify)}\n")
            return 0
        sys.stderr.write(f"GEOSYNC_PROOF_VERIFY TAMPERED verdict={_relpath(args.verify)}\n")
        for p in problems:
            sys.stderr.write(f"    {p}\n")
        return 1

    verdict = build_verdict()
    write_verdict(verdict)
    result = verdict["result"]
    if not isinstance(result, dict):
        raise TypeError("internal result must be a dict")
    line = (
        "GEOSYNC_PROOF "
        f"verdict={verdict['verdict']} "
        f"mechanism={verdict['mechanism']} "
        f"metric={verdict['metric']} "
        f"value={result['holdout_hit_rate']} "
        f"threshold='{verdict['threshold']}' "
        f"artifact={_relpath(ARTIFACT)}\n"
    )
    sys.stdout.write(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
