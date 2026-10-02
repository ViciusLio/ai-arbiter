"""Messages Arbiter sends to people, and the port that delivers them."""

import re
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ai_arbiter.core.errors import ArbiterError

# Deliberately loose: one "@", no spaces and no line breaks. The mail server decides
# whether the address exists.
_ADDRESS = re.compile(r"[^@\s<>,;]+@[^@\s<>,;]+")


class NotificationError(ArbiterError):
    """A message could not be delivered."""


def check_address(value: str) -> str:
    if not _ADDRESS.fullmatch(value):
        raise ValueError("not an e-mail address")
    return value


class OutboundMessage(BaseModel):
    """One message with a plain text body and, optionally, the same content as HTML."""

    model_config = ConfigDict(frozen=True)

    sender: str
    recipients: tuple[str, ...] = Field(min_length=1)
    subject: str = Field(min_length=1)
    text: str
    html: str | None = None

    @field_validator("sender")
    @classmethod
    def _sender(cls, value: str) -> str:
        return check_address(value)

    @field_validator("recipients")
    @classmethod
    def _recipients(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(check_address(item) for item in value)

    @field_validator("subject")
    @classmethod
    def _one_line(cls, value: str) -> str:
        # A line break in a header would let the subject add headers of its own.
        if "\r" in value or "\n" in value:
            raise ValueError("the subject must be one line")
        return value


class Notifier(Protocol):
    name: str

    async def send(self, message: OutboundMessage) -> None:
        """Deliver the message. Raises ``NotificationError`` when it cannot."""
        ...
