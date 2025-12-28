from __future__ import annotations

from pathlib import Path

import torch

import hbunified
import hydrobrain_v2.utils as hb_utils


def test_load_checkpoint_uses_weights_only(monkeypatch) -> None:
    calls: dict[str, object] = {}

    def fake_load(path, map_location=None, weights_only=None):  # type: ignore[override]
        calls["map_location"] = map_location
        calls["weights_only"] = weights_only
        return {"model": {}}

    monkeypatch.setattr(hb_utils.torch, "load", fake_load)

    hb_utils.load_checkpoint("dummy.pt")

    assert calls["weights_only"] is True
    assert calls["map_location"] == "cpu"


def test_build_model_prefers_safe_checkpoint_load(tmp_path: Path, monkeypatch) -> None:
    calls: dict[str, object] = {}

    class DummyModel:
        def __init__(self, cfg, A_tensor) -> None:  # noqa: ANN001 - external signature
            self.cfg = cfg

        def to(self, device):
            calls["device"] = device
            return self

        def load_state_dict(self, state, strict=False):  # noqa: ANN001
            calls["state"] = state
            calls["strict"] = strict

    monkeypatch.setattr(hbunified, "HydroBrainV2", DummyModel)

    def fake_load(path, map_location=None, weights_only=None):  # type: ignore[override]
        calls["map_location"] = map_location
        calls["weights_only"] = weights_only
        return {"model": {}}

    monkeypatch.setattr(hbunified.torch, "load", fake_load)

    weights = tmp_path / "ckpt.pt"
    weights.write_text("payload", encoding="utf-8")

    cfg = {"stations": {"adjacency": [[1, 0], [0, 1]]}, "weights": str(weights)}
    hbunified.build_model(cfg, device="cpu", A_tensor=torch.ones(2, 2))

    assert calls["weights_only"] is True
    assert calls["map_location"] == "cpu"

