"""Ask DataLume — architecture/06-intelligence-layer.md §1-2. Open to
any authenticated org member, same as Home/Property 360 — asking a
question about data you can already see doesn't need a narrower
permission than seeing that data does."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.tenancy import AuthContext, get_auth_context
from app.intelligence.ask.pipeline import ask_datalume
from app.intelligence.ask.schemas import AskRequest, AskResponseOut

router = APIRouter(prefix="/api/v1/ask", tags=["ask"])


@router.post("", response_model=AskResponseOut)
def ask(
    payload: AskRequest,
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    if ctx.organisation_id is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "X-Organisation-Id header is required")
    return ask_datalume(
        db, ctx.organisation_id, question=payload.question, entity_type=payload.entity_type, entity_id=payload.entity_id
    )
