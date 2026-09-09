"""Portfolio rollups — roadmap Sprint 13. Kept separate from router.py
(properties) for the same reason every other *_router.py in this module
is separate: a different URL shape (org-wide, not property-scoped)."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.tenancy import AuthContext, get_auth_context
from app.development.portfolio import get_portfolio_summary
from app.development.schemas import PortfolioSummaryOut

router = APIRouter(tags=["development"])


@router.get("/api/v1/portfolio/summary", response_model=PortfolioSummaryOut)
def portfolio_summary(
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    if ctx.organisation_id is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "X-Organisation-Id header is required")
    summary = get_portfolio_summary(db, ctx.organisation_id)
    db.commit()  # Data Health findings recomputed on read, same as GET /api/v1/data-health
    return summary
