"""The file and SMTP notifiers. No test opens a connection: the SMTP client is replaced."""

import smtplib
from email import message_from_bytes, policy
from email.message import EmailMessage
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from ai_arbiter.adapters.local.notifiers import (
    FileNotifier,
    FileNotifierSettings,
    SmtpNotifier,
    SmtpNotifierSettings,
    build_email,
)
from ai_arbiter.adapters.local.secrets import EnvSecretStore
from ai_arbiter.core.errors import SecretNotFoundError
from ai_arbiter.core.notification import NotificationError, OutboundMessage

SENDER = "arbiter@example.org"
MESSAGE = OutboundMessage(
    sender=SENDER,
    recipients=("ada@example.org", "grace@example.org"),
    subject="Digest giornaliero: perché no",
    text="Testo semplice, con una è.\n",
    html="<p>Testo <b>HTML</b>, con una è.</p>\n",
)
# Not a credential of anything: the value a fake server expects in these tests.
MAIL_PASSWORD = "-".join(["only", "for", "tests"])


def test_a_message_refuses_what_is_not_an_address_and_a_subject_with_a_line_break() -> None:
    with pytest.raises(ValidationError):
        OutboundMessage(sender="nobody", recipients=("ada@example.org",), subject="x", text="")
    with pytest.raises(ValidationError):
        OutboundMessage(sender=SENDER, recipients=("ada@example.org, x@y.z",), subject="x", text="")
    with pytest.raises(ValidationError):
        OutboundMessage(sender=SENDER, recipients=(), subject="x", text="")
    with pytest.raises(ValidationError):
        OutboundMessage(
            sender=SENDER, recipients=("ada@example.org",), subject="x\nBcc: eve@x.y", text=""
        )


def test_an_email_has_a_text_part_and_an_html_alternative() -> None:
    email = build_email(MESSAGE)

    assert email["From"] == SENDER
    assert email["To"] == "ada@example.org, grace@example.org"
    assert email["Subject"] == "Digest giornaliero: perché no"
    assert email["Message-ID"].endswith("@example.org>")
    assert email.get_content_type() == "multipart/alternative"
    text, html = email.iter_parts()
    assert (text.get_content_type(), html.get_content_type()) == ("text/plain", "text/html")
    assert text.get_content() == MESSAGE.text
    assert html.get_content() == MESSAGE.html


def test_an_email_without_html_is_plain_text() -> None:
    email = build_email(MESSAGE.model_copy(update={"html": None}))

    assert email.get_content_type() == "text/plain"


async def test_the_file_notifier_writes_one_file_per_message(
    tmp_path: Path, secret_store: EnvSecretStore
) -> None:
    notifier = FileNotifier(secret_store, FileNotifierSettings(directory=tmp_path / "outbox"))

    await notifier.send(MESSAGE)
    await notifier.send(MESSAGE)

    files = sorted((tmp_path / "outbox").glob("*.eml"))
    assert len(files) == 2
    stored = message_from_bytes(files[0].read_bytes(), policy=policy.default)
    assert stored["Subject"] == MESSAGE.subject
    body = stored.get_body(preferencelist=("plain",))
    assert body is not None
    assert body.get_content() == MESSAGE.text


async def test_the_file_notifier_reports_a_directory_it_cannot_write_to(
    tmp_path: Path, secret_store: EnvSecretStore
) -> None:
    (tmp_path / "taken").write_text("a file where the directory should be")
    notifier = FileNotifier(secret_store, FileNotifierSettings(directory=tmp_path / "taken"))

    with pytest.raises(NotificationError, match="could not be written"):
        await notifier.send(MESSAGE)


def test_smtp_settings_keep_credentials_together_and_off_plain_connections() -> None:
    reference = "secret://smtp-password"

    assert SmtpNotifierSettings(host="mail.example.org").security == "starttls"
    with pytest.raises(ValidationError, match="go together"):
        SmtpNotifierSettings(host="mail.example.org", username="arbiter")
    with pytest.raises(ValidationError, match="without encryption"):
        SmtpNotifierSettings(
            host="mail.example.org", security="none", username="arbiter", password=reference
        )
    with pytest.raises(ValidationError, match="not a secret reference"):
        SmtpNotifierSettings(host="mail.example.org", username="arbiter", password=MAIL_PASSWORD)
    with pytest.raises(ValidationError):
        SmtpNotifierSettings(host="mail.example.org", unknown=True)  # type: ignore[call-arg]


class FakeServer:
    """Stands in for ``smtplib.SMTP`` and ``smtplib.SMTP_SSL``: records what is asked."""

    calls: list[tuple[Any, ...]]
    fail_with: Exception | None = None

    def __init__(self, host: str, port: int, **options: Any) -> None:
        type(self).calls.append(("connect", type(self).__name__, host, port, options["timeout"]))

    def __enter__(self) -> "FakeServer":
        return self

    def __exit__(self, *details: object) -> None:
        type(self).calls.append(("quit",))

    def starttls(self, *, context: Any) -> None:
        type(self).calls.append(("starttls", context.check_hostname))

    def login(self, username: str, password: str) -> None:
        type(self).calls.append(("login", username, password))

    def send_message(self, email: EmailMessage) -> None:
        failure = type(self).fail_with
        if failure is not None:
            raise failure
        type(self).calls.append(("send", email["To"], email["Subject"]))


class FakeTlsServer(FakeServer):
    pass


@pytest.fixture
def server(monkeypatch: pytest.MonkeyPatch) -> type[FakeServer]:
    FakeServer.calls = []
    FakeServer.fail_with = None
    monkeypatch.setattr(smtplib, "SMTP", FakeServer)
    monkeypatch.setattr(smtplib, "SMTP_SSL", FakeTlsServer)
    return FakeServer


def store() -> EnvSecretStore:
    return EnvSecretStore({"ARBITER_SECRET_SMTP_PASSWORD": MAIL_PASSWORD})


async def test_smtp_upgrades_the_connection_before_it_logs_in_and_sends(
    server: type[FakeServer],
) -> None:
    settings = SmtpNotifierSettings(
        host="mail.example.org", username="arbiter", password="secret://smtp-password"
    )

    await SmtpNotifier(store(), settings).send(MESSAGE)

    assert server.calls == [
        ("connect", "FakeServer", "mail.example.org", 587, 30),
        ("starttls", True),
        ("login", "arbiter", MAIL_PASSWORD),
        ("send", "ada@example.org, grace@example.org", MESSAGE.subject),
        ("quit",),
    ]


async def test_smtp_over_tls_and_without_encryption(server: type[FakeServer]) -> None:
    encrypted = SmtpNotifierSettings(host="mail.example.org", port=465, security="tls")
    plain = SmtpNotifierSettings(host="localhost", port=1025, security="none")

    await SmtpNotifier(store(), encrypted).send(MESSAGE)
    await SmtpNotifier(store(), plain).send(MESSAGE)

    assert [call[:4] for call in server.calls if call[0] == "connect"] == [
        ("connect", "FakeTlsServer", "mail.example.org", 465),
        ("connect", "FakeServer", "localhost", 1025),
    ]
    assert not [call for call in server.calls if call[0] in ("starttls", "login")]


async def test_smtp_failures_keep_the_kind_of_error_and_drop_the_servers_words(
    server: type[FakeServer],
) -> None:
    server.fail_with = smtplib.SMTPRecipientsRefused({"ada@example.org": (550, b"no such user")})
    settings = SmtpNotifierSettings(host="mail.example.org", security="none")

    with pytest.raises(NotificationError) as raised:
        await SmtpNotifier(store(), settings).send(MESSAGE)

    assert "SMTPRecipientsRefused" in str(raised.value)
    assert "ada@example.org" not in str(raised.value)
    assert "no such user" not in str(raised.value)


async def test_smtp_reports_a_server_that_cannot_be_reached(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def refuse(*arguments: Any, **options: Any) -> None:
        raise ConnectionRefusedError

    monkeypatch.setattr(smtplib, "SMTP", refuse)
    settings = SmtpNotifierSettings(host="mail.example.org", security="none")

    with pytest.raises(NotificationError, match="ConnectionRefusedError"):
        await SmtpNotifier(store(), settings).send(MESSAGE)


async def test_smtp_needs_the_secret_its_settings_name(server: type[FakeServer]) -> None:
    settings = SmtpNotifierSettings(
        host="mail.example.org", username="arbiter", password="secret://smtp-password"
    )

    with pytest.raises(SecretNotFoundError):
        await SmtpNotifier(EnvSecretStore({}), settings).send(MESSAGE)
    assert server.calls == []
