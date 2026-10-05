"""``arbiter serve``: start the HTTP application.

The web stack is an optional dependency (ADR-0010), so it is imported inside the command
and a missing extra produces an instruction instead of a traceback.
"""

import asyncio
from typing import Annotated, Any

import typer

from ai_arbiter.core.config.settings import Role, load_settings
from ai_arbiter.core.errors import ArbiterError, MissingExtraError


def parse_roles(value: str) -> list[str]:
    """Validate a comma-separated list of roles and return it sorted."""
    names = sorted({item.strip() for item in value.split(",") if item.strip()})
    valid = {role.value for role in Role}
    unknown = [name for name in names if name not in valid]
    if unknown or not names:
        raise typer.BadParameter(f"valid roles are: {', '.join(sorted(valid))}")
    return names


def serve(
    ctx: typer.Context,
    host: Annotated[str | None, typer.Option(help="Address to bind.")] = None,
    port: Annotated[int | None, typer.Option(help="Port to bind.")] = None,
    roles: Annotated[
        str | None,
        typer.Option(help="Comma-separated roles of this process: gateway, admin, worker, mcp."),
    ] = None,
) -> None:
    """Start the HTTP application (needs the 'gateway' extra)."""
    server: dict[str, Any] = {}
    if host is not None:
        server["host"] = host
    if port is not None:
        server["port"] = port
    if roles is not None:
        server["roles"] = parse_roles(roles)

    try:
        settings = load_settings(ctx.obj.config_file, **({"server": server} if server else {}))
        try:
            import uvicorn

            from ai_arbiter.gateway.api.app import create_app
        except ImportError as exc:
            raise MissingExtraError("gateway", "arbiter serve") from exc
        # Unknown plugins, invalid deployments and missing secrets are reported here, as
        # one line, instead of as a traceback while the server starts.
        from ai_arbiter.gateway.runtime import preflight

        asyncio.run(preflight(settings))
    except ArbiterError as error:
        typer.echo(f"Error: {error}", err=True)
        raise typer.Exit(code=1) from error

    uvicorn.run(
        create_app(settings),
        host=settings.server.host,
        port=settings.server.port,
        log_level=settings.logging.level.lower(),
    )
