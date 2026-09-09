from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.auth.router import router as auth_router
from app.core.config import get_settings
from app.data_health.router import router as data_health_router
from app.documents.router import router as documents_router
from app.ingestion.router import router as ingestion_router
from app.organisations.router import router as organisations_router
from app.platform.router import router as billing_router

import app.development.importers  # noqa: F401  (registers IMPORTERS["PROPERTIES"] as a side effect)
from app.development.router import router as development_router

settings = get_settings()

app = FastAPI(title=settings.app_name)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(organisations_router)
app.include_router(billing_router)
app.include_router(ingestion_router)
app.include_router(documents_router)
app.include_router(development_router)
app.include_router(data_health_router)


@app.get("/health")
def health():
    return {"status": "ok", "service": settings.app_name}
