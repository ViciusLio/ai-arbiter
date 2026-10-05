"""Turn an HTML report into a PDF (ADR-0057).

The report is one self-contained document. The converter is given its text and may fetch
nothing: an address found in the report, which holds names typed by people, is never
followed.
"""

from typing import Any

from ai_arbiter.core.errors import ArbiterError, MissingExtraError

FEATURE = "A report as PDF"


class PdfUnavailableError(ArbiterError):
    """The extra is installed, and the library of the operating system it needs is not."""

    def __init__(self) -> None:
        super().__init__(
            "PDF output needs the Pango library of the operating system, which was not "
            "found. On Debian or Ubuntu: apt install libpango-1.0-0 libpangoft2-1.0-0. "
            "Markdown and HTML reports do not need it"
        )


def _weasyprint() -> Any:
    try:
        import weasyprint  # type: ignore[import-untyped]
    except ImportError as exc:
        raise MissingExtraError("pdf", FEATURE) from exc
    except OSError as exc:  # the Python package is there, a shared library is not
        raise PdfUnavailableError from exc
    return weasyprint


def html_to_pdf(html: str) -> bytes:
    """The PDF of an HTML document. Raises ``MissingExtraError`` without the extra."""
    weasyprint = _weasyprint()
    from weasyprint.urls import URLFetcher, URLFetchingError  # type: ignore[import-untyped]

    class NoFetching(URLFetcher):  # type: ignore[misc]
        def fetch(self, url: str, headers: Any = None) -> Any:
            raise URLFetchingError("a report is rendered without fetching anything")

    document: bytes = weasyprint.HTML(string=html, url_fetcher=NoFetching()).write_pdf()
    return document
