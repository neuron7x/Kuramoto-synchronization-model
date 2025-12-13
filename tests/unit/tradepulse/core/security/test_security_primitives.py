from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Mapping

import pytest

from tradepulse.core.auth.rbac import Permission, require, set_current_user
from tradepulse.core.security.audit import AuditLogger
from tradepulse.core.security.encryption import EncryptedField, Encryption
from tradepulse.core.security.ids import IDS
from tradepulse.core.security.incident import IncidentResponse
from tradepulse.core.security.secrets import Secrets


class _DummyKV:
    def __init__(self, data: Mapping[str, Mapping[str, str]]) -> None:
        self._data = data

    def read_secret_version(self, path: str) -> dict:
        return {"data": {"data": self._data.get(path, {})}}


class _DummyTransit:
    def encrypt_data(self, *, name: str, plaintext: str) -> dict:
        return {"data": {"ciphertext": f"{name}:{plaintext}"}}

    def decrypt_data(self, *, name: str, ciphertext: str) -> dict:
        prefix = f"{name}:"
        value = ciphertext[len(prefix) :] if ciphertext.startswith(prefix) else ciphertext
        return {"data": {"plaintext": value}}


class _DummyVault:
    def __init__(self, data: Mapping[str, Mapping[str, str]]) -> None:
        self.secrets = SimpleNamespace(
            kv=SimpleNamespace(v2=_DummyKV(data)),
            transit=_DummyTransit(),
        )


def test_secrets_with_custom_client() -> None:
    client = _DummyVault({"secret/data/demo": {"token": "value"}})
    secrets = Secrets(client=client)
    assert secrets.get("secret/data/demo") == {"token": "value"}
    cipher = secrets.encrypt("payload")
    assert secrets.decrypt(cipher) == "payload"


def test_encryption_round_trip(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENCRYPTION_KEY", "unit-test-key")
    monkeypatch.setenv("ENCRYPTION_SALT", "unit-test-salt")
    cipher = Encryption()
    payload = b"hello-world"
    encrypted = cipher.encrypt(payload)
    assert cipher.decrypt(encrypted) == payload
    field = EncryptedField()
    wrapped = field.encrypt_value("secret")
    assert field.decrypt_value(wrapped) == "secret"


def test_rbac_require_allows_only_permitted_roles() -> None:
    @require(Permission.TRADE_EXECUTE)
    def _execute() -> str:
        return "ok"

    set_current_user(None)
    with pytest.raises(PermissionError):
        _execute()

    set_current_user(SimpleNamespace(role="admin"))
    assert _execute() == "ok"


def test_audit_logger_writes_json(tmp_path: Path) -> None:
    log_path = tmp_path / "audit.log"
    logger = AuditLogger(log_path=log_path)
    logger.log(
        event="trade_executed",
        user="alice",
        resource="BTC/USDT",
        action="MARKET_BUY",
        result="SUCCESS",
        amount=1.0,
    )
    content = log_path.read_text(encoding="utf-8").strip()
    assert content
    record = json.loads(content)
    assert record["event"] == "trade_executed"
    assert record["result"] == "SUCCESS"


def test_ids_blocks_after_threshold() -> None:
    ids = IDS()
    user = "intruder"
    for _ in range(5):
        ids.record_failure(user)
    assert ids.check_brute_force(user, max_attempts=5)


def test_incident_response_records_and_handles_kill_switch() -> None:
    calls = {}

    def _hook() -> None:
        calls["activated"] = True

    ir = IncidentResponse(kill_switch_hook=_hook)
    ir.report("CRITICAL", "test_event", {"detail": "value"})
    assert ir.incidents[-1]["severity"] == "CRITICAL"
    assert calls["activated"]
