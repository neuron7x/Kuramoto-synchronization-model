#!/usr/bin/env python3
# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""GeoSyncHydro Unified System v2 CLI, pipeline, and API entrypoints."""

from __future__ import annotations

import argparse
import json
import logging
import os
from pathlib import Path
from typing import Any

import numpy as np
import torch
import yaml
from torch import nn

from geosync_hydro.data import generate_yangtze_npz, load_npz_dataset
from geosync_hydro.model import GeoSyncHydroV2
from geosync_hydro.monitor import RealTimeMonitor
from geosync_hydro.utils import save_checkpoint, setup_logging
from geosync_hydro.validator import GBStandardValidator


def build_A(cfg: dict) -> torch.Tensor:
    adjacency = np.array(cfg["stations"]["adjacency"], dtype=np.float32)
    return torch.tensor(adjacency, dtype=torch.float32)


def build_model(cfg: dict, device: str, A_tensor: torch.Tensor) -> GeoSyncHydroV2:
    model = GeoSyncHydroV2(cfg, A_tensor).to(device)
    weights_path = cfg.get("weights")
    if weights_path and os.path.exists(weights_path):
        obj = torch.load(weights_path, map_location=device, weights_only=True)
        model.load_state_dict(obj["model"] if "model" in obj else obj, strict=False)
        logging.info("Loaded weights from %s", weights_path)
    return model


def make_optim(model: GeoSyncHydroV2, cfg: dict):
    opt = torch.optim.AdamW(
        model.parameters(),
        lr=cfg["training"]["lr"],
        weight_decay=cfg["training"]["weight_decay"],
    )
    sch = torch.optim.lr_scheduler.CosineAnnealingLR(opt, T_max=cfg["training"]["t_max"])
    return opt, sch


def train(cfg_path: str) -> None:
    cfg = yaml.safe_load(Path(cfg_path).read_text())
    os.makedirs(cfg["training"]["save_dir"], exist_ok=True)
    setup_logging(cfg["logging"]["dir"], cfg["logging"]["file"])
    device = "cuda" if torch.cuda.is_available() else "cpu"
    A = build_A(cfg)

    (Xtr, yfr, yhr, yqr), _ = load_npz_dataset(cfg["data"]["train_npz"], cfg, synth_ok=True, N=512)
    (Xva, yfv, yhv, yqv), _ = load_npz_dataset(cfg["data"]["val_npz"], cfg, synth_ok=True, N=256)

    model = build_model(cfg, device, A)
    opt, sch = make_optim(model, cfg)
    loss_flood = nn.CrossEntropyLoss()
    loss_hydro = nn.HuberLoss()
    loss_qual = nn.HuberLoss()

    tr_loader = torch.utils.data.DataLoader(
        torch.utils.data.TensorDataset(Xtr, yfr, yhr, yqr),
        batch_size=cfg["training"]["batch_size"],
        shuffle=True,
    )
    va_loader = torch.utils.data.DataLoader(
        torch.utils.data.TensorDataset(Xva, yfv, yhv, yqv),
        batch_size=cfg["training"]["batch_size"],
        shuffle=False,
    )

    best = float("inf")
    es_pat = cfg["training"]["early_stopping"]
    es_cnt = 0
    for ep in range(1, cfg["training"]["epochs"] + 1):
        model.train()
        tot = 0.0
        for xb, yf, yh, yq in tr_loader:
            xb, yf, yh, yq = xb.to(device), yf.to(device), yh.to(device), yq.to(device)
            out = model(xb)
            lf = loss_flood(out["flood_logits"], yf)
            lh = loss_hydro(out["hydrology"], yh)
            lq = loss_qual(out["water_quality"], yq)
            phy = 0.0
            if cfg["physics"]["enable"]:
                lvl = out["hydrology"][:, 0]
                flw = out["hydrology"][:, 1]
                phy += torch.relu(cfg["physics"]["min_level"] - lvl).mean()
                phy += torch.relu(cfg["physics"]["min_flow"] - flw).mean()
                phy += torch.relu(flw - cfg["physics"]["max_flow"]).mean()
            loss = (
                cfg["loss_weights"]["flood"] * lf
                + cfg["loss_weights"]["hydrology"] * lh
                + cfg["loss_weights"]["quality"] * lq
                + cfg["loss_weights"]["physics"] * phy
            )
            opt.zero_grad()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            opt.step()
            tot += float(loss.detach().cpu())
        sch.step()

        model.eval()
        vtot = 0.0
        with torch.no_grad():
            for xb, yf, yh, yq in va_loader:
                xb, yf, yh, yq = (
                    xb.to(device),
                    yf.to(device),
                    yh.to(device),
                    yq.to(device),
                )
                out = model(xb)
                lf = loss_flood(out["flood_logits"], yf)
                lh = loss_hydro(out["hydrology"], yh)
                lq = loss_qual(out["water_quality"], yq)
                phy = 0.0
                if cfg["physics"]["enable"]:
                    lvl = out["hydrology"][:, 0]
                    flw = out["hydrology"][:, 1]
                    phy += torch.relu(cfg["physics"]["min_level"] - lvl).mean()
                    phy += torch.relu(cfg["physics"]["min_flow"] - flw).mean()
                    phy += torch.relu(flw - cfg["physics"]["max_flow"]).mean()
                vtot += float(
                    (
                        cfg["loss_weights"]["flood"] * lf
                        + cfg["loss_weights"]["hydrology"] * lh
                        + cfg["loss_weights"]["quality"] * lq
                        + cfg["loss_weights"]["physics"] * phy
                    ).cpu()
                )

        tr_loss = tot / len(tr_loader)
        va_loss = vtot / len(va_loader)
        logging.info("[Epoch %d] train=%.4f val=%.4f", ep, tr_loss, va_loss)

        if ep % cfg["training"]["ckpt_every"] == 0:
            save_checkpoint(
                cfg["training"]["save_dir"],
                f"ckpt_epoch_{ep}.pt",
                model,
                opt,
                sch,
                extra={"epoch": ep, "train_loss": tr_loss, "val_loss": va_loss},
            )

        if va_loss < best:
            best = va_loss
            es_cnt = 0
            save_checkpoint(
                cfg["training"]["save_dir"],
                cfg["training"]["save_name"],
                model,
                opt,
                sch,
                extra={
                    "epoch": ep,
                    "train_loss": tr_loss,
                    "val_loss": va_loss,
                    "best": True,
                },
            )
        else:
            es_cnt += 1
            if es_cnt >= es_pat:
                logging.info("Early stopping at epoch %d", ep)
                break


def infer(cfg_path: str, npz_path: str | None = None, window_json: str | None = None) -> None:
    cfg = yaml.safe_load(Path(cfg_path).read_text())
    setup_logging(cfg["logging"]["dir"], cfg["logging"]["file"])
    device = "cuda" if torch.cuda.is_available() else "cpu"
    A = build_A(cfg)
    model = build_model(cfg, device, A).eval()

    outs: list[dict[str, Any]] = []
    if npz_path:
        (X, _, _, _), _meta = load_npz_dataset(npz_path, cfg, synth_ok=False)
        logging.info("Loaded dataset for inference: %s", _meta["path"])
        X = X.to(device)
        with torch.no_grad():
            out = model(X)
            probs = torch.softmax(out["flood_logits"], dim=-1).cpu().numpy()
            hydro = out["hydrology"].cpu().numpy()
            qual = out["water_quality"].cpu().numpy()
        for p, h, q in zip(probs, hydro, qual):
            outs.append(
                {
                    "flood_prob": p.tolist(),
                    "hydrology": h.tolist(),
                    "water_quality": q.tolist(),
                }
            )
    elif window_json:
        W = np.array(json.loads(window_json), dtype=float)
        X = preprocess_window(W).to(device)
        with torch.no_grad():
            out = model(X)
            p = torch.softmax(out["flood_logits"], dim=-1)[0].cpu().tolist()
            h = out["hydrology"][0].cpu().tolist()
            q = out["water_quality"][0].cpu().tolist()
        outs.append({"flood_prob": p, "hydrology": h, "water_quality": q})
    else:
        raise SystemExit("Provide --npz or --window_json")

    os.makedirs(os.path.dirname(cfg["inference"]["save_path"]) or ".", exist_ok=True)
    with open(cfg["inference"]["save_path"], "w", encoding="utf-8") as f:
        for o in outs:
            f.write(json.dumps(o) + "\n")
    print("Saved:", cfg["inference"]["save_path"])


def pipeline(cfg_path: str) -> None:
    cfg = yaml.safe_load(Path(cfg_path).read_text())
    setup_logging(cfg["logging"]["dir"], cfg["logging"]["file"])

    for pth, N in [(cfg["data"]["train_npz"], 512), (cfg["data"]["val_npz"], 256)]:
        if not os.path.exists(pth):
            os.makedirs(os.path.dirname(pth) or ".", exist_ok=True)
            generate_yangtze_npz(
                pth,
                N=N,
                T=cfg["data"]["T"],
                S=cfg["model"]["num_stations"],
                F=cfg["model"]["num_features"],
            )
            logging.info("Generated %s", pth)

    train(cfg_path)

    device = "cuda" if torch.cuda.is_available() else "cpu"
    A = build_A(cfg)
    model = build_model(cfg, device, A).eval()
    (Xva, yfv, yhv, yqv), _ = load_npz_dataset(cfg["data"]["val_npz"], cfg, synth_ok=False)
    Xva = Xva.to(device)
    with torch.no_grad():
        out = model(Xva)
    validator = GBStandardValidator()
    results = validator.validate_all(
        {
            "water_quality": out["water_quality"].cpu(),
            "hydrology": out["hydrology"].cpu(),
        },
        {"y_hydro": yhv},
    )

    metrics_path = os.path.join(cfg["training"]["save_dir"], "metrics.json")
    with open(metrics_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    logging.info("Metrics saved: %s", metrics_path)
    print(
        json.dumps(
            {
                "pipeline": "ok",
                "metrics_path": metrics_path,
                "overall_compliance": results["overall_compliance"],
            },
            indent=2,
        )
    )


def serve(cfg_path: str) -> None:
    cfg = yaml.safe_load(Path(cfg_path).read_text())
    setup_logging(cfg["logging"]["dir"], cfg["logging"]["file"])
    try:
        import uvicorn
        from fastapi import FastAPI
        from pydantic import BaseModel
    except Exception as exc:  # pragma: no cover - optional dependency guard
        raise SystemExit("Install fastapi & uvicorn to use API") from exc

    device = "cuda" if torch.cuda.is_available() else "cpu"
    A = build_A(cfg)
    monitor = RealTimeMonitor(
        cfg,
        A,
        weights_path=os.path.join(cfg["training"]["save_dir"], cfg["training"]["save_name"]),
        device=device,
    )

    app = FastAPI(title="GeoSyncHydro Unified System v2")

    class InferRequest(BaseModel):
        window: list

    @app.post("/infer")
    def infer_endpoint(req: InferRequest) -> dict[str, Any]:
        W = np.array(req.window, dtype=float)
        out = monitor.infer_window(W)
        return out

    uvicorn.run(app, host=cfg["api"]["host"], port=cfg["api"]["port"])


def preprocess_window(window: np.ndarray) -> torch.Tensor:
    from geosync_hydro.utils import preprocess_window as _preprocess_window

    return _preprocess_window(window)


def main() -> None:
    ap = argparse.ArgumentParser(description="GeoSyncHydro Unified System v2")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p_train = sub.add_parser("train")
    p_train.add_argument("--config", required=True)
    p_infer = sub.add_parser("infer")
    p_infer.add_argument("--config", required=True)
    p_infer.add_argument("--npz", default="")
    p_infer.add_argument("--window_json", default="")
    p_pipe = sub.add_parser("pipeline")
    p_pipe.add_argument("--config", required=True)
    p_api = sub.add_parser("serve")
    p_api.add_argument("--config", required=True)

    args = ap.parse_args()
    if args.cmd == "train":
        train(args.config)
    elif args.cmd == "infer":
        infer(args.config, args.npz or None, args.window_json or None)
    elif args.cmd == "pipeline":
        pipeline(args.config)
    elif args.cmd == "serve":
        serve(args.config)


if __name__ == "__main__":
    raise SystemExit(
        "Deprecated entrypoint. Use: python -m application.runtime.server --config <path>"
    )
