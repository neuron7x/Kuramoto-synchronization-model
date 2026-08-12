"""Production Readiness Checkpoint runner.

Runs protocol phases sequentially and emits deterministic audit artifacts.
Designed for honest go/no-go validation (no fabricated pass states).
"""

from __future__ import annotations

import hashlib
import importlib
import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from core.io.parquet_compat import read_parquet_compat


@dataclass
class StepResult:
    phase: str
    task: str
    status: str  # PASS | FAIL | SKIP
    detail: str


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _count_env_keys(keys: list[str]) -> int:
    return sum(1 for k in keys if os.getenv(k))


def run(base_dir: Path) -> dict[str, Any]:
    results: list[StepResult] = []

    # Phase 1.1 imports
    modules = [
        "numpy",
        "pandas",
        "scipy",
        "praw",
        "core.physics.forman_ricci",
        "research.askar.sentiment_node_ricci_graph",
    ]
    failed_imports: list[str] = []
    for mod in modules:
        try:
            importlib.import_module(mod)
        except Exception as exc:
            failed_imports.append(f"{mod}: {exc}")
    if failed_imports:
        results.append(StepResult("PHASE_1", "import_check", "FAIL", "; ".join(failed_imports)))
    else:
        results.append(
            StepResult("PHASE_1", "import_check", "PASS", "All required imports resolved")
        )

    # Phase 1.2 dirs
    required_dirs = [
        base_dir / "results" / "prod",
        base_dir / "audit" / "prod",
        base_dir / "data" / "cache",
        base_dir / "logs",
    ]
    for d in required_dirs:
        d.mkdir(parents=True, exist_ok=True)
    writable = all(os.access(str(d), os.W_OK) for d in required_dirs)
    results.append(
        StepResult(
            "PHASE_1",
            "directory_structure",
            "PASS" if writable else "FAIL",
            "Directories created and writable" if writable else "Directory not writable",
        )
    )

    # Phase 1.3 env
    env_count = _count_env_keys(
        [
            "DUKASCOPY_DOWNLOAD_DIR",
            "DATABENTO_API_KEY",
            "OANDA_API_TOKEN",
            "POLYGON_API_KEY",
            "AGENT_SEED",
        ]
    )
    results.append(
        StepResult(
            "PHASE_1",
            "env_validation",
            "PASS" if env_count >= 1 else "FAIL",
            f"provider/env vars set: {env_count}",
        )
    )

    # Phase 2+3+4+5+6 rely on parquet and provider connectivity; run only if dependencies exist
    try:
        import numpy as np
        from scipy.stats import spearmanr
    except Exception as exc:
        results.append(StepResult("PHASE_2_6", "runtime_deps", "FAIL", str(exc)))
        verdict: dict[str, Any] = {
            "FINAL": "REJECT",
            "reason": "runtime_dependency_failure",
            "steps": [asdict(r) for r in results],
        }
        _write_json(base_dir / "results" / "prod" / "validation_verdict.json", verdict)
        _write_json(
            base_dir / "results" / "prod" / "action_intent.json",
            {
                "state": "REPORT",
                "action": "DORMANT",
                "admissible": True,
                "why": ["runtime_dependency_failure"],
            },
        )
        digest = hashlib.sha256(json.dumps(verdict, sort_keys=True).encode()).hexdigest()
        (base_dir / "audit" / "prod").mkdir(parents=True, exist_ok=True)
        (base_dir / "audit" / "prod" / "run_hash.sha256").write_text(digest, encoding="utf-8")
        return verdict

    # Try to load existing enriched panel if present; do not fabricate market data.
    panel_enriched = base_dir / "data" / "cache" / "panel_enriched.parquet"
    if not panel_enriched.exists():
        results.append(
            StepResult("PHASE_2", "data_ingestion", "FAIL", "panel_enriched.parquet missing")
        )
        verdict = {
            "FINAL": "REJECT",
            "reason": "missing_enriched_panel",
            "steps": [asdict(r) for r in results],
        }
        _write_json(base_dir / "results" / "prod" / "validation_verdict.json", verdict)
        _write_json(
            base_dir / "results" / "prod" / "action_intent.json",
            {
                "state": "REPORT",
                "action": "DORMANT",
                "admissible": True,
                "why": ["missing_enriched_panel"],
            },
        )
        digest = hashlib.sha256(json.dumps(verdict, sort_keys=True).encode()).hexdigest()
        (base_dir / "audit" / "prod" / "run_hash.sha256").write_text(digest, encoding="utf-8")
        return verdict

    try:
        df = read_parquet_compat(panel_enriched)
    except Exception as exc:
        results.append(StepResult("PHASE_2", "read_parquet", "FAIL", str(exc)))
        verdict = {
            "FINAL": "REJECT",
            "reason": "parquet_read_failure",
            "steps": [asdict(r) for r in results],
        }
        _write_json(base_dir / "results" / "prod" / "validation_verdict.json", verdict)
        _write_json(
            base_dir / "results" / "prod" / "action_intent.json",
            {
                "state": "REPORT",
                "action": "DORMANT",
                "admissible": True,
                "why": ["parquet_read_failure"],
            },
        )
        digest = hashlib.sha256(json.dumps(verdict, sort_keys=True).encode()).hexdigest()
        (base_dir / "audit" / "prod" / "run_hash.sha256").write_text(digest, encoding="utf-8")
        return verdict

    ic: float
    p: float
    cm: float
    cv: float
    if "mid_returns" not in df.columns:
        results.append(StepResult("PHASE_2", "schema_check", "FAIL", "mid_returns missing"))
        final = "REJECT"
        ic = p = cm = cv = 0.0
    else:
        s = df["mid_returns"].astype(float).dropna()
        if len(s) < 200:
            results.append(StepResult("PHASE_3", "unity_compute", "FAIL", "insufficient rows"))
            final = "REJECT"
            ic = p = cm = cv = 0.0
        else:
            window = 60
            unity = s.rolling(window).std().dropna().rename("unity")
            target = s.shift(-1).reindex(unity.index)
            valid = unity.notna() & target.notna()
            if int(valid.sum()) < 50:
                results.append(
                    StepResult("PHASE_4", "three_d", "FAIL", "insufficient valid observations")
                )
                final = "REJECT"
                ic = p = cm = cv = 0.0
            else:
                ic = float(spearmanr(unity[valid], target[valid]).statistic)
                rng = np.random.default_rng(42)
                obs = abs(ic)
                count = 0
                xv = unity[valid].to_numpy()
                yv = target[valid].to_numpy()
                for _ in range(500):
                    corr = float(spearmanr(xv, rng.permutation(yv)).statistic)
                    if abs(corr) >= obs:
                        count += 1
                p = float((count + 1) / 501)
                mom = s.rolling(20).sum().reindex(unity.index)
                vol = s.rolling(10).std().reindex(unity.index)
                cm = float(spearmanr(unity[valid], mom[valid]).statistic)
                cv = float(spearmanr(unity[valid], vol[valid]).statistic)
                final = (
                    "SIGNAL_READY"
                    if (ic >= 0.08 and p < 0.10 and abs(cm) < 0.15 and abs(cv) < 0.15)
                    else "REJECT"
                )
                results.append(
                    StepResult(
                        "PHASE_4",
                        "three_d",
                        "PASS",
                        f"IC={ic:.4f}, p={p:.4f}, cm={cm:.4f}, cv={cv:.4f}",
                    )
                )

    verdict = {
        "IC": round(ic, 4),
        "p_value": round(p, 4),
        "corr_momentum": round(cm, 4),
        "corr_vol": round(cv, 4),
        "DETECT": "PASS" if ic >= 0.08 else "FAIL",
        "DISCRIMINATE": "PASS" if abs(cm) < 0.15 and abs(cv) < 0.15 else "FAIL",
        "FINAL": final,
        "steps": [asdict(r) for r in results],
    }
    _write_json(base_dir / "results" / "prod" / "validation_verdict.json", verdict)

    action = "PAPER_TRADE" if final == "SIGNAL_READY" else "DORMANT"
    _write_json(
        base_dir / "results" / "prod" / "action_intent.json",
        {
            "state": "REPORT",
            "action": action,
            "IC": verdict["IC"],
            "p_value": verdict["p_value"],
            "why": [f"{k}={v}" for k, v in verdict.items() if k not in {"steps"}],
            "admissible": True,
        },
    )

    digest = hashlib.sha256(json.dumps(verdict, sort_keys=True).encode()).hexdigest()
    (base_dir / "audit" / "prod" / "run_hash.sha256").write_text(digest, encoding="utf-8")
    return verdict


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Run production readiness checkpoint")
    parser.add_argument("--base-dir", type=Path, default=Path("/opt/geosync-prod"))
    args = parser.parse_args()

    out = run(args.base_dir)
    print(json.dumps(out, indent=2))
