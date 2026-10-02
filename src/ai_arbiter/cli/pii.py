"""``arbiter pii``: what the active detector recognises, and a way to try it."""

import sys
from pathlib import Path
from typing import Annotated

import typer

from ai_arbiter.cli.common import DISCLAIMER, fail, settings_from
from ai_arbiter.core.config.settings import Settings
from ai_arbiter.core.errors import ArbiterError
from ai_arbiter.core.plugins.registry import PII_DETECTORS, PluginRegistry
from ai_arbiter.core.redaction import (
    GENERAL_LIMITS,
    PIIDetector,
    RedactionStrategy,
    categories,
    redact,
)

app = typer.Typer(help="Inspect and try PII detection.", no_args_is_help=True)


def _detector(settings: Settings) -> PIIDetector:
    try:
        detector: PIIDetector = PluginRegistry().load(
            PII_DETECTORS, settings.plugins.pii_detector
        )()
    except ArbiterError as error:
        raise fail(error) from error
    return detector


@app.command("detectors")
def detectors(ctx: typer.Context) -> None:
    """List what the active detector validates and what it misses."""
    detector = _detector(settings_from(ctx))
    typer.echo(f"Active detector: {detector.name}")
    typer.echo("")
    for info in detector.describe():
        typer.echo(f"{info.category}")
        typer.echo(f"  validates: {info.validates}")
        typer.echo(f"  misses:    {info.misses}")
    typer.echo("")
    typer.echo(f"Limits: {GENERAL_LIMITS}")
    typer.echo("")
    typer.echo(DISCLAIMER)


@app.command("redact")
def redact_text(
    ctx: typer.Context,
    file: Annotated[
        Path | None, typer.Argument(help="File to read. Default: standard input.")
    ] = None,
) -> None:
    """Print a text with detected personal data masked. Nothing is stored or sent."""
    detector = _detector(settings_from(ctx))
    if file is not None and not file.is_file():
        typer.echo(f"Error: file not found: {file}", err=True)
        raise typer.Exit(code=1)
    text = sys.stdin.read() if file is None else file.read_text(encoding="utf-8")
    spans = detector.detect(text)
    typer.echo(redact(text, spans, default=RedactionStrategy.MASK), nl=False)
    found = ", ".join(categories(spans)) or "nothing"
    typer.echo(f"Detected: {found} ({len(spans)} occurrences)", err=True)
