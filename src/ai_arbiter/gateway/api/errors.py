"""One error model for the whole API: RFC 9457 problem details.

The body also carries an ``error`` object in the shape OpenAI clients expect, so that an
application talking to ``/v1`` shows a readable message without knowing about Arbiter.
"""

import logging
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

from ai_arbiter.core.errors import (
    ArbiterError,
    AuthenticationError,
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
)
from ai_arbiter.core.i18n import Translator, negotiate
from ai_arbiter.core.rules import Decision
from ai_arbiter.gateway.chat import AuditUnavailableError, PolicyDeniedError
from ai_arbiter.gateway.llm_router.router import NoRouteError, UpstreamError

logger = logging.getLogger(__name__)

PROBLEM_JSON = "application/problem+json"

# Error class -> (status, code, title)
_KNOWN: dict[type[ArbiterError], tuple[int, str, str]] = {
    AuthenticationError: (status.HTTP_401_UNAUTHORIZED, "invalid_api_key", "Authentication failed"),
    PermissionDeniedError: (status.HTTP_403_FORBIDDEN, "permission_denied", "Permission denied"),
    NotFoundError: (status.HTTP_404_NOT_FOUND, "not_found", "Not found"),
    ConflictError: (status.HTTP_409_CONFLICT, "conflict", "Conflict"),
    NoRouteError: (status.HTTP_404_NOT_FOUND, "model_not_found", "Model not found"),
    UpstreamError: (status.HTTP_502_BAD_GATEWAY, "upstream_error", "Model provider failed"),
    AuditUnavailableError: (
        status.HTTP_503_SERVICE_UNAVAILABLE,
        "audit_unavailable",
        "Audit log unavailable",
    ),
}


def problem(
    status_code: int,
    code: str,
    title: str,
    detail: str,
    *,
    headers: dict[str, str] | None = None,
    **extensions: Any,
) -> JSONResponse:
    return JSONResponse(
        {
            "type": "about:blank",
            "title": title,
            "status": status_code,
            "detail": detail,
            "code": code,
            **extensions,
            "error": {"message": detail, "type": code, "code": code},
        },
        status_code=status_code,
        media_type=PROBLEM_JSON,
        headers=headers,
    )


def reasons(decision: Decision, locale: str) -> list[dict[str, Any]]:
    """Why a decision came out as it did: the matching rules, in the caller's language."""
    translator = Translator(locale)
    return [
        {
            "rule_id": match.rule_id,
            "pack": match.pack,
            "pack_version": match.pack_version,
            "outcome": match.outcome,
            "message": (
                translator.text(match.message_key)
                if translator.has(match.message_key)
                else match.message_key
            ),
            "legal_refs": [
                {"regulation": ref.regulation, "article": ref.article} for ref in match.legal_refs
            ],
        }
        for match in decision.matches
    ]


async def _policy_denied(request: Request, error: Exception) -> JSONResponse:
    assert isinstance(error, PolicyDeniedError)  # noqa: S101 - registered for this class
    locale = negotiate(request.headers.get("accept-language"))
    explained = reasons(error.decision, locale)
    return problem(
        status.HTTP_403_FORBIDDEN,
        "policy_denied",
        "Denied by policy",
        "; ".join(reason["message"] for reason in explained) or str(error),
        headers={
            "X-Arbiter-Interaction-Id": str(error.interaction_id),
            "X-Arbiter-Decision-Id": str(error.decision.id),
        },
        decision_id=str(error.decision.id),
        interaction_id=str(error.interaction_id),
        reasons=explained,
    )


async def _arbiter_error(request: Request, error: Exception) -> JSONResponse:
    for kind, (status_code, code, title) in _KNOWN.items():
        if isinstance(error, kind):
            extensions: dict[str, Any] = {}
            if isinstance(error, UpstreamError):
                extensions["decision_id"] = str(error.decision.id)
            headers = (
                {"WWW-Authenticate": "Bearer"} if isinstance(error, AuthenticationError) else None
            )
            return problem(status_code, code, title, str(error), headers=headers, **extensions)
    logger.error("unhandled Arbiter error", extra={"error": type(error).__name__})
    return problem(
        status.HTTP_500_INTERNAL_SERVER_ERROR,
        "internal_error",
        "Internal error",
        "the request could not be handled",
    )


async def _validation_error(request: Request, error: Exception) -> JSONResponse:
    assert isinstance(error, RequestValidationError)  # noqa: S101 - registered for this class
    # Field paths and messages only: the rejected input may be a prompt.
    invalid = [
        {"field": ".".join(str(part) for part in item["loc"]), "message": item["msg"]}
        for item in error.errors()
    ]
    detail = "; ".join(f"{item['field']}: {item['message']}" for item in invalid)
    return problem(
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        "invalid_request",
        "Invalid request",
        detail,
        invalid=invalid,
    )


async def _http_error(request: Request, error: Exception) -> JSONResponse:
    assert isinstance(error, HTTPException)  # noqa: S101 - registered for this class
    return problem(error.status_code, "http_error", str(error.detail), str(error.detail))


async def _unexpected(request: Request, error: Exception) -> JSONResponse:
    # The class name only: the message of an unexpected error may quote request content.
    logger.error("unexpected error", extra={"error": type(error).__name__})
    return problem(
        status.HTTP_500_INTERNAL_SERVER_ERROR,
        "internal_error",
        "Internal error",
        "the request could not be handled",
    )


def install(app: FastAPI) -> None:
    app.add_exception_handler(PolicyDeniedError, _policy_denied)
    app.add_exception_handler(ArbiterError, _arbiter_error)
    app.add_exception_handler(RequestValidationError, _validation_error)
    app.add_exception_handler(HTTPException, _http_error)
    app.add_exception_handler(Exception, _unexpected)
