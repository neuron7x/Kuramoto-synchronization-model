"""Core model definition for HydroBrain Unified System v2."""

from __future__ import annotations

import torch
import torch.nn as nn

from runtime.model_registry import ModelMetadata, register_model

# --- Graph backend (minimal, dependency free) ---
def _normalize_adjacency(A: torch.Tensor, add_self_loops: bool = True) -> torch.Tensor:
    if add_self_loops:
        I = torch.eye(A.size(-1), device=A.device, dtype=A.dtype)  # noqa: E741
        A = A + I
    deg = A.sum(-1)
    deg_inv_sqrt = torch.pow(deg + 1e-8, -0.5)
    D_inv_sqrt = torch.diag_embed(deg_inv_sqrt)
    return D_inv_sqrt @ A @ D_inv_sqrt


class _GraphLayer(nn.Module):
    def __init__(self, in_features: int, out_features: int) -> None:
        super().__init__()
        self.lin = nn.Linear(in_features, out_features)
        self.act = nn.GELU()

    def forward(self, X: torch.Tensor, A_hat: torch.Tensor) -> torch.Tensor:
        HX = self.lin(X)  # (B,S,F')
        out = torch.matmul(A_hat, HX)  # (S,S) @ (B,S,F') -> (B,S,F')
        return self.act(out)


class SpatialEncoderMinimal(nn.Module):
    def __init__(
        self, in_features: int, hidden: int = 128, layers: int = 2, pool: str = "mean"
    ) -> None:
        super().__init__()
        self.layers = nn.ModuleList()
        dims = [in_features] + [hidden] * layers
        for i in range(layers):
            self.layers.append(_GraphLayer(dims[i], dims[i + 1]))
        self.pool = pool

    def forward(self, X: torch.Tensor, A_hat: torch.Tensor) -> torch.Tensor:
        B, T, S, _ = X.shape
        Z = X
        for gl in self.layers:
            Z_new = []
            for t in range(T):
                zt = gl(Z[:, t], A_hat)  # (B,S,H)
                Z_new.append(zt)
            Z = torch.stack(Z_new, dim=1)  # (B,T,S,H)
        if self.pool == "mean":
            return Z.mean(dim=2)  # (B,T,H)
        if self.pool == "max":
            return Z.max(dim=2).values
        return torch.cat([Z.mean(dim=2), Z.max(dim=2).values], dim=-1)


class PositionalEncoding(nn.Module):
    def __init__(self, d_model: int, max_len: int = 2000) -> None:
        super().__init__()
        pe = torch.zeros(max_len, d_model)
        pos = torch.arange(0, max_len, dtype=torch.float).unsqueeze(1)
        div = torch.exp(
            torch.arange(0, d_model, 2).float()
            * (-torch.log(torch.tensor(10000.0)) / d_model)
        )
        pe[:, 0::2] = torch.sin(pos * div)
        pe[:, 1::2] = torch.cos(pos * div)
        self.register_buffer("pe", pe.unsqueeze(0))

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return x + self.pe[:, : x.size(1), :]


class TemporalEncoder(nn.Module):
    def __init__(
        self,
        input_size: int,
        lstm_hidden: int = 256,
        lstm_layers: int = 1,
        tfm_layers: int = 2,
        tfm_heads: int = 4,
        dropout: float = 0.1,
    ) -> None:
        super().__init__()
        self.lstm = nn.LSTM(
            input_size=input_size,
            hidden_size=lstm_hidden,
            num_layers=lstm_layers,
            batch_first=True,
            bidirectional=True,
            dropout=dropout if lstm_layers > 1 else 0.0,
        )
        self.pos = PositionalEncoding(2 * lstm_hidden)
        enc = nn.TransformerEncoderLayer(
            d_model=2 * lstm_hidden,
            nhead=tfm_heads,
            batch_first=True,
            dim_feedforward=4 * lstm_hidden,
            dropout=dropout,
            activation="gelu",
        )
        self.tfm = nn.TransformerEncoder(enc, num_layers=tfm_layers)
        self.attn = nn.MultiheadAttention(
            embed_dim=2 * lstm_hidden,
            num_heads=tfm_heads,
            batch_first=True,
            dropout=dropout,
        )
        self.norm = nn.LayerNorm(2 * lstm_hidden)

    def forward(self, Xt: torch.Tensor) -> torch.Tensor:
        Zl, _ = self.lstm(Xt)
        Zp = self.pos(Zl)
        Zf = self.tfm(Zp)
        q = Zf[:, -1:, :]
        a, _ = self.attn(q, Zf, Zf)
        return self.norm(a.squeeze(1))


class HydroBrainV2(nn.Module):
    """Unified spatial-temporal model with multi-head outputs."""

    def __init__(self, cfg: dict, A: torch.Tensor | None = None) -> None:
        super().__init__()
        m, tr = cfg["model"], cfg.get("training", {})
        self.pool = m.get("pool", "mean")
        in_feats = m["num_features"]
        gnn_hidden = m.get("gnn_hidden", 128)
        gnn_layers = m.get("gnn_layers", 2)

        self.spatial = SpatialEncoderMinimal(
            in_feats, gnn_hidden, gnn_layers, self.pool
        )

        hs_in = gnn_hidden if self.pool in ("mean", "max") else 2 * gnn_hidden
        self.temporal = TemporalEncoder(
            hs_in,
            m.get("lstm_hidden", 256),
            m.get("lstm_layers", 1),
            m.get("tfm_layers", 2),
            m.get("tfm_heads", 4),
            tr.get("dropout", 0.1),
        )
        self.proj_spatial = nn.Linear(hs_in, 256)
        self.proj_temporal = nn.Linear(2 * m.get("lstm_hidden", 256), 256)
        self.ln = nn.LayerNorm(512)

        self.flood_head = nn.Sequential(
            nn.Linear(512, 256),
            nn.GELU(),
            nn.Dropout(tr.get("dropout", 0.1)),
            nn.Linear(256, 128),
            nn.GELU(),
            nn.Linear(128, m.get("flood_classes", 3)),
        )
        self.hydro_head = nn.Sequential(
            nn.Linear(512, 256),
            nn.GELU(),
            nn.Dropout(tr.get("dropout", 0.1)),
            nn.Linear(256, 128),
            nn.GELU(),
            nn.Linear(128, 2),
        )
        self.quality_head = nn.Sequential(
            nn.Linear(512, 256),
            nn.GELU(),
            nn.Dropout(tr.get("dropout", 0.1)),
            nn.Linear(256, 128),
            nn.GELU(),
            nn.Linear(128, m.get("quality_dims", 5)),
        )

        A = A if A is not None else torch.ones(m["num_stations"], m["num_stations"])
        self.register_buffer("A_hat", _normalize_adjacency(A))

    def forward(self, X: torch.Tensor) -> dict[str, torch.Tensor]:
        Zs = self.spatial(X, self.A_hat)
        Zt = self.temporal(Zs)
        Zs_last = Zs[:, -1, :]
        U = torch.cat([self.proj_spatial(Zs_last), self.proj_temporal(Zt)], dim=1)
        U = self.ln(U)
        return {
            "flood_logits": self.flood_head(U),
            "hydrology": self.hydro_head(U),
            "water_quality": self.quality_head(U),
            "features": U,
        }


HYDROBRAIN_V2_METADATA = register_model(
    ModelMetadata(
        model_id="hydrobrain_v2",
        training_data_window={
            "source": "synthetic_yangtze_npz",
            "window_shape": "N=256, T=64, S=8, F=5",
            "seasonality": "0-4π seasonal cycle",
        },
        eval_metrics={
            "flood_f1": "pending",
            "hydrology_mae": "pending",
            "water_quality_mae": "pending",
        },
        model_type="spatiotemporal_gnn_tfm",
        module="hydrobrain_v2.model.HydroBrainV2",
        owners=("hydrobrain", "risk-monitoring"),
        notes="Unified GNN+LSTM+Transformer backbone with flood/hydrology/quality heads.",
    )
)
