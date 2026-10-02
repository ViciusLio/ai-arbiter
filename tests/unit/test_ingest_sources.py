import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from ai_arbiter.compliance.ingest.sources import JsonlSource, LiteLLMSource
from ai_arbiter.core.interaction import InteractionRecord, InteractionStatus
from ai_arbiter.core.plugins import TELEMETRY_SOURCES, PluginRegistry
from ai_arbiter.core.ports import TelemetrySource
from ai_arbiter.core.redaction import BuiltinDetector

EXAMPLES = Path(__file__).parents[2] / "examples"
LITELLM = [json.loads(line) for line in (EXAMPLES / "litellm-logs.jsonl").read_text().splitlines()]


def litellm(**changes: Any) -> dict[str, Any]:
    return {**LITELLM[0], **changes}


def test_the_sources_are_plugins_and_satisfy_the_port() -> None:
    registry = PluginRegistry()
    sources: list[TelemetrySource] = [
        registry.load(TELEMETRY_SOURCES, name)(BuiltinDetector()) for name in ("jsonl", "litellm")
    ]

    assert registry.available(TELEMETRY_SOURCES) == ["jsonl", "litellm"]
    assert [source.name for source in sources] == ["jsonl", "litellm"]
    assert "not captured from a running LiteLLM" in sources[1].tested_against


def test_a_litellm_record_becomes_metadata_only() -> None:
    record = LiteLLMSource(BuiltinDetector()).parse(LITELLM[0])

    assert record.source == "litellm"
    assert record.source_record_id == "chatcmpl-sample-001"
    assert record.started_at == datetime.fromtimestamp(1790000060.0, UTC)
    assert record.duration_ms == 1500
    assert (record.operation, record.status) == ("chat", InteractionStatus.OK)
    assert (record.requested_model, record.model, record.provider) == ("gpt-4o", "gpt-4o", "azure")
    assert (record.input_tokens, record.output_tokens) == (120, 30)
    assert (record.cost_estimate, record.currency) == ("0.00042", "USD")
    assert record.pii_categories == ["email"]
    assert record.labels == {"key_alias": "hr-suite", "team_alias": "people-ops"}
    assert record.system is None


def test_content_and_personal_identifiers_do_not_survive_the_mapping() -> None:
    record = LiteLLMSource(BuiltinDetector()).parse(LITELLM[0])
    kept = record.model_dump_json()

    for dropped in (
        "candidate@example.com",
        "Rank this application",
        "Synthetic answer",
        "end-user-not-kept",
        "203.0.113.7",
        "hash-not-kept",
        "example.invalid",
    ):
        assert dropped not in kept
    assert not {"messages", "response", "end_user"} & set(InteractionRecord.model_fields)


def test_a_tag_of_the_source_names_the_system() -> None:
    assert LiteLLMSource().parse(LITELLM[1]).system == "invoice-data-extraction"


def test_a_failed_call_has_no_tokens_and_no_cost_and_its_error_text_is_dropped() -> None:
    record = LiteLLMSource().parse(LITELLM[2])

    assert record.status is InteractionStatus.ERROR
    assert (record.input_tokens, record.output_tokens, record.cost_estimate, record.currency) == (
        None,
        None,
        None,
        None,
    )
    assert "synthetic error text" not in record.model_dump_json()


def test_without_a_detector_no_categories_are_reported() -> None:
    assert LiteLLMSource().parse(LITELLM[0]).pii_categories == []


@pytest.mark.parametrize(
    ("changes", "expected"),
    [
        ({"call_type": "aembedding"}, ("operation", "aembedding")),
        ({"model_parameters": {"stream": True}}, ("streamed", True)),
        ({"endTime": None}, ("duration_ms", None)),
        (
            {"startTime": "2026-10-01T09:00:00"},
            ("started_at", datetime(2026, 10, 1, 9, tzinfo=UTC)),
        ),
        ({"response_cost": None}, ("cost_estimate", None)),
        ({"model_group": None, "model": "m"}, ("requested_model", "m")),
        ({"custom_llm_provider": None}, ("provider", None)),
        (
            {
                "custom_llm_provider": None,
                "model_map_information": {"model_map_value": {"litellm_provider": "openai"}},
            },
            ("provider", "openai"),
        ),
        (
            {"metadata": {"usage_object": {"prompt_tokens_details": {"cached_tokens": 40}}}},
            ("cached_input_tokens", 40),
        ),
        ({"messages": "a plain string with a@b.io"}, ("pii_categories", ["email"])),
        ({"messages": None, "metadata": "not a mapping", "request_tags": "x"}, ("labels", {})),
    ],
)
def test_optional_and_odd_fields_are_tolerated(
    changes: dict[str, Any], expected: tuple[str, Any]
) -> None:
    record = LiteLLMSource(BuiltinDetector()).parse(litellm(**changes))

    assert getattr(record, expected[0]) == expected[1]


@pytest.mark.parametrize(
    "changes", [{"id": None}, {"startTime": None}, {"startTime": "yesterday"}, {"startTime": True}]
)
def test_a_litellm_record_without_id_or_start_is_refused(changes: dict[str, Any]) -> None:
    with pytest.raises(ValueError, match="needs 'id' and 'startTime'"):
        LiteLLMSource().parse(litellm(**changes))


def test_the_canonical_format_is_the_record_itself() -> None:
    lines = (EXAMPLES / "interactions.jsonl").read_text().splitlines()

    first, second = (JsonlSource().parse(json.loads(line)) for line in lines)

    assert (first.source, first.system, first.cost_estimate) == (
        "other-gateway",
        "cv-screening",
        "0.00155",
    )
    assert (second.pii_categories, second.labels) == (["email"], {"application": "careers-site"})


@pytest.mark.parametrize(
    ("changes", "field"),
    [
        ({"source": "native"}, "source"),
        ({"started_at": "2026-10-01T09:00:00"}, "started_at"),
        ({"cost_estimate": "abc"}, "cost_estimate"),
        ({"cost_estimate": "-1"}, "cost_estimate"),
        ({"currency": "usd"}, "currency"),
        ({"input_tokens": -1}, "input_tokens"),
        ({"messages": [{"role": "user", "content": "SECRET PROMPT"}]}, "messages"),
        ({"source_record_id": ""}, "source_record_id"),
    ],
)
def test_the_canonical_format_refuses_what_it_does_not_define(
    changes: dict[str, Any], field: str
) -> None:
    base = {"source": "other", "source_record_id": "1", "started_at": "2026-10-01T09:00:00Z"}

    with pytest.raises(ValueError, match=field) as raised:
        JsonlSource().parse({**base, **changes})

    assert "SECRET PROMPT" not in str(raised.value)
