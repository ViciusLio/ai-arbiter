"""Usage report in Markdown, in English and Italian."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from ai_arbiter.core.config.settings import ReportingCurrencySettings, parse_decimal
from ai_arbiter.core.i18n import Translator
from ai_arbiter.gateway.finops.catalogue import PriceCatalogue
from ai_arbiter.gateway.finops.metering import UsageLine, UsageTotals


@dataclass(frozen=True)
class UsageReport:
    tenant_name: str
    scope_type: str
    start: date
    end: date
    generated_at: datetime
    lines: Sequence[UsageLine]
    # Display names of the scopes, where known. Others are shown by identifier.
    names: Mapping[UUID, str]


def _sum(lines: Sequence[UsageLine]) -> UsageTotals:
    return UsageTotals(
        requests=sum(line.totals.requests for line in lines),
        denied=sum(line.totals.denied for line in lines),
        failed=sum(line.totals.failed for line in lines),
        unpriced=sum(line.totals.unpriced for line in lines),
        estimated=sum(line.totals.estimated for line in lines),
        input_tokens=sum(line.totals.input_tokens for line in lines),
        output_tokens=sum(line.totals.output_tokens for line in lines),
        cost_estimate=sum((line.totals.cost_estimate for line in lines), Decimal(0)),
        estimated_cost=sum((line.totals.estimated_cost for line in lines), Decimal(0)),
    )


def render_usage_report(
    report: UsageReport,
    catalogue: PriceCatalogue,
    *,
    locale: str = "en",
    reporting: ReportingCurrencySettings | None = None,
) -> str:
    t = Translator(locale)
    rate = parse_decimal(reporting.rate, positive=True) if reporting is not None else None
    currencies = sorted({line.currency for line in report.lines}) or [catalogue.currency]

    out = [
        f"# {t.text('usage.title')}",
        "",
        f"- **{t.text('usage.tenant')}**: {report.tenant_name}",
        f"- **{t.text('usage.period')}**: "
        + t.text("usage.period_value", start=t.date(report.start), end=t.date(report.end)),
        f"- **{t.text('usage.grouped_by')}**: {t.text('usage.scope.' + report.scope_type)}",
        f"- **{t.text('usage.catalogue')}**: "
        + t.text(
            "usage.catalogue_value",
            version=catalogue.version,
            currency=catalogue.currency,
            as_of=t.date(catalogue.as_of),
        ),
        f"- **{t.text('usage.generated')}**: {t.timestamp(report.generated_at)}",
        "",
        f"> {t.text('usage.estimate_note')}",
        "",
    ]
    if not report.lines:
        out += [t.text("usage.empty"), ""]

    for currency in currencies if report.lines else []:
        lines = [line for line in report.lines if line.currency == currency]
        convert = rate is not None and reporting is not None and currency == catalogue.currency
        header = [
            t.text("usage.column.scope"),
            t.text("usage.column.requests"),
            t.text("usage.column.denied"),
            t.text("usage.column.failed"),
            t.text("usage.column.input_tokens"),
            t.text("usage.column.output_tokens"),
            t.text("usage.column.cost", currency=currency),
        ]
        if convert and reporting is not None:
            header.append(t.text("usage.column.cost", currency=reporting.currency))
        header += [t.text("usage.column.unpriced"), t.text("usage.column.estimated")]

        def row(label: str, totals: UsageTotals, convert: bool = convert) -> str:
            cells = [
                label,
                t.integer(totals.requests),
                t.integer(totals.denied),
                t.integer(totals.failed),
                t.integer(totals.input_tokens),
                t.integer(totals.output_tokens),
                t.amount(totals.cost_estimate),
            ]
            if convert and rate is not None:
                cells.append(t.amount(totals.cost_estimate * rate))
            cells += [t.integer(totals.unpriced), t.integer(totals.estimated)]
            return "| " + " | ".join(cells) + " |"

        out.append("| " + " | ".join(header) + " |")
        out.append("|---|" + "---:|" * (len(header) - 1))
        for line in sorted(
            lines, key=lambda item: report.names.get(item.scope_id, str(item.scope_id))
        ):
            out.append(row(report.names.get(line.scope_id, str(line.scope_id)), line.totals))
        total = _sum(lines)
        out.append(row(f"**{t.text('usage.total')}**", total))
        out += ["", f"## {t.text('usage.notes')}", ""]
        if total.unpriced:
            out.append("- " + t.text("usage.note.unpriced", count=t.integer(total.unpriced)))
        if total.estimated:
            out.append(
                "- "
                + t.text(
                    "usage.note.estimated",
                    count=t.integer(total.estimated),
                    amount=t.amount(total.estimated_cost),
                    currency=currency,
                )
            )
        else:
            out.append("- " + t.text("usage.note.all_measured"))
        if convert and reporting is not None and rate is not None:
            out.append(
                "- "
                + t.text(
                    "usage.note.conversion",
                    currency=reporting.currency,
                    rate=t.decimal(rate),
                    base=catalogue.currency,
                    as_of=t.date(reporting.rate_as_of),
                )
            )
        out.append("")

    out += ["---", "", f"*{t.text('disclaimer')}*", ""]
    return "\n".join(out)
