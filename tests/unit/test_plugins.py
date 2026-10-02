from collections.abc import Iterable
from importlib.metadata import EntryPoint

import pytest

from ai_arbiter.adapters.local.secrets import EnvSecretStore
from ai_arbiter.core.errors import PluginError
from ai_arbiter.core.events.bus import InProcessEventBus
from ai_arbiter.core.plugins import EVENT_BUSES, SECRET_STORES, PluginRegistry


def fake_source(*entries: EntryPoint) -> PluginRegistry:
    def source(group: str) -> Iterable[EntryPoint]:
        return [entry for entry in entries if entry.group == group]

    return PluginRegistry(source)


def entry(name: str, value: str, group: str = "ai_arbiter.secret_stores") -> EntryPoint:
    return EntryPoint(name=name, value=value, group=group)


def test_lists_installed_plugins_of_a_group_sorted() -> None:
    registry = fake_source(
        entry("vault", "pkg.vault:Store"),
        entry("env", "pkg.env:Store"),
        entry("other", "pkg.bus:Bus", group="ai_arbiter.event_buses"),
    )

    assert registry.available(SECRET_STORES) == ["env", "vault"]
    assert registry.available(EVENT_BUSES) == ["other"]


def test_loads_the_named_plugin() -> None:
    registry = fake_source(entry("env", "ai_arbiter.adapters.local.secrets:EnvSecretStore"))

    assert registry.load(SECRET_STORES, "env") is EnvSecretStore


def test_unknown_name_fails_and_says_what_is_installed() -> None:
    registry = fake_source(entry("env", "pkg.env:Store"))

    with pytest.raises(PluginError, match=r"unknown plugin 'vault'.*installed: env"):
        registry.load(SECRET_STORES, "vault")


def test_unknown_name_in_an_empty_group_says_none() -> None:
    with pytest.raises(PluginError, match="installed: none"):
        fake_source().load(SECRET_STORES, "env")


def test_two_packages_registering_the_same_name_is_an_error() -> None:
    registry = fake_source(entry("env", "first.pkg:Store"), entry("env", "second.pkg:Store"))

    with pytest.raises(PluginError, match=r"registered twice: first\.pkg:Store, second\.pkg:Store"):
        registry.load(SECRET_STORES, "env")


def test_import_failure_is_reported_as_plugin_error() -> None:
    registry = fake_source(entry("broken", "no_such_package_for_arbiter_tests:Store"))

    with pytest.raises(PluginError, match="failed to load"):
        registry.load(SECRET_STORES, "broken")


def test_built_in_plugins_are_registered_as_entry_points() -> None:
    registry = PluginRegistry()

    assert registry.load(SECRET_STORES, "env") is EnvSecretStore
    assert registry.load(EVENT_BUSES, "in_process") is InProcessEventBus
