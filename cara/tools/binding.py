from collections.abc import Callable

from cara.tools.di import ToolContext
from cara.tools.views import ToolAvailability, ToolDescription


def provided[T](dependency: type[T]) -> ToolAvailability:
    return lambda context: context.resolve(dependency) is not None


def requires[T](dependency: type[T], predicate: Callable[[T], bool]) -> ToolAvailability:
    def available(context: ToolContext) -> bool:
        resolved = context.resolve(dependency)
        return resolved is not None and predicate(resolved)

    return available


def described[T](dependency: type[T], render: Callable[[T], str], *, default: str) -> ToolDescription:
    def describe(context: ToolContext) -> str:
        resolved = context.resolve(dependency)
        return default if resolved is None else render(resolved)

    return describe
