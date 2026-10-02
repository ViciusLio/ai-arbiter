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


def table_cell(value: object) -> str:
    """Text typed by a person, made safe for one cell of a Markdown table."""
    return " ".join(str(value).split()).replace("|", "\\|")


@cache
def environment() -> Environment:
    """The template environment shared by the digest and the reports."""
    env = Environment(
        loader=FunctionLoader(_load),
        # HTML output escapes every value: names and purposes are typed by people.
        autoescape=select_autoescape(enabled_extensions=("html.j2",), default=False),
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
    )
    env.filters["cell"] = table_cell
    return env


def render_digest(
    digest: DigestModel, *, locale: str = "en", output: DigestFormat = "markdown"
) -> str:
    """The digest as text. Raises ``LocalisationError`` for an unsupported locale."""
    translator = Translator(locale)
    template = environment().get_template(_TEMPLATES[output])
    return template.render(d=digest, t=translator.text, f=translator, locale=locale)
