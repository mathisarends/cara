from fastapi_canon import Feature

from gateway.features.llm.infrastructure import LlmProvider
from gateway.features.llm.presentation import llm_router

feature = Feature(name="llm", routers=(llm_router,), providers=(LlmProvider,))
