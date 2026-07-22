from collections.abc import Iterable
from typing import Self

from llmify import ChatModel

from cara.llm.models import ModelProfile

_DEFAULT_PROFILE_NAME = "default"
_DEFAULT_PROFILE_DESCRIPTION = "General-purpose language model used for everyday conversation."


class LanguageModels:
    """The language model profiles the assistant can switch between at runtime.

    Exactly one profile is active at a time; :meth:`current` returns its
    :class:`ChatModel`, and :meth:`select` swaps which profile is active.
    """

    def __init__(self, profiles: Iterable[ModelProfile], *, active: str | None = None) -> None:
        self._profiles: dict[str, ModelProfile] = {profile.name: profile for profile in profiles}
        if not self._profiles:
            raise ValueError("LanguageModels requires at least one model profile.")
        self._active = active if active is not None else next(iter(self._profiles))
        if self._active not in self._profiles:
            raise ValueError(f"Unknown active model profile {active!r}.")

    @classmethod
    def single(
        cls,
        model: ChatModel,
        *,
        name: str = _DEFAULT_PROFILE_NAME,
        description: str = _DEFAULT_PROFILE_DESCRIPTION,
    ) -> Self:
        return cls([ModelProfile(name=name, description=description, model=model)])

    def current(self) -> ChatModel:
        return self._profiles[self._active].model

    def active(self) -> ModelProfile:
        return self._profiles[self._active]

    def get(self, name: str) -> ModelProfile | None:
        return self._profiles.get(name)

    def select(self, name: str) -> ModelProfile:
        profile = self._profiles.get(name)
        if profile is None:
            available = ", ".join(self._profiles)
            raise ValueError(f"Unknown language model {name!r}. Available: {available}.")
        self._active = name
        return profile

    def profiles(self) -> list[ModelProfile]:
        return list(self._profiles.values())

    def names(self) -> list[str]:
        return list(self._profiles)
