"""Entry-point based plugin registry.

Discovery uses Python entry points, one group per port. Activation is separate: the
registry loads a plugin only when asked for it by name, and the name comes from
configuration. An installed package can therefore never run code in Arbiter unless the
operator named it.
"""

from collections.abc import Callable, Iterable
from importlib.metadata import EntryPoint, entry_points
from typing import Any

from ai_arbiter.core.errors import PluginError

GROUP_PREFIX = "ai_arbiter."

SECRET_STORES = "secret_stores"  # noqa: S105 - a group name, not a secret
EVENT_BUSES = "event_buses"

# Port groups known to this version, in display order.
GROUPS: tuple[str, ...] = (SECRET_STORES, EVENT_BUSES)

EntryPointSource = Callable[[str], Iterable[EntryPoint]]


def _installed_entry_points(group: str) -> Iterable[EntryPoint]:
    return entry_points(group=group)


class PluginRegistry:
    def __init__(self, source: EntryPointSource = _installed_entry_points) -> None:
        self._source = source

    def available(self, group: str) -> list[str]:
        """Names of the installed plugins for a port group, sorted."""
        return sorted(entry.name for entry in self._source(GROUP_PREFIX + group))

    def load(self, group: str, name: str) -> Any:
        """Import and return the object registered as ``name`` in ``group``.

        Raises ``PluginError`` if no such plugin is installed or if importing it fails.
        """
        matches = [entry for entry in self._source(GROUP_PREFIX + group) if entry.name == name]
        if not matches:
            known = ", ".join(self.available(group)) or "none"
            raise PluginError(f"unknown plugin '{name}' for '{group}' (installed: {known})")
        if len(matches) > 1:
            origins = ", ".join(sorted(entry.value for entry in matches))
            raise PluginError(f"plugin '{name}' for '{group}' is registered twice: {origins}")
        try:
            return matches[0].load()
        except Exception as exc:
            raise PluginError(f"plugin '{name}' for '{group}' failed to load: {exc}") from exc
