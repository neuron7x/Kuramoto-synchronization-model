"""Run walk-forward SABRE CAL evaluation."""

from __future__ import annotations

import argparse

import yaml

from neuropro.data import read_ticks_csv
from neuropro.walkforward import walkforward


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    args = parser.parse_args()
    cfg = yaml.safe_load(open(args.config))
    base_cfg = yaml.safe_load(open(cfg.get("extends", "configs/demo.yaml")))
    base_cfg.update(cfg.get("overrides", {}))
    df = read_ticks_csv(base_cfg["data"]["path"], base_cfg["data"]["time_col"])
    feat_cols = ["ret1", "ret5", "ret20", "vol10", "vol50", "spread", "regime"]
    y_col = "y"
    res = walkforward(
        df,
        base_cfg,
        feat_cols,
        y_col,
        train_frac=cfg["walkforward"]["train_frac"],
        step_frac=cfg["walkforward"]["step_frac"],
    )
    res.to_csv("wf_results.csv", index=False)
    print("Saved wf_results.csv | Rows:", len(res))


if __name__ == "__main__":
    main()
