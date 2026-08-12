# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Validation helpers for GB hydrology and water quality standards."""

from __future__ import annotations

import torch


class GBStandardValidator:
    """GB/T 22482-2008 (hydrology) + GB 3838-2002 (water quality) compliance checks."""

    def __init__(self) -> None:
        self.h_tol: dict[str, float] = {
            "water_level_rel": 0.10,
            "flow_rel": 0.15,
            "lead_hours": 6.0,
        }
        self.ph_range: tuple[float, float] = (6.0, 9.0)
        self.do_min: float = 5.0
        self.turb_max: float = 30.0
        self.nit_max: float = 10.0
        self.bact_max: float = 10000.0

    def validate_hydrology(
        self, pred: torch.Tensor, true: torch.Tensor
    ) -> dict[str, float | bool | str]:
        level_rel = torch.mean(
            torch.abs(pred[:, 0] - true[:, 0]) / (true[:, 0].abs() + 1e-6)
        ).item()
        flow_rel = torch.mean(torch.abs(pred[:, 1] - true[:, 1]) / (true[:, 1].abs() + 1e-6)).item()
        ok = (level_rel <= self.h_tol["water_level_rel"]) and (flow_rel <= self.h_tol["flow_rel"])
        return {
            "standard": "GB/T 22482-2008",
            "water_level_rel_err": level_rel,
            "flow_rel_err": flow_rel,
            "compliance": ok,
        }

    def validate_water_quality(self, pred: torch.Tensor) -> dict[str, float | bool | str]:
        ph_ok = (
            ((pred[:, 0] >= self.ph_range[0]) & (pred[:, 0] <= self.ph_range[1]))
            .float()
            .mean()
            .item()
        )
        do_ok = (pred[:, 1] >= self.do_min).float().mean().item()
        turb_ok = (pred[:, 2] <= self.turb_max).float().mean().item()
        nit_ok = (pred[:, 3] <= self.nit_max).float().mean().item()
        bact_ok = (pred[:, 4] <= self.bact_max).float().mean().item()
        compliance = min(ph_ok, do_ok, turb_ok, nit_ok, bact_ok) >= 0.9
        return {
            "standard": "GB 3838-2002",
            "class": "III",
            "pH_ok": ph_ok,
            "DO_ok": do_ok,
            "turb_ok": turb_ok,
            "nit_ok": nit_ok,
            "bact_ok": bact_ok,
            "compliance": compliance,
        }

    def validate_all(
        self,
        outputs: dict[str, torch.Tensor],
        targets: dict[str, torch.Tensor] | None = None,
    ) -> dict[str, dict[str, float | bool | str] | bool]:
        res: dict[str, dict[str, float | bool | str] | bool] = {}
        if "water_quality" in outputs:
            res["water_quality"] = self.validate_water_quality(outputs["water_quality"])
        if targets and ("hydrology" in outputs) and ("y_hydro" in targets):
            res["hydrology"] = self.validate_hydrology(outputs["hydrology"], targets["y_hydro"])
        res["overall_compliance"] = all(
            v.get("compliance", True) if isinstance(v, dict) else True
            for v in res.values()
            if v is not None
        )
        return res
