from __future__ import annotations

from pathlib import Path

from runtime.riee.engine import (
    KernelPanic,
    PrefrontalCortexEngine,
    enforce_runtime_invariant,
    generate_ed25519_keypair,
    runtime_interceptor,
    sign_file,
    state_interceptor,
    verify_file,
)
from scripts.riee.chaos_engine import run_chaos


def _claims_with_gamma(tmp_path: Path) -> Path:
    p = tmp_path / "CLAIMS.md"
    p.write_text("GAMMA-CLAIM: 1.0\n", encoding="utf-8")
    return p


def test_delta_engine_and_interceptor(tmp_path: Path) -> None:
    claims = _claims_with_gamma(tmp_path)
    status = enforce_runtime_invariant(1.0, claims)
    assert status.state_validity

    @state_interceptor(claims)
    def good() -> float:
        return 1.0

    assert good() == 1.0


def test_kernel_panic_on_drift(tmp_path: Path) -> None:
    claims = _claims_with_gamma(tmp_path)

    @state_interceptor(claims)
    def bad() -> float:
        return 1.1

    try:
        bad()
    except KernelPanic as exc:
        assert "Kernel_Panic" in str(exc)
    else:
        raise AssertionError("panic expected")


def test_prefrontal_runtime_interceptor() -> None:
    pfc = PrefrontalCortexEngine(gamma_claim=1.0)

    @runtime_interceptor(pfc)
    def drifted() -> float:
        return 1.01

    try:
        drifted()
    except KernelPanic:
        pass
    else:
        raise AssertionError("runtime interceptor must panic on drift")


def test_ed25519_sign_verify(tmp_path: Path) -> None:
    f = tmp_path / "claims.txt"
    f.write_text("abc", encoding="utf-8")
    sk = tmp_path / "sk.bin"
    pk = tmp_path / "pk.bin"
    sig = tmp_path / "sig.bin"
    generate_ed25519_keypair(sk, pk)
    sign_file(f, sk, sig)
    assert verify_file(f, pk, sig)


def test_chaos_engine_detection(tmp_path: Path, monkeypatch) -> None:
    _claims_with_gamma(tmp_path)
    monkeypatch.chdir(tmp_path)
    (tmp_path / "CLAIMS.md").write_text("GAMMA-CLAIM: 1.0\n", encoding="utf-8")
    detected, total = run_chaos(1000)
    assert detected == total // 2
