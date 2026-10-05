"""Settings tree.

Precedence, highest first: explicit overrides, environment variables (``ARBITER_`` prefix,
``__`` between nested keys), the YAML configuration file, built-in defaults.
"""

import os
from contextvars import ContextVar
from datetime import date
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from pathlib import Path
from typing import Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    YamlConfigSettingsSource,
)
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError

from ai_arbiter.core.config.secrets import SecretRef
from ai_arbiter.core.errors import ConfigurationError
from ai_arbiter.core.notification import check_address

DEFAULT_CONFIG_FILE = Path("arbiter.yaml")
DEFAULT_DATABASE_URL = "sqlite+aiosqlite:///./.arbiter/arbiter.db"
CONFIG_ENV_VAR = "ARBITER_CONFIG"

# Set by ``load_settings`` for the duration of one load, so that the YAML source knows
# which file to read without the path being part of the settings themselves.
_config_file: ContextVar[Path | None] = ContextVar("arbiter_config_file", default=None)


class Role(StrEnum):
    """What a server process does (ADR-0020)."""

    GATEWAY = "gateway"
    ADMIN = "admin"
    WORKER = "worker"
    # The MCP proxy: the data plane for calls to MCP servers (ADR-0047).
    MCP = "mcp"


class _Section(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DatabaseSettings(_Section):
    url: str = DEFAULT_DATABASE_URL
    echo: bool = False


class ServerSettings(_Section):
    host: str = "127.0.0.1"
    port: int = Field(default=8080, ge=1, le=65535)
    roles: frozenset[Role] = frozenset(Role)


class PluginSettings(_Section):
    """Which implementation is active for each port (ADR-0011).

    A plugin runs only if it is named here; being installed is not enough.
    """

    secret_store: str = "env"  # noqa: S105 - a plugin name, not a secret
    event_bus: str = "in_process"
    pii_detector: str = "builtin"
    # "file" writes messages to a directory: nothing leaves the machine by default.
    notifier: str = "file"
    # Reads and verifies A2A Agent Cards. Needs the a2a extra when first used.
    agent_card_reader: str = "a2a"


def _secret_reference(value: str) -> str:
    SecretRef.parse(value)
    return value


class PepperSettings(_Section):
    """Peppers that key the hash of API keys (ADR-0028).

    ``secrets`` maps a pepper id to a secret reference. New keys use ``active``; a key
    issued earlier is verified with the pepper whose id is stored on it, so rotating
    means adding an entry and changing ``active``.
    """

    active: str = "1"
    secrets: dict[str, str] = {"1": "secret://api-key-pepper"}

    @model_validator(mode="after")
    def _check(self) -> "PepperSettings":
        if self.active not in self.secrets:
            raise ValueError(f"active pepper '{self.active}' is not listed under secrets")
        for reference in self.secrets.values():
            _secret_reference(reference)
        return self


class IdentitySettings(_Section):
    api_key_pepper: PepperSettings = PepperSettings()


class DeploymentSettings(_Section):
    """One place a model can be called (ADR-0013).

    ``provider`` names a plugin of the ``llm_providers`` group; ``settings`` is validated
    by that plugin's own settings model when the gateway starts (ADR-0011).
    """

    name: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]*$")
    provider: str
    # The model name at the provider. For Azure OpenAI, the name of the Azure deployment.
    model: str
    # The model names clients may ask for that this deployment answers. Default: ``model``.
    serves: tuple[str, ...] = ()
    region: str | None = None
    # Lower is tried first.
    priority: int = 100
    # The catalogue entry that prices this deployment. Default: ``model``.
    priced_as: str | None = None
    # What to do when the provider returns no token counts (ADR-0031).
    usage_fallback: Literal["none", "estimate"] = "none"
    chars_per_token: int = Field(default=4, ge=1)
    settings: dict[str, Any] = {}

    @property
    def served_models(self) -> tuple[str, ...]:
        return self.serves or (self.model,)

    @property
    def price_model(self) -> str:
        return self.priced_as or self.model


class RiskConstraint(_Section):
    """Where the requests of systems of one risk tier may go."""

    # Deployment names. ``None`` puts no limit on names.
    allowed_deployments: tuple[str, ...] | None = None
    # Regions, as written on the deployments. ``None`` puts no limit on regions.
    allowed_regions: tuple[str, ...] | None = None


class RouterSettings(_Section):
    strategy: Literal["priority", "cost"] = "priority"
    # How many deployments are tried for one request before giving up.
    max_attempts: int = Field(default=3, ge=1)
    # Extra calls to the same deployment after a failure that may be transient.
    retries: int = Field(default=1, ge=0)
    retry_backoff_ms: int = Field(default=200, ge=0)
    # Routing constraints by risk tier (prohibited, high_risk, transparency, minimal,
    # out_of_scope, undetermined), applied to requests whose API key is tied to a
    # declared system.
    constraints: dict[
        Literal[
            "prohibited", "high_risk", "transparency", "minimal", "out_of_scope", "undetermined"
        ],
        RiskConstraint,
    ] = {}


def parse_decimal(value: str, *, positive: bool = False) -> Decimal:
    """Read a decimal written as a string. Numbers are refused: a YAML float is inexact."""
    if not isinstance(value, str):
        raise ValueError('write the amount as a string, for example "0.15"')
    try:
        amount = Decimal(value)
    except InvalidOperation as exc:
        raise ValueError(f"'{value}' is not a decimal number") from exc
    if not amount.is_finite() or amount < 0 or (positive and amount == 0):
        raise ValueError(f"'{value}' must be {'greater than zero' if positive else 'zero or more'}")
    return amount


class PriceSettings(_Section):
    """One price, per million tokens, as decimal strings (ADR-0030)."""

    provider: str
    model: str
    region: str | None = None
    input_per_million: str
    output_per_million: str
    cached_input_per_million: str | None = None

    @model_validator(mode="after")
    def _amounts(self) -> "PriceSettings":
        parse_decimal(self.input_per_million)
        parse_decimal(self.output_per_million)
        if self.cached_input_per_million is not None:
            parse_decimal(self.cached_input_per_million)
        return self


class ReportingCurrencySettings(_Section):
    """The currency reports are also shown in, with the rate used to convert."""

    currency: str = Field(pattern=r"^[A-Z]{3}$")
    # Units of this currency for one unit of the catalogue's currency.
    rate: str
    rate_as_of: date

    @model_validator(mode="after")
    def _rate(self) -> "ReportingCurrencySettings":
        parse_decimal(self.rate, positive=True)
        return self


class FinOpsSettings(_Section):
    # A catalogue file to use instead of the one shipped with the package.
    catalogue_file: Path | None = None
    # Prices added to the catalogue, or replacing the ones it has.
    prices: tuple[PriceSettings, ...] = ()
    reporting: ReportingCurrencySettings | None = None


class RedactionSettings(_Section):
    """How detected personal data is replaced, by category (ADR-0014)."""

    default_strategy: Literal["mask", "hash", "drop"] = "mask"
    strategies: dict[str, Literal["mask", "hash", "drop"]] = {}
    # Root secret for hashed tags and prompt fingerprints, as a secret reference. Without
    # it the hash strategy is refused and no prompt fingerprint is stored.
    key: str | None = None

    @model_validator(mode="after")
    def _check(self) -> "RedactionSettings":
        if self.key is not None:
            _secret_reference(self.key)
        uses_hash = self.default_strategy == "hash" or "hash" in self.strategies.values()
        if uses_hash and self.key is None:
            raise ValueError("the hash strategy needs redaction.key")
        return self


class PolicySettings(_Section):
    # A rule pack file to use instead of the default policy shipped with the package.
    pack: Path | None = None
    # Model names clients may ask for. ``None`` allows every model a deployment serves.
    allowed_models: tuple[str, ...] | None = None


class AuditSettings(_Section):
    # What happens to a request whose audit entry cannot be written: ``closed`` fails
    # the request, ``open`` lets it through. A tenant can override it (ADR-0017).
    fail_mode: Literal["closed", "open"] = "closed"


class IngestMapping(_Section):
    """Attribute imported records to a declared system (ADR-0019).

    A record matches when every label named here has the given value. Labels depend on
    the source; LiteLLM records carry ``key_alias`` and ``team_alias``.
    """

    source: str | None = None
    labels: dict[str, str] = {}
    system: str


class IngestSettings(_Section):
    mappings: tuple[IngestMapping, ...] = ()


class ComplianceSettings(_Section):
    # Rule pack files to use instead of the ones shipped with the package.
    ai_act_pack: Path | None = None
    scan_pack: Path | None = None


class RetentionSettings(_Section):
    """How long data is kept before ``arbiter retention purge`` deletes it (ADR-0038)."""

    # Interactions. A tenant can set its own period; a system classified high-risk
    # keeps its interactions for at least six months whatever is configured.
    interaction_months: int = Field(default=13, ge=1)
    # Outbox events, counted from when they were dispatched.
    outbox_days: int = Field(default=7, ge=1)


class NotificationRecipient(_Section):
    address: str
    # The language this person reads the digest in.
    locale: str = "en"

    @field_validator("address")
    @classmethod
    def _address(cls, value: str) -> str:
        return check_address(value)


class NotificationSettings(_Section):
    """Who receives the digest, and how the notifier named in ``plugins`` is set up."""

    sender: str | None = None
    recipients: tuple[NotificationRecipient, ...] = ()
    # Checked by the notifier plugin against its own settings model (ADR-0011).
    settings: dict[str, Any] = {}

    @field_validator("sender")
    @classmethod
    def _sender(cls, value: str | None) -> str | None:
        return value if value is None else check_address(value)


class McpSettings(_Section):
    """The MCP catalogue and proxy (ADR-0046 to ADR-0050)."""

    # Hosts a server may be registered for with plain http. Everything else needs https.
    allow_http_hosts: tuple[str, ...] = ()
    timeout_seconds: int = Field(default=30, ge=1)
    # Larger request bodies are refused before they are read into memory.
    max_request_bytes: int = Field(default=1_048_576, ge=1024)
    # A response that is not a stream is refused beyond this size.
    max_response_bytes: int = Field(default=10_485_760, ge=1024)
    # How long a response stream may stay silent before the proxy gives up on it.
    stream_idle_seconds: int = Field(default=300, ge=1)
    # Browser origins allowed to call the proxy. A request with any other Origin header
    # is refused; a request without one, as programs send, is not affected.
    allowed_origins: tuple[str, ...] = ()
    # A rule pack file to use instead of the one shipped with the package.
    pack: Path | None = None


class TelemetrySettings(_Section):
    enabled: bool = False
    service_name: str = "arbiter"
    otlp_endpoint: str | None = None


class LoggingSettings(_Section):
    level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="ARBITER_",
        env_nested_delimiter="__",
        extra="forbid",
    )

    environment: str = "local"
    database: DatabaseSettings = DatabaseSettings()
    server: ServerSettings = ServerSettings()
    plugins: PluginSettings = PluginSettings()
    identity: IdentitySettings = IdentitySettings()
    deployments: tuple[DeploymentSettings, ...] = ()
    router: RouterSettings = RouterSettings()
    finops: FinOpsSettings = FinOpsSettings()
    redaction: RedactionSettings = RedactionSettings()
    policy: PolicySettings = PolicySettings()
    audit: AuditSettings = AuditSettings()
    compliance: ComplianceSettings = ComplianceSettings()
    ingest: IngestSettings = IngestSettings()
    retention: RetentionSettings = RetentionSettings()
    notifications: NotificationSettings = NotificationSettings()
    mcp: McpSettings = McpSettings()
    telemetry: TelemetrySettings = TelemetrySettings()
    logging: LoggingSettings = LoggingSettings()

    @model_validator(mode="after")
    def _unique_deployments(self) -> "Settings":
        names = [deployment.name for deployment in self.deployments]
        duplicates = sorted({name for name in names if names.count(name) > 1})
        if duplicates:
            raise ValueError(f"deployment names are used twice: {', '.join(duplicates)}")
        return self

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        sources: list[PydanticBaseSettingsSource] = [init_settings, env_settings]
        config_file = _config_file.get()
        if config_file is not None:
            sources.append(YamlConfigSettingsSource(settings_cls, yaml_file=config_file))
        return tuple(sources)

    def redacted(self) -> dict[str, Any]:
        """Settings as plain data, safe to print: credentials in URLs are masked."""
        data = self.model_dump(mode="json")
        data["database"]["url"] = _mask_url(self.database.url)
        data["server"]["roles"] = sorted(data["server"]["roles"])
        return data


def _mask_url(url: str) -> str:
    try:
        return make_url(url).render_as_string(hide_password=True)
    except ArgumentError:
        return "<unparseable url>"


def _resolve_config_file(explicit: Path | None) -> Path | None:
    """Pick the configuration file.

    A file named explicitly (argument or ``ARBITER_CONFIG``) must exist. The default
    file is optional: without it, defaults and environment variables apply.
    """
    named = explicit
    if named is None and (from_env := os.environ.get(CONFIG_ENV_VAR)):
        named = Path(from_env)
    if named is not None:
        if not named.is_file():
            raise ConfigurationError(f"configuration file not found: {named}")
        return named
    return DEFAULT_CONFIG_FILE if DEFAULT_CONFIG_FILE.is_file() else None


def load_settings(config_file: Path | None = None, **overrides: Any) -> Settings:
    """Load and validate settings. Raises ``ConfigurationError`` with a readable message."""
    token = _config_file.set(_resolve_config_file(config_file))
    try:
        return Settings(**overrides)
    except ValidationError as exc:
        problems = "; ".join(
            f"{'.'.join(str(part) for part in error['loc'])}: {error['msg']}"
            for error in exc.errors(include_input=False, include_url=False)
        )
        raise ConfigurationError(f"invalid configuration: {problems}") from exc
    finally:
        _config_file.reset(token)
