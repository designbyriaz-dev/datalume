import uuid
from datetime import date

from pydantic import BaseModel


class CreateStockConditionSurveyRequest(BaseModel):
    property_id: uuid.UUID
    survey_date: date
    surveyor: str
    condition_ratings: dict = {}
    next_survey_due: date | None = None
    document_id: uuid.UUID | None = None


class StockConditionSurveyOut(BaseModel):
    id: uuid.UUID
    property_id: uuid.UUID
    survey_date: date
    surveyor: str
    condition_ratings: dict
    next_survey_due: date | None
    document_id: uuid.UUID | None

    model_config = {"from_attributes": True}
