from fastapi import APIRouter, Depends

from app.core.tenancy import AuthContext, get_auth_context
from app.organisations.adaptive import WorkspaceLayout, resolve_workspace_layout
from app.organisations.models import Organisation
from app.core.db import get_db
from sqlalchemy.orm import Session
from fastapi import HTTPException, status

router = APIRouter(prefix="/api/v1/workspaces", tags=["organisations"])


@router.get("/layout", response_model=WorkspaceLayout)
def get_workspace_layout(
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    if ctx.organisation_id is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "X-Organisation-Id header is required")
    org = db.get(Organisation, ctx.organisation_id)
    if org is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Organisation not found")
    return resolve_workspace_layout(org.organisation_type, org.goals)
