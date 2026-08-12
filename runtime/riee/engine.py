from __future__ import annotations

import math
import shutil
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

from runtime.riee.telemetry import emit_riee_event


@dataclass(frozen=True)
class RIEEStatus:
    state_validity: bool
    delta: float
    reason: str
    threshold: float


class KernelPanic(RuntimeError):
    pass


@dataclass(frozen=True)
class EpistemicState:
    gamma_fact: float
    gamma_claim: float
    delta_threshold: float = 1e-6


class PrefrontalCortexEngine:
    """Active runtime invariant enforcer with allostatic threshold control."""

    def __init__(self, gamma_claim: float, base_threshold: float = 1e-6) -> None:
        self._gamma_claim = gamma_claim
        self._base_threshold = base_threshold

    def threshold_for_stress(self, stress_level: float) -> float:
        stress = max(stress_level, 0.0)
        return self._base_threshold / (1.0 + stress)

    def enforce(self, gamma_fact: float, stress_level: float = 0.0) -> RIEEStatus:
        if not math.isfinite(gamma_fact):
            status = RIEEStatus(
                False,
                float("inf"),
                "non-finite runtime signal",
                self.threshold_for_stress(stress_level),
            )
            emit_riee_event(status, gamma_fact=gamma_fact, gamma_claim=self._gamma_claim)
            return status
        threshold = self.threshold_for_stress(stress_level)
        delta = abs(gamma_fact - self._gamma_claim)
        if delta > threshold:
            status = RIEEStatus(False, delta, "epistemic drift detected", threshold)
            emit_riee_event(status, gamma_fact=gamma_fact, gamma_claim=self._gamma_claim)
            return status
        status = RIEEStatus(True, delta, "ok", threshold)
        emit_riee_event(status, gamma_fact=gamma_fact, gamma_claim=self._gamma_claim)
        return status


def load_claim_gamma(claims_path: Path) -> float:
    text = claims_path.read_text(encoding="utf-8")
    marker = "GAMMA-CLAIM:"
    for line in text.splitlines():
        if marker in line:
            return float(line.split(marker, 1)[1].strip())
    raise KernelPanic(f"Kernel_Panic: {marker} missing in {claims_path}")


def enforce_runtime_invariant(
    gamma_fact: float,
    claims_path: Path,
    threshold: float = 1e-6,
) -> RIEEStatus:
    pfc = PrefrontalCortexEngine(load_claim_gamma(claims_path), base_threshold=threshold)
    return pfc.enforce(gamma_fact)


def quarantine_snapshot(
    source_paths: list[Path],
    out_dir: Path = Path("artifacts/quarantine"),
) -> Path:
    ts = int(time.time() * 1000)
    target = out_dir / f"panic_{ts}"
    target.mkdir(parents=True, exist_ok=True)
    for src in source_paths:
        if src.exists() and src.is_file():
            shutil.copy2(src, target / src.name)
    return target


def state_interceptor(
    claims_path: Path,
    threshold: float = 1e-6,
) -> Callable[[Callable[..., float]], Callable[..., float]]:
    pfc = PrefrontalCortexEngine(load_claim_gamma(claims_path), base_threshold=threshold)

    def deco(fn: Callable[..., float]) -> Callable[..., float]:
        def wrapped(*args: Any, **kwargs: Any) -> float:
            gamma_fact = fn(*args, **kwargs)
            status = pfc.enforce(gamma_fact)
            if not status.state_validity:
                q = quarantine_snapshot([claims_path, Path("docs/architecture/claim_graph.json")])
                raise KernelPanic(
                    "Kernel_Panic "
                    f"delta={status.delta} threshold={status.threshold} quarantine={q}"
                )
            return gamma_fact

        return wrapped

    return deco


def runtime_interceptor(
    pfc: PrefrontalCortexEngine,
) -> Callable[[Callable[..., float]], Callable[..., float]]:
    def deco(fn: Callable[..., float]) -> Callable[..., float]:
        def wrapped(*args: Any, **kwargs: Any) -> float:
            gamma_fact = fn(*args, **kwargs)
            status = pfc.enforce(gamma_fact)
            if not status.state_validity:
                raise KernelPanic(f"Kernel_Panic delta={status.delta} threshold={status.threshold}")
            return gamma_fact

        return wrapped

    return deco


def generate_ed25519_keypair(signing_key_path: Path, verify_key_path: Path) -> None:
    signing_key = Ed25519PrivateKey.generate()
    verify_key = signing_key.public_key()
    signing_key_path.write_bytes(
        signing_key.private_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PrivateFormat.Raw,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    verify_key_path.write_bytes(
        verify_key.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
    )


def sign_file(path: Path, signing_key_path: Path, sig_path: Path) -> None:
    signing_key = Ed25519PrivateKey.from_private_bytes(signing_key_path.read_bytes())
    sig_path.write_bytes(signing_key.sign(path.read_bytes()))


def verify_file(path: Path, verify_key_path: Path, sig_path: Path) -> bool:
    verify_key = Ed25519PublicKey.from_public_bytes(verify_key_path.read_bytes())
    try:
        verify_key.verify(sig_path.read_bytes(), path.read_bytes())
        return True
    except Exception:
        return False
