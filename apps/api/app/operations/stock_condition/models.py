"""Stock Condition Surveys — architecture/04-operations-domain.md §6.

`condition_ratings` is a JSONB blob (a free-form {element: rating} map,
e.g. {"roof": "GOOD", "windows": "POOR"}) rather than a fixed set of
columns — same reasoning as everywhere else in this build that avoids
hard-coding a specific survey methodology's own element taxonomy as if
canonical. This build does not attempt to map those free-form keys onto
individual Components for planned-investment scoring (see
app/development/planned_investment.py's own docstring for why) —
architecture's own instruction is that a survey "feeds... Planned
Investment... as one more input signal, not a separate scoring
system," and the one part of that instruction with an unambiguous,
already-existing mapping is Data Health's missing/stale-survey checks
(app/data_health/rules.py), which this sprint adds.

`document_id` (not `evidence_document_id`, matching architecture's own
SQL sketch column name here) is a plain FK to an already-uploaded
Document — same two-step "upload separately, then link" flow as every
other evidence-linking column in this codebase.
"""

import uuid
from datetime import date

from sqlalchemy import Date, ForeignKey, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class StockConditionSurvey(Base):
    __tablename__ = "stock_condition_surveys"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organisation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organisations.id"))
    property_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("properties.id"))
    survey_date: Mapped[date] = mapped_column(Date)
    surveyor: Mapped[str] = mapped_column(String(255))
    condition_ratings: Mapped[dict] = mapped_column(JSON, default=dict)
    next_survey_due: Mapped[date | None] = mapped_column(Date, nullable=True)
    document_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("documents.id"), nullable=True)
