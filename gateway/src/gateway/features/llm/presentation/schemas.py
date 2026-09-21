from pydantic import BaseModel

from llm import CodexModel, CodexReasoningEffort


class ModelOptionsResponse(BaseModel):
    models: tuple[CodexModel, ...]
    default_model: CodexModel
    reasoning_efforts: tuple[CodexReasoningEffort, ...]
