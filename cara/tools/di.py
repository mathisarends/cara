from typing import TYPE_CHECKING, Annotated, Any, Self, final


@final
class _InjectMarker:
    def __repr__(self) -> str:
        return "ToolContext.Inject"


@final
class ToolContext:
    _marker_instance: _InjectMarker | None = None

    if TYPE_CHECKING:
        type Inject[T] = T
    else:

        class Inject:
            def __class_getitem__(cls, item: Any) -> Any:
                return Annotated[item, ToolContext._get_marker()]

    @staticmethod
    def _get_marker() -> "_InjectMarker":
        if ToolContext._marker_instance is None:
            ToolContext._marker_instance = _InjectMarker()
        return ToolContext._marker_instance

    def __init__(self, *dependencies: Any) -> None:
        self._dependencies: list[Any] = list(dependencies)

    def provide(self, *dependencies: Any) -> Self:
        self._dependencies.extend(dependencies)
        return self

    def clear(self) -> Self:
        self._dependencies.clear()
        return self

    def resolve[T](self, expected_type: type[T]) -> T | None:
        for dependency in self._dependencies:
            if isinstance(dependency, expected_type):
                return dependency
        return None

    def __len__(self) -> int:
        return len(self._dependencies)


Inject = ToolContext.Inject
