"""Render a digest as Markdown or HTML, in English or Italian."""

from functools import cache
from importlib import resources
from typing import Literal

from jinja2 import Environment, FunctionLoader, StrictUndefined, select_autoescape

from ai_arbiter.compliance.digest.model import DigestModel
from ai_arbiter.core.i18n import Translator

DigestFormat = Literal["markdown", "html"]
_TEMPLATES = {"markdown": "digest.md.j2", "html": "digest.html.j2"}


def _load(name: str) -> str:
    return resources.files("ai_arbiter").joinpath("templates", name).read_text(encoding="utf-8")


@cache
def _environment() -> Environment:
    return Environment(
        loader=FunctionLoader(_load),
        # HTML output escapes every value: names and purposes are typed by people.
        autoescape=select_autoescape(enabled_extensions=("html.j2",), default=False),
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
    )


def render_digest(
    digest: DigestModel, *, locale: str = "en", output: DigestFormat = "markdown"
) -> str:
    """The digest as text. Raises ``LocalisationError`` for an unsupported locale."""
    translator = Translator(locale)
    template = _environment().get_template(_TEMPLATES[output])
    return template.render(d=digest, t=translator.text, f=translator, locale=locale)
