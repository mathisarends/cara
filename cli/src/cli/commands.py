"""The slash commands the chat loop understands.

One list feeds three consumers - `/help`, the completion menu, and the
dispatcher in `chat.py` - so a command cannot appear in one and be missing
from another.
"""

from collections.abc import Sequence
from dataclasses import dataclass

from cli.console import Suggestion


@dataclass(frozen=True, slots=True)
class Command:
    name: str
    summary: str
    aliases: tuple[str, ...] = ()

    @property
    def names(self) -> tuple[str, ...]:
        return (self.name, *self.aliases)


COMMANDS: tuple[Command, ...] = (
    Command("/new", "start a fresh session on the channel"),
    Command("/session", "show the current session id"),
    Command("/history", "replay the session snapshot from the gateway"),
    Command("/events", "toggle the raw event trace"),
    Command("/cancel", "interrupt the running turn"),
    Command("/help", "list these commands", aliases=("/h",)),
    Command("/quit", "leave (ctrl-c works too)", aliases=("/exit", "/q")),
)


def find(name: str) -> Command | None:
    """The command a typed word names, following aliases."""
    return next((command for command in COMMANDS if name in command.names), None)


def suggest(text: str) -> Sequence[Suggestion]:
    """Completions for a half-typed command line.

    Only the command word completes: once there is a space the rest of the
    line is an argument the console has nothing to say about.
    """
    if not text.startswith("/") or " " in text:
        return []
    return [
        Suggestion(value=command.name, label=command.name, detail=command.summary)
        for command in COMMANDS
        if command.name.startswith(text)
    ]


def help_text() -> str:
    width = max(len(command.name) for command in COMMANDS)
    return "\n".join(
        f"{command.name:<{width}}  {command.summary}" for command in COMMANDS
    )
