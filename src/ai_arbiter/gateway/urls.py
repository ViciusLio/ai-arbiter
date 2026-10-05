"""Addresses Arbiter is allowed to send requests to on behalf of a catalogue."""

from collections.abc import Collection
from urllib.parse import urlsplit

from ai_arbiter.core.errors import ConflictError


def host_of(url: str) -> str:
    return (urlsplit(url).hostname or "").lower()


def checked_url(url: str, *, what: str, allow_http_hosts: Collection[str], setting: str) -> str:
    """An address a proxy may forward to, or fetch from. Raises ``ConflictError``.

    It must use https, name a host and hold no credentials. Plain http is accepted only
    for hosts the configuration lists, so that a catalogue entry cannot point a request
    at whatever answers inside the network.
    """
    parts = urlsplit(url)
    host = (parts.hostname or "").lower()
    if not host or parts.username or parts.password:
        raise ConflictError(f"the URL of {what} needs a host and must hold no credentials")
    if parts.fragment:
        raise ConflictError(f"the URL of {what} must have no fragment")
    allowed = {item.lower() for item in allow_http_hosts}
    if parts.scheme == "https" or (parts.scheme == "http" and host in allowed):
        return url
    raise ConflictError(
        f"the URL of {what} must use https; plain http is accepted only for the hosts "
        f"listed in {setting}"
    )
