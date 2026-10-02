from pathlib import Path

import pytest

from ai_arbiter.core.config import (
    DEFAULT_DATABASE_URL,
    Role,
    SecretRef,
    Settings,
    load_settings,
)
from ai_arbiter.core.errors import ConfigurationError


def write(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


def test_defaults_apply_without_file_or_environment() -> None:
    settings = load_settings()

    assert settings.environment == "local"
    assert settings.database.url == DEFAULT_DATABASE_URL
    assert settings.server.roles == frozenset(Role)
    assert settings.plugins.secret_store == "env"
    assert settings.telemetry.enabled is False


def test_values_come_from_the_named_file(tmp_path: Path) -> None:
    config = write(tmp_path / "custom.yaml", "environment: staging\nserver:\n  port: 9000\n")

    settings = load_settings(config)

    assert settings.environment == "staging"
    assert settings.server.port == 9000


def test_default_file_in_the_working_directory_is_used(tmp_path: Path) -> None:
    write(tmp_path / "arbiter.yaml", "environment: from-default-file\n")

    assert load_settings().environment == "from-default-file"


def test_file_can_be_named_by_environment_variable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = write(tmp_path / "elsewhere.yaml", "environment: from-env-named-file\n")
    monkeypatch.setenv("ARBITER_CONFIG", str(config))

    assert load_settings().environment == "from-env-named-file"


def test_environment_overrides_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config = write(tmp_path / "c.yaml", "server:\n  host: 10.0.0.1\n  port: 9000\n")
    monkeypatch.setenv("ARBITER_SERVER__PORT", "9100")

    settings = load_settings(config)

    assert settings.server.port == 9100
    assert settings.server.host == "10.0.0.1"


def test_explicit_override_wins_and_keeps_sibling_keys(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = write(tmp_path / "c.yaml", "server:\n  host: 10.0.0.1\n  port: 9000\n")
    monkeypatch.setenv("ARBITER_SERVER__PORT", "9100")

    settings = load_settings(config, server={"port": 9200})

    assert settings.server.port == 9200
    assert settings.server.host == "10.0.0.1"


def test_roles_are_parsed_from_a_list(tmp_path: Path) -> None:
    config = write(tmp_path / "c.yaml", "server:\n  roles: [gateway, admin]\n")

    assert load_settings(config).server.roles == {Role.GATEWAY, Role.ADMIN}


def test_unknown_key_is_reported_by_name(tmp_path: Path) -> None:
    config = write(tmp_path / "c.yaml", "databse:\n  url: sqlite://\n")

    with pytest.raises(ConfigurationError, match="databse"):
        load_settings(config)


def test_invalid_value_is_reported_with_its_path(tmp_path: Path) -> None:
    config = write(tmp_path / "c.yaml", "server:\n  port: 70000\n")

    with pytest.raises(ConfigurationError, match=r"server\.port"):
        load_settings(config)


def test_named_file_must_exist(tmp_path: Path) -> None:
    with pytest.raises(ConfigurationError, match="not found"):
        load_settings(tmp_path / "missing.yaml")


def test_unrelated_arbiter_variables_are_ignored(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ARBITER_SECRET_PROVIDER_KEY", "not-a-setting")
    monkeypatch.setenv("ARBITER_POSTGRES_PASSWORD", "not-a-setting")

    assert load_settings().environment == "local"


def test_redacted_output_masks_database_credentials() -> None:
    settings = Settings(
        database={"url": "postgresql+asyncpg://arbiter:s3cret@db.example:5432/arbiter"}
    )

    shown = settings.redacted()

    assert "s3cret" not in str(shown)
    assert shown["database"]["url"] == "postgresql+asyncpg://arbiter:***@db.example:5432/arbiter"
    assert shown["server"]["roles"] == ["admin", "gateway", "worker"]


def test_redacted_output_survives_an_unparseable_url() -> None:
    settings = Settings(database={"url": "not a url"})

    assert settings.redacted()["database"]["url"] == "<unparseable url>"


class TestSecretRef:
    def test_parses_a_reference(self) -> None:
        ref = SecretRef.parse("secret://azure-openai.key")

        assert ref.name == "azure-openai.key"
        assert str(ref) == "secret://azure-openai.key"

    @pytest.mark.parametrize(
        "value", ["plain-value", "secret://", "secret://has space", "http://x"]
    )
    def test_rejects_anything_else(self, value: str) -> None:
        with pytest.raises(ValueError, match="secret"):
            SecretRef.parse(value)

    def test_recognises_references(self) -> None:
        assert SecretRef.is_reference("secret://name")
        assert not SecretRef.is_reference("name")
