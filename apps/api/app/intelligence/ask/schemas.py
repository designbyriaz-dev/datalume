import uuid
from datetime import date

from pydantic import BaseModel


class DateRangeOut(BaseModel):
    start: date | None = None
    end: date | None = None


class ToolResultOut(BaseModel):
    """architecture/06-intelligence-layer.md §2's own ToolResult shape,
    implemented field-for-field. `records` is the actual grounding data
    handed to the LLM (and shown to the user in the explainability
    panel); `calculation` names what was computed, in plain words, so a
    user (or the response renderer) never has to guess."""

    tool_name: str
    dataset: str
    fields: list[str]
    filters: dict
    time_period: DateRangeOut | None
    records: list[dict]
    calculation: str | None


class AskRequest(BaseModel):
    question: str
    entity_type: str
    entity_id: uuid.UUID


class AskResponseOut(BaseModel):
    """architecture §2's own AskResponse shape. `grounded=False` means
    no registered tool matched the question for this entity — the
    router then forces a fixed "I don't have data" family of
    responses rather than letting anything resembling a free-form
    answer through (spec §56/§91)."""

    answer_text: str
    tool_results: list[ToolResultOut]
    grounded: bool
    suggested_follow_ups: list[str]
