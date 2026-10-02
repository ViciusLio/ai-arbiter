"""Dependencies shared by the routers: the runtime, the caller, the caller's roles."""

from collections.abc import Awaitable, Callable
from typing import Annotated

from fastapi import Depends, Request

from ai_arbiter.core.domain.tenancy import AccessRole
from ai_arbiter.core.errors import AuthenticationError, PermissionDeniedError
from ai_arbiter.gateway.identity.service import AuthenticatedKey
from ai_arbiter.gateway.runtime import GatewayRuntime


def get_runtime(request: Request) -> GatewayRuntime:
    runtime: GatewayRuntime = request.app.state.runtime
    return runtime


Runtime = Annotated[GatewayRuntime, Depends(get_runtime)]


async def authenticated(request: Request, runtime: Runtime) -> AuthenticatedKey:
    """Identify the caller from ``Authorization: Bearer <API key>``."""
    scheme, _, token = request.headers.get("authorization", "").partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise AuthenticationError("missing API key: send it as 'Authorization: Bearer <key>'")
    async with runtime.database.session() as session:
        return await runtime.identity.authenticate(session, token.strip())


def require(*roles: AccessRole) -> Callable[..., Awaitable[AuthenticatedKey]]:
    """A dependency that lets the caller through only with one of ``roles``."""

    async def check(
        key: Annotated[AuthenticatedKey, Depends(authenticated)],
    ) -> AuthenticatedKey:
        if not key.context.roles & set(roles):
            needed = " or ".join(sorted(role.value for role in roles))
            raise PermissionDeniedError(f"this operation needs the role {needed}")
        return key

    return check


Caller = Annotated[AuthenticatedKey, Depends(require(AccessRole.DEVELOPER, AccessRole.ADMIN))]
Admin = Annotated[AuthenticatedKey, Depends(require(AccessRole.ADMIN))]
Reader = Annotated[AuthenticatedKey, Depends(require(AccessRole.ADMIN, AccessRole.AUDITOR))]
AnyKey = Annotated[AuthenticatedKey, Depends(authenticated)]
