"""Secret store backed by environment variables, with a local ``.env`` file as fallback."""

import os
import re
from collections.abc import Mapping
from pathlib import Path

from pydantic import SecretStr

from ai_arbiter.core.config.secrets import SecretRef
from ai_arbiter.core.errors import SecretNotFoundError

ENV_PREFIX = "ARBITER_SECRET_"
DEFAULT_DOTENV = Path(".env")


def read_dotenv_secrets(path: Path) -> dict[str, str]:
    """``ARBITER_SECRET_*`` assignments of a ``.env`` file. Other lines are ignored."""
    if not path.is_file():
        return {}
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        name, separator, value = line.strip().partition("=")
        name = name.removeprefix("export ").strip()
        if not separator or not name.startswith(ENV_PREFIX):
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        values[name] = value
    return values


class EnvSecretStore:
    """Resolves ``secret://my-key`` from the environment variable ``ARBITER_SECRET_MY_KEY``.

    When the variable is not set, the same name is looked up in ``.env`` in the working
    directory. That file is where ``arbiter init`` puts the secrets it generates for a
    local workspace; the environment always wins over it.
    """

    def __init__(
        self, environ: Mapping[str, str] | None = None, *, dotenv: Path | None = None
    ) -> None:
        self._environ = os.environ if environ is None else environ
        # An explicit environment (tests, embedding) gets no file unless one is named.
        self._dotenv = dotenv if dotenv is not None or environ is not None else DEFAULT_DOTENV
        self._file_state: tuple[float, int] | None = None
        self._file_values: dict[str, str] = {}

    @staticmethod
    def variable_name(ref: SecretRef) -> str:
        return ENV_PREFIX + re.sub(r"[^A-Za-z0-9]", "_", ref.name).upper()

    def _from_file(self, variable: str) -> str | None:
        if self._dotenv is None:
            return None
        try:
            stat = self._dotenv.stat()
        except OSError:
            return None
        state = (stat.st_mtime, stat.st_size)
        if state != self._file_state:
            self._file_values = read_dotenv_secrets(self._dotenv)
            self._file_state = state
        return self._file_values.get(variable)

    async def get(self, ref: SecretRef) -> SecretStr:
        variable = self.variable_name(ref)
        value = self._environ.get(variable) or self._from_file(variable)
        if not value:
            raise SecretNotFoundError(f"secret '{ref.name}' not found: set {variable}")
        return SecretStr(value)
