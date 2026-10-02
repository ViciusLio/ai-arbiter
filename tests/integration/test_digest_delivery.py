"""Sending the digest: who gets which language, what is recorded, what the CLI does."""

import json
import smtplib
from email import message_from_bytes, policy
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
from sqlalchemy import select

from ai_arbiter.compliance.digest.delivery import (
    check_delivery_settings,
    digest_messages,
    record_delivery,
    send_messages,
)
from ai_arbiter.compliance.inventory.declarations import SystemDeclaration, load_declarations
from ai_arbiter.compliance.runtime import ComplianceRuntime, build_compliance
from ai_arbiter.core.audit import AuditEntry, DatabaseAuditLog
from ai_arbiter.core.config import load_settings
from ai_arbiter.core.config.settings import NotificationSettings
from ai_arbiter.core.domain.ids import new_id
from ai_arbiter.core.errors import ConfigurationError
from ai_arbiter.core.events.bus import InProcessEventBus
from ai_arbiter.core.notification import NotificationError, OutboundMessage
from ai_arbiter.core.persistence.database import Database
from tests.integration.test_cli_compliance import arbiter, workspace
from tests.integration.test_compliance import EXAMPLES, FixedClock, declare, digest_for

RECIPIENTS = [
    {"address": "ada@example.org", "locale": "it"},
    {"address": "grace@example.org"},
    {"address": "edsger@example.org", "locale": "it"},
]


def notifications(**values: Any) -> NotificationSettings:
    defaults = {"sender": "arbiter@example.org", "recipients": RECIPIENTS}
    return load_settings(notifications={**defaults, **values}).notifications


@pytest.fixture
def compliance() -> ComplianceRuntime:
    clock = FixedClock()
    return build_compliance(
        load_settings(), audit=DatabaseAuditLog(clock), bus=InProcessEventBus(), clock=clock
    )


@pytest.fixture
def declarations() -> dict[str, SystemDeclaration]:
    return {system.key: system for system in load_declarations(EXAMPLES)}


class RecordingNotifier:
    name = "recording"

    def __init__(self, fail_from: int | None = None) -> None:
        self.sent: list[OutboundMessage] = []
        self._fail_from = fail_from

    async def send(self, message: OutboundMessage) -> None:
        if self._fail_from is not None and len(self.sent) >= self._fail_from:
            raise NotificationError("refused") from TimeoutError()
        self.sent.append(message)


def test_a_delivery_needs_a_sender_recipients_and_languages_that_exist() -> None:
    with pytest.raises(ConfigurationError, match=r"notifications\.sender"):
        check_delivery_settings(notifications(sender=None))
    with pytest.raises(ConfigurationError, match=r"notifications\.recipients"):
        check_delivery_settings(notifications(recipients=[]))
    with pytest.raises(ConfigurationError, match="unsupported locale 'fr'"):
        check_delivery_settings(
            notifications(recipients=[{"address": "ada@example.org", "locale": "fr"}])
        )
    with pytest.raises(ConfigurationError):
        notifications(recipients=[{"address": "not an address"}])


async def test_each_recipient_gets_the_digest_in_their_language(
    compliance: ComplianceRuntime,
    database: Database,
    tenant_id: UUID,
    declarations: dict[str, SystemDeclaration],
) -> None:
    await declare(compliance, database, tenant_id, declarations, "cv-screening")
    digest = await digest_for(compliance, database, tenant_id)

    english, italian = digest_messages(digest, notifications())

    assert english.recipients == ("grace@example.org",)
    assert italian.recipients == ("ada@example.org", "edsger@example.org")
    assert english.subject.startswith("Arbiter daily digest: Acme, ")
    assert italian.subject.startswith("Digest giornaliero di Arbiter: Acme, ")
    assert english.text.startswith("# Daily digest\n")
    assert italian.text.startswith("# Digest giornaliero\n")
    assert italian.html is not None
    assert "<h1>Digest giornaliero</h1>" in italian.html
    assert "non fornisce consulenza legale" in italian.text.lower()


async def test_a_delivery_stops_at_the_first_failure_and_is_audited_without_addresses(
    compliance: ComplianceRuntime, database: Database, tenant_id: UUID
) -> None:
    digest = await digest_for(compliance, database, tenant_id)
    messages = digest_messages(digest, notifications())
    working, failing = RecordingNotifier(), RecordingNotifier(fail_from=1)
    run_id = new_id()

    sent = await send_messages(working, messages)
    partial = await send_messages(failing, messages)
    async with database.transaction() as session:
        await record_delivery(session, compliance.audit, tenant_id, run_id, sent, len(messages))
        await record_delivery(session, compliance.audit, tenant_id, run_id, partial, len(messages))

    assert (sent.messages, sent.recipients, sent.error) == (2, 3, None)
    assert (partial.messages, partial.recipients, partial.error) == (1, 1, "TimeoutError")
    async with database.session() as session:
        entries = (await session.scalars(select(AuditEntry).order_by(AuditEntry.seq))).all()
        report = await compliance.audit.verify(session, tenant_id)
    assert [(entry.action, entry.outcome) for entry in entries] == [
        ("digest.sent", "messages:2/2"),
        ("digest.send_failed", "messages:1/2"),
    ]
    assert entries[0].resource_id == str(run_id)
    assert entries[1].decision == {
        "notifier": "recording",
        "messages": 1,
        "expected": 2,
        "recipients": 1,
        "error": "TimeoutError",
    }
    assert "example.org" not in json.dumps([entry.decision for entry in entries])
    assert report.ok


# --- command line ------------------------------------------------------------------------


def configure(monkeypatch: pytest.MonkeyPatch, **settings: Any) -> None:
    monkeypatch.setenv("ARBITER_NOTIFICATIONS__SENDER", "arbiter@example.org")
    monkeypatch.setenv("ARBITER_NOTIFICATIONS__RECIPIENTS", json.dumps(RECIPIENTS))
    if settings:
        monkeypatch.setenv("ARBITER_NOTIFICATIONS__SETTINGS", json.dumps(settings))


def test_send_writes_the_messages_to_the_outbox_by_default(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    workspace()
    configure(monkeypatch)

    output = arbiter("digest", "run", "--send")
    files = sorted(Path(".arbiter/outbox").glob("*.eml"))
    stored = [message_from_bytes(path.read_bytes(), policy=policy.default) for path in files]

    assert output.strip() == ("Sent 2 of 2 messages to 3 recipients through the 'file' notifier.")
    assert sorted(message["To"] for message in stored) == [
        "ada@example.org, edsger@example.org",
        "grace@example.org",
    ]
    assert all(message.get_content_type() == "multipart/alternative" for message in stored)
    assert "| `digest.sent` |" in arbiter("report", "audit")
    assert "notifiers:\n  file                 active\n  smtp                 installed" in arbiter(
        "plugins", "list"
    )


def test_send_also_writes_the_files_asked_for(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    workspace()
    configure(monkeypatch, directory=str(tmp_path / "mail"))

    output = arbiter("digest", "run", "--send", "-o", str(tmp_path / "out"))

    assert [path.name.split(".", 1)[1] for path in (tmp_path / "out").iterdir()] == ["en.md"]
    assert len(list((tmp_path / "mail").glob("*.eml"))) == 2
    assert "Sent 2 of 2 messages" in output


def test_send_refuses_a_configuration_that_cannot_deliver(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace()

    assert "Error: sending needs a sender" in arbiter("digest", "run", "--send", ok=False)
    configure(monkeypatch, host="mail.example.org")
    assert "invalid settings for notifier 'file': host" in arbiter(
        "digest", "run", "--send", ok=False
    )
    monkeypatch.setenv("ARBITER_PLUGINS__NOTIFIER", "pigeon")
    assert "Error: unknown plugin 'pigeon' for 'notifiers'" in arbiter(
        "digest", "run", "--send", ok=False
    )
    assert "`digest.sent`" not in arbiter("report", "audit")


def test_a_failed_send_exits_with_an_error_and_is_audited(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def refuse(*arguments: Any, **options: Any) -> None:
        raise ConnectionRefusedError

    workspace()
    configure(monkeypatch, host="mail.example.org", security="none")
    monkeypatch.setenv("ARBITER_PLUGINS__NOTIFIER", "smtp")
    monkeypatch.setattr(smtplib, "SMTP", refuse)

    output = arbiter("digest", "run", "--send", ok=False)

    assert "Sent 0 of 2 messages to 0 recipients through the 'smtp' notifier." in output
    assert "Error: a message could not be delivered (ConnectionRefusedError)" in output
    assert "| `digest.send_failed` |" in arbiter("report", "audit")
