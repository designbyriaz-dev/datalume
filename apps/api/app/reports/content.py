"""Builds report content — architecture §4: "a report is a rendering
target, not a separate data path." Every builder below is a thin
composition over an already-built service-layer function; nothing here
computes a new number.

`ReportContent` is a generic, format-agnostic shape (a title/subtitle
plus a list of sections, each either a flat list of headline fields or
a table) so render.py's three renderers (PDF/XLSX/CSV) each only need
to understand this one shape, not five report-specific ones.

**COMPLIANCE_EXECUTIVE_SUMMARY vs BOARD_ASSURANCE**: both read the same
underlying data (get_board_assurance_report, portfolio-wide) — spec
item 57 only formally defines one assurance methodology, and
architecture §4 explicitly allows one data path to back more than one
rendering target. The two report types differ only in altitude: Board
Assurance renders the full per-domain breakdown table (what the
`/assurance-report` UI already shows); Compliance Executive Summary
renders only the headline totals, for a one-page exec readout. Neither
invents a second data source.

**CSV is inherently flat.** For the two multi-table report types
(Handover Readiness's per-development checks, Commercial Portfolio's
per-lease arrears), CSV export renders the primary table only —
documented on the section itself via `csv_note`, not silently dropped.
"""

import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timezone

from sqlalchemy.orm import Session

from app.commercial.arrears import arrears_for_lease, collection_rate
from app.commercial.service import list_leases
from app.development.handover import compute_handover_readiness
from app.development.models import Development
from app.development.portfolio import get_portfolio_summary
from app.operations.compliance.assurance import get_board_assurance_report


@dataclass
class ReportSection:
    title: str
    summary_fields: list[tuple[str, str]] = field(default_factory=list)
    columns: list[str] = field(default_factory=list)
    rows: list[list[str]] = field(default_factory=list)
    csv_note: str | None = None

    @property
    def is_table(self) -> bool:
        return bool(self.columns)


@dataclass
class ReportContent:
    title: str
    organisation_name: str
    generated_at: datetime
    scope_description: str
    sections: list[ReportSection]


def _pct(value: float) -> str:
    return f"{value:.1f}%"


def build_development_summary_report(db: Session, organisation_id: uuid.UUID, organisation_name: str) -> ReportContent:
    summary = get_portfolio_summary(db, organisation_id)
    sections = [
        ReportSection(
            title="Portfolio headline",
            summary_fields=[
                ("Developments", str(summary.total_developments)),
                ("Properties", str(summary.total_properties)),
                ("Buildings", str(summary.total_buildings)),
                ("Components", str(summary.total_components)),
                ("Data health score", _pct(summary.data_health_score_pct)),
                ("Open defects", str(summary.open_defects_count)),
                ("Overdue defects", str(summary.overdue_defects_count)),
                ("Warranties expiring within 90 days", str(summary.warranties_expiring_within_90_days_count)),
            ],
        ),
        ReportSection(
            title="Properties by status",
            columns=["Status", "Count"],
            rows=[[row.key, str(row.count)] for row in summary.properties_by_status],
        ),
        ReportSection(
            title="Handover readiness by development",
            columns=["Development", "Reference", "Readiness score"],
            rows=[
                [d.name, d.development_reference, _pct(d.score_pct)]
                for d in summary.development_readiness
            ],
        ),
    ]
    return ReportContent(
        title="Development Summary",
        organisation_name=organisation_name,
        generated_at=datetime.now(timezone.utc),
        scope_description="Whole portfolio",
        sections=sections,
    )


def build_handover_readiness_report(db: Session, organisation_id: uuid.UUID, organisation_name: str) -> ReportContent:
    developments = db.query(Development).filter(Development.organisation_id == organisation_id).order_by(Development.name).all()
    sections: list[ReportSection] = []
    overview_rows: list[list[str]] = []
    for dev in developments:
        score_pct, checks = compute_handover_readiness(db, organisation_id, dev.id)
        overview_rows.append([dev.name, dev.development_reference, _pct(score_pct), "Ready" if score_pct >= 100 else "Not ready"])
        sections.append(
            ReportSection(
                title=f"{dev.name} — check breakdown",
                columns=["Check", "Weight", "Applicable", "Failing", "Pass ratio"],
                rows=[
                    [c.label, f"{c.weight:.2f}", str(c.applicable_count), str(c.failing_count), f"{c.pass_ratio:.2f}"]
                    for c in checks
                ],
                csv_note="Per-development check breakdown; export once per development for CSV.",
            )
        )
    overview = ReportSection(
        title="Handover readiness overview",
        columns=["Development", "Reference", "Score", "Status"],
        rows=overview_rows,
    )
    return ReportContent(
        title="Handover Readiness",
        organisation_name=organisation_name,
        generated_at=datetime.now(timezone.utc),
        scope_description=f"{len(developments)} development(s)",
        sections=[overview, *sections],
    )


def _board_assurance_sections(
    db: Session,
    organisation_id: uuid.UUID,
    *,
    building_id: uuid.UUID | None,
    property_id: uuid.UUID | None,
    include_domain_table: bool,
) -> list[ReportSection]:
    report = get_board_assurance_report(db, organisation_id, building_id=building_id, property_id=property_id)
    all_statuses = sorted({status for domain in report.domains for status in domain.status_counts})
    headline = ReportSection(
        title="Assurance headline",
        summary_fields=[
            ("Compliance domains in scope", str(len(report.domains))),
            ("Total open actions", str(report.total_open_actions)),
            ("Total overdue actions", str(report.total_overdue_actions)),
            *[(f"Hazards — {status}", str(count)) for status, count in sorted(report.hazard_status_counts.items())],
            *[
                (f"Open hazards — {severity}", str(count))
                for severity, count in sorted(report.open_hazard_severity_counts.items())
            ],
        ],
    )
    if not include_domain_table:
        return [headline]
    domain_table = ReportSection(
        title="Compliance status by domain",
        columns=["Domain", *all_statuses, "Open actions", "Overdue actions"],
        rows=[
            [
                domain.domain_name,
                *[str(domain.status_counts.get(status, 0)) for status in all_statuses],
                str(domain.open_actions),
                str(domain.overdue_actions),
            ]
            for domain in report.domains
        ],
    )
    return [headline, domain_table]


def build_compliance_executive_summary_report(
    db: Session, organisation_id: uuid.UUID, organisation_name: str, *, building_id: uuid.UUID | None, property_id: uuid.UUID | None
) -> ReportContent:
    sections = _board_assurance_sections(
        db, organisation_id, building_id=building_id, property_id=property_id, include_domain_table=False
    )
    scope = "Whole portfolio" if not (building_id or property_id) else f"Scoped to {'property' if property_id else 'building'}"
    return ReportContent(
        title="Compliance Executive Summary",
        organisation_name=organisation_name,
        generated_at=datetime.now(timezone.utc),
        scope_description=scope,
        sections=sections,
    )


def build_board_assurance_report(
    db: Session, organisation_id: uuid.UUID, organisation_name: str, *, building_id: uuid.UUID | None, property_id: uuid.UUID | None
) -> ReportContent:
    sections = _board_assurance_sections(
        db, organisation_id, building_id=building_id, property_id=property_id, include_domain_table=True
    )
    scope = "Whole portfolio" if not (building_id or property_id) else f"Scoped to {'property' if property_id else 'building'}"
    return ReportContent(
        title="Board Assurance",
        organisation_name=organisation_name,
        generated_at=datetime.now(timezone.utc),
        scope_description=scope,
        sections=sections,
    )


def build_commercial_portfolio_report(
    db: Session,
    organisation_id: uuid.UUID,
    organisation_name: str,
    *,
    period_start: date,
    period_end: date,
) -> ReportContent:
    leases = list_leases(db, organisation_id)
    rate = collection_rate(db, organisation_id, period_start, period_end)
    headline = ReportSection(
        title="Collection rate",
        summary_fields=[
            ("Period", f"{rate.period_start.isoformat()} to {rate.period_end.isoformat()}"),
            ("Due", f"£{rate.due_pence / 100:,.2f}"),
            ("Collected", f"£{rate.collected_pence / 100:,.2f}"),
            ("Collection rate", _pct(rate.collection_rate * 100)),
            ("Active leases", str(len([l for l in leases if l.lease_status.value == "ACTIVE"]))),
        ],
    )
    lease_rows = []
    for lease in leases:
        snapshot = arrears_for_lease(db, organisation_id, lease.id)
        lease_rows.append(
            [
                lease.lease_reference,
                lease.lease_status.value,
                lease.occupancy_status.value,
                f"£{lease.contractual_rent_pence / 100:,.2f}",
                f"£{snapshot.outstanding_pence / 100:,.2f}",
                f"£{snapshot.unallocated_pence / 100:,.2f}",
            ]
        )
    lease_table = ReportSection(
        title="Leases — arrears snapshot",
        columns=["Lease", "Status", "Occupancy", "Contractual rent", "Outstanding", "Unallocated credit"],
        rows=lease_rows,
    )
    return ReportContent(
        title="Commercial Portfolio",
        organisation_name=organisation_name,
        generated_at=datetime.now(timezone.utc),
        scope_description=f"{len(leases)} lease(s)",
        sections=[headline, lease_table],
    )
