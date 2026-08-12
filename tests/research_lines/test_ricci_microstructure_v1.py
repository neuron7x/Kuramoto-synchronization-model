from __future__ import annotations

import json
from pathlib import Path

import networkx as nx
import numpy as np
import pandas as pd
import pytest

from geosync_research.lines.ricci_microstructure_v1.artifact import validate_artifact_payload
from geosync_research.lines.ricci_microstructure_v1.graph_builder import build_l2_graph
from geosync_research.lines.ricci_microstructure_v1.ingest import (
    DataFrameSchemaError,
    ingest_manifest,
    load_manifest,
    validate_l2_frame,
)
from geosync_research.lines.ricci_microstructure_v1.ricci_kernel import (
    RicciKernelConfig,
    compute_ricci_curvature,
    edge_curvature_records,
)
from geosync_research.lines.ricci_microstructure_v1.stability import (
    bonferroni,
    seed_stability,
)
from geosync_research.lines.ricci_microstructure_v1.synthetic_controls import (
    curvature_series,
    effect_size_class,
    surrogate_frame,
)


def frame(depth: int = 5) -> pd.DataFrame:
    rows = []
    for t in range(3):
        row = {"timestamp": f"2026-01-01T00:00:0{t}Z", "price": 100.0 + t}
        for i in range(1, depth + 1):
            row[f"bid_px_{i}"] = 100.0 - i * 0.01
            row[f"ask_px_{i}"] = 100.0 + i * 0.01
            row[f"bid_sz_{i}"] = 10.0 + i + t
            row[f"ask_sz_{i}"] = 9.0 + i
        rows.append(row)
    return pd.DataFrame(rows)


def test_l2_schema_rejects_missing_column() -> None:
    bad = frame().drop(columns=["bid_sz_3"])
    with pytest.raises(DataFrameSchemaError):
        validate_l2_frame(bad, depth=5)


def test_l2_schema_rejects_negative_size() -> None:
    bad = frame()
    bad.loc[0, "ask_sz_2"] = -1
    with pytest.raises(DataFrameSchemaError):
        validate_l2_frame(bad, depth=5)


def test_l2_schema_rejects_non_monotonic_timestamp() -> None:
    bad = frame()
    bad.loc[2, "timestamp"] = "2025-01-01T00:00:00Z"
    with pytest.raises(DataFrameSchemaError):
        validate_l2_frame(bad, depth=5)


def test_graph_builder_and_ricci_emit_curvature() -> None:
    graph = build_l2_graph(frame().iloc[0], depth=5)
    curved = compute_ricci_curvature(graph, config=RicciKernelConfig(alpha=0.5, n_min_edges=2))
    records = edge_curvature_records(curved)
    assert records
    assert all(isinstance(record["ricciCurvature"], float) for record in records)


def test_too_few_edges_fails_closed() -> None:
    graph = nx.DiGraph()
    graph.add_edge("a", "b", edge_weight=1.0, weight=1.0)
    with pytest.raises(RuntimeError, match="graph_edges < N_min"):
        compute_ricci_curvature(graph, config=RicciKernelConfig(n_min_edges=2))


def test_synthetic_cycle_curvature_near_zero_and_complete_positive() -> None:
    cycle = nx.DiGraph()
    for u, v in nx.cycle_graph(6).edges():
        cycle.add_edge(u, v, edge_weight=1.0, weight=1.0)
        cycle.add_edge(v, u, edge_weight=1.0, weight=1.0)
    cycle_curved = compute_ricci_curvature(
        cycle, config=RicciKernelConfig(alpha=0.5, n_min_edges=2)
    )
    cycle_mean = (
        sum(r["ricciCurvature"] for r in edge_curvature_records(cycle_curved))
        / cycle_curved.number_of_edges()
    )
    assert abs(cycle_mean) < 1e-9

    complete = nx.complete_graph(5).to_directed()
    for src, dst in complete.edges:
        complete[src][dst]["edge_weight"] = 1.0
        complete[src][dst]["weight"] = 1.0
    complete_curved = compute_ricci_curvature(
        complete, config=RicciKernelConfig(alpha=0.5, n_min_edges=2)
    )
    complete_mean = (
        sum(r["ricciCurvature"] for r in edge_curvature_records(complete_curved))
        / complete_curved.number_of_edges()
    )
    assert complete_mean > 0.0


def test_effect_size_classes() -> None:
    assert effect_size_class(0.0) == "negligible"
    assert effect_size_class(0.2) == "small"
    assert effect_size_class(0.4) == "medium"
    assert effect_size_class(0.6) == "large"


def test_artifact_schema_requires_fields() -> None:
    errors = validate_artifact_payload({})
    assert errors


def test_artifact_schema_forbids_market_mythology() -> None:
    payload = {
        "run_id": "x",
        "schema_version": "ricci_microstructure_artifact.v1",
        "config_hash": "a" * 64,
        "data_sha256": "b" * 64,
        "git_sha": "c" * 40,
        "mean_curvature": 0.0,
        "p_value": 1.0,
        "cliffs_delta": 0.0,
        "effect_size_class": "negligible",
        "null_model_type": "iaaft",
        "n_surrogates": 1000,
        "falsification_status": "ALPHA_FOUND",
        "replay_command": "geosync-research run --line ricci_microstructure_v1 --config c --data d --out o",
        "timestamp_utc": "2026-01-01T00:00:00Z",
        "claim_tier": "T3/NOVEL/EXPLORATORY/FALSIFIABLE",
    }
    errors = validate_artifact_payload(payload)
    assert errors


# --------------------------- V2: kernel must be microstructure-sensitive --------


def _mean_curv(row: pd.Series) -> float:
    graph = build_l2_graph(row, depth=5)
    curved = compute_ricci_curvature(graph, config=RicciKernelConfig(alpha=0.5, n_min_edges=2))
    return float(np.mean([r["ricciCurvature"] for r in edge_curvature_records(curved)]))


def test_kernel_invariant_changing_size_changes_curvature() -> None:
    """Constant topology + changed sizes => curvature MUST change (anti-vacuity)."""
    base = frame().iloc[0].copy()
    perturbed = base.copy()
    for i in range(1, 6):
        perturbed[f"bid_sz_{i}"] = base[f"bid_sz_{i}"] * (1.0 + 0.5 * i)
    assert abs(_mean_curv(base) - _mean_curv(perturbed)) > 1e-6


def test_kernel_invariant_changing_price_changes_curvature() -> None:
    base = frame().iloc[0].copy()
    perturbed = base.copy()
    for i in range(1, 6):
        perturbed[f"ask_px_{i}"] = base[f"ask_px_{i}"] + 0.02 * i
    assert abs(_mean_curv(base) - _mean_curv(perturbed)) > 1e-6


def test_kernel_anti_invariant_timestamp_only_does_not_change_curvature() -> None:
    """Changing only the timestamp must NOT change per-snapshot curvature."""
    base = frame().iloc[0].copy()
    relabelled = base.copy()
    relabelled["timestamp"] = "2099-12-31T23:59:59Z"
    assert abs(_mean_curv(base) - _mean_curv(relabelled)) < 1e-12


@pytest.mark.parametrize(
    "null_model", ["iaaft", "volume_neutral", "size_permutation_within_side", "block_bootstrap"]
)
def test_nulls_modify_consumed_variables(null_model: str) -> None:
    """Each kernel-consuming null must move the mean curvature off the observed."""
    df = pd.concat([frame() for _ in range(8)], ignore_index=True)
    df["timestamp"] = [f"2026-01-01T00:00:{i:02d}Z" for i in range(len(df))]
    rng = np.random.default_rng(0)
    obs = float(np.mean(curvature_series(df, depth=5, alpha=0.5, n_min_edges=2)))
    surrogate = surrogate_frame(df, depth=5, null_model=null_model, rng=rng)
    null = float(np.mean(curvature_series(surrogate, depth=5, alpha=0.5, n_min_edges=2)))
    assert abs(obs - null) > 1e-9


# --------------------------- V2: source honesty ---------------------------------


def _write_manifest(tmp_path: Path, source: str) -> Path:
    raw = tmp_path / "raw.csv"
    f = frame()
    f["timestamp"] = [f"2026-01-01T00:00:0{t}Z" for t in range(len(f))]
    f.to_csv(raw, index=False)
    manifest = tmp_path / "l2_manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "source": source,
                "symbol": "X",
                "date": "2026-06-20",
                "depth": 5,
                "data_path": "raw.csv",
                "schema_version": "l2_manifest.v1",
            }
        )
    )
    return manifest


def test_manifest_rejects_unknown_source(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="source must be one of"):
        load_manifest(_write_manifest(tmp_path, "ACME_HEDGE_FUND"))


def test_binance_source_passes_through_verbatim(tmp_path: Path) -> None:
    out = ingest_manifest(
        _write_manifest(tmp_path, "BINANCE_FUTURES_DEPTH"), out_dir=tmp_path / "o"
    )
    manifest = json.loads(out["data_manifest"].read_text())
    assert manifest["source"] == "BINANCE_FUTURES_DEPTH"  # never relabelled to LOBSTER


def test_lobster_licensed_source_passes_through_verbatim(tmp_path: Path) -> None:
    out = ingest_manifest(_write_manifest(tmp_path, "LOBSTER_LICENSED_L2"), out_dir=tmp_path / "o")
    manifest = json.loads(out["data_manifest"].read_text())
    assert manifest["source"] == "LOBSTER_LICENSED_L2"


# --------------------------- V2: artifact hardening -----------------------------


def _hardened_payload() -> dict[str, object]:
    return {
        "run_id": "x",
        "schema_version": "ricci_microstructure_artifact.v1",
        "kernel_version": "ricci_kernel.v2-weighted-sizemeasure",
        "source": "BINANCE_FUTURES_DEPTH",
        "source_class": "BINANCE_PUBLIC_DEPTH",
        "license_status": "PUBLIC_NO_LICENSE",
        "config_hash": "a" * 64,
        "config_sha256": "a" * 64,
        "data_sha256": "b" * 64,
        "collector_sha256": "e" * 64,
        "git_sha": "c" * 40,
        "dirty_git": False,
        "seed": 1337,
        "mean_curvature": -0.1,
        "observed_count": 600,
        "null_mean": -0.2,
        "null_std": 0.1,
        "p_value": 0.4,
        "cliffs_delta": 0.2,
        "effect_size_class": "small",
        "null_model_type": "iaaft",
        "n_surrogates": 1000,
        "falsification_status": "HYPOTHESIS_NOT_SUPPORTED",
        "forbidden_claims_absent": True,
        "replay_command": "geosync-research run --line ricci_microstructure_v1 --config c --data d --out o",
        "timestamp_utc": "2026-01-01T00:00:00Z",
        "claim_tier": "T3/NOVEL/EXPLORATORY/FALSIFIABLE",
    }


def test_hardened_artifact_validates() -> None:
    assert validate_artifact_payload(_hardened_payload()) == []


def test_dirty_git_artifact_fails() -> None:
    payload = _hardened_payload()
    payload["dirty_git"] = True
    assert validate_artifact_payload(payload)


def test_forbidden_claims_absent_must_be_true() -> None:
    payload = _hardened_payload()
    payload["forbidden_claims_absent"] = False
    payload["falsification_status"] = "ALPHA_FOUND"
    assert validate_artifact_payload(payload)


# --------------------------- V2 task 6: seed stability + correction -------------


def _seed_artifact(seed: int, status: str, p: float, delta: float) -> dict[str, object]:
    return {
        "seed": seed,
        "falsification_status": status,
        "p_value": p,
        "cliffs_delta": delta,
        "mean_curvature": -0.1,
    }


def test_bonferroni_correction() -> None:
    adj = bonferroni({"iaaft": 0.01, "volume_neutral": 0.2, "block_bootstrap": 0.5})
    assert adj["iaaft"] == pytest.approx(0.03)
    assert adj["volume_neutral"] == pytest.approx(0.6)
    assert adj["block_bootstrap"] == 1.0  # clamped


def test_seed_stability_consistent_not_supported() -> None:
    arts = [_seed_artifact(s, "HYPOTHESIS_NOT_SUPPORTED", 0.4, 0.2) for s in (1337, 2026, 7719)]
    v = seed_stability(arts)
    assert v["stable"] is True
    assert v["aggregate_status"] == "HYPOTHESIS_NOT_SUPPORTED"
    assert v["required_seeds_present"] is True


def test_seed_stability_demotes_on_disagreement() -> None:
    arts = [
        _seed_artifact(1337, "SUPPORTED", 0.001, 0.5),
        _seed_artifact(2026, "HYPOTHESIS_NOT_SUPPORTED", 0.4, 0.1),
        _seed_artifact(7719, "SUPPORTED", 0.002, 0.5),
    ]
    v = seed_stability(arts)
    assert v["stable"] is False
    assert v["aggregate_status"] == "HYPOTHESIS_NOT_SUPPORTED"  # fail-closed demotion


def test_seed_stability_supported_only_if_all_pass() -> None:
    arts = [_seed_artifact(s, "SUPPORTED", 0.001, 0.5) for s in (1337, 2026, 7719)]
    v = seed_stability(arts)
    assert v["aggregate_status"] == "SUPPORTED"


# --------------------------- NC-06: substrate / source-class enforcement --------


def _write_manifest_with(tmp_path: Path, **overrides: object) -> Path:
    """Manifest writer that allows injecting (mis)labelled provenance fields."""
    raw = tmp_path / "binance_raw.csv"
    f = frame()
    f["timestamp"] = [f"2026-01-01T00:00:0{t}Z" for t in range(len(f))]
    f.to_csv(raw, index=False)
    payload: dict[str, object] = {
        "source": "BINANCE_FUTURES_DEPTH",
        "symbol": "BTCUSDT",
        "date": "2026-06-20",
        "depth": 5,
        "data_path": "binance_raw.csv",
        "schema_version": "l2_manifest.v1",
    }
    payload.update(overrides)
    manifest = tmp_path / "l2_manifest.json"
    manifest.write_text(json.dumps(payload))
    return manifest


def test_ingest_stamps_source_class_for_binance(tmp_path: Path) -> None:
    """NC-06: a Binance session is stamped BINANCE_PUBLIC_DEPTH / PUBLIC_NO_LICENSE."""
    out = ingest_manifest(_write_manifest_with(tmp_path), out_dir=tmp_path / "o")
    manifest = json.loads(out["data_manifest"].read_text())
    assert manifest["source"] == "BINANCE_FUTURES_DEPTH"
    assert manifest["source_class"] == "BINANCE_PUBLIC_DEPTH"
    assert manifest["license_status"] == "PUBLIC_NO_LICENSE"


def test_ingest_rejects_binance_relabelled_as_lobster_class(tmp_path: Path) -> None:
    """NC-06: Binance data declaring a LOBSTER substrate class is rejected."""
    bad = _write_manifest_with(tmp_path, source_class="LOBSTER_LICENSED")
    with pytest.raises(ValueError, match="relabel rejected"):
        ingest_manifest(bad, out_dir=tmp_path / "o")


def test_ingest_rejects_binance_relabelled_license(tmp_path: Path) -> None:
    """NC-06: Binance data declaring a LICENSED status is rejected (no fake license)."""
    bad = _write_manifest_with(tmp_path, license_status="LICENSED")
    with pytest.raises(ValueError, match="relabel rejected"):
        ingest_manifest(bad, out_dir=tmp_path / "o")


def test_artifact_schema_rejects_lobster_grade_on_binance_substrate() -> None:
    """NC-06 claim-boundary: a Binance source cannot carry a LOBSTER source_class.

    This is the machine-enforced 'no LOBSTER-grade result without licensed
    provenance' boundary: the artifact schema's source<->source_class binding
    rejects the relabel.
    """
    payload = _hardened_payload()
    payload["source_class"] = "LOBSTER_LICENSED"
    payload["license_status"] = "LICENSED"
    assert validate_artifact_payload(payload)  # schema rejects the mismatch


def test_artifact_schema_accepts_honest_binance_substrate() -> None:
    """NC-06: the honest Binance public-depth substrate validates."""
    assert validate_artifact_payload(_hardened_payload()) == []


# --------------------------- NC-10: negative-result preservation ----------------


def test_negative_result_round_trips_through_schema() -> None:
    """NC-10: HYPOTHESIS_NOT_SUPPORTED is a legitimate terminal result, preserved."""
    payload = _hardened_payload()
    payload["falsification_status"] = "HYPOTHESIS_NOT_SUPPORTED"
    assert validate_artifact_payload(payload) == []  # not coerced to a pass


def test_invalid_status_round_trips_through_schema() -> None:
    """NC-10: INVALID (a blocked/honest non-result) is also a legitimate terminal."""
    payload = _hardened_payload()
    payload["falsification_status"] = "INVALID"
    assert validate_artifact_payload(payload) == []


@pytest.mark.parametrize(
    "overclaim",
    ["ALPHA_FOUND", "MARKET_SIGNAL_PROVEN", "PRODUCTION_READY", "PHYSICS_CONFIRMED"],
)
def test_forbidden_overclaim_status_rejected(overclaim: str) -> None:
    """NC-10: no artifact may ever carry an overclaim falsification_status."""
    payload = _hardened_payload()
    payload["falsification_status"] = overclaim
    assert validate_artifact_payload(payload)  # schema/forbidden-status guard fails it


def test_committed_canonical_artifact_is_honest_negative() -> None:
    """NC-10: the committed canonical artifact is a preserved honest negative.

    Guards against a future edit silently promoting the committed evidence to a
    SUPPORTED/overclaim status or relabelling its substrate.
    """
    canon = Path("geosync_research/lines/ricci_microstructure_v1/canonical/artifact.json")
    art = json.loads(canon.read_text())
    assert art["falsification_status"] == "HYPOTHESIS_NOT_SUPPORTED"
    assert art["forbidden_claims_absent"] is True
    assert art["dirty_git"] is False
    assert art["source"] == "BINANCE_FUTURES_DEPTH"
    assert art["source_class"] == "BINANCE_PUBLIC_DEPTH"
    assert art["license_status"] == "PUBLIC_NO_LICENSE"
    assert art["claim_tier"] == "T3/NOVEL/EXPLORATORY/FALSIFIABLE"
    assert validate_artifact_payload(art) == []
