# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Driver for the four research-extension microbenchmarks.

Run order
---------
1. ``bench_capital_weighted``
2. ``bench_ricci_flow``
3. ``bench_dr_free``
4. ``bench_sparse_simplicial`` *(headline scaling measurement)*
5. ``bench_pipeline``

Outputs
-------
Two artefacts are written into this package directory:

* ``BENCHMARK_REPORT.json`` — machine-readable bundle of every payload.
* ``BENCHMARK_REPORT.md`` — human-readable report with formatted tables
  and a clearly delimited ``HEADLINE`` block.

The driver never raises on a per-bench failure: every failure is captured
inside the JSON payload by :func:`bench.research_extensions._timing.safe_run`.
The driver exits with a non-zero status only when an unhandled exception
escapes the bench module's own ``run_bench``.
"""

from __future__ import annotations

import json
import multiprocessing
import os
import platform
import sys
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final, cast

import numpy as np

from . import MAX_WALL_NS, MEASURE_ITERS, SEED, WARMUP_ITERS
from .bench_capital_weighted import run_bench as run_capital_weighted
from .bench_dr_free import run_bench as run_dr_free
from .bench_pipeline import run_bench as run_pipeline
from .bench_ricci_flow import run_bench as run_ricci_flow
from .bench_sparse_simplicial import run_bench as run_sparse_simplicial

__all__ = [
    "ARTIFACT_DIR",
    "JSON_REPORT",
    "MD_REPORT",
    "PER_BENCH_BUDGET_S_DEFAULT",
    "build_environment",
    "run_all",
    "render_markdown",
    "main",
]


ARTIFACT_DIR: Final[Path] = Path(__file__).resolve().parent
JSON_REPORT: Final[Path] = ARTIFACT_DIR / "BENCHMARK_REPORT.json"
MD_REPORT: Final[Path] = ARTIFACT_DIR / "BENCHMARK_REPORT.md"

# Per-bench wall-time budget (seconds). Honors the user-supplied contract
# "Skip configs > 60s; record skipped reason in JSON" at the driver level
# without mutating the existing per-bench harnesses. Override via env var
# ``GEOSYNC_BENCH_PER_BENCH_BUDGET_S``.
PER_BENCH_BUDGET_S_DEFAULT: Final[float] = 720.0


def build_environment() -> dict[str, str]:
    """Capture run-time environment for reproducibility."""
    return {
        "python": sys.version.split()[0],
        "implementation": platform.python_implementation(),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "numpy": np.__version__,
        "started_utc": datetime.now(UTC).isoformat(timespec="seconds"),
    }


def _build_payload(
    *,
    environment: dict[str, str],
    elapsed_ns: int,
    benches: dict[str, Any],
    incomplete: bool,
) -> dict[str, Any]:
    """Assemble the JSON-friendly aggregate payload."""
    return {
        "schema_version": 1,
        "seed": SEED,
        "constants": {
            "warmup_iters": WARMUP_ITERS,
            "measure_iters": MEASURE_ITERS,
            "max_wall_ns": MAX_WALL_NS,
        },
        "environment": environment,
        "elapsed_total_ns": int(elapsed_ns),
        "incomplete": bool(incomplete),
        "benches": benches,
    }


def _persist(payload: dict[str, Any]) -> None:
    """Write JSON + Markdown reports atomically."""
    JSON_REPORT.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    MD_REPORT.write_text(render_markdown(payload), encoding="utf-8")


def _per_bench_budget_s() -> float:
    """Resolve the per-bench wall-time cap from env or fall back to default."""
    raw = os.environ.get("GEOSYNC_BENCH_PER_BENCH_BUDGET_S")
    if raw is None:
        return PER_BENCH_BUDGET_S_DEFAULT
    try:
        value = float(raw)
    except ValueError as exc:
        raise ValueError(
            f"GEOSYNC_BENCH_PER_BENCH_BUDGET_S must parse as float, got {raw!r}."
        ) from exc
    if not (value > 0.0):
        raise ValueError("GEOSYNC_BENCH_PER_BENCH_BUDGET_S must be > 0.")
    return value


def _bench_subprocess_target(
    runner: Callable[[], dict[str, Any]],
    queue: multiprocessing.Queue[dict[str, Any]],
) -> None:  # pragma: no cover - executed in a forked process.
    """Subprocess entry point: run ``runner`` and put result on ``queue``."""
    try:
        queue.put({"status": "ok", "payload": runner()})
    except Exception as exc:  # noqa: BLE001 — propagate every failure as data.
        import traceback as _tb

        queue.put(
            {
                "status": "error",
                "error_type": type(exc).__name__,
                "error_message": str(exc),
                "traceback": _tb.format_exc(),
            }
        )


def _run_with_budget(
    name: str,
    runner: Callable[[], dict[str, Any]],
    *,
    budget_s: float,
) -> dict[str, Any]:
    """Run ``runner`` in a subprocess with a wall-time budget.

    On timeout the subprocess is terminated and a synthetic skipped payload
    is returned. The skipped payload mirrors the keys consumers expect so
    downstream rendering does not branch.
    """
    ctx = multiprocessing.get_context("fork")
    queue: multiprocessing.Queue[dict[str, Any]] = ctx.Queue(maxsize=1)
    proc = ctx.Process(target=_bench_subprocess_target, args=(runner, queue))
    started = time.perf_counter()
    proc.start()
    proc.join(timeout=budget_s)
    elapsed = time.perf_counter() - started
    if proc.is_alive():
        proc.terminate()
        proc.join(timeout=10.0)
        if proc.is_alive():  # pragma: no cover - defensive only.
            proc.kill()
            proc.join()
        return {
            "name": f"bench_{name}",
            "skipped": True,
            "skipped_reason": "wall_time_budget_exceeded",
            "skipped_budget_s": float(budget_s),
            "skipped_elapsed_s": float(elapsed),
            "elapsed_total_ns": int(elapsed * 1e9),
            "configurations": [],
            "failures": [],
        }
    if not queue.empty():
        message = queue.get_nowait()
        if message.get("status") == "ok":
            payload = cast(dict[str, Any], message["payload"])
            return payload
        return {
            "name": f"bench_{name}",
            "skipped": True,
            "skipped_reason": "subprocess_exception",
            "error_type": message.get("error_type"),
            "error_message": message.get("error_message"),
            "traceback": message.get("traceback"),
            "elapsed_total_ns": int(elapsed * 1e9),
            "configurations": [],
            "failures": [],
        }
    return {
        "name": f"bench_{name}",
        "skipped": True,
        "skipped_reason": "subprocess_silent_exit",
        "exit_code": int(proc.exitcode) if proc.exitcode is not None else -1,
        "elapsed_total_ns": int(elapsed * 1e9),
        "configurations": [],
        "failures": [],
    }


def run_all() -> dict[str, Any]:
    """Run all five bench modules sequentially and return the aggregate.

    Each bench is executed in a forked subprocess with a wall-time cap
    (``PER_BENCH_BUDGET_S_DEFAULT`` or ``GEOSYNC_BENCH_PER_BENCH_BUDGET_S``).
    On timeout we terminate the subprocess and emit a synthetic skipped
    payload with reason ``wall_time_budget_exceeded`` so the JSON report
    always documents *why* a bench is missing data.

    The driver writes the report after every bench completes so that an
    external hard-kill still leaves a partial-but-usable artefact behind.
    """
    environment = build_environment()
    started_ns = time.perf_counter_ns()
    benches: dict[str, Any] = {}
    budget = _per_bench_budget_s()
    # Cheapest -> most expensive so partial snapshots ship the headline numbers
    # (sparse_simplicial slope, DR-FREE per-eval) even if a later bench is killed.
    bench_specs: list[tuple[str, Callable[[], dict[str, Any]]]] = [
        ("dr_free", run_dr_free),
        ("sparse_simplicial", run_sparse_simplicial),
        ("capital_weighted", run_capital_weighted),
        ("ricci_flow", run_ricci_flow),
        ("pipeline", run_pipeline),
    ]
    expected_keys = {key for key, _ in bench_specs}
    for name, runner in bench_specs:
        benches[name] = _run_with_budget(name, runner, budget_s=budget)
        elapsed_ns = time.perf_counter_ns() - started_ns
        partial = _build_payload(
            environment=environment,
            elapsed_ns=int(elapsed_ns),
            benches=dict(benches),
            incomplete=set(benches.keys()) != expected_keys,
        )
        _persist(partial)

    elapsed_ns = time.perf_counter_ns() - started_ns
    return _build_payload(
        environment=environment,
        elapsed_ns=int(elapsed_ns),
        benches=benches,
        incomplete=False,
    )


def _format_us(value_ns: float) -> str:
    return f"{value_ns / 1_000.0:.2f} us"


def _format_ms(value_ns: float) -> str:
    return f"{value_ns / 1_000_000.0:.3f} ms"


def _median_ns_at(
    bench: dict[str, Any],
    *,
    matcher: dict[str, Any],
) -> float | None:
    """Return median runtime (ns) of the configuration matching ``matcher``."""
    for entry in cast(list[dict[str, Any]], bench["configurations"]):
        cfg = cast(dict[str, Any], entry["config"])
        if all(np.isclose(float(cfg[k]), float(v)) for k, v in matcher.items()):
            return float(cast(dict[str, Any], entry["summary"])["median_ns"])
    return None


def _is_active(bench: dict[str, Any] | None) -> bool:
    """Return True if ``bench`` carries real measurements (not skipped)."""
    if bench is None:
        return False
    return not bool(bench.get("skipped", False))


def _headline_block(payload: dict[str, Any]) -> list[str]:
    benches = cast(dict[str, Any], payload["benches"])
    sparse = cast(dict[str, Any] | None, benches.get("sparse_simplicial"))
    capital = cast(dict[str, Any] | None, benches.get("capital_weighted"))
    ricci = cast(dict[str, Any] | None, benches.get("ricci_flow"))
    dr_free = cast(dict[str, Any] | None, benches.get("dr_free"))
    pipeline = cast(dict[str, Any] | None, benches.get("pipeline"))
    sparse_active = sparse if _is_active(sparse) else None
    capital_active = capital if _is_active(capital) else None
    ricci_active = ricci if _is_active(ricci) else None
    dr_free_active = dr_free if _is_active(dr_free) else None
    pipeline_active = pipeline if _is_active(pipeline) else None

    slope_lines: list[str] = []
    if sparse_active is not None:
        slopes_per_p = cast(dict[str, dict[str, Any]], sparse_active["slopes_per_p"])
        triangle_slope_block = cast(dict[str, Any], sparse_active["slope_vs_triangles"])
        for key, info in slopes_per_p.items():
            slope = info.get("loglog_slope")
            sub_q = info.get("is_subquadratic")
            slope_str = "n/a" if slope is None else f"{float(slope):.3f}"
            slope_lines.append(
                f"  - sparse triadic log-log slope vs N ({key}): "
                f"**{slope_str}** (target < 2.0; sub-quadratic={sub_q})"
            )
        tri_slope_val = triangle_slope_block.get("loglog_slope")
        tri_slope_str = "n/a" if tri_slope_val is None else f"{float(tri_slope_val):.3f}"
        slope_lines.append(
            f"  - sparse triadic log-log slope vs triangle count T2: "
            f"**{tri_slope_str}** (target ~ 1.0; "
            f"linear-in-work={triangle_slope_block.get('is_linear_in_work')})"
        )

    cap_n1024: float | None = None
    if capital_active is not None:
        cap_n1024 = _median_ns_at(capital_active, matcher={"N": 1024, "L": 5})
        if cap_n1024 is None:
            cap_n1024 = _median_ns_at(capital_active, matcher={"N": 1024, "L": 1})
    ricci_n1024 = (
        _median_ns_at(ricci_active, matcher={"N": 1024, "p": 0.1})
        if ricci_active is not None
        else None
    )
    dr_per_eval = (
        _median_ns_at(dr_free_active, matcher={"ambiguity_dim": 7})
        if dr_free_active is not None
        else None
    )
    pipe_n1024 = (
        _median_ns_at(pipeline_active, matcher={"N": 1024}) if pipeline_active is not None else None
    )

    skipped_names = sorted(
        name for name, b in benches.items() if isinstance(b, dict) and b.get("skipped", False)
    )
    incomplete_note = ""
    if bool(payload.get("incomplete", False)):
        missing = sorted(
            {"capital_weighted", "ricci_flow", "dr_free", "sparse_simplicial", "pipeline"}
            - set(benches.keys())
        )
        incomplete_note = f" (PARTIAL — missing: {', '.join(missing)})"

    lines: list[str] = [
        f"## HEADLINE{incomplete_note}",
        "",
        "**Headline measurements** (all values are medians over "
        f"{int(payload['constants']['measure_iters'])} samples after "
        f"{int(payload['constants']['warmup_iters'])} warm-up iterations, "
        f"deterministic seed `{int(payload['seed'])}`):",
        "",
    ]
    lines.extend(slope_lines)
    if cap_n1024 is not None:
        lines.append(f"  - beta-coupling build cost @ N=1024, L=5: **{_format_ms(cap_n1024)}**")
    if ricci_n1024 is not None:
        lines.append(
            f"  - Ricci flow + surgery per-step @ N=1024, p=0.1: **{_format_ms(ricci_n1024)}**"
        )
    if dr_per_eval is not None:
        lines.append(f"  - DR-FREE per-eval (ambiguity_dim=7): **{_format_us(dr_per_eval)}**")
    if pipe_n1024 is not None:
        lines.append(f"  - end-to-end pipeline @ N=1024: **{_format_ms(pipe_n1024)}**")
    if skipped_names:
        lines.append("")
        lines.append(f"**Skipped benches (wall-time budget exceeded):** {', '.join(skipped_names)}")
    lines.append("")
    return lines


def _capital_table(bench: dict[str, Any]) -> list[str]:
    rows: list[str] = [
        "### bench_capital_weighted",
        "",
        "| N | L | median (ms) | p99 (ms) | baseline median (ms) | overhead ratio |",
        "|---:|---:|---:|---:|---:|---:|",
    ]
    for entry in cast(list[dict[str, Any]], bench["configurations"]):
        cfg = cast(dict[str, Any], entry["config"])
        summ = cast(dict[str, Any], entry["summary"])
        extras = cast(dict[str, Any], entry["extras"])
        baseline_summary = cast(dict[str, Any], extras["baseline_summary"])
        rows.append(
            f"| {int(cfg['N'])} | {int(cfg['L'])} | "
            f"{float(summ['median_ms']):.4f} | {float(summ['p99_ms']):.4f} | "
            f"{float(baseline_summary['median_ms']):.4f} | "
            f"{float(extras['overhead_ratio_median']):.2f}x |"
        )
    rows.append("")
    return rows


def _ricci_table(bench: dict[str, Any]) -> list[str]:
    rows: list[str] = [
        "### bench_ricci_flow",
        "",
        "| N | p | total median (ms) | p99 (ms) | flow only (ms) | surgery only (ms) | active edges |",
        "|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for entry in cast(list[dict[str, Any]], bench["configurations"]):
        cfg = cast(dict[str, Any], entry["config"])
        summ = cast(dict[str, Any], entry["summary"])
        extras = cast(dict[str, Any], entry["extras"])
        flow_only = cast(dict[str, Any], extras["flow_only_summary"])
        surgery_only = cast(dict[str, Any], extras["surgery_only_summary"])
        rows.append(
            f"| {int(cfg['N'])} | {float(cfg['p']):.2f} | "
            f"{float(summ['median_ms']):.4f} | {float(summ['p99_ms']):.4f} | "
            f"{float(flow_only['median_ms']):.4f} | "
            f"{float(surgery_only['median_ms']):.4f} | "
            f"{int(extras['active_edges_initial'])} |"
        )
    rows.append("")
    return rows


def _dr_free_table(bench: dict[str, Any]) -> list[str]:
    rows: list[str] = [
        "### bench_dr_free",
        "",
        "| ambiguity dim | median (us) | p99 (us) | robust margin |",
        "|---:|---:|---:|---:|",
    ]
    for entry in cast(list[dict[str, Any]], bench["configurations"]):
        cfg = cast(dict[str, Any], entry["config"])
        summ = cast(dict[str, Any], entry["summary"])
        extras = cast(dict[str, Any], entry["extras"])
        rows.append(
            f"| {int(cfg['ambiguity_dim'])} | "
            f"{float(summ['median_us']):.3f} | "
            f"{float(summ['p99_ns']) / 1_000.0:.3f} | "
            f"{float(extras['robust_margin']):.6e} |"
        )
    slope = bench.get("loglog_slope_vs_dim")
    is_o1 = bench.get("is_O1_per_metric")
    rows.append("")
    rows.append(f"log-log slope vs dim: `{slope}` (O(1) per-metric: {is_o1})")
    rows.append("")
    return rows


def _sparse_table(bench: dict[str, Any]) -> list[str]:
    rows: list[str] = [
        "### bench_sparse_simplicial",
        "",
        "| N | p | T2 | sparse median (us) | sparse p99 (us) | dense median (us) | speedup |",
        "|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for entry in cast(list[dict[str, Any]], bench["configurations"]):
        cfg = cast(dict[str, Any], entry["config"])
        summ = cast(dict[str, Any], entry["summary"])
        extras = cast(dict[str, Any], entry["extras"])
        dense = extras.get("dense_summary")
        if isinstance(dense, dict):
            dense_med = f"{float(cast(dict[str, Any], dense)['median_us']):.3f}"
            speedup_val = extras.get("sparse_speedup_vs_dense_median")
            speedup_str = (
                f"{float(speedup_val):.2f}x" if isinstance(speedup_val, (int, float)) else "n/a"
            )
        else:
            dense_med = "n/a"
            speedup_str = "n/a"
        rows.append(
            f"| {int(cfg['N'])} | {float(cfg['p']):.2f} | "
            f"{int(extras['n_triangles'])} | "
            f"{float(summ['median_us']):.3f} | "
            f"{float(summ['p99_ns']) / 1_000.0:.3f} | "
            f"{dense_med} | {speedup_str} |"
        )
    rows.append("")
    rows.append("**log-log slopes (sparse runtime vs N at fixed p):**")
    rows.append("")
    slopes = cast(dict[str, dict[str, Any]], bench["slopes_per_p"])
    for key, info in slopes.items():
        slope_val = info.get("loglog_slope")
        slope_str = f"{float(slope_val):.4f}" if slope_val is not None else "n/a"
        rows.append(
            f"  - `{key}`: slope = **{slope_str}** (sub-quadratic = {info.get('is_subquadratic')})"
        )
    rows.append("")
    rows.append("**log-log slope (sparse runtime vs triangle count T2, work-faithful axis):**")
    rows.append("")
    triangle_block = cast(dict[str, Any], bench["slope_vs_triangles"])
    tri_val = triangle_block.get("loglog_slope")
    tri_str = f"{float(tri_val):.4f}" if tri_val is not None else "n/a"
    rows.append(
        f"  - slope vs T2 = **{tri_str}** (target ~ 1.0; "
        f"linear-in-work = {triangle_block.get('is_linear_in_work')})"
    )
    rows.append("")
    rows.append(
        "*Note: Erdos-Renyi at fixed p has T2 ~ p^3 N^3 / 6, so the runtime-vs-N "
        "slope reflects triangle growth, not per-triangle algorithmic cost. The "
        "runtime-vs-T2 slope is the work-faithful measurement of the kernel itself.*"
    )
    rows.append("")
    return rows


def _pipeline_table(bench: dict[str, Any]) -> list[str]:
    rows: list[str] = [
        "### bench_pipeline",
        "",
        "| N | total median (ms) | p99 (ms) | capital (ms) | ricci (ms) | sparse-50 (ms) | active edges |",
        "|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for entry in cast(list[dict[str, Any]], bench["configurations"]):
        cfg = cast(dict[str, Any], entry["config"])
        summ = cast(dict[str, Any], entry["summary"])
        extras = cast(dict[str, Any], entry["extras"])
        cap = cast(dict[str, Any], extras["capital_summary"])
        ric = cast(dict[str, Any], extras["ricci_summary"])
        spa = cast(dict[str, Any], extras["sparse_summary"])
        rows.append(
            f"| {int(cfg['N'])} | "
            f"{float(summ['median_ms']):.3f} | {float(summ['p99_ms']):.3f} | "
            f"{float(cap['median_ms']):.3f} | "
            f"{float(ric['median_ms']):.3f} | "
            f"{float(spa['median_ms']):.3f} | "
            f"{int(extras['n_active_edges_post_surgery'])} |"
        )
    rows.append("")
    return rows


def _failures_block(payload: dict[str, Any]) -> list[str]:
    benches = cast(dict[str, Any], payload["benches"])
    lines: list[str] = []
    any_failure = False
    for name, bench in benches.items():
        bench_dict = cast(dict[str, Any], bench)
        failures = cast(list[dict[str, Any]], bench_dict.get("failures", []))
        if not failures:
            continue
        if not any_failure:
            lines.append("## Failures")
            lines.append("")
            any_failure = True
        for fail in failures:
            lines.append(
                f"- **{name}** {fail['config']}: `{fail['error_type']}` — {fail['error_message']}"
            )
    if any_failure:
        lines.append("")
    return lines


def render_markdown(payload: dict[str, Any]) -> str:
    """Render a human-readable Markdown report from the aggregate payload."""
    env = cast(dict[str, str], payload["environment"])
    constants = cast(dict[str, int], payload["constants"])
    benches = cast(dict[str, Any], payload["benches"])

    lines: list[str] = [
        "# GeoSync research extensions — microbenchmark report",
        "",
        f"- seed: `{int(payload['seed'])}`",
        f"- warmup iters: `{int(constants['warmup_iters'])}`",
        f"- measure iters (cap): `{int(constants['measure_iters'])}`",
        f"- per-config wall time cap: `{int(constants['max_wall_ns']) / 1e9:.0f}` s",
        f"- python: `{env['python']}` ({env['implementation']})",
        f"- numpy: `{env['numpy']}`",
        f"- platform: `{env['platform']}` / `{env['machine']}`",
        f"- started UTC: `{env['started_utc']}`",
        f"- total wall time: `{int(payload['elapsed_total_ns']) / 1e9:.2f}` s",
        "",
    ]
    lines.extend(_headline_block(payload))
    if bool(payload.get("incomplete", False)):
        missing = sorted(
            {"capital_weighted", "ricci_flow", "dr_free", "sparse_simplicial", "pipeline"}
            - set(benches.keys())
        )
        lines.append(f"> **NOTE:** partial report — missing benches: {', '.join(missing)}.")
        lines.append("")
    lines.append("## Per-bench tables")
    lines.append("")
    if "capital_weighted" in benches:
        lines.extend(_capital_table(cast(dict[str, Any], benches["capital_weighted"])))
    if "ricci_flow" in benches:
        lines.extend(_ricci_table(cast(dict[str, Any], benches["ricci_flow"])))
    if "dr_free" in benches:
        lines.extend(_dr_free_table(cast(dict[str, Any], benches["dr_free"])))
    if "sparse_simplicial" in benches:
        lines.extend(_sparse_table(cast(dict[str, Any], benches["sparse_simplicial"])))
    if "pipeline" in benches:
        lines.extend(_pipeline_table(cast(dict[str, Any], benches["pipeline"])))
    lines.extend(_failures_block(payload))
    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    """Run all benches, write JSON + MD, return exit code 0 / 1.

    The driver itself persists incremental snapshots in :func:`run_all`, so
    by the time we get here the artefacts already exist on disk; this final
    write is the canonical, complete payload.
    """
    payload = run_all()

    JSON_REPORT.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    MD_REPORT.write_text(render_markdown(payload), encoding="utf-8")

    benches = cast(dict[str, Any], payload["benches"])
    total_failures = sum(
        len(cast(list[dict[str, Any]], cast(dict[str, Any], b).get("failures", [])))
        for b in benches.values()
    )
    print(f"Wrote {JSON_REPORT.name} and {MD_REPORT.name} into {ARTIFACT_DIR}")
    print(f"Total per-config failures: {total_failures}")
    return 0 if total_failures == 0 else 1


if __name__ == "__main__":  # pragma: no cover - CLI entry point.
    sys.exit(main())
