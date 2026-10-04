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

from app.operations.compliance.models import (
    ComplianceAction,
    ComplianceActionStatus,
    ComplianceDomain,
    ComplianceRequirement,
    Inspection,
    RequirementApplicability,
)
from app.operations.compliance.schemas import BoardAssuranceDomainSummaryOut, BoardAssuranceReportOut
from app.operations.compliance.service import get_or_create_status_config
from app.operations.compliance.status_engine import ComplianceStatus, resolve_compliance_status
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

    # Bulk-fetch what compliance_status() would otherwise look up once
    # per (entity, requirement) pair — for a portfolio-wide report that
    # can be tens of thousands of pairs, each costing 3-4 individual
    # queries (status config, applicability, latest inspection, open
    # actions) via compliance_status() itself. `row` already satisfies
    # every filter `compliance_status()`'s own applicability lookup
    # would apply (same organisation/entity_type/entity_id/requirement_id,
    # same applicable_from/applicable_to window — applicable_rows was
    # fetched with that exact window above), so it's passed straight
    # through as the applicability instead of re-querying for it.
    # Inspections and open actions are fetched in two bulk queries
    # scoped to the entities/requirements actually appearing in
    # applicable_rows, then grouped in Python — same inputs, same
    # `resolve_compliance_status` decision logic, just O(1) queries instead of
    # O(pairs).
    config = get_or_create_status_config(db, organisation_id)
    today = date.today()

    pair_keys = {(row.entity_type, row.entity_id, row.requirement_id) for row in applicable_rows}
    entity_types = {k[0] for k in pair_keys}
    entity_ids = {k[1] for k in pair_keys}

    latest_inspection_by_key: dict[tuple[str, str, uuid.UUID], Inspection] = {}
    inspections = (
        db.query(Inspection)
        .filter(
            Inspection.organisation_id == organisation_id,
            Inspection.entity_type.in_(entity_types),
            Inspection.entity_id.in_(entity_ids),
            Inspection.requirement_id.in_(requirement_ids),
        )
        .order_by(Inspection.inspection_date.desc())
        .all()
    ) if requirement_ids else []
    for inspection in inspections:
        key = (inspection.entity_type, inspection.entity_id, inspection.requirement_id)
        if key not in latest_inspection_by_key:  # already ordered desc, so the first one seen per key is the latest
            latest_inspection_by_key[key] = inspection

    open_actions_by_key: dict[tuple[str, str, uuid.UUID], list[ComplianceAction]] = defaultdict(list)
    actions = (
        db.query(ComplianceAction)
        .filter(
            ComplianceAction.organisation_id == organisation_id,
            ComplianceAction.entity_type.in_(entity_types),
            ComplianceAction.entity_id.in_(entity_ids),
            ComplianceAction.requirement_id.in_(requirement_ids),
            ComplianceAction.status == ComplianceActionStatus.OPEN,
        )
        .order_by(ComplianceAction.deadline)
        .all()
    ) if requirement_ids else []
    for action in actions:
        key = (action.entity_type, action.entity_id, action.requirement_id)
        open_actions_by_key[key].append(action)

    for row in applicable_rows:
        requirement = requirements_by_id.get(row.requirement_id)
        if requirement is None:
            continue
        key = (row.entity_type, row.entity_id, row.requirement_id)
        status, _open_action, _days_to_due = resolve_compliance_status(
            requirement=requirement,
            applicability=row,
            latest=latest_inspection_by_key.get(key),
            open_actions=open_actions_by_key.get(key, []),
            due_soon_days=config.due_soon_days,
            never_assessed_grace_days=config.never_assessed_grace_days,
            today=today,
        )
        status_counts[requirement.domain_id][status.value] += 1
        if status == ComplianceStatus.OPEN_ACTION:
            open_actions[requirement.domain_id] += 1
        elif status == ComplianceStatus.OVERDUE_ACTION:
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
