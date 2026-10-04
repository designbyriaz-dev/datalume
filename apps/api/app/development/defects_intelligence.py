"""Defects Intelligence — architecture/03-development-domain.md §8,
spec §35. A fixed set of aggregate reads over the defect register — see
DefectsIntelligenceOut's docstring for why this isn't a scored/weighted
engine like Data Health (Sprint 5)."""

import uuid
from datetime import date

from sqlalchemy import func
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


def _top_n(rows: list[tuple[str, int]], limit: int = 10) -> list[DefectsByKeyOut]:
    top = sorted(rows, key=lambda row: row[1], reverse=True)[:limit]
    return [DefectsByKeyOut(key=key, count=count) for key, count in top]


def get_defects_intelligence(
    db: Session,
    organisation_id: uuid.UUID,
    *,
    development_id: uuid.UUID | None = None,
    building_id: uuid.UUID | None = None,
) -> DefectsIntelligenceOut:
    filters = [Defect.organisation_id == organisation_id]
    if development_id is not None:
        filters.append(Defect.development_id == development_id)
    if building_id is not None:
        filters.append(Defect.building_id == building_id)

    today = date.today()
    base = db.query(Defect).filter(*filters)

    total_count = base.count()
    open_count = base.filter(Defect.status.in_(OPEN_STATUSES)).count()
    overdue_count = base.filter(
        Defect.status.in_(OPEN_STATUSES), Defect.target_date.isnot(None), Defect.target_date < today
    ).count()
    warranty_related_count = base.filter(Defect.warranty_related.is_(True)).count()

    contractor_rows = (
        db.query(Defect.contractor, func.count())
        .filter(*filters, Defect.contractor.isnot(None))
        .group_by(Defect.contractor)
        .all()
    )
    category_rows = db.query(Defect.category, func.count()).filter(*filters).group_by(Defect.category).all()

    # by_component_type counts *distinct affected components* per type,
    # not defects per type — preserved exactly from the original
    # Python implementation, which deduped defects down to their
    # component_id before counting, so several defects against the
    # same component only ever counted that one component once.
    distinct_component_ids = (
        db.query(Defect.component_id).filter(*filters, Defect.component_id.isnot(None)).distinct().subquery()
    )
    component_type_rows = (
        db.query(ComponentType.name, func.count())
        .select_from(distinct_component_ids)
        .join(Component, Component.id == distinct_component_ids.c.component_id)
        .join(ComponentType, ComponentType.id == Component.component_type_id)
        .group_by(ComponentType.name)
        .all()
    )

    # "7 properties have repeat water-ingress defects" (spec §35) — a
    # category counts as "repeat" when it occurs more than once at the
    # same property (or, for a defect with no property_id, the same
    # building/component instead — whichever location it's actually
    # tied to): group by (location, category), keep groups with more
    # than one defect, then count how many such locations exist per
    # category.
    location = func.coalesce(Defect.property_id, Defect.building_id, Defect.component_id)
    location_category_counts = (
        db.query(location.label("location"), Defect.category.label("category"), func.count().label("defect_count"))
        .filter(*filters, location.isnot(None))
        .group_by(location, Defect.category)
        .subquery()
    )
    repeat_category_rows = (
        db.query(location_category_counts.c.category, func.count())
        .filter(location_category_counts.c.defect_count > 1)
        .group_by(location_category_counts.c.category)
        .all()
    )

    total_estimated_cost_pence, total_actual_cost_pence = (
        db.query(
            func.coalesce(func.sum(Defect.estimated_cost_pence), 0),
            func.coalesce(func.sum(Defect.actual_cost_pence), 0),
        )
        .filter(*filters)
        .one()
    )

    # average_resolution_days needs (completion_date - reported_date)
    # in days, which isn't portable the same way across SQLite (this
    # codebase's test dialect) and Postgres (production) — so this
    # stays a Python computation, just fed by a narrow two-column
    # projection instead of loading every full Defect row.
    resolution_pairs = (
        db.query(Defect.reported_date, Defect.completion_date)
        .filter(*filters, Defect.status.in_(RESOLVED_STATUSES), Defect.completion_date.isnot(None))
        .all()
    )
    resolution_days = [(completion - reported).days for reported, completion in resolution_pairs]
    average_resolution_days = round(sum(resolution_days) / len(resolution_days), 1) if resolution_days else None

    return DefectsIntelligenceOut(
        total_count=total_count,
        open_count=open_count,
        overdue_count=overdue_count,
        warranty_related_count=warranty_related_count,
        by_contractor=_top_n(contractor_rows),
        by_category=_top_n(category_rows),
        by_component_type=_top_n(component_type_rows),
        repeat_categories=_top_n(repeat_category_rows),
        total_estimated_cost_pence=total_estimated_cost_pence,
        total_actual_cost_pence=total_actual_cost_pence,
        average_resolution_days=average_resolution_days,
    )
