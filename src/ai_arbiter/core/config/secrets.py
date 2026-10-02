"""Secret references.

Configuration never holds a secret value. It holds a reference, ``secret://NAME``, that
is resolved at use through the ``SecretStore`` port.
"""

import re

from pydantic import BaseModel, ConfigDict

SECRET_SCHEME = "secret://"  # noqa: S105 - a URL scheme, not a secret
_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,126}")


class SecretRef(BaseModel):
    """A pointer to a secret held by a secret store."""

    model_config = ConfigDict(frozen=True)

    name: str

    @classmethod
    def parse(cls, value: str) -> "SecretRef":
        """Parse ``secret://NAME``. Raises ``ValueError`` on anything else."""
        if not value.startswith(SECRET_SCHEME):
            raise ValueError(f"not a secret reference (expected {SECRET_SCHEME}NAME)")
        name = value.removeprefix(SECRET_SCHEME)
        if not _NAME.fullmatch(name):
            raise ValueError("invalid secret name: use letters, digits, '_', '-' and '.'")
        return cls(name=name)

    @staticmethod
    def is_reference(value: str) -> bool:
        return value.startswith(SECRET_SCHEME)

    def __str__(self) -> str:
        return f"{SECRET_SCHEME}{self.name}"
