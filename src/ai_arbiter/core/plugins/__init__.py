"""Plugin discovery and activation (ADR-0011)."""

from ai_arbiter.core.plugins.registry import (
    EVENT_BUSES,
    GROUPS,
    LLM_PROVIDERS,
    PII_DETECTORS,
    SECRET_STORES,
    PluginRegistry,
)

__all__ = [
    "EVENT_BUSES",
    "GROUPS",
    "LLM_PROVIDERS",
    "PII_DETECTORS",
    "SECRET_STORES",
    "PluginRegistry",
]
