"""Central configuration for the TradePulse FastAPI service."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Iterable

if TYPE_CHECKING:
    import ssl

    from application.configuration import CentralConfigurationStore
    from application.secrets.manager import SecretManager
    from application.secrets.rotation import SecretRotator
    from core.config.template_manager import ConfigTemplateManager
    from core.utils.security import SecretDetector
    from src.audit.audit_logger import AuditLogger
    from src.security import AccessController

from pydantic import (
    AnyUrl,
    BaseModel,
    ConfigDict,
    Field,
    HttpUrl,
    PositiveFloat,
    PositiveInt,
    PostgresDsn,
    SecretStr,
    ValidationInfo,
    field_validator,
    model_validator,
)
from pydantic_settings import BaseSettings, SettingsConfigDict

from application.security.two_factor import decode_totp_secret
from core.config.cli_models import PostgresTLSConfig
from core.config.postgres import ensure_secure_postgres_uri
from core.security import (
    DEFAULT_HTTP_ALPN_PROTOCOLS,
    DEFAULT_MODERN_CIPHER_SUITES,
    parse_tls_version,
)


def _default_config_vault_key() -> SecretStr:
    from application.secrets.vault import SecretVault

    return SecretStr(SecretVault.generate_key().decode("utf-8"))


class KillSwitchPostgresSettings(BaseModel):
    """Configuration for the PostgreSQL-backed kill-switch store."""

    dsn: PostgresDsn
    tls: PostgresTLSConfig
    min_pool_size: int = Field(
        1, ge=0, description="Minimum number of pooled connections to pre-create."
    )
    max_pool_size: PositiveInt = Field(
        4, description="Maximum number of pooled connections available concurrently."
    )
    acquire_timeout_seconds: float | None = Field(
        2.0,
        ge=0.0,
        description="Seconds to wait for a pooled connection before timing out. Use null for infinite wait.",
    )
    connect_timeout_seconds: PositiveFloat = Field(
        5.0,
        description="Timeout, in seconds, applied to the initial TCP and TLS handshake when establishing new connections.",
    )
    statement_timeout_ms: PositiveInt = Field(
        5000,
        description="PostgreSQL statement timeout applied to store operations, in milliseconds.",
    )
    max_retries: int = Field(
        3,
        ge=0,
        description="Maximum number of retries for transient PostgreSQL errors.",
    )
    retry_interval_seconds: float = Field(
        0.1,
        ge=0.0,
        description="Initial delay, in seconds, between retries for transient errors.",
    )
    backoff_multiplier: float = Field(
        2.0,
        ge=1.0,
        description="Multiplier applied to the retry delay after each failed attempt.",
    )

    @model_validator(mode="after")
    def _validate_pool(self) -> "KillSwitchPostgresSettings":
        ensure_secure_postgres_uri(str(self.dsn))
        if self.max_pool_size < self.min_pool_size:
            raise ValueError(
                "max_pool_size must be greater than or equal to min_pool_size"
            )
        return self

    model_config = ConfigDict(extra="forbid")


class ConfigNamespaceSettings(BaseModel):
    """Describe how configuration namespaces are exposed to operators."""

    name: str = Field(..., min_length=1, description="Namespace identifier.")
    readers: tuple[str, ...] = Field(
        default=("system",), description="Actors allowed to read from the namespace."
    )
    writers: tuple[str, ...] = Field(
        default=("system",), description="Actors allowed to write to the namespace."
    )
    allow_ci: bool = Field(
        default=False,
        description="Whether secrets from this namespace can be injected into CI environments.",
    )
    description: str | None = Field(
        default=None, description="Optional human readable context for operators."
    )

    @model_validator(mode="after")
    def _normalise(self) -> "ConfigNamespaceSettings":
        readers = tuple(actor.strip() for actor in self.readers if actor.strip())
        writers = tuple(actor.strip() for actor in self.writers if actor.strip())
        if not readers and not writers:
            raise ValueError(
                "At least one reader or writer must be configured for a namespace"
            )
        if not self.name.strip():
            raise ValueError("Namespace name must not be blank")
        return self.model_copy(update={"readers": readers, "writers": writers})

    model_config = ConfigDict(extra="forbid")


class ApiServerTLSSettings(BaseModel):
    """TLS certificate bundle used to secure the external TradePulse API."""

    certificate: Path = Field(
        ...,
        alias="cert_file",
        description="PEM encoded certificate chain presented to clients.",
    )
    private_key: Path = Field(
        ...,
        alias="key_file",
        description="Private key paired with the server certificate.",
    )
    client_ca: Path | None = Field(
        default=None,
        alias="client_ca_file",
        description="Optional CA bundle trusted for client certificate authentication.",
    )
    client_revocation_list: Path | None = Field(
        default=None,
        alias="client_revocation_list_file",
        description="Optional certificate revocation list enforced for mutual TLS.",
    )
    require_client_certificate: bool = Field(
        True,
        description="Require connecting clients to present a trusted certificate.",
    )
    minimum_version: str = Field(
        "TLSv1.2",
        description="Lowest TLS protocol version accepted for inbound requests.",
    )
    cipher_suites: tuple[str, ...] = Field(
        DEFAULT_MODERN_CIPHER_SUITES,
        description="TLS 1.2 cipher suites enabled for backwards compatible clients.",
    )
    alpn_protocols: tuple[str, ...] = Field(
        DEFAULT_HTTP_ALPN_PROTOCOLS,
        description="Application protocols announced during ALPN negotiation.",
    )

    @field_validator(
        "certificate",
        "private_key",
        "client_ca",
        "client_revocation_list",
        mode="before",
    )
    @classmethod
    def _coerce_path(cls, value: object) -> object:
        if value is None or isinstance(value, Path):
            return value
        return Path(str(value))

    @field_validator("cipher_suites", "alpn_protocols", mode="before")
    @classmethod
    def _normalise_sequence(
        cls, value: object, info: ValidationInfo
    ) -> tuple[str, ...]:
        if value is None:
            return ()
        if isinstance(value, str):
            candidates = [item.strip() for item in value.split(",")]
        else:
            candidates = [str(item).strip() for item in value]
        cleaned = tuple(dict.fromkeys(item for item in candidates if item))
        if not cleaned:
            msg = f"{info.field_name.replace('_', ' ')} must not be empty"
            raise ValueError(msg)
        return cleaned

    @field_validator("minimum_version")
    @classmethod
    def _validate_version(cls, value: str) -> str:
        parse_tls_version(value)
        return value

    @model_validator(mode="after")
    def _validate_files(self) -> ApiServerTLSSettings:
        for attribute in ("certificate", "private_key"):
            candidate = getattr(self, attribute)
            if not candidate.exists():
                msg = f"{attribute.replace('_', ' ')} '{candidate}' does not exist"
                raise ValueError(msg)
            if not candidate.is_file():
                msg = f"{attribute.replace('_', ' ')} '{candidate}' must be a file"
                raise ValueError(msg)
        for attribute in ("client_ca", "client_revocation_list"):
            candidate = getattr(self, attribute)
            if candidate is None:
                continue
            if not candidate.exists():
                msg = f"{attribute.replace('_', ' ')} '{candidate}' does not exist"
                raise ValueError(msg)
            if not candidate.is_file():
                msg = f"{attribute.replace('_', ' ')} '{candidate}' must be a file"
                raise ValueError(msg)
        if self.require_client_certificate and self.client_ca is None:
            raise ValueError(
                "Client certificate authentication requires a trusted CA bundle"
            )
        return self

    def resolved_minimum_version(self) -> ssl.TLSVersion:
        """Return the negotiated minimum TLS version."""
        return parse_tls_version(self.minimum_version)


class ApiServerSettings(BaseSettings):
    """Runtime configuration for the HTTPS listener."""

    host: str = Field(
        "0.0.0.0", description="Network interface bound by the API server."
    )
    port: PositiveInt = Field(8000, description="TCP port exposed by the API server.")
    allow_plaintext: bool = Field(
        False,
        description="Permit HTTP without TLS. Intended for specialised test harnesses only.",
    )
    tls: ApiServerTLSSettings | None = Field(
        default=None,
        description="Certificate material securing inbound HTTPS traffic.",
    )

    @model_validator(mode="after")
    def _enforce_tls(self) -> "ApiServerSettings":
        if not self.allow_plaintext and self.tls is None:
            raise ValueError(
                "TLS configuration is required for the TradePulse API server"
            )
        return self

    model_config = SettingsConfigDict(
        env_prefix="TRADEPULSE_API_SERVER_",
        env_nested_delimiter="__",
        extra="ignore",
        secrets_dir=Path("/run/secrets"),
    )


class AdminApiSettings(BaseSettings):
    """Configuration governing administrative controls and audit logging."""

    audit_secret: SecretStr = Field(
        ...,
        min_length=16,
        description="Secret used to sign administrative audit records.",
    )
    audit_secret_path: Path | None = Field(
        default=None,
        description=(
            "Optional filesystem path managed by the platform secret manager that contains "
            "the audit signing secret. When supplied the application refreshes the key "
            "periodically to honour rotations."
        ),
    )
    secret_refresh_interval_seconds: PositiveFloat = Field(
        300.0,
        description="Minimum interval, in seconds, between managed secret refresh attempts.",
    )
    admin_subject: str = Field(
        "remote-admin",
        min_length=1,
        description="Default subject recorded for administrative actions when no override is provided.",
    )
    admin_environment: str = Field(
        "production",
        min_length=1,
        description=(
            "Environment label attached to administrative RBAC attribute checks. "
            "Defaults to 'production'."
        ),
    )
    admin_rate_limit_max_attempts: PositiveInt = Field(
        5,
        description="Number of administrative requests allowed within the configured interval.",
    )
    admin_rate_limit_interval_seconds: PositiveFloat = Field(
        60.0,
        description="Length of the rolling window used for administrative rate limiting.",
    )
    two_factor_secret: SecretStr = Field(
        ...,
        min_length=16,
        description=(
            "Base32 encoded shared secret used for administrator time-based one-time"
            " passwords. Configure via TRADEPULSE_TWO_FACTOR_SECRET or a managed"
            " secrets path."
        ),
    )
    two_factor_secret_path: Path | None = Field(
        default=None,
        description=(
            "Optional filesystem path managed by the platform secret manager that"
            " stores the administrator TOTP secret. When provided the in-memory"
            " fallback is only used until the file becomes available."
        ),
    )
    two_factor_header_name: str = Field(
        "X-Admin-OTP",
        min_length=1,
        description=(
            "HTTP header that must contain a valid administrator TOTP code for"
            " privileged requests."
        ),
    )
    two_factor_digits: int = Field(
        6,
        ge=4,
        le=10,
        description="Number of digits expected in administrator TOTP codes.",
    )
    two_factor_period_seconds: PositiveInt = Field(
        30,
        description="Validity period, in seconds, for administrator TOTP codes.",
    )
    two_factor_allowed_drift_windows: int = Field(
        1,
        ge=0,
        le=4,
        description=(
            "Number of additional TOTP windows accepted on either side of the current"
            " period to tolerate minor clock drift."
        ),
    )
    two_factor_algorithm: str = Field(
        "SHA1",
        description="HMAC algorithm used to validate administrator TOTP codes.",
    )
    audit_webhook_url: HttpUrl | None = Field(
        default=None,
        description="Optional HTTP endpoint that receives signed audit records for external storage.",
    )
    config_vault_path: Path = Field(
        Path("state/config_vault.json"),
        description="Filesystem path for the centralised configuration vault.",
    )
    config_vault_master_key: SecretStr = Field(
        default_factory=_default_config_vault_key,
        min_length=44,
        description="Base64 encoded 32-byte master key securing the configuration vault.",
    )
    config_vault_master_key_path: Path | None = Field(
        default=None,
        description="Optional path to read the configuration vault master key from.",
    )
    config_template_directory: Path = Field(
        Path("configs/templates"),
        description="Directory containing templated environment configuration files.",
    )
    config_namespaces: tuple[ConfigNamespaceSettings, ...] = Field(
        default_factory=lambda: (ConfigNamespaceSettings(name="system"),),
        description="Isolated namespaces used for configuration and secret segregation.",
    )
    access_policy_path: Path = Field(
        Path("configs/security/access_policy.yaml"),
        description=(
            "Filesystem path to the access control policy defining privileged "
            "operations."
        ),
    )
    kill_switch_store_path: Path = Field(
        Path("state/kill_switch_state.sqlite"),
        description="Filesystem path used to persist the risk kill-switch state.",
    )
    kill_switch_postgres: KillSwitchPostgresSettings | None = Field(
        default=None,
        description=(
            "Optional PostgreSQL configuration for kill-switch persistence. When provided the service uses a pooled "
            "PostgreSQL backend; otherwise it falls back to the local SQLite store."
        ),
    )
    siem_endpoint: HttpUrl | None = Field(
        default=None,
        description="Optional SIEM API endpoint that receives replicated audit records.",
    )
    siem_client_id: str | None = Field(
        default=None,
        min_length=1,
        description="Client identifier used when authenticating against the SIEM ingest API.",
    )
    siem_client_secret: SecretStr | None = Field(
        default=None,
        description=(
            "Client secret used for SIEM authentication. Provide via environment variable "
            "or mounted secrets directory to avoid embedding credentials in configuration files."
        ),
    )
    siem_client_secret_path: Path | None = Field(
        default=None,
        description=(
            "Optional filesystem path monitored for SIEM client secret rotations."
        ),
    )
    siem_scope: str | None = Field(
        default=None,
        description="Optional OAuth2 scope requested when exchanging SIEM credentials for a token.",
    )

    @model_validator(mode="after")
    def _validate_siem_configuration(self) -> "AdminApiSettings":
        if self.siem_endpoint is not None:
            has_secret = (
                self.siem_client_secret is not None
                or self.siem_client_secret_path is not None
            )
            if not self.siem_client_id or not has_secret:
                raise ValueError(
                    "siem_client_id and siem_client_secret must be configured when "
                    "siem_endpoint is set"
                )
        return self

    @field_validator("admin_environment", mode="before")
    @classmethod
    def _normalise_admin_environment(cls, value: Any) -> str:
        candidate = str(value).strip()
        if not candidate:
            raise ValueError("admin_environment must be a non-empty string")
        return candidate.lower()

    @field_validator("two_factor_secret")
    @classmethod
    def _validate_two_factor_secret(cls, value: SecretStr) -> SecretStr:
        decode_totp_secret(value.get_secret_value())
        return value

    @field_validator("two_factor_header_name", mode="before")
    @classmethod
    def _normalise_two_factor_header(cls, value: Any) -> str:
        candidate = str(value).strip()
        if not candidate:
            raise ValueError("two_factor_header_name must be a non-empty string")
        return candidate

    @field_validator("two_factor_algorithm", mode="before")
    @classmethod
    def _normalise_two_factor_algorithm(cls, value: Any) -> str:
        candidate = str(value).strip()
        if not candidate:
            raise ValueError("two_factor_algorithm must be a non-empty string")
        upper = candidate.upper()
        if upper not in {"SHA1", "SHA256", "SHA512"}:
            raise ValueError("two_factor_algorithm must be SHA1, SHA256, or SHA512")
        return upper

    def build_secret_manager(
        self,
        *,
        audit_logger_factory: Callable[["SecretManager"], "AuditLogger"] | None = None,
        access_controller: "AccessController" | None = None,
    ) -> "SecretManager":
        """Return a configured secret manager for administrative components."""

        from application.secrets.manager import (
            ManagedSecret,
            ManagedSecretConfig,
            SecretManager,
        )

        refresh_interval = float(self.secret_refresh_interval_seconds)
        secrets: dict[str, ManagedSecret] = {
            "audit_secret": ManagedSecret(
                config=ManagedSecretConfig(
                    name="audit_secret",
                    path=self.audit_secret_path,
                    min_length=16,
                ),
                fallback=self.audit_secret.get_secret_value(),
                refresh_interval_seconds=refresh_interval,
            )
        }

        secrets["two_factor_secret"] = ManagedSecret(
            config=ManagedSecretConfig(
                name="two_factor_secret",
                path=self.two_factor_secret_path,
                min_length=16,
            ),
            fallback=self.two_factor_secret.get_secret_value(),
            refresh_interval_seconds=refresh_interval,
        )

        if (
            self.siem_client_secret is not None
            or self.siem_client_secret_path is not None
        ):
            fallback: str | None = None
            if self.siem_client_secret is not None:
                fallback = self.siem_client_secret.get_secret_value()
            secrets["siem_client_secret"] = ManagedSecret(
                config=ManagedSecretConfig(
                    name="siem_client_secret",
                    path=self.siem_client_secret_path,
                    min_length=12,
                ),
                fallback=fallback,
                refresh_interval_seconds=refresh_interval,
            )

        return SecretManager(
            secrets,
            audit_logger_factory=audit_logger_factory,
            access_controller=access_controller,
        )

    def build_access_controller(self) -> "AccessController":
        """Instantiate the access controller defined by the configured policy."""

        from src.security import AccessController, AccessPolicy

        policy = AccessPolicy.load(self.access_policy_path)
        return AccessController(policy)

    def build_configuration_store(
        self,
        *,
        audit_logger: "AuditLogger" | None = None,
        template_manager: "ConfigTemplateManager" | None = None,
        secret_detector: "SecretDetector" | None = None,  # pragma: allowlist secret
        rotator: "SecretRotator" | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> "CentralConfigurationStore":
        """Instantiate the secure configuration store with namespace policies."""

        from application.configuration import (
            CentralConfigurationStore,
            NamespaceDefinition,
        )
        from application.secrets.rotation import SecretRotator
        from application.secrets.vault import SecretVault
        from core.config.template_manager import ConfigTemplateManager
        from core.utils.security import SecretDetector

        key_bytes = self._resolve_config_vault_key()
        clock_fn = clock or (lambda: datetime.now(timezone.utc))
        vault = SecretVault(
            storage_path=self.config_vault_path,
            master_key=key_bytes,
            audit_logger=audit_logger,
            clock=clock_fn,
        )
        template_mgr = template_manager or ConfigTemplateManager(
            self.config_template_directory
        )
        detector = secret_detector or SecretDetector()
        rotator_instance = rotator or SecretRotator(vault=vault, clock=clock_fn)
        store = CentralConfigurationStore(
            vault=vault,
            template_manager=template_mgr,
            audit_logger=audit_logger,
            secret_detector=detector,
            rotator=rotator_instance,
            clock=clock_fn,
        )
        for namespace in self.config_namespaces:
            store.register_namespace(
                NamespaceDefinition(
                    name=namespace.name,
                    readers=frozenset(namespace.readers),
                    writers=frozenset(namespace.writers),
                    allow_ci=namespace.allow_ci,
                    description=namespace.description,
                )
            )
        return store

    def _resolve_config_vault_key(self) -> bytes:
        if self.config_vault_master_key_path is not None:
            key_text = self.config_vault_master_key_path.read_text(
                encoding="utf-8"
            ).strip()
            if not key_text:
                raise ValueError("Configuration vault master key file is empty")
            if len(key_text) < 44:
                raise ValueError(
                    "Configuration vault master key must be a base64-encoded 32 byte value"
                )
            return key_text.encode("utf-8")
        key_value = self.config_vault_master_key.get_secret_value()
        if not key_value:
            raise ValueError("config_vault_master_key must be provided")
        if len(key_value) < 44:
            raise ValueError(
                "config_vault_master_key must be a base64-encoded 32 byte value"
            )
        return key_value.encode("utf-8")

    model_config = SettingsConfigDict(
        env_prefix="TRADEPULSE_",
        extra="ignore",
        secrets_dir=Path("/run/secrets"),
    )


class ApiSecuritySettings(BaseSettings):
    """Runtime configuration for OAuth2, mutual TLS, and upstream WAF hand-off."""

    oauth2_issuer: HttpUrl = Field(
        "https://auth.tradepulse.invalid/issuer",
        description=(
            "Expected issuer claim for incoming OAuth2 JWT bearer tokens."
            " Defaults ensure unit tests can import the API without extra"
            " environment configuration."
        ),
    )
    oauth2_audience: str = Field(
        "tradepulse-api",
        min_length=1,
        description=(
            "Audience that must be present within validated JWT access tokens."
            " Override in production via environment variables."
        ),
    )
    oauth2_jwks_uri: HttpUrl = Field(
        "https://auth.tradepulse.invalid/jwks",
        description=(
            "JWKS endpoint used to discover signing keys for JWT validation."
            " Defaults are non-routable placeholders suitable for tests."
        ),
    )
    oauth2_algorithms: tuple[str, ...] = Field(
        (
            "RS256",
            "RS384",
            "RS512",
            "PS256",
            "PS384",
            "PS512",
            "ES256",
            "ES256K",
            "ES384",
            "ES512",
            "ES521",
            "EDDSA",
        ),
        min_length=1,
        description=(
            "Allow-list of JWT signing algorithms accepted for OAuth2 bearer tokens."
            " Algorithms outside of this set are rejected before signature verification."
        ),
    )
    mtls_trusted_ca_path: Path | None = Field(
        default=None,
        description=(
            "Optional path to a PEM bundle containing certificate authorities trusted for "
            "mutual TLS client authentication."
        ),
    )
    mtls_revocation_list_path: Path | None = Field(
        default=None,
        description=(
            "Optional path to a certificate revocation list checked during mTLS handshakes."
        ),
    )

    trusted_hosts: list[str] = Field(
        default_factory=lambda: ["testserver", "localhost"],
        description=(
            "Host header values accepted by the API gateway. Requests from other hosts "
            "are rejected before hitting route handlers."
        ),
        min_length=1,
    )
    max_request_bytes: PositiveInt = Field(
        1_000_000,
        description="Maximum request payload size, in bytes, accepted by the gateway.",
    )
    suspicious_json_keys: list[str] = Field(
        default_factory=lambda: ["$where", "__proto__", "$regex"],
        description=(
            "JSON keys that trigger an early rejection when present in request payloads."
        ),
    )
    suspicious_json_substrings: list[str] = Field(
        default_factory=lambda: ["<script", "javascript:"],
        description=(
            "Case-insensitive substrings that mark a JSON value as suspicious and cause "
            "the request to be rejected."
        ),
    )
    upstream_waf_request_id_header: str = Field(
        "X-Request-ID",
        min_length=1,
        description=(
            "Header normalised by the external gateway or cloud WAF that uniquely tags each "
            "request for downstream log correlation."
        ),
    )
    upstream_waf_forwarded_for_header: str = Field(
        "X-Forwarded-For",
        min_length=1,
        description=(
            "Header populated by the upstream WAF containing the client IP chain that the "
            "FastAPI layer trusts for rate-limiting and audit trails."
        ),
    )
    upstream_waf_event_header: str = Field(
        "X-WAF-Event",
        min_length=1,
        description=(
            "Header propagated from the external gateway describing the inspection decision "
            "(allow, challenged, mitigated) to be recorded alongside local security logs."
        ),
    )

    @model_validator(mode="after")
    def _normalise_algorithms(self) -> "ApiSecuritySettings":
        canonical: list[str] = []
        for algorithm in self.oauth2_algorithms:
            if not algorithm or not algorithm.strip():
                continue
            cleaned = algorithm.strip()
            upper = cleaned.upper()
            if upper == "EDDSA":
                value = "EdDSA"
            else:
                value = upper
            if value not in canonical:
                canonical.append(value)
        algorithms = tuple(canonical)
        if not algorithms:
            raise ValueError(
                "oauth2_algorithms must define at least one signing algorithm"
            )
        return self.model_copy(update={"oauth2_algorithms": algorithms})

    model_config = SettingsConfigDict(env_prefix="TRADEPULSE_", extra="ignore")


class RateLimitPolicy(BaseModel):
    """Rate limit definition expressed as a sliding-window quota."""

    max_requests: PositiveInt = Field(
        ...,
        description="Number of requests permitted within the configured window.",
    )
    window_seconds: PositiveFloat = Field(
        ...,
        description="Duration of the sliding window, in seconds, used for quota checks.",
    )


class ApiRateLimitSettings(BaseSettings):
    """Runtime configuration for per-client API rate limiting."""

    default_policy: RateLimitPolicy = Field(
        default_factory=lambda: RateLimitPolicy(max_requests=120, window_seconds=60.0),
        description="Fallback policy applied when a subject specific policy is not defined.",
    )
    unauthenticated_policy: RateLimitPolicy | None = Field(
        default=None,
        description=(
            "Optional policy applied to unauthenticated requests. When unset the "
            "default policy is used."
        ),
    )
    client_policies: dict[str, RateLimitPolicy] = Field(
        default_factory=dict,
        description=(
            "Mapping of authenticated subject identifiers to dedicated rate policies."
        ),
    )
    redis_url: AnyUrl | None = Field(
        default=None,
        description=(
            "Redis connection string used to coordinate rate limits across instances. "
            "When omitted an in-memory limiter is used."
        ),
    )
    redis_key_prefix: str = Field(
        default="tradepulse:rate", description="Prefix applied to Redis keys."
    )

    model_config = SettingsConfigDict(env_prefix="TRADEPULSE_RATE_", extra="ignore")


class EmailNotificationSettings(BaseModel):
    """SMTP configuration used for email notifications."""

    host: str = Field(..., min_length=1, description="SMTP server hostname.")
    port: PositiveInt = Field(587, description="SMTP server port.")
    sender: str = Field(
        ..., min_length=3, description="Email address used as the sender."
    )
    recipients: list[str] = Field(
        default_factory=list,
        description="Email recipients that receive TradePulse notifications.",
    )
    username: str | None = Field(
        default=None, description="Optional username used for SMTP authentication."
    )
    password: SecretStr | None = Field(
        default=None, description="Optional password used for SMTP authentication."
    )
    use_tls: bool = Field(True, description="Enable STARTTLS for SMTP connections.")
    use_ssl: bool = Field(
        False, description="Use implicit TLS when connecting to SMTP."
    )
    timeout_seconds: PositiveFloat = Field(10.0, description="SMTP connection timeout.")

    @model_validator(mode="after")
    def _validate_configuration(self) -> "EmailNotificationSettings":
        if not self.recipients:
            raise ValueError("recipients must contain at least one address")
        if self.use_tls and self.use_ssl:
            raise ValueError("use_tls and use_ssl are mutually exclusive")
        return self


class NotificationSettings(BaseSettings):
    """Runtime configuration for out-of-band notifications."""

    email: EmailNotificationSettings | None = Field(
        default=None,
        description="Optional SMTP configuration for email alerts.",
    )
    slack_webhook_url: HttpUrl | None = Field(
        default=None,
        description="Incoming webhook URL used for Slack notifications.",
    )
    slack_channel: str | None = Field(
        default=None,
        description="Override Slack channel routed by the webhook.",
    )
    slack_username: str | None = Field(
        default=None,
        description="Display name used by the Slack notifier.",
    )
    slack_timeout_seconds: PositiveFloat = Field(
        5.0,
        description="HTTP timeout used for Slack webhook requests.",
    )

    model_config = SettingsConfigDict(env_prefix="TRADEPULSE_NOTIFY_", extra="ignore")


class BackendRuntimeSettings(BaseSettings):
    """Configure logging and debug behaviour for backend applications."""

    debug: bool = Field(
        False,
        description=(
            "Enable FastAPI debug mode and expose authenticated debug endpoints."
        ),
    )
    log_level: int | str = Field(
        "INFO",
        description="Logging level applied to backend components.",
    )
    inspect_variables: tuple[str, ...] = Field(
        default_factory=tuple,
        description=(
            "Environment variables surfaced through debug snapshots. Accepts a "
            "comma separated list."
        ),
    )
    redact_patterns: tuple[str, ...] = Field(
        default=("secret", "token", "key", "password"),
        description=(
            "Case-insensitive substrings that trigger redaction in debug output."
        ),
    )
    force_log_configuration: bool = Field(
        False,
        description=(
            "Reinitialise logging even when handlers already exist. Useful for test"
            " harnesses that replace handlers."
        ),
    )
    log_variables_on_startup: bool = Field(
        True,
        description=("Emit a debug snapshot at startup when debug mode is enabled."),
    )
    controllers_required: bool = Field(
        True,
        description="Require serotonin/thermo controllers to be present during runtime init.",
    )
    gate_defaults: dict[str, float | str] = Field(
        default_factory=lambda: {
            "min_position_multiplier": 0.0,
            "max_position_multiplier": 1.0,
            "default_decision": "ALLOW",
        },
        description="Default bounds for control-gate decisions.",
    )

    model_config = SettingsConfigDict(env_prefix="TRADEPULSE_BACKEND_", extra="ignore")

    @staticmethod
    def _coerce_sequence(value: Any, *, lower: bool) -> tuple[str, ...]:
        if value is None:
            return ()
        if isinstance(value, str):
            candidates = [item.strip() for item in value.split(",")]
        elif isinstance(value, Iterable):
            candidates = [str(item).strip() for item in value]
        else:  # pragma: no cover - defensive guard
            raise TypeError("Expected a string or iterable for configuration sequence")
        filtered = [item.lower() if lower else item for item in candidates if item]
        return tuple(dict.fromkeys(filtered))

    @field_validator("inspect_variables", mode="before")
    @classmethod
    def _normalise_inspect_variables(cls, value: Any) -> tuple[str, ...]:
        return cls._coerce_sequence(value, lower=False)

    @field_validator("redact_patterns", mode="before")
    @classmethod
    def _normalise_redact_patterns(cls, value: Any) -> tuple[str, ...]:
        return cls._coerce_sequence(value, lower=True)

    @model_validator(mode="after")
    def _validate_gate_defaults(self) -> "BackendRuntimeSettings":
        defaults = dict(self.gate_defaults or {})
        min_mul = float(defaults.get("min_position_multiplier", 0.0) or 0.0)
        max_mul = float(defaults.get("max_position_multiplier", 1.0) or 1.0)
        if min_mul < 0 or max_mul < 0 or max_mul < min_mul:
            raise ValueError("gate_defaults must define non-negative min/max multipliers")
        decision = str(defaults.get("default_decision", "ALLOW")).upper()
        if decision not in {"ALLOW", "THROTTLE", "DENY"}:
            raise ValueError("gate_defaults.default_decision must be ALLOW, THROTTLE, or DENY")
        defaults["min_position_multiplier"] = min_mul
        defaults["max_position_multiplier"] = max_mul
        defaults["default_decision"] = decision
        return self.model_copy(update={"gate_defaults": defaults})

    def resolve_log_level(self) -> int:
        """Return the numeric logging level configured for the backend."""

        if isinstance(self.log_level, int):
            return self.log_level
        numeric = logging.getLevelName(str(self.log_level).upper())
        if isinstance(numeric, int):
            return numeric
        raise ValueError(f"Unknown log level: {self.log_level}")

    def should_configure_logging(
        self, *, handlers_installed: bool, sink_provided: bool = False
    ) -> bool:
        """Decide whether logging should be reconfigured."""

        if self.force_log_configuration or sink_provided:
            return True
        return not handlers_installed

    def redact_pattern_values(self) -> tuple[str, ...]:
        """Return the redaction substrings for debug sanitisation."""

        return self.redact_patterns


__all__ = [
    "ApiServerTLSSettings",
    "ApiServerSettings",
    "AdminApiSettings",
    "ApiSecuritySettings",
    "RateLimitPolicy",
    "ApiRateLimitSettings",
    "EmailNotificationSettings",
    "NotificationSettings",
    "BackendRuntimeSettings",
]
