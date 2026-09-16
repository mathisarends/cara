from fastapi_canon import Feature

from gateway.features.llm.infrastructure import LlmProvider

feature = Feature(name="llm", providers=(LlmProvider,))
