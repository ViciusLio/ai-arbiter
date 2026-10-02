import pytest

from ai_arbiter.adapters.local.secrets import EnvSecretStore
from ai_arbiter.core.config import SecretRef
from ai_arbiter.core.errors import SecretNotFoundError


async def test_resolves_a_secret_from_the_environment() -> None:
    store = EnvSecretStore({"ARBITER_SECRET_AZURE_OPENAI_KEY": "value-from-env"})

    secret = await store.get(SecretRef.parse("secret://azure-openai.key"))

    assert secret.get_secret_value() == "value-from-env"
    assert "value-from-env" not in repr(secret)


async def test_missing_secret_names_the_variable_to_set() -> None:
    store = EnvSecretStore({})

    with pytest.raises(SecretNotFoundError, match="ARBITER_SECRET_PROVIDER_KEY"):
        await store.get(SecretRef(name="provider-key"))


async def test_empty_value_counts_as_missing() -> None:
    store = EnvSecretStore({"ARBITER_SECRET_KEY": ""})

    with pytest.raises(SecretNotFoundError):
        await store.get(SecretRef(name="key"))


async def test_reads_the_process_environment_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ARBITER_SECRET_FROM_PROCESS", "present")

    secret = await EnvSecretStore().get(SecretRef(name="from-process"))

    assert secret.get_secret_value() == "present"
