#!/usr/bin/env python3
"""Pairwise Transfer Entropy CLI over the symbol OFI panel.

For every ordered pair (A, B) in the universe, compute TE(A→B) and
TE(B→A) from the L2 OFI with surrogate-shuffle null. Writes a pairwise
matrix + summary to results/L2_TRANSFER_ENTROPY.json.

Interpretation:
    Near-zero asymmetry across pairs → Ricci cross-sectional signal is
    driven by contemporaneous correlation, not lead-lag flow.
    Significant asymmetry on specific pairs → leader/follower dynamics
    that could augment κ_min with directional context.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

from research.microstructure.l2_cli import (
    SubstrateError,
    add_common_args,
    load_substrate,
    setup_logging,
)
from research.microstructure.transfer_entropy import (
    DEFAULT_LAG_ROWS,
    DEFAULT_N_BINS,
    DEFAULT_N_SURROGATES,
    transfer_entropy,
)

_log = logging.getLogger("l2_transfer_entropy")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    add_common_args(parser, output_default=Path("results/L2_TRANSFER_ENTROPY.json"))
    parser.add_argument("--n-bins", type=int, default=DEFAULT_N_BINS)
    parser.add_argument("--lag-rows", type=int, default=DEFAULT_LAG_ROWS)
    parser.add_argument("--n-surrogates", type=int, default=DEFAULT_N_SURROGATES)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    setup_logging(str(args.log_level))

    try:
        loaded = load_substrate(Path(args.data_dir), str(args.symbols))
    except SubstrateError as exc:
        _log.error("%s", exc)
        return 2
    features = loaded.features

    pairs: list[dict[str, Any]] = []
    for i, sym_a in enumerate(features.symbols):
        for j, sym_b in enumerate(features.symbols):
            if i >= j:
                continue
            report = transfer_entropy(
                features.ofi[:, i],
                features.ofi[:, j],
                n_bins=int(args.n_bins),
                lag_rows=int(args.lag_rows),
                n_surrogates=int(args.n_surrogates),
                seed=int(args.seed),
            )
            pairs.append(
                {
                    "symbol_x": sym_a,
                    "symbol_y": sym_b,
                    "report": asdict(report),
                }
            )
            _log.info(
                "pair %s↔%s  TE(Y→X)=%.4f p=%.3f  TE(X→Y)=%.4f p=%.3f  verdict=%s",
                sym_a,
                sym_b,
                report.te_y_to_x_nats,
                report.p_value_y_to_x,
                report.te_x_to_y_nats,
                report.p_value_x_to_y,
                report.verdict,
            )

    verdict_counts: dict[str, int] = {}
    for entry in pairs:
        verdict = str(entry["report"]["verdict"])
        verdict_counts[verdict] = verdict_counts.get(verdict, 0) + 1

    payload: dict[str, Any] = {
        "n_rows": features.n_rows,
        "n_symbols": features.n_symbols,
        "n_bins": int(args.n_bins),
        "lag_rows": int(args.lag_rows),
        "n_surrogates": int(args.n_surrogates),
        "seed": int(args.seed),
        "n_pairs": len(pairs),
        "verdict_counts": verdict_counts,
        "pairs": pairs,
    }
    body = json.dumps(payload, indent=2, sort_keys=True, default=str)
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(body, encoding="utf-8")
    print(body)

    _log.info("verdict summary: %s", verdict_counts)
    return 0


if __name__ == "__main__":
    sys.exit(main())
