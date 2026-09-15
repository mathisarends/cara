from agenttoolkit import Tools

from .filesystem import register_filesystem_tools
from .model_control import register_model_control_tools
from .reminders import register_reminder_tools
from .shell import register_shell_tools
from .skills import register_skill_tools
from .time import register_time_tools

__all__ = ["register_tools"]


def register_tools(tools: Tools) -> None:
    for register in (
        register_skill_tools,
        register_model_control_tools,
        register_time_tools,
        register_shell_tools,
        register_filesystem_tools,
        register_reminder_tools,
    ):
        register(tools)
