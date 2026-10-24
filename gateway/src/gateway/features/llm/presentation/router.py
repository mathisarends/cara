from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import Depends
from fastapi_canon import CanonRouter

from gateway.features.llm.infrastructure import LlmSettings
from gateway.features.llm.presentation.schemas import ModelOptionsResponse
from gateway.presentation.authentication import require_token
from llm import CodexReasoningEffort

llm_router = CanonRouter(
    prefix="/llm",
    tags=["llm"],
    route_class=DishkaRoute,
    dependencies=[Depends(require_token)],
)


@llm_router.get(
    "/model-options",
    operation_id="get_model_options",
    response_model=ModelOptionsResponse,
    summary="List the models and reasoning efforts available for runtime selection",
)
async def get_model_options(
    settings: FromDishka[LlmSettings],
) -> ModelOptionsResponse:
    return ModelOptionsResponse(
        models=settings.available,
        default_model=settings.default,
        reasoning_efforts=tuple(CodexReasoningEffort),
    )
