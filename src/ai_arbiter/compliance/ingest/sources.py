"""Source adapters: one external format each, mapped to the canonical record."""

from collections.abc import Mapping
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from pydantic import ValidationError

from ai_arbiter.core.interaction import InteractionRecord, InteractionStatus
from ai_arbiter.core.redaction import PIIDetector, categories

SYSTEM_TAG = "arbiter:system="


class JsonlSource:
    """Arbiter's own canonical format: one ``InteractionRecord`` per line."""

    name = "jsonl"
    tested_against = "the InteractionRecord schema of this version"

    def __init__(self, detector: PIIDetector | None = None) -> None:
        self._detector = detector

    def parse(self, payload: Mapping[str, Any]) -> InteractionRecord:
        try:
            return InteractionRecord.model_validate(dict(payload))
        except ValidationError as exc:
            fields = sorted({".".join(str(p) for p in error["loc"]) for error in exc.errors()})
            raise ValueError(f"invalid fields: {', '.join(fields)}") from exc


def _timestamp(value: Any) -> datetime | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return datetime.fromtimestamp(value, UTC)
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError:
            return None
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    return None


def _count(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None


def _text(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def _texts(messages: Any) -> list[str]:
    """Every piece of text in a ``messages`` field, whatever its shape."""
    if isinstance(messages, str):
        return [messages]
    if isinstance(messages, Mapping):
        return _texts(messages.get("content"))
    if isinstance(messages, list):
        return [text for item in messages for text in _texts(item)]
    return []


class LiteLLMSource:
    """LiteLLM's standard logging payload, one JSON object per record.

    The mapping keeps metadata and drops content: ``messages`` and ``response`` are read
    only to list the categories of personal data the detector finds in the request, and
    are not kept. The end user, the requester's address and the key hash are not carried
    over. The cost is LiteLLM's own figure, in US dollars.
    """

    name = "litellm"
    tested_against = (
        "the StandardLoggingPayload specification at docs.litellm.ai/docs/proxy/logging_spec "
        "as read on 2026-10-02 (it states no version); samples built from that "
        "specification, not captured from a running LiteLLM"
    )

    def __init__(self, detector: PIIDetector | None = None) -> None:
        self._detector = detector

    def parse(self, payload: Mapping[str, Any]) -> InteractionRecord:
        record_id = _text(payload.get("id"))
        started = _timestamp(payload.get("startTime"))
        if record_id is None or started is None:
            raise ValueError("a LiteLLM record needs 'id' and 'startTime'")
        ended = _timestamp(payload.get("endTime"))
        succeeded = payload.get("status") == "success"
        metadata = payload.get("metadata") if isinstance(payload.get("metadata"), Mapping) else {}
        assert isinstance(metadata, Mapping)  # noqa: S101 - narrowed on the line above

        cost: str | None = None
        raw_cost = payload.get("response_cost")
        if succeeded and isinstance(raw_cost, int | float) and not isinstance(raw_cost, bool):
            try:
                amount = Decimal(str(raw_cost))
            except InvalidOperation:
                amount = Decimal(-1)
            if amount.is_finite() and amount >= 0:
                cost = format(amount, "f")

        usage = metadata.get("usage_object")
        details = usage.get("prompt_tokens_details") if isinstance(usage, Mapping) else None
        parameters = payload.get("model_parameters")
        model_map = payload.get("model_map_information")
        map_value = model_map.get("model_map_value") if isinstance(model_map, Mapping) else None
        provider = _text(payload.get("custom_llm_provider")) or (
            _text(map_value.get("litellm_provider")) if isinstance(map_value, Mapping) else None
        )
        call_type = _text(payload.get("call_type")) or "chat"
        tags = payload.get("request_tags") if isinstance(payload.get("request_tags"), list) else []
        assert isinstance(tags, list)  # noqa: S101 - narrowed on the line above
        system = next(
            (
                tag.removeprefix(SYSTEM_TAG)
                for tag in tags
                if isinstance(tag, str) and tag.startswith(SYSTEM_TAG)
            ),
            None,
        )
        labels = {
            name: value
            for name, value in (
                ("key_alias", _text(metadata.get("user_api_key_alias"))),
                ("team_alias", _text(metadata.get("user_api_key_team_alias"))),
            )
            if value is not None
        }
        found = (
            categories(
                [
                    span
                    for text in _texts(payload.get("messages"))
                    for span in self._detector.detect(text)
                ]
            )
            if self._detector is not None
            else []
        )
        try:
            return InteractionRecord(
                source=self.name,
                source_record_id=record_id[:100],
                started_at=started,
                duration_ms=(
                    max(0, int((ended - started).total_seconds() * 1000)) if ended else None
                ),
                operation="chat" if call_type in ("completion", "acompletion") else call_type[:30],
                requested_model=_text(payload.get("model_group")) or _text(payload.get("model")),
                provider=provider,
                model=_text(payload.get("model")),
                status=InteractionStatus.OK if succeeded else InteractionStatus.ERROR,
                streamed=isinstance(parameters, Mapping) and parameters.get("stream") is True,
                input_tokens=_count(payload.get("prompt_tokens")) if succeeded else None,
                output_tokens=_count(payload.get("completion_tokens")) if succeeded else None,
                cached_input_tokens=(
                    _count(details.get("cached_tokens")) if isinstance(details, Mapping) else None
                ),
                cost_estimate=cost,
                currency="USD" if cost is not None else None,
                pii_categories=found,
                system=system,
                # The team, not the key: a key alias can be the name of a person.
                group=(labels.get("team_alias") or "")[:200] or None,
                labels=labels,
            )
        except ValidationError as exc:
            fields = sorted({".".join(str(p) for p in error["loc"]) for error in exc.errors()})
            raise ValueError(f"invalid fields: {', '.join(fields)}") from exc
