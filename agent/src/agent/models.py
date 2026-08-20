import asyncio
from collections.abc import Awaitable, Callable
from typing import Self

from llmify import ChatModel, UserMessage

type _ModelFactory = Callable[[str | None], ChatModel]
type _ModelSmokeTest = Callable[[ChatModel], Awaitable[None]]


class ModelSwitch:
    """The model driving the agent, validated before runtime changes."""

    def __init__(
        self,
        models: dict[str, ChatModel],
        *,
        default: str,
        smoke_test: _ModelSmokeTest | None = None,
    ) -> None:
        if default not in models:
            raise ValueError(f"Unknown default model '{default}'.")
        self._models = models
        self._factories: dict[str, _ModelFactory] | None = None
        self._reasoning_efforts: tuple[str, ...] = ()
        self._current_name = default
        self._current_reasoning_effort: str | None = None
        self._smoke_test = smoke_test or _smoke_test_model
        self._switch_lock = asyncio.Lock()

    @classmethod
    def single(cls, model: ChatModel, *, name: str = "default") -> Self:
        return cls({name: model}, default=name)

    @classmethod
    def configurable(
        cls,
        factories: dict[str, _ModelFactory],
        *,
        default: str,
        reasoning_efforts: tuple[str, ...],
        smoke_test: _ModelSmokeTest | None = None,
    ) -> Self:
        if default not in factories:
            raise ValueError(f"Unknown default model '{default}'.")
        instance = cls(
            {default: factories[default](None)},
            default=default,
            smoke_test=smoke_test,
        )
        instance._factories = factories
        instance._reasoning_efforts = reasoning_efforts
        return instance

    @property
    def current(self) -> ChatModel:
        return self._models[self._current_name]

    @property
    def current_name(self) -> str:
        return self._current_name

    @property
    def current_reasoning_effort(self) -> str | None:
        return self._current_reasoning_effort

    @property
    def names(self) -> tuple[str, ...]:
        if self._factories is not None:
            return tuple(self._factories)
        return tuple(self._models)

    @property
    def reasoning_efforts(self) -> tuple[str, ...]:
        return self._reasoning_efforts

    @property
    def has_alternatives(self) -> bool:
        return len(self.names) > 1

    @property
    def supports_reasoning_effort(self) -> bool:
        return bool(self._reasoning_efforts)

    async def switch(self, name: str) -> None:
        await self._activate(name, self._current_reasoning_effort)

    async def switch_with_reasoning_effort(
        self,
        name: str,
        reasoning_effort: str | None,
    ) -> None:
        await self._activate(name, reasoning_effort)

    async def set_reasoning_effort(self, reasoning_effort: str | None) -> None:
        await self._activate(self._current_name, reasoning_effort)

    async def _activate(
        self,
        name: str,
        reasoning_effort: str | None,
    ) -> None:
        async with self._switch_lock:
            self._validate_configuration(name, reasoning_effort)
            try:
                candidate = self._create_candidate(name, reasoning_effort)
                await self._smoke_test(candidate)
            except Exception as error:
                raise RuntimeError(
                    f"Model '{name}' failed its smoke test: {error}"
                ) from error
            self._models[name] = candidate
            self._current_name = name
            self._current_reasoning_effort = reasoning_effort

    def _validate_configuration(
        self,
        name: str,
        reasoning_effort: str | None,
    ) -> None:
        if name not in self.names:
            available = ", ".join(self.names)
            raise ValueError(f"Unknown model '{name}'. Available: {available}.")
        if (
            reasoning_effort is not None
            and reasoning_effort not in self._reasoning_efforts
        ):
            available = ", ".join(self._reasoning_efforts)
            raise ValueError(
                f"Unknown reasoning effort '{reasoning_effort}'. "
                f"Available: default, {available}."
            )

    def _create_candidate(
        self,
        name: str,
        reasoning_effort: str | None,
    ) -> ChatModel:
        if self._factories is None:
            if reasoning_effort is not None:
                raise ValueError(
                    "This model registry does not support reasoning effort."
                )
            return self._models[name]
        return self._factories[name](reasoning_effort)


async def _smoke_test_model(model: ChatModel) -> None:
    received_event = False
    async for _ in model.stream(
        messages=[UserMessage(content="Reply with exactly OK.")],
    ):
        received_event = True
    if not received_event:
        raise RuntimeError("the model returned no events")
