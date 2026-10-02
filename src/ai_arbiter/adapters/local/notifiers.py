"""Notifiers that need no cloud service: files in a directory, and SMTP.

Both use the standard library only, so they work on a base install.
"""

import asyncio
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import format_datetime, make_msgid
from pathlib import Path
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ai_arbiter.core.config.secrets import SecretRef
from ai_arbiter.core.domain.ids import new_id
from ai_arbiter.core.domain.time import utcnow
from ai_arbiter.core.notification import NotificationError, OutboundMessage
from ai_arbiter.core.ports import SecretStore


def build_email(message: OutboundMessage) -> EmailMessage:
    """The message as an e-mail: plain text, with the HTML as an alternative part."""
    email = EmailMessage()
    email["From"] = message.sender
    email["To"] = ", ".join(message.recipients)
    email["Subject"] = message.subject
    email["Date"] = format_datetime(utcnow())
    email["Message-ID"] = make_msgid(domain=message.sender.rpartition("@")[2])
    email.set_content(message.text)
    if message.html is not None:
        email.add_alternative(message.html, subtype="html")
    return email


class FileNotifierSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    # Where messages are written, one ``.eml`` file each.
    directory: Path = Path(".arbiter/outbox")


class FileNotifier:
    """Writes each message to a file instead of sending it (ADR-0025).

    The default: nothing leaves the machine until an operator names another notifier.
    """

    name = "file"
    settings_model: type[BaseModel] = FileNotifierSettings

    def __init__(self, secrets: SecretStore, settings: FileNotifierSettings) -> None:
        self._directory = settings.directory

    async def send(self, message: OutboundMessage) -> None:
        email = build_email(message)
        path = self._directory / f"{utcnow():%Y%m%dT%H%M%SZ}-{new_id()}.eml"
        try:
            self._directory.mkdir(parents=True, exist_ok=True)
            path.write_bytes(email.as_bytes())
        except OSError as exc:
            raise NotificationError(
                f"the message could not be written to {self._directory} ({type(exc).__name__})"
            ) from exc


class SmtpNotifierSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    host: str = Field(min_length=1)
    port: int = Field(default=587, ge=1, le=65535)
    # starttls: upgrade a plain connection (port 587). tls: encrypted from the start
    # (port 465). none: no encryption, for a relay on the same host or a test catcher.
    security: Literal["starttls", "tls", "none"] = "starttls"
    username: str | None = None
    # A secret reference (secret://NAME), never the password itself.
    password: str | None = None
    timeout_seconds: int = Field(default=30, ge=1)

    @field_validator("password")
    @classmethod
    def _reference(cls, value: str | None) -> str | None:
        if value is not None:
            SecretRef.parse(value)
        return value

    @model_validator(mode="after")
    def _credentials(self) -> Self:
        if (self.username is None) != (self.password is None):
            raise ValueError("username and password go together")
        if self.password is not None and self.security == "none":
            raise ValueError("credentials are not sent over a connection without encryption")
        return self


class SmtpNotifier:
    """Sends through an SMTP server. The blocking client runs in a worker thread."""

    name = "smtp"
    settings_model: type[BaseModel] = SmtpNotifierSettings

    def __init__(self, secrets: SecretStore, settings: SmtpNotifierSettings) -> None:
        self._secrets = secrets
        self._settings = settings

    def _deliver(self, email: EmailMessage, password: str | None) -> None:
        settings = self._settings
        client: smtplib.SMTP
        if settings.security == "tls":
            client = smtplib.SMTP_SSL(
                settings.host,
                settings.port,
                timeout=settings.timeout_seconds,
                context=ssl.create_default_context(),
            )
        else:
            client = smtplib.SMTP(settings.host, settings.port, timeout=settings.timeout_seconds)
        with client:
            if settings.security == "starttls":
                client.starttls(context=ssl.create_default_context())
            if settings.username is not None and password is not None:
                client.login(settings.username, password)
            client.send_message(email)

    async def send(self, message: OutboundMessage) -> None:
        settings = self._settings
        password = (
            (await self._secrets.get(SecretRef.parse(settings.password))).get_secret_value()
            if settings.password is not None
            else None
        )
        try:
            await asyncio.to_thread(self._deliver, build_email(message), password)
        except (smtplib.SMTPException, OSError) as exc:
            # The server's own words may quote addresses: only the kind of failure is kept.
            raise NotificationError(
                f"the SMTP server {settings.host}:{settings.port} could not be reached or "
                f"refused the message ({type(exc).__name__})"
            ) from exc
