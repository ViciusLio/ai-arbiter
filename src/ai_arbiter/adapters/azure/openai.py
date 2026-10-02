"""Azure OpenAI: the OpenAI wire format with Azure's URL shape and key header.

Authentication is by API key from the secret store. Entra ID tokens arrive in Phase 6,
with the Azure identity adapter. This module needs no Azure SDK.
"""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ai_arbiter.adapters.openai_compat.provider import OpenAIWireProvider
from ai_arbiter.core.config.secrets import SecretRef
from ai_arbiter.core.ports.llm import ChatRequest, Deployment, ProviderError


class AzureOpenAISettings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    # The resource endpoint, for example https://my-resource.openai.azure.com
    endpoint: str
    api_version: str
    # A secret reference (secret://NAME), never the key itself.
    api_key: str
    timeout_seconds: int = Field(default=120, ge=1)

    @field_validator("api_key")
    @classmethod
    def _reference(cls, value: str) -> str:
        SecretRef.parse(value)
        return value


class AzureOpenAIProvider(OpenAIWireProvider):
    """Registered as ``azure_openai``. The deployment's ``model`` is the Azure deployment name."""

    settings_model: type[BaseModel] = AzureOpenAISettings
    feature = "The Azure OpenAI provider"

    @staticmethod
    def _azure(target: Deployment) -> AzureOpenAISettings:
        settings = target.settings
        if not isinstance(settings, AzureOpenAISettings):
            raise ProviderError("deployment settings do not match the provider", retryable=False)
        return settings

    def _url(self, target: Deployment) -> str:
        settings = self._azure(target)
        return (
            f"{settings.endpoint.rstrip('/')}/openai/deployments/{target.model}"
            f"/chat/completions?api-version={settings.api_version}"
        )

    async def _headers(self, target: Deployment) -> dict[str, str]:
        key = await self._secrets.get(SecretRef.parse(self._azure(target).api_key))
        return {"api-key": key.get_secret_value()}

    def _timeout(self, target: Deployment) -> int:
        return self._azure(target).timeout_seconds

    def _body(self, request: ChatRequest, target: Deployment) -> dict[str, Any]:
        # The deployment in the URL selects the model; Azure does not need it in the body.
        return {**request.params, "messages": list(request.messages)}
