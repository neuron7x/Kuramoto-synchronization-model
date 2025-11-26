"""Smoke tests for HydroBrainV2 output shapes."""

from __future__ import annotations

import pytest

torch = pytest.importorskip("torch")

from hydrobrain_v2.model import HydroBrainV2  # noqa: E402 - after importorskip


def test_forward_shapes() -> None:
    cfg = {
        "model": {
            "num_features": 5,
            "num_stations": 4,
            "flood_classes": 3,
            "quality_dims": 5,
            "graph_backend": "minimal",
            "gnn_hidden": 64,
            "gnn_layers": 1,
            "lstm_hidden": 64,
            "lstm_layers": 1,
            "tfm_layers": 1,
            "tfm_heads": 2,
            "pool": "mean",
        },
        "training": {"dropout": 0.1},
    }
    A = torch.ones(4, 4)
    model = HydroBrainV2(cfg, A)
    X = torch.randn(2, 8, 4, 5)
    out = model(X)
    assert out["flood_logits"].shape == (2, 3)
    assert out["hydrology"].shape == (2, 2)
    assert out["water_quality"].shape == (2, 5)
