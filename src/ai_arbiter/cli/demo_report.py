"""The run of a demonstration as one page to show: the story of a day, as a deck (ADR-0060).

The page is self-contained: no script, style or font is loaded from anywhere. Every
figure on it comes from the run it is given.
"""

from typing import Any

from ai_arbiter.cli.demo_consulting import DemoRun, ToolUse
from ai_arbiter.compliance.digest.render import environment
from ai_arbiter.core.i18n import Translator

_TEMPLATE = "demo-report.html.j2"
_TIER_TONE = {"prohibited": "no", "high_risk": "warn", "transparency": "info", "minimal": "ok"}
_SEVERITY_TONE = {"critical": "no", "high": "no", "medium": "warn", "low": "info", "info": "info"}
_VERDICT_TONE = {
    "allowed": "ok",
    "masked": "ok",
    "blocked": "no",
    "both": "warn",
    "review": "warn",
    "noted": "info",
}
# The people of the story, in the order the page introduces them.
_CAST = ("elena", "giulia", "marco", "sara", "luca", "lab", "vendor")


def _initials(name: str) -> str:
    words = [word for word in name.split() if word[:1].isalpha()]
    return "".join(word[0] for word in words[-2:]).upper() or "?"


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
            "level": str(item.get("severity", "info")),
            "severity": t("severity." + str(item.get("severity", "info"))),
            "tone": _SEVERITY_TONE.get(str(item.get("severity")), "info"),
            "system": item.get("system", ""),
            "text": item.get("text", ""),
        }
        for item in run.findings
    ]
    models, matrix = _matrix(run.usage)
    cast = [
        {
            "key": key,
            "name": t(f"demo.story.cast.{key}"),
            "role": t(f"demo.story.cast.{key}.role"),
            "initials": _initials(t(f"demo.story.cast.{key}")),
        }
        for key in _CAST
    ]
    people = {person["key"]: person for person in cast}
    scenes = [
        {
            "step": step,
            "person": people.get(step.who, {"name": "", "role": "", "initials": "?"}),
            "verdict": t("demo.story.verdict." + step.verdict) if step.verdict else "",
            "tone": _VERDICT_TONE.get(step.verdict, "info"),
        }
        for step in run.steps
        if step.is_scene
    ]
    major = [item for item in findings if item["level"] in ("critical", "high", "medium")]
    return (
        environment()
        .get_template(_TEMPLATE)
        .render(
            r=run,
            t=t,
            locale=translator.locale,
            passed=sum(1 for step in run.steps if step.ok),
            systems=systems,
            findings=major,
            minor_findings=len(findings) - len(major),
            models=models,
            matrix=matrix,
            cast=cast,
            scenes=scenes,
        )
    )
