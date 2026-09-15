import asyncio
from collections.abc import AsyncIterator
from typing import cast

import pytest

from agent.models import ModelSwitch
from llm import ChatModel, Message, ModelResponse, UserMessage


class _StreamingModel:
    def __init__(self) -> None:
        self.requests: list[list[Message]] = []

    async def stream(
        self,
        messages: list[Message],
        **options: object,
    ) -> AsyncIterator[ModelResponse]:
        del options
        self.requests.append(messages)
        yield ModelResponse(completion="OK", finish_reason="stop")


def test_model_switch_smoke_tests_before_switching() -> None:
    first = cast(ChatModel, object())
    streaming_model = _StreamingModel()
    second = cast(ChatModel, streaming_model)
    models = ModelSwitch({"first": first, "second": second}, default="first")

    assert models.current is first
    assert models.current_name == "first"
    assert models.names == ("first", "second")
    assert models.has_alternatives

    asyncio.run(models.switch("second"))

    assert models.current is second
    assert models.current_name == "second"
    assert streaming_model.requests == [[UserMessage(content="Reply with exactly OK.")]]


def test_model_switch_rejects_an_unknown_model() -> None:
    models = ModelSwitch.single(cast(ChatModel, object()), name="first")

    async def switch() -> None:
        await models.switch("missing")

    with pytest.raises(ValueError, match="Unknown model 'missing'"):
        asyncio.run(switch())


def test_configurable_model_switch_changes_reasoning_effort_atomically() -> None:
    created: list[tuple[str, str | None, ChatModel]] = []

    def factory(name: str):
        def create(reasoning_effort: str | None) -> ChatModel:
            model = cast(ChatModel, object())
            created.append((name, reasoning_effort, model))
            return model

        return create

    async def smoke_test(model: ChatModel) -> None:
        if model is created[-1][2] and created[-1][0] == "broken":
            raise RuntimeError("not available")

    models = ModelSwitch.configurable(
        {"first": factory("first"), "broken": factory("broken")},
        default="first",
        reasoning_efforts=("low", "high"),
        smoke_test=smoke_test,
    )

    asyncio.run(models.set_reasoning_effort("high"))

    assert models.current_name == "first"
    assert models.current_reasoning_effort == "high"
    active_model = models.current

    async def switch_to_broken() -> None:
        await models.switch("broken")

    with pytest.raises(RuntimeError, match="failed its smoke test"):
        asyncio.run(switch_to_broken())

    assert models.current is active_model
    assert models.current_name == "first"
    assert models.current_reasoning_effort == "high"
