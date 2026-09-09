"""ProvenanceMixin has no real consumer table until Sprint 5+ domain
models land (see app/core/provenance.py docstring), so it's exercised
here against a throwaway table defined only for this test."""

import uuid

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.core.provenance import ProvenanceMixin, SourceType


class _WidgetForProvenanceTest(Base, ProvenanceMixin):
    __tablename__ = "_test_widgets"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(64))


def test_provenance_mixin_round_trips_manual_source(client):
    import app.core.db as db_module

    db = db_module.SessionLocal()
    try:
        widget = _WidgetForProvenanceTest(name="test widget", source_type=SourceType.MANUAL)
        db.add(widget)
        db.commit()
        db.refresh(widget)

        assert widget.source_type == SourceType.MANUAL
        assert widget.source_dataset_id is None
        assert widget.import_job_id is None
        assert widget.created_at is not None
        assert widget.updated_at is not None
    finally:
        db.close()


def test_provenance_mixin_links_to_dataset_and_job(client):
    import app.core.db as db_module
    from app.ingestion.models import Dataset, DatasetStatus, ImportJob, ImportJobStatus

    signup = client.post(
        "/api/v1/auth/signup",
        json={
            "name": "Jamie Ward",
            "email": "jamie@northstar-housing.example",
            "password": "correct-horse-battery",
            "organisation_name": "Northstar Housing",
            "organisation_type": "HOUSING_ASSOCIATION",
            "goals": [],
        },
    ).json()

    db = db_module.SessionLocal()
    try:
        org_id = uuid.UUID(signup["organisation_id"])
        user_id = uuid.UUID(signup["user_id"])
        dataset = Dataset(
            organisation_id=org_id,
            name="Test upload",
            dataset_type="PROPERTIES",
            status=DatasetStatus.VALIDATED,
            row_count=1,
            uploaded_by=user_id,
        )
        db.add(dataset)
        db.flush()
        job = ImportJob(organisation_id=org_id, dataset_id=dataset.id, status=ImportJobStatus.AWAITING_MAPPING)
        db.add(job)
        db.flush()

        widget = _WidgetForProvenanceTest(
            name="imported widget",
            source_type=SourceType.FILE_UPLOAD,
            source_dataset_id=dataset.id,
            import_job_id=job.id,
            original_reference="row 3",
            created_by=user_id,
        )
        db.add(widget)
        db.commit()
        db.refresh(widget)

        assert widget.source_dataset_id == dataset.id
        assert widget.import_job_id == job.id
        assert widget.original_reference == "row 3"
        assert widget.created_by == user_id
    finally:
        db.close()
