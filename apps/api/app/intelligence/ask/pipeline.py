"""Ask DataLume orchestration — architecture/06-intelligence-layer.md §2.

    DATA -> ... -> DETERMINISTIC ANALYTICS -> CONTROLLED AI TOOLS ->
    LLM INTERPRETATION -> USER

`select_tools` (deterministic keyword matching) decides WHICH tools
run — never the LLM. Each matched tool then executes against the real
deterministic services (tools.py). Only the LAST step — turning
already-grounded ToolResultOut rows into prose — goes to an LLM, and
only when one is configured (app/integrations/llm_provider.py);
otherwise a templated summary built from the same typed fields stands
in, so the response is always genuinely grounded even when
uninterpreted.

If no tool matches the question for the given entity, `grounded=False`
and a fixed "I don't have data" message is returned — spec §56/§91:
"if mock/real data can't answer a question, say so explicitly rather
than guessing." This is enforced here, in the API layer, not left to
a system prompt to (maybe) honour.
"""

import uuid

from sqlalchemy.orm import Session

from app.integrations.llm_provider import LLMNotConfiguredError, get_llm_provider
from app.intelligence.ask.schemas import AskResponseOut, ToolResultOut
from app.intelligence.ask.tools import TOOL_REGISTRY, ToolDefinition

NO_DATA_MESSAGE = (
    "I don't have data to answer that. Try asking about compliance status, repairs, defects, arrears, "
    "or planned investment for this record."
)


def select_tools(question: str, entity_type: str) -> list[ToolDefinition]:
    question_lower = question.lower()
    return [
        tool
        for tool in TOOL_REGISTRY.values()
        if entity_type in tool.applicable_entity_types and any(keyword in question_lower for keyword in tool.keywords)
    ]


def _templated_summary(tool_results: list[ToolResultOut]) -> str:
    lines = [tr.calculation for tr in tool_results if tr.calculation]
    return " ".join(lines) if lines else "No further detail is available for this record."


def _follow_ups_for_entity_type(entity_type: str) -> list[str]:
    applicable = [t for t in TOOL_REGISTRY.values() if entity_type in t.applicable_entity_types]
    return [f"What about {t.keywords[0]}?" for t in applicable[:3]]


def ask_datalume(db: Session, organisation_id: uuid.UUID, *, question: str, entity_type: str, entity_id: uuid.UUID) -> AskResponseOut:
    matched_tools = select_tools(question, entity_type)
    if not matched_tools:
        return AskResponseOut(
            answer_text=NO_DATA_MESSAGE,
            tool_results=[],
            grounded=False,
            suggested_follow_ups=_follow_ups_for_entity_type(entity_type),
        )

    tool_results = [tool.execute(db, organisation_id, entity_type, entity_id) for tool in matched_tools]

    provider = get_llm_provider()
    try:
        answer_text = provider.interpret(question, [tr.model_dump(mode="json") for tr in tool_results])
    except LLMNotConfiguredError:
        answer_text = _templated_summary(tool_results)

    return AskResponseOut(
        answer_text=answer_text,
        tool_results=tool_results,
        grounded=True,
        suggested_follow_ups=_follow_ups_for_entity_type(entity_type),
    )
