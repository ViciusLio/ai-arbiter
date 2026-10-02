"""Render the reports as Markdown or HTML, in English or Italian."""

from typing import Literal

from ai_arbiter.compliance.digest.render import environment
from ai_arbiter.compliance.reports.model import AuditReport, SystemReport
from ai_arbiter.core.i18n import Translator

ReportFormat = Literal["markdown", "html"]
_SUFFIX = {"markdown": "md.j2", "html": "html.j2"}


def render_system_report(
    report: SystemReport, *, locale: str = "en", output: ReportFormat = "markdown"
) -> str:
    translator = Translator(locale)
    template = environment().get_template(f"report-system.{_SUFFIX[output]}")
    return template.render(r=report, t=translator.text, f=translator, locale=locale)


def render_audit_report(
    report: AuditReport, *, locale: str = "en", output: ReportFormat = "markdown"
) -> str:
    translator = Translator(locale)
    template = environment().get_template(f"report-audit.{_SUFFIX[output]}")
    return template.render(r=report, t=translator.text, f=translator, locale=locale)
