"""The run of a demonstration as one page to show: a deck of what happened (ADR-0060).

The page is self-contained: no script, style or font is loaded from anywhere. Every
figure on it comes from the run it is given.
"""

import json
from typing import Any

from markupsafe import Markup

from ai_arbiter.cli.demo_consulting import DemoRun, ToolUse
from ai_arbiter.compliance.digest.render import environment
from ai_arbiter.core.i18n import Translator

_TEMPLATE = "demo-report.html.j2"
_TIER_TONE = {"prohibited": "no", "high_risk": "warn", "transparency": "info", "minimal": "ok"}
_SEVERITY_TONE = {"critical": "no", "high": "no", "medium": "warn", "low": "info", "info": "info"}


def _script(value: Any) -> Markup:
    """A value as a JavaScript literal that is safe inside a script element."""
    text = json.dumps(value, ensure_ascii=False)
    for unsafe, safe in (("<", "\\u003c"), (">", "\\u003e"), ("&", "\\u0026")):
        text = text.replace(unsafe, safe)
    return Markup(text)  # noqa: S704


def _matrix(
    usage: tuple[ToolUse, ...],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """The models as columns, approved ones first, and one row of cells for each tool."""
    models = sorted({(not use.approved, use.model) for use in usage})
    columns = [{"name": name, "approved": not other} for other, name in models]
    by_tool: dict[str, dict[str, ToolUse]] = {}
    for use in usage:
        by_tool.setdefault(use.tool, {})[use.model] = use
    rows = [
        {"tool": tool, "cells": [cells.get(str(column["name"])) for column in columns]}
        for tool, cells in sorted(by_tool.items())
    ]
    return columns, rows


def render_demo_report(run: DemoRun, translator: Translator) -> str:
    """The page for a run, in the language of ``translator``."""
    t = translator.text
    systems = []
    for item in run.systems:
        classification = item.get("classification") or {}
        tier = str(classification.get("tier") or "not_classified")
        systems.append(
            {
                "key": item.get("key", ""),
                "name": item.get("name", ""),
                "purpose": item.get("purpose", ""),
                "tier": t("tier." + tier),
                "tone": _TIER_TONE.get(tier, "info"),
                "review": t("demo.report.review." + str(classification.get("status", "proposed"))),
            }
        )
    findings = [
        {
            "severity": t("severity." + str(item.get("severity", "info"))),
            "tone": _SEVERITY_TONE.get(str(item.get("severity")), "info"),
            "system": item.get("system", ""),
            "text": item.get("text", ""),
        }
        for item in run.findings
    ]
    models, matrix = _matrix(run.usage)
    labels = {
        "expected": t("demo.as_expected"),
        "differs": t("demo.differs"),
        "play": t("demo.report.steps.play"),
        "pause": t("demo.report.steps.pause"),
        "step": t("demo.report.steps.step"),
    }
    return (
        environment()
        .get_template(_TEMPLATE)
        .render(
            r=run,
            t=t,
            locale=translator.locale,
            passed=sum(1 for step in run.steps if step.ok),
            systems=systems,
            findings=findings,
            models=models,
            matrix=matrix,
            steps_json=_script(
                [{"title": step.title, "detail": step.detail, "ok": step.ok} for step in run.steps]
            ),
            labels_json=_script(labels),
        )
    )
