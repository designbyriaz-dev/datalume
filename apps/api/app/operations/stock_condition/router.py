"""Stock Condition Surveys — architecture/04-operations-domain.md §6.
Gated by `operations.write`, same as Repairs — this is day-to-day
operational recording, not a reshaping of any framework the way
`operations.compliance` gates. ASSET_MANAGER gained `operations.write`
in this sprint's RBAC update specifically so the role this domain is
named for can actually record a survey (previously operations.read
only) — see auth/rbac.py.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.tenancy import AuthContext, get_auth_context, require_permission
from app.operations.stock_condition.schemas import CreateStockConditionSurveyRequest, StockConditionSurveyOut
from app.operations.stock_condition.service import StockConditionNotFoundError, create_survey, list_surveys

router = APIRouter(prefix="/api/v1/stock-condition-surveys", tags=["stock-condition"])


@router.post("", response_model=StockConditionSurveyOut, status_code=status.HTTP_201_CREATED)
def add_survey(
    payload: CreateStockConditionSurveyRequest,
    ctx: AuthContext = Depends(require_permission("operations.write")),
    db: Session = Depends(get_db),
):
    try:
        survey = create_survey(
            db,
            ctx.organisation_id,
            property_id=payload.property_id,
            survey_date=payload.survey_date,
            surveyor=payload.surveyor,
            condition_ratings=payload.condition_ratings,
            next_survey_due=payload.next_survey_due,
            document_id=payload.document_id,
            actor_user_id=ctx.user.id,
        )
    except StockConditionNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    db.commit()
    db.refresh(survey)
    return survey


@router.get("", response_model=list[StockConditionSurveyOut])
def get_surveys(
    property_id: uuid.UUID | None = None,
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    if ctx.organisation_id is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "X-Organisation-Id header is required")
    return list_surveys(db, ctx.organisation_id, property_id=property_id)
