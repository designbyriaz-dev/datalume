from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.attention.router import router as attention_router
from app.auth.router import router as auth_router
from app.commercial.router import router as commercial_router
from app.core.config import get_settings
from app.core.logging import configure_structlog
from app.core.request_logging import RequestLoggingMiddleware
from app.data_health.router import router as data_health_router
from app.documents.router import router as documents_router
from app.identifiers.router import router as identifiers_router
from app.ingestion.router import router as ingestion_router
from app.intelligence.ask.router import router as ask_router
from app.organisations.router import (
    invitations_router,
    members_router,
    router as organisations_router,
)
from app.platform.router import router as billing_router
from app.reports.router import router as reports_router

import app.development.importers  # noqa: F401  (registers IMPORTERS["PROPERTIES", "COMPONENTS"] as a side effect)
from app.development.change_control_router import router as change_control_router
from app.development.components_router import router as components_router
from app.development.defects_router import router as defects_router
from app.development.handover_router import router as handover_router
from app.development.hierarchy_router import router as development_hierarchy_router
from app.development.planned_investment_router import router as planned_investment_router
from app.development.portfolio_router import router as portfolio_router
from app.development.router import router as development_router
from app.development.specifications_router import router as specifications_router
from app.development.warranties_router import router as warranties_router
from app.operations.compliance.router import router as compliance_router
from app.operations.hazards.router import router as hazards_router
from app.operations.repairs_router import router as repairs_router
from app.operations.stock_condition.router import router as stock_condition_router

settings = get_settings()
configure_structlog()

app = FastAPI(title=settings.app_name)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# Added after CORS so it becomes the outermost middleware (Starlette
# wraps in reverse add-order) and observes the full request lifecycle,
# preflight OPTIONS requests included.
app.add_middleware(RequestLoggingMiddleware)

app.include_router(auth_router)
app.include_router(attention_router)
app.include_router(commercial_router)
app.include_router(organisations_router)
app.include_router(members_router)
app.include_router(invitations_router)
app.include_router(billing_router)
app.include_router(ingestion_router)
app.include_router(documents_router)
app.include_router(development_router)
app.include_router(development_hierarchy_router)
app.include_router(components_router)
app.include_router(specifications_router)
app.include_router(change_control_router)
app.include_router(defects_router)
app.include_router(warranties_router)
app.include_router(handover_router)
app.include_router(portfolio_router)
app.include_router(repairs_router)
app.include_router(compliance_router)
app.include_router(hazards_router)
app.include_router(stock_condition_router)
app.include_router(planned_investment_router)
app.include_router(data_health_router)
app.include_router(identifiers_router)
app.include_router(ask_router)
app.include_router(reports_router)


@app.get("/health")
def health():
    return {"status": "ok", "service": settings.app_name}
