from cara.tools.binding import described, provided, requires
from cara.tools.di import ToolContext


class Dependency:
    def __init__(self, size: int) -> None:
        self.size = size


def test_provided_is_true_only_when_the_dependency_is_present() -> None:
    assert provided(Dependency)(ToolContext(Dependency(2))) is True
    assert provided(Dependency)(ToolContext()) is False


def test_requires_evaluates_the_predicate_against_the_resolved_dependency() -> None:
    available = requires(Dependency, predicate=lambda dependency: dependency.size > 1)

    assert available(ToolContext(Dependency(2))) is True
    assert available(ToolContext(Dependency(1))) is False


def test_requires_is_none_safe_and_skips_the_predicate_when_unresolved() -> None:
    calls: list[Dependency] = []
    available = requires(Dependency, predicate=lambda dependency: calls.append(dependency) or True)

    assert available(ToolContext()) is False
    assert calls == []


def test_described_renders_from_the_dependency_or_falls_back_to_the_default() -> None:
    describe = described(Dependency, render=lambda dependency: f"size {dependency.size}", default="fallback")

    assert describe(ToolContext(Dependency(5))) == "size 5"
    assert describe(ToolContext()) == "fallback"
