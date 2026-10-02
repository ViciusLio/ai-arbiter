from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID

from ai_arbiter.core.config import ReportingCurrencySettings
from ai_arbiter.gateway.finops.catalogue import load_catalogue
from ai_arbiter.gateway.finops.metering import UsageLine, UsageTotals
from ai_arbiter.gateway.finops.report import UsageReport, render_usage_report

ALPHA = UUID("018f0000-0000-7000-8000-00000000000a")
BETA = UUID("018f0000-0000-7000-8000-00000000000b")
REPORTING = ReportingCurrencySettings(currency="EUR", rate="0.92", rate_as_of=date(2026, 10, 1))


def report(*lines: UsageLine) -> UsageReport:
    return UsageReport(
        tenant_name="Acme",
        scope_type="project",
        start=date(2026, 10, 1),
        end=date(2026, 10, 31),
        generated_at=datetime(2026, 10, 31, 18, 0, tzinfo=UTC),
        lines=lines,
        names={ALPHA: "assistant"},
    )


def line(scope_id: UUID, **totals: object) -> UsageLine:
    return UsageLine("project", scope_id, "USD", UsageTotals(**totals))  # type: ignore[arg-type]


LINES = (
    line(BETA, requests=10, input_tokens=5000, output_tokens=900, cost_estimate=Decimal("1.25")),
    line(
        ALPHA,
        requests=1234,
        denied=3,
        failed=1,
        unpriced=7,
        estimated=2,
        input_tokens=1_000_000,
        output_tokens=250_000,
        cost_estimate=Decimal("1234.5"),
        estimated_cost=Decimal("0.75"),
    ),
)


def test_the_report_lists_scopes_by_name_and_totals_them() -> None:
    text = render_usage_report(report(*LINES), load_catalogue())

    assert text.startswith("# Usage report\n")
    assert "- **Tenant**: Acme" in text
    assert "- **Period**: October 1, 2026 to October 31, 2026" in text
    assert "- **Grouped by**: project" in text
    assert "| assistant | 1,234 | 3 | 1 | 1,000,000 | 250,000 | 1,234.5000 | 7 | 2 |" in text
    assert f"| {BETA} | 10 | 0 | 0 | 5,000 | 900 | 1.2500 | 0 | 0 |" in text
    assert "| **Total** | 1,244 | 3 | 1 | 1,005,000 | 250,900 | 1,235.7500 | 7 | 2 |" in text
    assert text.index("| assistant |") > text.index(f"| {BETA} |")


def test_the_report_says_what_the_totals_leave_out() -> None:
    text = render_usage_report(report(*LINES), load_catalogue())

    assert "Every cost is an estimate computed from the price catalogue." in text
    assert "7 completed requests have no cost" in text
    assert "2 completed requests have token counts that were estimated" in text
    assert "They account for 0.7500 USD of the total." in text
    assert "Arbiter is a support tool. It does not provide legal advice." in text


def test_a_report_with_measured_costs_only_says_so() -> None:
    text = render_usage_report(report(LINES[0]), load_catalogue())

    assert "Every cost above comes from token counts reported by a provider." in text
    assert "have no cost" not in text


def test_the_report_adds_the_reporting_currency_and_states_the_rate() -> None:
    text = render_usage_report(report(LINES[0]), load_catalogue(), reporting=REPORTING)

    assert "| Estimated cost (USD) | Estimated cost (EUR) |" in text
    assert "| 1.2500 | 1.1500 |" in text
    assert "Amounts in EUR are converted at 0.92 EUR per USD, the rate of October 1, 2026" in text


def test_the_report_in_italian() -> None:
    text = render_usage_report(report(*LINES), load_catalogue(), locale="it", reporting=REPORTING)

    assert text.startswith("# Report dei consumi\n")
    assert "- **Periodo**: dal 1 ottobre 2026 al 31 ottobre 2026" in text
    assert "- **Raggruppato per**: progetto" in text
    assert (
        "| assistant | 1.234 | 3 | 1 | 1.000.000 | 250.000 | 1.234,5000 | 1.135,7400 | 7 | 2 |"
        in text
    )
    assert "| **Totale** |" in text
    assert "convertiti a 0,92 EUR per USD, il tasso del 1 ottobre 2026" in text
    assert "Non fornisce consulenza legale." in text


def test_an_empty_report_says_there_was_no_usage() -> None:
    text = render_usage_report(report(), load_catalogue())

    assert "No usage was recorded in this period." in text
    assert "|---|" not in text
    assert "It does not provide legal advice." in text
