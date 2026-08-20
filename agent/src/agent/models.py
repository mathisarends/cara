from typing import Self

from llmify import ChatModel


class ModelSwitch:
    """The model driving the agent, swappable by name between turns."""

    def __init__(self, models: dict[str, ChatModel], *, default: str) -> None:
        if default not in models:
            raise ValueError(f"Unknown default model '{default}'.")
        self._models = models
        self._current = default

    @classmethod
    def single(cls, model: ChatModel, *, name: str = "default") -> Self:
        return cls({name: model}, default=name)

    @property
    def current(self) -> ChatModel:
        return self._models[self._current]

    @property
    def current_name(self) -> str:
        return self._current

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(self._models)

    @property
    def has_alternatives(self) -> bool:
        return len(self._models) > 1

    def switch(self, name: str) -> None:
        if name not in self._models:
            available = ", ".join(self._models)
            raise ValueError(f"Unknown model '{name}'. Available: {available}.")
        self._current = name
