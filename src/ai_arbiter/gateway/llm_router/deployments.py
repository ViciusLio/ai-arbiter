"""Turn the configured deployments into validated routing targets."""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError

from ai_arbiter.core.config.settings import DeploymentSettings
from ai_arbiter.core.errors import ConfigurationError
from ai_arbiter.core.plugins.registry import LLM_PROVIDERS, PluginRegistry
from ai_arbiter.core.ports import LLMProvider, SecretStore
from ai_arbiter.core.ports.llm import Deployment


@dataclass(frozen=True)
class Target:
    """A deployment ready to be called, with what the router needs to know about it."""

    deployment: Deployment
    config: DeploymentSettings

    @property
    def name(self) -> str:
        return self.deployment.name


def build_targets(
    deployments: Sequence[DeploymentSettings],
    registry: PluginRegistry,
    secrets: SecretStore,
    *,
    provider_options: dict[str, dict[str, Any]] | None = None,
) -> tuple[list[Target], dict[str, LLMProvider]]:
    """Load the provider plugins that the deployments name and validate their settings.

    One provider instance is created per plugin and shared by its deployments. Raises
    ``PluginError`` for an unknown plugin and ``ConfigurationError`` for settings the
    plugin rejects, both before the first request.
    """
    providers: dict[str, LLMProvider] = {}
    targets: list[Target] = []
    for config in deployments:
        if config.provider not in providers:
            plugin = registry.load(LLM_PROVIDERS, config.provider)
            options = (provider_options or {}).get(config.provider, {})
            providers[config.provider] = plugin(secrets, **options)
        provider = providers[config.provider]
        try:
            settings = provider.settings_model.model_validate(config.settings)
        except ValidationError as exc:
            problems = "; ".join(
                f"{'.'.join(str(part) for part in error['loc'])}: {error['msg']}"
                for error in exc.errors(include_input=False, include_url=False)
            )
            raise ConfigurationError(
                f"deployment '{config.name}': invalid settings for provider "
                f"'{config.provider}': {problems}"
            ) from exc
        targets.append(
            Target(
                deployment=Deployment(
                    name=config.name,
                    provider=config.provider,
                    model=config.model,
                    region=config.region,
                    settings=settings,
                ),
                config=config,
            )
        )
    return targets, providers
