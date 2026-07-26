from cara.tools.sandbox.models import BashSandboxConfig


class BashCommandPolicy:
    """Temporarily allows every command; configured commands are not enforced yet."""

    def __init__(self, config: BashSandboxConfig) -> None:
        self._allowed_commands = config.allowed_commands

    def check(self, command: str) -> str | None:
        del command
        return None
