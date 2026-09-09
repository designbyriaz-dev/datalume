"""Portfolio rollups — roadmap Sprint 13 "portfolio rollups", spec §41's
org-wide counterpart to Property 360. See PortfolioSummaryOut's
docstring: nothing here is stored, every number is a direct read over
tables that already exist.
"""

import uuid
from collections import Counter
from datetime import date, timedelta

from sqlalchemy.orm import Session

from app.data_health.rules import run_data_health_checks
from app.development.handover import compute_handover_readiness
from app.development.models import Building, Component, Defect, DefectStatus, Development, Property, Warranty
from app.development.schemas import DevelopmentReadinessSummaryOut, PortfolioStatusCountOut, PortfolioSummaryOut

OPEN_DEFECT_STATUSES = (
    DefectStatus.OPEN,
    DefectStatus.ASSIGNED,
    DefectStatus.IN_PROGRESS,
    DefectStatus.READY_FOR_INSPECTION,
)


def get_portfolio_summary(db: Session, organisation_id: uuid.UUID) -> PortfolioSummaryOut:
    properties = db.query(Property).filter(Property.organisation_id == organisation_id).all()
    status_counts = Counter(p.status.value for p in properties)

    total_developments = db.query(Development).filter(Development.organisation_id == organisation_id).count()
    total_buildings = db.query(Building).filter(Building.organisation_id == organisation_id).count()
    total_components = db.query(Component).filter(Component.organisation_id == organisation_id).count()

    score_pct, _ = run_data_health_checks(db, organisation_id)

    open_defects_count = (
        db.query(Defect)
        .filter(Defect.organisation_id == organisation_id, Defect.status.in_(OPEN_DEFECT_STATUSES))
        .count()
    )
    today = date.today()
    overdue_defects_count = (
        db.query(Defect)
        .filter(
            Defect.organisation_id == organisation_id,
            Defect.status.in_(OPEN_DEFECT_STATUSES),
            Defect.target_date.isnot(None),
            Defect.target_date < today,
        )
        .count()
    )

    expiry_cutoff = today + timedelta(days=90)
    warranties_expiring_count = (
        db.query(Warranty)
        .filter(
            Warranty.organisation_id == organisation_id,
            Warranty.expiry_date >= today,
            Warranty.expiry_date <= expiry_cutoff,
        )
        .count()
    )

    developments = db.query(Development).filter(Development.organisation_id == organisation_id).all()
    development_readiness = []
    for dev in developments:
        dev_score, _ = compute_handover_readiness(db, organisation_id, dev.id)
        development_readiness.append(
            DevelopmentReadinessSummaryOut(
                development_id=dev.id, development_reference=dev.development_reference, name=dev.name, score_pct=dev_score
            )
        )

    return PortfolioSummaryOut(
        total_properties=len(properties),
        total_developments=total_developments,
        total_buildings=total_buildings,
        total_components=total_components,
        properties_by_status=[PortfolioStatusCountOut(key=k, count=v) for k, v in status_counts.items()],
        data_health_score_pct=score_pct,
        open_defects_count=open_defects_count,
        overdue_defects_count=overdue_defects_count,
        warranties_expiring_within_90_days_count=warranties_expiring_count,
        development_readiness=development_readiness,
    )
