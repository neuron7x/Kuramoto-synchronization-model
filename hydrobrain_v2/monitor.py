"""Real-time monitoring utilities for HydroBrain Unified System v2."""

from __future__ import annotations

import logging
from typing import Any

import numpy as np
import torch

from .degradation import DegradationPolicy, apply_degradation
from .model import HydroBrainV2
from .utils import AnomalyDetector, DataImputer, preprocess_window
from .validator import GBStandardValidator


class RealTimeMonitor:
    def __init__(
        self,
        cfg: dict,
        A_tensor: torch.Tensor,
        weights_path: str | None = None,
        device: str | None = None,
    ) -> None:
        self.cfg = cfg
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.model = HydroBrainV2(cfg, A_tensor).to(self.device).eval()
        if weights_path:
            obj = torch.load(
                weights_path, map_location=self.device, weights_only=True
            )
            self.model.load_state_dict(
                obj["model"] if "model" in obj else obj, strict=False
            )
            logging.info("Weights loaded from %s", weights_path)
        self.validator = GBStandardValidator()
        self.imputer = DataImputer()
        self.anom = AnomalyDetector()
        self.th = cfg["monitoring"]

    @torch.no_grad()
    def infer_window(self, window_np: np.ndarray) -> dict[str, Any]:
        window_np = self.imputer.impute(window_np)
        z = self.anom.zscore(window_np)
        if z > self.th["sensor_anomaly_z"]:
            logging.warning(
                "Sensor anomaly: z=%.2f > %.2f", z, self.th["sensor_anomaly_z"]
            )
        X = preprocess_window(window_np).to(self.device)
        out = self.model(X)
        probs = torch.softmax(out["flood_logits"], dim=-1)
        resp: dict[str, Any] = {
            "flood_prob": probs[0].cpu().tolist(),
            "hydrology": out["hydrology"][0].cpu().tolist(),
            "water_quality": out["water_quality"][0].cpu().tolist(),
            "sensor_anomaly_z": z,
        }
        comp = self.validator.validate_all(
            {"water_quality": out["water_quality"], "hydrology": out["hydrology"]}
        )
        resp["compliance"] = comp

        alerts = []
        if resp["flood_prob"][-1] >= self.th["flood_high_risk"]:
            alerts.append(
                {
                    "type": "FLOOD_WARNING",
                    "level": "HIGH",
                    "message": "Високий ризик повені",
                }
            )
        if z > self.th["sensor_anomaly_z"]:
            alerts.append(
                {
                    "type": "SENSOR_ANOMALY",
                    "level": "MEDIUM",
                    "message": f"Підозрілі сенсорні дані (z={z:.2f})",
                }
            )
        resp["alerts"] = alerts
        return resp

    def infer_window_with_degradation(
        self,
        window_np: np.ndarray,
        *,
        policy: DegradationPolicy | None = None,
    ) -> tuple[dict[str, Any], "DegradationReport"]:
        """Run inference with timeout + fallback handling."""

        return apply_degradation(self.infer_window, window_np, policy=policy)
