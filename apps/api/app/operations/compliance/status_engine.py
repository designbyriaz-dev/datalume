"""Compliance status engine — architecture/04-operations-domain.md §4,
spec §47: "do not let the LLM invent status" / "AI may explain results
but never invent status." Deterministic status per (entity, requirement),
computed fresh on every read from Inspection/ComplianceAction/
RequirementApplicability rows — same "computed at read time, nothing
persisted to go stale" approach as Data Health, Handover Readiness, and
the repeat-repair/repeat-hazard engines. There is deliberately no write
path from anywhere (let alone a future `intelligence/` package) into a
stored status column, because there is no stored status column — the
only way to get a status is to call this function, which always
recomputes it from the underlying facts.

Follows architecture §4's own pseudocode almost line for line:

    def compliance_status(entity_id, requirement_id):
        latest = latest_inspection(entity_id, requirement_id)
        open_action = open_action_exists(entity_id, requirement_id)
        if not applicable(entity_id, requirement_id): return NOT_APPLICABLE
        if latest is None: return UNKNOWN if never_assessed else MISSING_EVIDENCE
        if open_action and action_overdue(open_action): return OVERDUE_ACTION
        if open_action: return OPEN_ACTION
        days_to_due = (latest.next_due_date - today()).days
        if days_to_due < 0: return OVERDUE if hard_deadline else EXPIRED
        if days_to_due <= org_due_soon_threshold(): return DUE_SOON
        if requires_review(latest): return NEEDS_REVIEW
        return CURRENT

Two signals the pseudocode names but doesn't define are resolved here,
documented at the point each is used below: `never_assessed` (vs.
`latest is None`, which the sketch's own literal reading makes
identical — see ComplianceStatusConfig.never_assessed_grace_days) and
`requires_review(latest)` (an UNSATISFACTORY/ADVISORY result with no
open action covering it — e.g. the action was completed without a
follow-up reinspection, or no action was ever raised for an advisory
note).
"""

import enum
import uuid
from dataclasses import dataclass
from datetime import date

from sqlalchemy.orm import Session

from app.operations.compliance.models import (
    ComplianceAction,
    ComplianceActionStatus,
    ComplianceRequirement,
    Inspection,
    InspectionResult,
    RequirementApplicability,
)
from app.operations.compliance.service import get_or_create_status_config


class ComplianceStatus(str, enum.Enum):
    """Not a DB column — see this module's own docstring for why nothing
    here is ever persisted. Still a real enum (not just string
    constants) for the same type-safety reasons every other status enum
    in this codebase is one."""

    NOT_APPLICABLE = "NOT_APPLICABLE"
    UNKNOWN = "UNKNOWN"
    MISSING_EVIDENCE = "MISSING_EVIDENCE"
    OVERDUE_ACTION = "OVERDUE_ACTION"
    OPEN_ACTION = "OPEN_ACTION"
    OVERDUE = "OVERDUE"
    EXPIRED = "EXPIRED"
    DUE_SOON = "DUE_SOON"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    CURRENT = "CURRENT"


@dataclass
class ComplianceStatusResult:
    status: ComplianceStatus
    requirement_id: uuid.UUID
    domain_id: uuid.UUID
    entity_type: str
    entity_id: str
    latest_inspection: Inspection | None
    open_action: ComplianceAction | None
    days_to_due: int | None


def _current_applicability(
    db: Session, organisation_id: uuid.UUID, entity_type: str, entity_id: uuid.UUID, requirement_id: uuid.UUID
) -> RequirementApplicability | None:
    today = date.today()
    return (
        db.query(RequirementApplicability)
        .filter(
            RequirementApplicability.organisation_id == organisation_id,
            RequirementApplicability.entity_type == entity_type,
            RequirementApplicability.entity_id == str(entity_id),
            RequirementApplicability.requirement_id == requirement_id,
            RequirementApplicability.applicable_from <= today,
            (RequirementApplicability.applicable_to.is_(None)) | (RequirementApplicability.applicable_to >= today),
        )
        .first()
    )


def _latest_inspection(
    db: Session, organisation_id: uuid.UUID, entity_type: str, entity_id: uuid.UUID, requirement_id: uuid.UUID
) -> Inspection | None:
    return (
        db.query(Inspection)
        .filter(
            Inspection.organisation_id == organisation_id,
            Inspection.entity_type == entity_type,
            Inspection.entity_id == str(entity_id),
            Inspection.requirement_id == requirement_id,
        )
        .order_by(Inspection.inspection_date.desc())
        .first()
    )


def _open_actions(
    db: Session, organisation_id: uuid.UUID, entity_type: str, entity_id: uuid.UUID, requirement_id: uuid.UUID
) -> list[ComplianceAction]:
    return (
        db.query(ComplianceAction)
        .filter(
            ComplianceAction.organisation_id == organisation_id,
            ComplianceAction.entity_type == entity_type,
            ComplianceAction.entity_id == str(entity_id),
            ComplianceAction.requirement_id == requirement_id,
            ComplianceAction.status == ComplianceActionStatus.OPEN,
        )
        .order_by(ComplianceAction.deadline)
        .all()
    )


def _resolve_status(
    *,
    requirement: ComplianceRequirement,
    applicability: RequirementApplicability | None,
    latest: Inspection | None,
    open_actions: list[ComplianceAction],
    due_soon_days: int,
    never_assessed_grace_days: int,
    today: date,
) -> tuple[ComplianceStatus, ComplianceAction | None, int | None]:
    if applicability is None:
        return ComplianceStatus.NOT_APPLICABLE, None, None

    if latest is None:
        # The architecture pseudocode names both UNKNOWN and
        # MISSING_EVIDENCE for "latest is None" but gives no second
        # signal to tell them apart — this build's reading: UNKNOWN
        # means applicability only started recently (there hasn't
        # reasonably been time to get evidence yet); MISSING_EVIDENCE
        # means the grace period has elapsed with still nothing on
        # record, which is a genuine gap rather than just "too soon."
        age_days = (today - applicability.applicable_from).days
        if age_days <= never_assessed_grace_days:
            return ComplianceStatus.UNKNOWN, None, None
        return ComplianceStatus.MISSING_EVIDENCE, None, None

    if open_actions:
        overdue = next((a for a in open_actions if a.deadline < today), None)
        if overdue is not None:
            return ComplianceStatus.OVERDUE_ACTION, overdue, None
        return ComplianceStatus.OPEN_ACTION, open_actions[0], None

    if latest.next_due_date is None:
        # No cadence-based due date was recorded on the inspection, so
        # staleness can't be judged — fall straight to the review check
        # rather than guessing a due date.
        if latest.result != InspectionResult.SATISFACTORY:
            return ComplianceStatus.NEEDS_REVIEW, None, None
        return ComplianceStatus.CURRENT, None, None

    days_to_due = (latest.next_due_date - today).days
    if days_to_due < 0:
        status = ComplianceStatus.OVERDUE if requirement.hard_deadline else ComplianceStatus.EXPIRED
        return status, None, days_to_due
    if days_to_due <= due_soon_days:
        return ComplianceStatus.DUE_SOON, None, days_to_due
    if latest.result != InspectionResult.SATISFACTORY:
        return ComplianceStatus.NEEDS_REVIEW, None, days_to_due
    return ComplianceStatus.CURRENT, None, days_to_due


def compliance_status(
    db: Session, organisation_id: uuid.UUID, *, entity_type: str, entity_id: uuid.UUID, requirement: ComplianceRequirement
) -> ComplianceStatusResult:
    today = date.today()
    config = get_or_create_status_config(db, organisation_id)
    applicability = _current_applicability(db, organisation_id, entity_type, entity_id, requirement.id)
    latest = _latest_inspection(db, organisation_id, entity_type, entity_id, requirement.id)
    open_actions = _open_actions(db, organisation_id, entity_type, entity_id, requirement.id)

    status, open_action, days_to_due = _resolve_status(
        requirement=requirement,
        applicability=applicability,
        latest=latest,
        open_actions=open_actions,
        due_soon_days=config.due_soon_days,
        never_assessed_grace_days=config.never_assessed_grace_days,
        today=today,
    )
    return ComplianceStatusResult(
        status=status,
        requirement_id=requirement.id,
        domain_id=requirement.domain_id,
        entity_type=entity_type,
        entity_id=str(entity_id),
        latest_inspection=latest,
        open_action=open_action,
        days_to_due=days_to_due,
    )


def list_compliance_statuses_for_entity(
    db: Session, organisation_id: uuid.UUID, entity_type: str, entity_id: uuid.UUID
) -> list[ComplianceStatusResult]:
    """Every requirement currently applicable to this one entity — the
    per-entity view a Building/Property/Component detail page composes,
    replacing a bare "Applicable" badge with a real computed status."""
    applicable_rows = (
        db.query(RequirementApplicability)
        .filter(
            RequirementApplicability.organisation_id == organisation_id,
            RequirementApplicability.entity_type == entity_type,
            RequirementApplicability.entity_id == str(entity_id),
        )
        .all()
    )
    requirement_ids = {row.requirement_id for row in applicable_rows}
    if not requirement_ids:
        return []
    requirements = (
        db.query(ComplianceRequirement)
        .filter(
            ComplianceRequirement.id.in_(requirement_ids),
            (ComplianceRequirement.organisation_id == organisation_id) | (ComplianceRequirement.organisation_id.is_(None)),
        )
        .all()
    )
    return [
        compliance_status(db, organisation_id, entity_type=entity_type, entity_id=entity_id, requirement=requirement)
        for requirement in requirements
    ]
