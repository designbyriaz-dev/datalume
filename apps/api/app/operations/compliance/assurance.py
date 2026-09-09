"""Board Assurance report — architecture/04-operations-domain.md §6,
spec item 57: "a read-only rollup of compliance_status counts +
open/overdue compliance_actions + hazard status, grouped by domain and
property/portfolio — assurance is a view over the deterministic status
engine," giving the same "never invent, only explain" guarantee at
executive-reporting altitude that §4 gives at the individual-check
level. Nothing here scores or narrates anything — it counts
already-computed compliance_status values (status_engine.py) and
already-recorded hazard rows, grouped, full stop.

`building_id`/`property_id` scope the report to one property/portfolio
slice (spec's "property" granularity); omitting both is the "portfolio"
granularity. Hazards have no building_id column (only property_id, per
Hazard's own model) — a `building_id` filter narrows the compliance
side of the report but leaves the hazard section portfolio-wide, which
is documented on BoardAssuranceReportOut rather than silently doing
something the data model can't actually support.
"""

import uuid
from collections import Counter, defaultdict
from datetime import date

from sqlalchemy.orm import Session

from app.operations.compliance.models import ComplianceDomain, ComplianceRequirement, RequirementApplicability
from app.operations.compliance.schemas import BoardAssuranceDomainSummaryOut, BoardAssuranceReportOut
from app.operations.compliance.status_engine import ComplianceStatus, compliance_status
from app.operations.hazards.models import Hazard


def get_board_assurance_report(
    db: Session,
    organisation_id: uuid.UUID,
    *,
    building_id: uuid.UUID | None = None,
    property_id: uuid.UUID | None = None,
) -> BoardAssuranceReportOut:
    entity_type: str | None = None
    entity_id: uuid.UUID | None = None
    if property_id is not None:
        entity_type, entity_id = "property", property_id
    elif building_id is not None:
        entity_type, entity_id = "building", building_id

    applicability_query = db.query(RequirementApplicability).filter(
        RequirementApplicability.organisation_id == organisation_id,
        RequirementApplicability.applicable_from <= date.today(),
        (RequirementApplicability.applicable_to.is_(None)) | (RequirementApplicability.applicable_to >= date.today()),
    )
    if entity_type is not None:
        applicability_query = applicability_query.filter(
            RequirementApplicability.entity_type == entity_type, RequirementApplicability.entity_id == str(entity_id)
        )
    applicable_rows = applicability_query.all()

    requirement_ids = {row.requirement_id for row in applicable_rows}
    requirements_by_id = {
        r.id: r
        for r in db.query(ComplianceRequirement).filter(
            ComplianceRequirement.id.in_(requirement_ids),
            (ComplianceRequirement.organisation_id == organisation_id) | (ComplianceRequirement.organisation_id.is_(None)),
        )
    } if requirement_ids else {}

    domain_ids = {r.domain_id for r in requirements_by_id.values()}
    domains_by_id = {
        d.id: d
        for d in db.query(ComplianceDomain).filter(
            ComplianceDomain.id.in_(domain_ids),
            (ComplianceDomain.organisation_id == organisation_id) | (ComplianceDomain.organisation_id.is_(None)),
        )
    } if domain_ids else {}

    status_counts: dict[uuid.UUID, Counter] = defaultdict(Counter)
    open_actions: dict[uuid.UUID, int] = defaultdict(int)
    overdue_actions: dict[uuid.UUID, int] = defaultdict(int)

    for row in applicable_rows:
        requirement = requirements_by_id.get(row.requirement_id)
        if requirement is None:
            continue
        result = compliance_status(
            db, organisation_id, entity_type=row.entity_type, entity_id=uuid.UUID(row.entity_id), requirement=requirement
        )
        status_counts[requirement.domain_id][result.status.value] += 1
        if result.status == ComplianceStatus.OPEN_ACTION:
            open_actions[requirement.domain_id] += 1
        elif result.status == ComplianceStatus.OVERDUE_ACTION:
            overdue_actions[requirement.domain_id] += 1

    domain_summaries = [
        BoardAssuranceDomainSummaryOut(
            domain_id=domain_id,
            domain_code=domains_by_id[domain_id].code,
            domain_name=domains_by_id[domain_id].name,
            status_counts=dict(counts),
            open_actions=open_actions.get(domain_id, 0),
            overdue_actions=overdue_actions.get(domain_id, 0),
        )
        for domain_id, counts in status_counts.items()
        if domain_id in domains_by_id
    ]

    hazard_query = db.query(Hazard).filter(Hazard.organisation_id == organisation_id)
    if property_id is not None:
        hazard_query = hazard_query.filter(Hazard.property_id == property_id)
    hazards = hazard_query.all()
    hazard_status_counts = Counter(h.status.value for h in hazards)
    open_hazard_severity_counts = Counter(h.severity.value for h in hazards if h.status.value != "CLOSED")

    return BoardAssuranceReportOut(
        domains=domain_summaries,
        total_open_actions=sum(open_actions.values()),
        total_overdue_actions=sum(overdue_actions.values()),
        hazard_status_counts=dict(hazard_status_counts),
        open_hazard_severity_counts=dict(open_hazard_severity_counts),
    )
