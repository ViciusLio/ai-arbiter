"""Send a digest to its recipients, each in their language."""

from collections.abc import Sequence
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from ai_arbiter.compliance.digest.model import DigestModel
from ai_arbiter.compliance.digest.render import render_digest
from ai_arbiter.core.audit import AuditRecord
from ai_arbiter.core.config.settings import NotificationSettings
from ai_arbiter.core.errors import ConfigurationError
from ai_arbiter.core.i18n import SUPPORTED_LOCALES, Translator
from ai_arbiter.core.notification import NotificationError, Notifier, OutboundMessage
from ai_arbiter.core.ports import AuditLog


@dataclass(frozen=True)
class DeliveryReport:
    notifier: str
    messages: int
    recipients: int
    # Class name of what went wrong, when a message could not be delivered.
    error: str | None = None


def check_delivery_settings(settings: NotificationSettings) -> None:
    """Refuse to start a delivery that cannot end well. Raises ``ConfigurationError``."""
    if settings.sender is None:
        raise ConfigurationError("sending needs a sender: set notifications.sender")
    if not settings.recipients:
        raise ConfigurationError("sending needs recipients: set notifications.recipients")
    unsupported = sorted({r.locale for r in settings.recipients} - set(SUPPORTED_LOCALES))
    if unsupported:
        raise ConfigurationError(
            f"notifications.recipients: unsupported locale '{unsupported[0]}': "
            f"use {' or '.join(SUPPORTED_LOCALES)}"
        )


def digest_messages(digest: DigestModel, settings: NotificationSettings) -> list[OutboundMessage]:
    """One message per language, addressed to the recipients who read that language."""
    check_delivery_settings(settings)
    assert settings.sender is not None  # noqa: S101 - checked on the line above
    messages = []
    for locale in sorted({recipient.locale for recipient in settings.recipients}):
        translator = Translator(locale)
        messages.append(
            OutboundMessage(
                sender=settings.sender,
                recipients=tuple(r.address for r in settings.recipients if r.locale == locale),
                subject=translator.text(
                    "digest.mail_subject",
                    tenant=digest.tenant_name,
                    date=translator.date(digest.period_end.date()),
                ),
                text=render_digest(digest, locale=locale, output="markdown"),
                html=render_digest(digest, locale=locale, output="html"),
            )
        )
    return messages


async def send_messages(notifier: Notifier, messages: Sequence[OutboundMessage]) -> DeliveryReport:
    """Send every message. Stops at the first that fails and reports how far it got.

    Called with no database transaction open: a mail server can take its time.
    """
    sent = 0
    recipients = 0
    error: str | None = None
    for message in messages:
        try:
            await notifier.send(message)
        except NotificationError as exc:
            error = type(exc.__cause__ or exc).__name__
            break
        sent += 1
        recipients += len(message.recipients)
    return DeliveryReport(notifier=notifier.name, messages=sent, recipients=recipients, error=error)


async def record_delivery(
    session: AsyncSession,
    audit: AuditLog,
    tenant_id: UUID,
    run_id: UUID,
    report: DeliveryReport,
    expected: int,
) -> None:
    """One audit entry per delivery: how many messages left, never to whom."""
    await audit.append(
        session,
        tenant_id,
        AuditRecord(
            action="digest.sent" if report.error is None else "digest.send_failed",
            outcome=f"messages:{report.messages}/{expected}",
            resource_type="digest_run",
            resource_id=str(run_id),
            decision={
                "notifier": report.notifier,
                "messages": report.messages,
                "expected": expected,
                "recipients": report.recipients,
                "error": report.error,
            },
        ),
    )
