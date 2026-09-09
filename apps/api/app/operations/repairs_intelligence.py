"""Repairs Intelligence — architecture/04-operations-domain.md §1, spec
§43. A fixed set of aggregate reads over the repair register, same
"not a scored engine" reasoning as Defects Intelligence (Sprint 11) —
the spec's own examples ("Block A has 42 defects...") are plain counts
and averages. Folds in the Repeat Repair / Component Failure engine
(§2) results for every property/component actually in scope, so a
single call surfaces both the raw numbers and the deterministic
signals derived from them.
"""

import uuid
from collections import Counter

from sqlalchemy.orm import Session

from app.operations.models import Repair, RepairStatus
from app.operations.repeat_repair import repeat_failures_for_component, repeat_repairs_for_property
from app.operations.schemas import RepairsByKeyOut, RepairsIntelligenceOut

OPEN_STATUSES = (RepairStatus.REPORTED, RepairStatus.SCHEDULED, RepairStatus.IN_PROGRESS)


def _top_counts(counter: Counter, limit: int = 10) -> list[RepairsByKeyOut]:
    return [RepairsByKeyOut(key=key, count=count) for key, count in counter.most_common(limit)]


def get_repairs_intelligence(db: Session, organisation_id: uuid.UUID) -> RepairsIntelligenceOut:
    repairs = db.query(Repair).filter(Repair.organisation_id == organisation_id).all()

    open_count = sum(1 for r in repairs if r.status in OPEN_STATUSES)
    completed_count = sum(1 for r in repairs if r.status == RepairStatus.COMPLETED)
    emergency_count = sum(1 for r in repairs if r.is_emergency)

    category_counts = Counter(r.category for r in repairs)
    contractor_counts = Counter(r.contractor for r in repairs if r.contractor)

    completion_days = [
        (r.completed_date - r.reported_date).days
        for r in repairs
        if r.status == RepairStatus.COMPLETED and r.completed_date is not None
    ]
    average_completion_days = round(sum(completion_days) / len(completion_days), 1) if completion_days else None

    property_ids = {r.property_id for r in repairs}
    repeat_repair_properties = [
        signal
        for property_id in property_ids
        if (signal := repeat_repairs_for_property(db, organisation_id, property_id)) is not None
    ]

    component_ids = {r.component_id for r in repairs if r.component_id}
    repeat_failure_components = [
        signal
        for component_id in component_ids
        if (signal := repeat_failures_for_component(db, organisation_id, component_id)) is not None
    ]

    return RepairsIntelligenceOut(
        total_count=len(repairs),
        open_count=open_count,
        completed_count=completed_count,
        emergency_count=emergency_count,
        by_category=_top_counts(category_counts),
        by_contractor=_top_counts(contractor_counts),
        total_cost_pence=sum(r.cost_pence or 0 for r in repairs),
        average_completion_days=average_completion_days,
        repeat_repair_properties=repeat_repair_properties,
        repeat_failure_components=repeat_failure_components,
    )
