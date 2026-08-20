from agenttoolkit import Inject, ToolAvailability, Tools
from pydantic import Field

from agent.tools.params import ToolParams
from retrieval import RetrievalResult, TextIndex

# Not wired to a concrete TextIndex yet, so keep this out of the schema
# entirely until a real implementation is injected.
_DISABLED = ToolAvailability(lambda _context: False)


class RecallParams(ToolParams):
    query: str = Field(description="What to search memory for.")
    limit: int = Field(
        default=5,
        ge=1,
        le=20,
        description="Maximum number of remembered items to return.",
    )


def register_memory_tools(tools: Tools) -> None:
    @tools.action(
        description="Search long-term memory for previously remembered facts.",
        params=RecallParams,
        available_when=_DISABLED,
    )
    async def recall(params: RecallParams, index: Inject[TextIndex]) -> str:
        results = await index.retrieve(params.query, limit=params.limit)
        return _render_results(results)


def _render_results(results: list[RetrievalResult]) -> str:
    if not results:
        return "(nothing found)"
    return "\n".join(f"- {result.document.text}" for result in results)
