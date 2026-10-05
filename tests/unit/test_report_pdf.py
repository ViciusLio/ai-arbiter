"""The converter of reports to PDF (ADR-0057)."""

import importlib
import logging

import pytest

from ai_arbiter.compliance.reports.pdf import html_to_pdf

try:
    importlib.import_module("weasyprint")
except (ImportError, OSError):
    pytestmark = pytest.mark.skip("needs the pdf extra and the Pango library of the system")


def test_a_document_becomes_a_pdf() -> None:
    document = html_to_pdf("<html><body><h1>Rapporto</h1><p>Perché sì.</p></body></html>")

    assert document.startswith(b"%PDF-")


def test_nothing_named_in_a_document_is_fetched(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    import urllib.request

    def opened(*args: object, **kwargs: object) -> None:
        raise AssertionError("the converter tried to open an address")

    monkeypatch.setattr(urllib.request, "urlopen", opened)
    monkeypatch.setattr(urllib.request.OpenerDirector, "open", opened)
    html = (
        "<html><head><link rel='stylesheet' href='https://elsewhere.example/a.css'></head>"
        "<body><img src='https://elsewhere.example/pixel.png'>"
        "<img src='file:///etc/hostname'><p>Text</p></body></html>"
    )

    with caplog.at_level(logging.ERROR, logger="weasyprint"):
        document = html_to_pdf(html)

    assert document.startswith(b"%PDF-")
