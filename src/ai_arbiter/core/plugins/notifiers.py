"""Load the notifier named in the configuration and check its settings (ADR-0011)."""

from collections.abc import Mapping
from typing import Any

from pydantic import ValidationError

from ai_arbiter.core.errors import ConfigurationError
from ai_arbiter.core.notification import Notifier
from ai_arbiter.core.plugins.registry import NOTIFIERS, PluginRegistry
from ai_arbiter.core.ports import SecretStore


def load_notifier(
    registry: PluginRegistry, name: str, options: Mapping[str, Any], secrets: SecretStore
) -> Notifier:
    """The notifier ``name`` with ``options`` validated by its own settings model.

    Raises ``PluginError`` for an unknown notifier and ``ConfigurationError`` for
    settings it rejects, before anything is sent.
    """
    plugin = registry.load(NOTIFIERS, name)
    try:
        settings = plugin.settings_model.model_validate(dict(options))
    except ValidationError as exc:
        problems = "; ".join(
            f"{'.'.join(str(part) for part in error['loc']) or 'settings'}: {error['msg']}"
            for error in exc.errors(include_input=False, include_url=False)
        )
        raise ConfigurationError(
            f"notifications.settings: invalid settings for notifier '{name}': {problems}"
        ) from exc
    notifier: Notifier = plugin(secrets, settings)
    return notifier
