"""Secret store backed by environment variables."""

import os
import re
from collections.abc import Mapping

from pydantic import SecretStr

from ai_arbiter.core.config.secrets import SecretRef
from ai_arbiter.core.errors import SecretNotFoundError

ENV_PREFIX = "ARBITER_SECRET_"


class EnvSecretStore:
    """Resolves ``secret://my-key`` from the environment variable ``ARBITER_SECRET_MY_KEY``."""

    def __init__(self, environ: Mapping[str, str] | None = None) -> None:
        self._environ = os.environ if environ is None else environ

    @staticmethod
    def variable_name(ref: SecretRef) -> str:
        return ENV_PREFIX + re.sub(r"[^A-Za-z0-9]", "_", ref.name).upper()

    async def get(self, ref: SecretRef) -> SecretStr:
        variable = self.variable_name(ref)
        value = self._environ.get(variable)
        if not value:
            raise SecretNotFoundError(f"secret '{ref.name}' not found: set {variable}")
        return SecretStr(value)
