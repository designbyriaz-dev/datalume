"""LLMProvider adapter boundary — architecture/06-intelligence-layer.md
§1-2. Same "deferred adapter, not a fake implementation" pattern as
app/integrations/billing_provider.py: NullLLMProvider is what every
request gets when ANTHROPIC_API_KEY is unset (the case in this
environment today), and it fails loudly and specifically rather than
silently no-opping.

**Unlike Stripe, an unconfigured LLM doesn't take down the whole
feature.** architecture §1's pipeline is DATA -> ... -> DETERMINISTIC
ANALYTICS -> CONTROLLED AI TOOLS -> LLM INTERPRETATION -> USER — the
LLM is the very last, narrowest step: turning already-selected,
already-executed, typed tool results into a natural-language write-up.
Which tools to call is decided by app/intelligence/ask/pipeline.py's
own deterministic keyword router, never by the LLM — a stronger
reading of spec §57's "never invent" guarantee than native
function-calling would give, where the model itself picks which query
to run. So NullLLMProvider.interpret() still gets called with real,
grounded ToolResult data; it just can't produce prose from it, and the
pipeline falls back to a templated summary built from the same typed
fields instead (see pipeline.py) — grounded, cited data over an
unavailable interpretation layer, never a fake interpretation.
"""

from typing import Protocol

from app.core.config import get_settings


class LLMNotConfiguredError(Exception):
    pass


class LLMProvider(Protocol):
    def interpret(self, question: str, tool_results: list[dict]) -> str:
        """Returns natural-language prose interpreting tool_results —
        never permitted to state a fact absent from tool_results."""
        ...


class NullLLMProvider:
    """Active whenever settings.anthropic_api_key is unset."""

    def interpret(self, question: str, tool_results: list[dict]) -> str:
        raise LLMNotConfiguredError("AI interpretation is not configured — set ANTHROPIC_API_KEY to enable it.")


_SYSTEM_PROMPT = (
    "You are DataLume's data assistant. You will be given a user's question and a JSON list of "
    "tool_results already retrieved from DataLume's own records. Write a short, direct answer to the "
    "question using ONLY facts, numbers, and dates present in tool_results. Never state a number, date, "
    "reference, or status that does not appear in tool_results. If tool_results don't actually answer "
    "the question, say so plainly instead of guessing. Do not add caveats about data freshness or "
    "disclaimers beyond what's needed — be concise."
)


class AnthropicLLMProvider:
    def __init__(self, api_key: str, model: str):
        import anthropic

        self._client = anthropic.Anthropic(api_key=api_key)
        self._model = model

    def interpret(self, question: str, tool_results: list[dict]) -> str:
        import json

        message = self._client.messages.create(
            model=self._model,
            max_tokens=1024,
            system=_SYSTEM_PROMPT,
            messages=[
                {
                    "role": "user",
                    "content": f"Question: {question}\n\ntool_results:\n{json.dumps(tool_results, default=str)}",
                }
            ],
        )
        return "".join(block.text for block in message.content if block.type == "text").strip()


def get_llm_provider() -> LLMProvider:
    settings = get_settings()
    if not settings.anthropic_api_key:
        return NullLLMProvider()
    return AnthropicLLMProvider(settings.anthropic_api_key, settings.anthropic_model)
