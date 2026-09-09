"""Stock Condition Surveys write path — same "manual entry calls the
same function" reasoning as every other *_service.py in this
codebase."""

import uuid
from datetime import date

from sqlalchemy.orm import Session

from app.development.models import Property
from app.documents.models import Document
from app.operations.stock_condition.models import StockConditionSurvey
from app.platform.audit import record_audit_event


class StockConditionNotFoundError(ValueError):
    """A given property_id/document_id doesn't exist in this
    organisation — the router maps this to a 404."""


def _get_org_property(db: Session, organisation_id: uuid.UUID, property_id: uuid.UUID) -> Property:
    prop = db.query(Property).filter(Property.id == property_id, Property.organisation_id == organisation_id).first()
    if prop is None:
        raise StockConditionNotFoundError(f"Property {property_id} not found")
    return prop


def _get_org_document(db: Session, organisation_id: uuid.UUID, document_id: uuid.UUID) -> Document:
    document = db.query(Document).filter(Document.id == document_id, Document.organisation_id == organisation_id).first()
    if document is None:
        raise StockConditionNotFoundError(f"Document {document_id} not found")
    return document


def create_survey(
    db: Session,
    organisation_id: uuid.UUID,
    *,
    property_id: uuid.UUID,
    survey_date: date,
    surveyor: str,
    condition_ratings: dict,
    next_survey_due: date | None,
    document_id: uuid.UUID | None,
    actor_user_id: uuid.UUID | None,
) -> StockConditionSurvey:
    _get_org_property(db, organisation_id, property_id)
    if document_id is not None:
        _get_org_document(db, organisation_id, document_id)

    survey = StockConditionSurvey(
        organisation_id=organisation_id,
        property_id=property_id,
        survey_date=survey_date,
        surveyor=surveyor,
        condition_ratings=condition_ratings,
        next_survey_due=next_survey_due,
        document_id=document_id,
    )
    db.add(survey)
    db.flush()

    record_audit_event(
        db,
        organisation_id=organisation_id,
        actor_user_id=actor_user_id,
        action_code="stock_condition_survey.recorded",
        entity_type="stock_condition_survey",
        entity_id=str(survey.id),
        after={"property_id": str(property_id), "survey_date": str(survey_date)},
    )
    return survey


def list_surveys(
    db: Session, organisation_id: uuid.UUID, *, property_id: uuid.UUID | None = None
) -> list[StockConditionSurvey]:
    query = db.query(StockConditionSurvey).filter(StockConditionSurvey.organisation_id == organisation_id)
    if property_id is not None:
        query = query.filter(StockConditionSurvey.property_id == property_id)
    return query.order_by(StockConditionSurvey.survey_date.desc()).all()


def latest_survey_for_property(
    db: Session, organisation_id: uuid.UUID, property_id: uuid.UUID
) -> StockConditionSurvey | None:
    return (
        db.query(StockConditionSurvey)
        .filter(StockConditionSurvey.organisation_id == organisation_id, StockConditionSurvey.property_id == property_id)
        .order_by(StockConditionSurvey.survey_date.desc())
        .first()
    )
