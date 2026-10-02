"""Configuration: one validated settings tree, layered from file and environment."""

from ai_arbiter.core.config.secrets import SecretRef
from ai_arbiter.core.config.settings import (
    DEFAULT_CONFIG_FILE,
    DEFAULT_DATABASE_URL,
    DatabaseSettings,
    LoggingSettings,
    PluginSettings,
    Role,
    ServerSettings,
    Settings,
    TelemetrySettings,
    load_settings,
)

__all__ = [
    "DEFAULT_CONFIG_FILE",
    "DEFAULT_DATABASE_URL",
    "DatabaseSettings",
    "LoggingSettings",
    "PluginSettings",
    "Role",
    "SecretRef",
    "ServerSettings",
    "Settings",
    "TelemetrySettings",
    "load_settings",
]
