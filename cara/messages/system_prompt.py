from importlib import resources


def _read_default_system_prompt() -> str:
    return resources.files("cara.messages").joinpath("system_prompt.md").read_text(encoding="utf-8").strip()


class SystemPrompt:
    """System prompt loaded from the package markdown file."""

    def __init__(
        self,
        *,
        override_system_prompt: str | None = None,
        extend_system_prompt: str | None = None,
    ) -> None:
        if override_system_prompt is not None and extend_system_prompt is not None:
            raise ValueError("Use either override_system_prompt or extend_system_prompt, not both.")
        self._override_system_prompt = override_system_prompt
        self._extend_system_prompt = extend_system_prompt

    def render(self) -> str:
        if self._override_system_prompt is not None:
            return self._override_system_prompt.strip()

        prompt = _read_default_system_prompt()
        if self._extend_system_prompt is None:
            return prompt

        extension = self._extend_system_prompt.strip()
        if not extension:
            return prompt
        return f"{prompt}\n\n{extension}"

    def __str__(self) -> str:
        return self.render()
