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
from collections import defaultdict
from datetime import date, timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.operations.models import Repair, RepairStatus
from app.operations.repeat_repair import REPEAT_FAILURES_PER_COMPONENT, REPEAT_REPAIRS_PER_PROPERTY, RULE_DEFAULTS
from app.operations.schemas import (
    RepairsByKeyOut,
    RepairsIntelligenceOut,
    RepeatFailureSignalOut,
    RepeatRepairSignalOut,
)
from app.operations.service import get_or_create_repair_rule_config

OPEN_STATUSES = (RepairStatus.REPORTED, RepairStatus.SCHEDULED, RepairStatus.IN_PROGRESS)


def _top_n(rows: list[tuple[str, int]], limit: int = 10) -> list[RepairsByKeyOut]:
    top = sorted(rows, key=lambda row: row[1], reverse=True)[:limit]
    return [RepairsByKeyOut(key=key, count=count) for key, count in top]


def get_repairs_intelligence(db: Session, organisation_id: uuid.UUID) -> RepairsIntelligenceOut:
    filters = [Repair.organisation_id == organisation_id]
    base = db.query(Repair).filter(*filters)

    total_count = base.count()
    open_count = base.filter(Repair.status.in_(OPEN_STATUSES)).count()
    completed_count = base.filter(Repair.status == RepairStatus.COMPLETED).count()
    emergency_count = base.filter(Repair.is_emergency.is_(True)).count()

    category_rows = db.query(Repair.category, func.count()).filter(*filters).group_by(Repair.category).all()
    contractor_rows = (
        db.query(Repair.contractor, func.count())
        .filter(*filters, Repair.contractor.isnot(None))
        .group_by(Repair.contractor)
        .all()
    )
    total_cost_pence = db.query(func.coalesce(func.sum(Repair.cost_pence), 0)).filter(*filters).scalar()

    # average_completion_days needs (completed_date - reported_date) in
    # days, which isn't portable the same way across SQLite (this
    # codebase's test dialect) and Postgres (production) — stays a
    # Python computation, fed by a narrow two-column projection instead
    # of every full Repair row.
    completion_pairs = (
        db.query(Repair.reported_date, Repair.completed_date)
        .filter(*filters, Repair.status == RepairStatus.COMPLETED, Repair.completed_date.isnot(None))
        .all()
    )
    completion_days = [(completed - reported).days for reported, completed in completion_pairs]
    average_completion_days = round(sum(completion_days) / len(completion_days), 1) if completion_days else None

    # Repeat-repair/repeat-failure signals — the exact same decision
    # rule as repeat_repair.py's own repeat_repairs_for_property/
    # repeat_failures_for_component (N+ repairs within a configured
    # window), computed for every property/component with any repair
    # in one pass instead of once per property/component. Those two
    # functions stay untouched and keep being called per-entity by the
    # per-property/per-component endpoints, the attention engine, Ask
    # DataLume, and Planned Investment Intelligence — each of those is
    # genuinely single-entity, so there's no N+1 there. This report is
    # the one caller that needs the signal for every property/
    # component that has one, so it fetches each rule's config once
    # (was: once per property, once per component) and bulk-queries
    # repairs once, grouping in Python by the config's own threshold.
    property_config = get_or_create_repair_rule_config(
        db, organisation_id, REPEAT_REPAIRS_PER_PROPERTY, RULE_DEFAULTS[REPEAT_REPAIRS_PER_PROPERTY]
    )
    component_config = get_or_create_repair_rule_config(
        db, organisation_id, REPEAT_FAILURES_PER_COMPONENT, RULE_DEFAULTS[REPEAT_FAILURES_PER_COMPONENT]
    )
    property_cutoff = date.today() - timedelta(days=round(property_config.window_months * 30.44))
    component_cutoff = date.today() - timedelta(days=round(component_config.window_months * 30.44))

    windowed_repairs = (
        db.query(Repair.id, Repair.property_id, Repair.component_id, Repair.reported_date)
        .filter(*filters, Repair.reported_date >= min(property_cutoff, component_cutoff), Repair.status != RepairStatus.CANCELLED)
        .all()
    )

    repair_ids_by_property: dict[uuid.UUID, list[uuid.UUID]] = defaultdict(list)
    repair_ids_by_component: dict[uuid.UUID, list[uuid.UUID]] = defaultdict(list)
    for repair_id, property_id, component_id, reported_date in windowed_repairs:
        if reported_date >= property_cutoff:
            repair_ids_by_property[property_id].append(repair_id)
        if component_id is not None and reported_date >= component_cutoff:
            repair_ids_by_component[component_id].append(repair_id)

    repeat_repair_properties = [
        RepeatRepairSignalOut(
            property_id=property_id,
            repair_count=len(repair_ids),
            window_months=property_config.window_months,
            threshold=property_config.threshold,
            repair_ids=repair_ids,
        )
        for property_id, repair_ids in repair_ids_by_property.items()
        if len(repair_ids) >= property_config.threshold
    ]
    repeat_failure_components = [
        RepeatFailureSignalOut(
            component_id=component_id,
            repair_count=len(repair_ids),
            window_months=component_config.window_months,
            threshold=component_config.threshold,
            repair_ids=repair_ids,
        )
        for component_id, repair_ids in repair_ids_by_component.items()
        if len(repair_ids) >= component_config.threshold
    ]

    return RepairsIntelligenceOut(
        total_count=total_count,
        open_count=open_count,
        completed_count=completed_count,
        emergency_count=emergency_count,
        by_category=_top_n(category_rows),
        by_contractor=_top_n(contractor_rows),
        total_cost_pence=total_cost_pence,
        average_completion_days=average_completion_days,
        repeat_repair_properties=repeat_repair_properties,
        repeat_failure_components=repeat_failure_components,
    )
