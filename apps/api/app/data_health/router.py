from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.tenancy import AuthContext, get_auth_context
from app.data_health.rules import run_data_health_checks
from app.data_health.schemas import CheckSummary, DataHealthOut, FindingOut

router = APIRouter(prefix="/api/v1/data-health", tags=["data-health"])


@router.get("", response_model=DataHealthOut)
def get_data_health(
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    if ctx.organisation_id is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "X-Organisation-Id header is required")
    score, results = run_data_health_checks(db, ctx.organisation_id)
    db.commit()

    return DataHealthOut(
        score_pct=score,
        checks=[
            CheckSummary(
                check_code=r.check_code,
                applicable_count=r.applicable_count,
                failing_count=r.failing_count,
                pass_ratio=round(r.pass_ratio, 3),
            )
            for r in results
        ],
        findings=[
            FindingOut(
                check_code=f.check_code,
                severity=f.severity.value,
                affected_entity_type=f.affected_entity_type,
                affected_entity_id=f.affected_entity_id,
                message=f.message,
            )
            for r in results
            for f in r.findings
        ],
    )
