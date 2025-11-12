from pydantic import BaseModel, Field
from typing import Literal

ForbiddenMode = Literal["static", "quantile", "mad", "pid"]


class QLWConfig(BaseModel):
    nx: int = Field(128, ge=16, le=8192)
    nt: int = Field(512, ge=32, le=65536)
    dx: float = Field(1.0, gt=0)
    dt: float = Field(0.01, gt=0)
    noise_sigma: float = Field(0.02, ge=0, le=1.0)
    hotspot_k: int = Field(8, ge=1, le=128)
    resonance_window: int = Field(16, ge=4, le=1024)
    forbidden_threshold: float = Field(1.5, gt=0)
    forbidden_mode: ForbiddenMode = Field("quantile")
    forbidden_quantile: float = Field(0.95, ge=0.5, le=0.99)
    forbidden_k: float = Field(3.0, gt=1.0)
    c_min: float = Field(1.0, gt=0)
    c_max: float = Field(5.0, gt=0)
    gamma_lo: float = Field(0.05, gt=0)
    gamma_hi: float = Field(0.6, gt=0)
    pml_width_frac: float = Field(0.075, ge=0.0, le=0.2)
    pml_gain: float = Field(2.0, gt=0)
    seed: int = Field(42, ge=0)
    phase_smooth_len: int = Field(8, ge=1, le=64)
    c_ema_alpha: float = Field(0.1, gt=0, le=1.0)
    use_numba: bool = Field(True)
    use_gpu: bool = Field(False)
    # PID‑Tau safety
    tau_min: float = Field(0.5, gt=0)
    tau_max: float = Field(10.0, gt=0)
    pid_target: float = Field(0.15, ge=0.01, le=0.8)
