"""Liveness and readiness endpoints."""

from typing import Literal

from fastapi import APIRouter, Request, Response, status
from pydantic import BaseModel
from sqlalchemy.exc import SQLAlchemyError

from ai_arbiter import __version__
from ai_arbiter.core.persistence.database import Database
from ai_arbiter.core.persistence.migrate import current_revision, head_revision

router = APIRouter(tags=["health"])

CheckResult = Literal["ok", "unavailable", "migration_pending"]


class Liveness(BaseModel):
    status: Literal["ok"] = "ok"
    version: str


class Readiness(BaseModel):
    status: Literal["ready", "not_ready"]
    checks: dict[str, CheckResult]


@router.get("/healthz", summary="Liveness", description="The process is running.")
async def healthz() -> Liveness:
    return Liveness(version=__version__)


async def _database_check(database: Database) -> CheckResult:
    try:
        await database.ping()
        current = await current_revision(database)
    except (SQLAlchemyError, OSError):
        # Drivers report a refused or timed-out connection as a plain OSError.
        return "unavailable"
    return "ok" if current == head_revision() else "migration_pending"


@router.get(
    "/readyz",
    summary="Readiness",
    description="The process can serve requests: the database is reachable and its schema "
    "is at the revision this version expects.",
    responses={status.HTTP_503_SERVICE_UNAVAILABLE: {"model": Readiness}},
)
async def readyz(request: Request, response: Response) -> Readiness:
    checks: dict[str, CheckResult] = {"database": await _database_check(request.app.state.database)}
    ready = all(result == "ok" for result in checks.values())
    if not ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return Readiness(status="ready" if ready else "not_ready", checks=checks)
