"""Defects Intelligence — architecture/03-development-domain.md §8,
spec §35. A fixed set of aggregate reads over the defect register — see
DefectsIntelligenceOut's docstring for why this isn't a scored/weighted
engine like Data Health (Sprint 5)."""

import uuid
from collections import Counter
from datetime import date

from sqlalchemy.orm import Session

from app.development.models import Component, ComponentType, Defect, DefectStatus
from app.development.schemas import DefectsByKeyOut, DefectsIntelligenceOut

OPEN_STATUSES = (
    DefectStatus.OPEN,
    DefectStatus.ASSIGNED,
    DefectStatus.IN_PROGRESS,
    DefectStatus.READY_FOR_INSPECTION,
)
RESOLVED_STATUSES = (DefectStatus.COMPLETED, DefectStatus.CLOSED)


def _top_counts(counter: Counter, limit: int = 10) -> list[DefectsByKeyOut]:
    return [DefectsByKeyOut(key=key, count=count) for key, count in counter.most_common(limit)]


def get_defects_intelligence(
    db: Session,
    organisation_id: uuid.UUID,
    *,
    development_id: uuid.UUID | None = None,
    building_id: uuid.UUID | None = None,
) -> DefectsIntelligenceOut:
    query = db.query(Defect).filter(Defect.organisation_id == organisation_id)
    if development_id is not None:
        query = query.filter(Defect.development_id == development_id)
    if building_id is not None:
        query = query.filter(Defect.building_id == building_id)
    defects = query.all()

    today = date.today()
    open_count = sum(1 for d in defects if d.status in OPEN_STATUSES)
    overdue_count = sum(
        1 for d in defects if d.status in OPEN_STATUSES and d.target_date is not None and d.target_date < today
    )
    warranty_related_count = sum(1 for d in defects if d.warranty_related)

    contractor_counts = Counter(d.contractor for d in defects if d.contractor)
    category_counts = Counter(d.category for d in defects)

    component_ids = [d.component_id for d in defects if d.component_id]
    component_type_names: dict[uuid.UUID, str] = {}
    if component_ids:
        components = db.query(Component).filter(Component.id.in_(component_ids)).all()
        type_ids = {c.component_type_id for c in components}
        types_by_id = {t.id: t.name for t in db.query(ComponentType).filter(ComponentType.id.in_(type_ids))}
        component_by_id = {c.id: c for c in components}
        component_type_names = {
            cid: types_by_id.get(component_by_id[cid].component_type_id, "Unknown") for cid in component_ids
        }
    component_type_counts = Counter(component_type_names.values())

    # "7 properties have repeat water-ingress defects" (spec §35) — a
    # category counts as "repeat" when it occurs more than once at the
    # same property (or, for a defect with no property_id, the same
    # building/component instead — whichever location it's actually
    # tied to).
    location_category_counts = Counter(
        (d.property_id or d.building_id or d.component_id, d.category)
        for d in defects
        if d.property_id or d.building_id or d.component_id
    )
    repeat_category_counts = Counter()
    for (_, category), count in location_category_counts.items():
        if count > 1:
            repeat_category_counts[category] += 1

    resolution_days = [
        (d.completion_date - d.reported_date).days
        for d in defects
        if d.status in RESOLVED_STATUSES and d.completion_date is not None
    ]
    average_resolution_days = round(sum(resolution_days) / len(resolution_days), 1) if resolution_days else None

    return DefectsIntelligenceOut(
        total_count=len(defects),
        open_count=open_count,
        overdue_count=overdue_count,
        warranty_related_count=warranty_related_count,
        by_contractor=_top_counts(contractor_counts),
        by_category=_top_counts(category_counts),
        by_component_type=_top_counts(component_type_counts),
        repeat_categories=_top_counts(repeat_category_counts),
        total_estimated_cost_pence=sum(d.estimated_cost_pence or 0 for d in defects),
        total_actual_cost_pence=sum(d.actual_cost_pence or 0 for d in defects),
        average_resolution_days=average_resolution_days,
    )
