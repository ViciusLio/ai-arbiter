from pathlib import Path

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


async def test_falls_back_to_the_dotenv_file_when_the_variable_is_not_set(tmp_path: Path) -> None:
    dotenv = tmp_path / ".env"
    dotenv.write_text(
        "# local secrets\n"
        "OTHER=ignored\n"
        "ARBITER_SECRET_FROM_FILE=file-value\n"
        'export ARBITER_SECRET_QUOTED="quoted value"\n',
        encoding="utf-8",
    )
    store = EnvSecretStore({}, dotenv=dotenv)

    assert (await store.get(SecretRef(name="from-file"))).get_secret_value() == "file-value"
    assert (await store.get(SecretRef(name="quoted"))).get_secret_value() == "quoted value"


async def test_the_environment_wins_over_the_dotenv_file(tmp_path: Path) -> None:
    dotenv = tmp_path / ".env"
    dotenv.write_text("ARBITER_SECRET_KEY=from-file\n", encoding="utf-8")
    store = EnvSecretStore({"ARBITER_SECRET_KEY": "from-environment"}, dotenv=dotenv)

    assert (await store.get(SecretRef(name="key"))).get_secret_value() == "from-environment"


async def test_a_change_to_the_dotenv_file_is_picked_up(tmp_path: Path) -> None:
    dotenv = tmp_path / ".env"
    store = EnvSecretStore({}, dotenv=dotenv)
    with pytest.raises(SecretNotFoundError):
        await store.get(SecretRef(name="key"))

    dotenv.write_text("ARBITER_SECRET_KEY=added-later\n", encoding="utf-8")

    assert (await store.get(SecretRef(name="key"))).get_secret_value() == "added-later"


async def test_the_default_store_reads_dotenv_in_the_working_directory(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text("ARBITER_SECRET_LOCAL=here\n", encoding="utf-8")

    assert (await EnvSecretStore().get(SecretRef(name="local"))).get_secret_value() == "here"
