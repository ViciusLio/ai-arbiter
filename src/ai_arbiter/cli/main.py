"""Root of the ``arbiter`` command."""

import asyncio
import os
import secrets
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated

import typer
import yaml

from ai_arbiter import __version__
from ai_arbiter.adapters.local.secrets import DEFAULT_DOTENV, EnvSecretStore, read_dotenv_secrets
from ai_arbiter.cli import serve as serve_command
from ai_arbiter.core.config.secrets import SecretRef
from ai_arbiter.core.config.settings import (
    DEFAULT_CONFIG_FILE,
    DEFAULT_DATABASE_URL,
    Settings,
    load_settings,
)
from ai_arbiter.core.domain.tenancy import LOCAL_TENANT_SLUG
from ai_arbiter.core.errors import ArbiterError
from ai_arbiter.core.persistence import migrate
from ai_arbiter.core.persistence.database import Database
from ai_arbiter.core.persistence.tenant import ensure_tenant
from ai_arbiter.core.plugins.registry import EVENT_BUSES, GROUPS, SECRET_STORES, PluginRegistry

DISCLAIMER = "Arbiter is a support tool. It does not provide legal advice."

STARTER_CONFIG = f"""\
# Arbiter configuration.
#
# Every key can be overridden by an environment variable: prefix ARBITER_, nested keys
# joined by a double underscore (for example ARBITER_DATABASE__URL).
# Never put secrets here: reference them as secret://NAME and provide the value through
# the active secret store (by default the environment variable ARBITER_SECRET_NAME).

environment: local

database:
  # SQLite keeps everything in a local file. Use PostgreSQL for the gateway:
  #   postgresql+asyncpg://user@host:5432/arbiter
  url: {DEFAULT_DATABASE_URL}

plugins:
  secret_store: env
  event_bus: in_process

identity:
  # The pepper keys the hash of API keys. `arbiter init` generated one in .env.
  api_key_pepper:
    active: "1"
    secrets:
      "1": secret://api-key-pepper

telemetry:
  enabled: false
"""

app = typer.Typer(
    name="arbiter",
    help=f"AI governance gateway and EU AI Act compliance toolkit.\n\n{DISCLAIMER}",
    no_args_is_help=True,
    add_completion=False,
)
db_app = typer.Typer(help="Manage the database schema.", no_args_is_help=True)
config_app = typer.Typer(help="Inspect the configuration.", no_args_is_help=True)
plugins_app = typer.Typer(help="Inspect plugins.", no_args_is_help=True)
app.add_typer(db_app, name="db")
app.add_typer(config_app, name="config")
app.add_typer(plugins_app, name="plugins")
app.command(name="serve")(serve_command.serve)


@dataclass
class CliState:
    config_file: Path | None = None


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"arbiter {__version__}")
        raise typer.Exit


@app.callback()
def main(
    ctx: typer.Context,
    config: Annotated[
        Path | None,
        typer.Option(
            "--config",
            "-c",
            help=f"Configuration file. Default: ./{DEFAULT_CONFIG_FILE} if present.",
        ),
    ] = None,
    version: Annotated[
        bool,
        typer.Option(
            "--version",
            callback=_version_callback,
            is_eager=True,
            help="Show the version and exit.",
        ),
    ] = False,
) -> None:
    ctx.obj = CliState(config_file=config)


def fail(error: ArbiterError) -> typer.Exit:
    typer.echo(f"Error: {error}", err=True)
    return typer.Exit(code=1)


def settings_from(ctx: typer.Context) -> Settings:
    state: CliState = ctx.obj
    try:
        return load_settings(state.config_file)
    except ArbiterError as error:
        raise fail(error) from error


async def _create_local_tenant(settings: Settings) -> None:
    database = Database(settings.database.url)
    try:
        async with database.transaction() as session:
            await ensure_tenant(session, slug=LOCAL_TENANT_SLUG, name="Local workspace")
    finally:
        await database.dispose()


def ensure_local_secrets(settings: Settings) -> list[str]:
    """Generate the secrets a local workspace needs and that are not set anywhere.

    Values go to ``.env`` in the working directory, readable by the owner only. Returns
    the names of the variables that were written.
    """
    references = [settings.identity.api_key_pepper.secrets[settings.identity.api_key_pepper.active]]
    present = read_dotenv_secrets(DEFAULT_DOTENV)
    written: list[str] = []
    for reference in references:
        variable = EnvSecretStore.variable_name(SecretRef.parse(reference))
        if os.environ.get(variable) or present.get(variable):
            continue
        descriptor = os.open(DEFAULT_DOTENV, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        with os.fdopen(descriptor, "a", encoding="utf-8") as file:
            file.write(f"{variable}={secrets.token_urlsafe(48)}\n")
        written.append(variable)
    return written


@app.command()
def init(
    ctx: typer.Context,
    force: Annotated[
        bool, typer.Option("--force", help="Overwrite an existing configuration file.")
    ] = False,
) -> None:
    """Create a local workspace in the current directory: configuration and database."""
    state: CliState = ctx.obj
    config_path = state.config_file or DEFAULT_CONFIG_FILE
    if config_path.exists() and not force:
        typer.echo(f"Keeping existing configuration: {config_path}")
    else:
        config_path.write_text(STARTER_CONFIG, encoding="utf-8")
        typer.echo(f"Wrote configuration: {config_path}")

    try:
        settings = load_settings(config_path)
        migrate.upgrade(settings.database.url)
        asyncio.run(_create_local_tenant(settings))
        generated = ensure_local_secrets(settings)
    except ArbiterError as error:
        raise fail(error) from error
    typer.echo(f"Database ready: {settings.redacted()['database']['url']}")
    for variable in generated:
        typer.echo(f"Generated {variable} in {DEFAULT_DOTENV} (keep this file out of git)")
    typer.echo("")
    typer.echo(DISCLAIMER)


@db_app.command("upgrade")
def db_upgrade(ctx: typer.Context) -> None:
    """Apply all pending schema migrations."""
    settings = settings_from(ctx)
    try:
        migrate.upgrade(settings.database.url)
    except ArbiterError as error:
        raise fail(error) from error
    typer.echo(f"Schema is at revision {migrate.head_revision()}")


async def _current_revision(settings: Settings) -> str | None:
    database = Database(settings.database.url)
    try:
        return await migrate.current_revision(database)
    finally:
        await database.dispose()


@db_app.command("current")
def db_current(ctx: typer.Context) -> None:
    """Show the schema revision of the database and the one this version expects."""
    settings = settings_from(ctx)
    try:
        current = asyncio.run(_current_revision(settings))
    except ArbiterError as error:
        raise fail(error) from error
    head = migrate.head_revision()
    typer.echo(f"database: {current or 'not migrated'}")
    typer.echo(f"expected: {head}")
    if current != head:
        raise typer.Exit(code=1)


@config_app.command("show")
def config_show(ctx: typer.Context) -> None:
    """Print the effective configuration, with credentials masked."""
    settings = settings_from(ctx)
    typer.echo(yaml.safe_dump(settings.redacted(), sort_keys=False).rstrip())


@plugins_app.command("list")
def plugins_list(ctx: typer.Context) -> None:
    """List installed plugins per port and mark the active ones."""
    settings = settings_from(ctx)
    active = {
        SECRET_STORES: {settings.plugins.secret_store},
        EVENT_BUSES: {settings.plugins.event_bus},
    }
    registry = PluginRegistry()
    for group in GROUPS:
        typer.echo(f"{group}:")
        names = registry.available(group)
        for name in names:
            marker = "active" if name in active.get(group, set()) else "installed"
            typer.echo(f"  {name:<20} {marker}")
        for missing in sorted(active.get(group, set()) - set(names)):
            typer.echo(f"  {missing:<20} configured but NOT installed")
