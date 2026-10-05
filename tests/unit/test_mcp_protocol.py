"""What the MCP proxy checks of a request against its headers (revision 2026-07-28)."""

import json
from typing import Any

import pytest

pytest.importorskip("mcp_types", reason="needs the mcp extra")

from ai_arbiter.gateway.mcp.protocol import (
    McpRequest,
    ProtocolError,
    decode_header_value,
    error_body,
    forwarded_headers,
    parse_request,
    read_response,
)
from tests.mcp_requests import META_VERSION, REVISION, mcp_request

HEADER_MISMATCH = -32020
UNSUPPORTED_VERSION = -32022


def test_a_conforming_tool_call_is_read_with_its_tool() -> None:
    body, headers = mcp_request("tools/call", name="read", arguments={"path": "notes/x.txt"})

    parsed = parse_request(body, headers)

    assert parsed == McpRequest(request_id=1, method="tools/call", name="read")
    assert (parsed.tool, parsed.recorded_name) == ("read", "read")


def test_the_address_of_a_resource_is_checked_and_not_kept() -> None:
    body, headers = mcp_request("resources/read", name="file:///home/ada/notes.txt")

    parsed = parse_request(body, headers)

    assert parsed.name == "file:///home/ada/notes.txt"
    assert (parsed.tool, parsed.recorded_name) == (None, None)


def test_a_name_that_ascii_cannot_carry_is_compared_after_decoding() -> None:
    body, headers = mcp_request("tools/call", name="ricerca-città")

    assert headers["mcp-name"].startswith("=?base64?")
    assert parse_request(body, headers).name == "ricerca-città"
    assert decode_header_value("plain") == "plain"
    with pytest.raises(ValueError, match="Base64"):
        decode_header_value("=?base64?***?=")


def changed(method: str = "tools/call", **edits: Any) -> tuple[bytes, dict[str, str]]:
    body, headers = mcp_request(method, name="read" if method == "tools/call" else None)
    payload = json.loads(body)
    for key, value in edits.items():
        if key.startswith("header_"):
            name = key.removeprefix("header_").replace("_", "-")
            if value is None:
                headers.pop(name, None)
            else:
                headers[name] = value
        elif key == "meta_version":
            payload["params"]["_meta"][META_VERSION] = value
        elif key == "params_name":
            payload["params"]["name"] = value
        elif value is None:
            payload.pop(key, None)
        else:
            payload[key] = value
    return json.dumps(payload).encode(), headers


@pytest.mark.parametrize(
    ("edits", "code", "message"),
    [
        ({"header_mcp_protocol_version": None}, HEADER_MISMATCH, "MCP-Protocol-Version header is"),
        ({"meta_version": "2025-11-25"}, HEADER_MISMATCH, "does not match the protocol version"),
        ({"header_mcp_method": "tools/list"}, HEADER_MISMATCH, "Mcp-Method header does not"),
        ({"header_mcp_method": None}, HEADER_MISMATCH, "Mcp-Method header does not"),
        ({"header_mcp_name": None}, HEADER_MISMATCH, "Mcp-Name header is missing"),
        ({"header_mcp_name": "write"}, HEADER_MISMATCH, "Mcp-Name header does not match"),
        ({"header_mcp_name": "=?base64?***?="}, HEADER_MISMATCH, "Mcp-Name header is not valid"),
        ({"params_name": ""}, -32602, "tools/call needs params.name"),
        ({"jsonrpc": "1.0"}, -32600, "not a JSON-RPC 2.0 request"),
        ({"method": None}, -32600, "not a JSON-RPC 2.0 request"),
        ({"result": {}}, -32600, "requests, not responses"),
        ({"id": None}, -32600, "notifications are not forwarded"),
        ({"params": []}, -32600, "params must be an object"),
    ],
)
def test_a_request_whose_headers_and_body_disagree_is_rejected(
    edits: dict[str, Any], code: int, message: str
) -> None:
    body, headers = changed(**edits)

    with pytest.raises(ProtocolError, match=message) as raised:
        parse_request(body, headers)

    assert (raised.value.status, raised.value.code) == (400, code)


def test_an_earlier_revision_is_answered_with_the_ones_the_proxy_speaks() -> None:
    body, headers = mcp_request("tools/list", version="2025-11-25")

    with pytest.raises(ProtocolError) as raised:
        parse_request(body, headers)

    error = raised.value
    assert (error.status, error.code, error.request_id) == (400, UNSUPPORTED_VERSION, 1)
    assert error.data == {"supported": [REVISION], "requested": "2025-11-25"}


def test_a_body_that_is_not_one_json_object_is_rejected() -> None:
    _, headers = mcp_request("tools/list")

    with pytest.raises(ProtocolError, match="not valid JSON") as broken:
        parse_request(b"{", headers)
    with pytest.raises(ProtocolError, match="not a batch") as batch:
        parse_request(b"[]", headers)

    assert (broken.value.code, batch.value.code) == (-32700, -32600)


def test_only_what_an_mcp_server_needs_is_forwarded() -> None:
    _, headers = mcp_request(
        "tools/call",
        name="read",
        headers={
            "authorization": "Bearer the-callers-own-key",
            "cookie": "session=1",
            "mcp-param-region": "eu-west",
            "mcp-session-id": "old",
        },
    )

    kept = forwarded_headers(headers)

    assert kept == {
        "content-type": "application/json",
        "accept": "application/json, text/event-stream",
        "mcp-protocol-version": REVISION,
        "mcp-method": "tools/call",
        "mcp-name": "read",
        "mcp-param-region": "eu-west",
    }


def test_an_error_body_has_an_id_only_when_one_was_read() -> None:
    assert error_body(-32600, "no") == {
        "jsonrpc": "2.0",
        "error": {"code": -32600, "message": "no"},
    }
    assert error_body(-32010, "no", request_id="a", data={"rules": ["X"]}) == {
        "jsonrpc": "2.0",
        "id": "a",
        "error": {"code": -32010, "message": "no", "data": {"rules": ["X"]}},
    }


def test_a_response_is_read_from_json_or_from_an_event_stream() -> None:
    answer = {"jsonrpc": "2.0", "id": 1, "result": {"ok": True}}
    stream = (
        ': keep-alive\n\ndata: {"jsonrpc":"2.0","method":"notifications/progress"}\n\n'
        f"data: {json.dumps(answer)}\n\n"
    )

    assert read_response("application/json", json.dumps(answer).encode()) == answer
    assert read_response("text/event-stream; charset=utf-8", stream.encode()) == answer
    assert read_response("application/json", b"Bad Request") is None
    assert read_response("text/event-stream", b"data: nonsense\n\n") is None
