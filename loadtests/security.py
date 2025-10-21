"""Security utilities for performance test harnesses."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Callable

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.algorithms import RSAAlgorithm

from application.settings import ApiSecuritySettings

LOADTEST_PRIVATE_KEY_PEM = """-----BEGIN PRIVATE KEY-----
MIIEvQIBADANBgkqhkiG9w0BAQEFAASCBKcwggSjAgEAAoIBAQDurg/WFMeAmmvq
1kHh3LqWVNTfIKlhbZ6HAg/s6acyDSl2fmD52Un7dvtO6/cfMoasWJ3is5nV/o8m
wBp0yT5s2AHbjGu00j4XMZAMML5ElR7CaaFbCQlT2OaTm9JZlENjg+ZuBHGq4YWR
Oq2IEnW40HaqBLn139NGow9xwDl07I0SnAuxD2QEoOyXsgHQZtPvFIoF7ddciHfX
ZuVetDUm1YTt4DFrDOsG1sj/fSDzdpP4WZdcVkJFvqow0qL/2V6EvgmXdGww2Wyr
mbSBO2PkYIUkEEntWypGL8IVinh5BEAF5ZMezikl7DJGxRmGI9Q597KrDwEOf13u
p7zLpgzZAgMBAAECggEAVq3m+WfNdhJem8fY4EYxivPe5PNvH/9X4Y7pqq/GNQKb
qrlFzabQW97/cE94jR9j0kZSfGieNx197mQ4l24YWh3uOsXZva7WtsScnBi9mJmR
NKh43V9AQG+WeUfPEhIqkQLvVcgOYbEKOU5WhAK0NvyaA6+4uybgixgfvT9CfofQ
Lby3PkMm6UuWcU19d4RqvGwgzmPeMD0xmB7l0BCEDjRU3sT5aVl0NlxztBRmi4eY
tlZOAvCWnD1anIl1ICPyhiqDaFLQWXHFIktrGWtc7bL4REE9RDOqUFiKgC1i/0Xx
Jp6f4AxPhbU0BgVUoS/V/LuTeGx1al40QxTbpk+tewKBgQD+HHhkavAs4/QD59vF
yzbEM8p6gRSn1T3LGYCuu/snjlZovlS8DIbg9jjveCfp6KyME6jOohPTk9m07NiN
6gpwzVZFqR/T28yl3av+dJL7FD0hF1z9GySp16Id/E7kuOedz2b/kQPPNRc47EQ8
zeNN7wvBDpOby3h5MmgJ7pOlTwKBgQDwdDp/4Ujrj7c+MuffG/RIJiGAm66BNB8h
bluxJzOxTmIL33/tDzLv7JveslREYsRZWYy9+si81DIlML6I9DdfqkLRQ8/eW1zI
6XKJ/+rtODyU+KEmIzZXFdrYKpggPTzp16DVpImcGIZZmhQnfuwrDbKH8u3qz6aM
x6NiLi9xVwKBgCqaw2SyuUoNfiAZg7OJ+siylkQr2Da7ffzLbdPeGKHtL3eoUbSl
tQeKwMkFsEt7g1KJCUh7zC8xHtNC0pwYnV+ETe6oCHoQ5CL7I5cqHGqUXhtqO2EE
aAVB7iBw6RlYFx1SZMZ8ndLj59zXYCmBq5apeaMIup7oYm6PkPn5Ui/pAoGBAJcs
S7coeUL4KPmm4ZaoqY1Ow9NqjWzXyxamnmkjP2Gi6QuT6Yat/pVPCbQaI9aWzeFq
5oxuhhQJyLkPC0tpVwMDNV0BqEeg4xXBh2xxhE6+A4CZTB+BFeHscJllNh1Wwtw1
3/1Ro96KoLTmpPMr3ek3hF3qgmAVSx3JSdQpO1SjAoGAS4kJ7RLOJMWK0fuOX6nM
IxNx3EV7DMunMS/UW5b/FuEqP8LVDW4wV28WcamFV2LThsWCOEEysA2t9rfjZSvA
QwThU5f26ulQif2ZpxQFMzOIIAYYR44FQXoaLU/WzKE43izwAzBkcdHwQUpsEt2X
Zmh1+xtSzNpZZ1cgs5lFjNY=
-----END PRIVATE KEY-----
"""

LOADTEST_PUBLIC_KEY_PEM = """-----BEGIN PUBLIC KEY-----
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEA7q4P1hTHgJpr6tZB4dy6
llTU3yCpYW2ehwIP7OmnMg0pdn5g+dlJ+3b7Tuv3HzKGrFid4rOZ1f6PJsAadMk+
bNgB24xrtNI+FzGQDDC+RJUewmmhWwkJU9jmk5vSWZRDY4PmbgRxquGFkTqtiBJ1
uNB2qgS59d/TRqMPccA5dOyNEpwLsQ9kBKDsl7IB0GbT7xSKBe3XXIh312blXrQ1
JtWE7eAxawzrBtbI/30g83aT+FmXXFZCRb6qMNKi/9lehL4Jl3RsMNlsq5m0gTtj
5GCFJBBJ7VsqRi/CFYp4eQRABeWTHs4pJewyRsUZhiPUOfeyqw8BDn9d7qe8y6YM
2QIDAQAB
-----END PUBLIC KEY-----
"""

LOADTEST_OAUTH_ISSUER = "https://perf.tradepulse.test"
LOADTEST_OAUTH_AUDIENCE = "tradepulse-api"
LOADTEST_JWKS_PATH = "/.well-known/jwks.json"
LOADTEST_KID = "loadtest-perf-key"


def _public_key() -> rsa.RSAPublicKey:
    return serialization.load_pem_public_key(LOADTEST_PUBLIC_KEY_PEM.encode("utf-8"))


def configure_security_overrides() -> ApiSecuritySettings:
    """Patch API security to use deterministic RSA credentials for load tests."""

    from application.api import security as security_module

    settings = ApiSecuritySettings(
        oauth2_issuer=LOADTEST_OAUTH_ISSUER,
        oauth2_audience=LOADTEST_OAUTH_AUDIENCE,
        oauth2_jwks_uri=f"{LOADTEST_OAUTH_ISSUER}{LOADTEST_JWKS_PATH}",
        trusted_hosts=("127.0.0.1", "localhost"),
    )

    # Ensure FastAPI dependency injection reuses our explicit settings instance.
    loader: Callable[[], ApiSecuritySettings] = lambda: settings
    security_module._default_settings_loader = loader  # type: ignore[attr-defined]
    setattr(security_module.get_api_security_settings, "_instance", settings)
    setattr(security_module.get_api_security_settings, "_loader", loader)
    setattr(security_module.get_api_security_settings, "_manual_override", True)

    public_key = _public_key()
    jwk_dict = RSAAlgorithm.to_jwk(public_key, as_dict=True)
    jwk_dict.update({"kid": LOADTEST_KID, "alg": "RS256", "use": "sig"})

    async def fake_get_key(jwks_uri: str, request_kid: str) -> dict[str, str] | None:
        if jwks_uri == str(settings.oauth2_jwks_uri) and request_kid == LOADTEST_KID:
            return jwk_dict
        return None

    security_module._jwks_resolver.get_key = fake_get_key  # type: ignore[assignment]
    return settings


def mint_loadtest_token(
    *,
    subject: str = "loadtest-user",
    lifetime: timedelta = timedelta(minutes=5),
    audience: str | None = None,
    issuer: str | None = None,
) -> str:
    """Generate a signed bearer token compatible with the load-test settings."""

    now = datetime.now(timezone.utc)
    payload = {
        "iss": issuer or LOADTEST_OAUTH_ISSUER,
        "aud": audience or LOADTEST_OAUTH_AUDIENCE,
        "sub": subject,
        "iat": int(now.timestamp()),
        "exp": int((now + lifetime).timestamp()),
        "roles": ["loadtest", "system"],
    }
    headers = {"kid": LOADTEST_KID, "alg": "RS256", "typ": "JWT"}
    token = jwt.encode(payload, LOADTEST_PRIVATE_KEY_PEM, algorithm="RS256", headers=headers)
    return token
