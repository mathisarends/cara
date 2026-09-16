from agent.nudges import ProgressNudges
from llm import ToolResultMessage


class _Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def _result(name: str, *, is_error: bool = False) -> ToolResultMessage:
    return ToolResultMessage(
        tool_call_id=name, tool_name=name, content="out", is_error=is_error
    )


def test_repeated_failures_of_one_tool_are_reported_once() -> None:
    nudges = ProgressNudges(clock=_Clock())

    first = nudges.annotate([_result("hue", is_error=True)])
    second = nudges.annotate([_result("hue", is_error=True), _result("sonos")])
    third = nudges.annotate([_result("hue", is_error=True)])

    assert first[0].content == "out"
    assert second[0].content == "out"
    assert second[1].content.startswith(
        "out\n\n[Runtime note] `hue` has failed 2 times"
    )
    assert third[0].content == "out"


def test_failures_of_different_tools_are_counted_separately() -> None:
    nudges = ProgressNudges(clock=_Clock())

    results = nudges.annotate(
        [_result("hue", is_error=True), _result("sonos", is_error=True)]
    )

    assert [result.content for result in results] == ["out", "out"]


def test_long_silence_is_reported_and_rearmed() -> None:
    clock = _Clock()
    nudges = ProgressNudges(clock=clock)

    clock.now = 19.0
    assert nudges.annotate([_result("hue")])[0].content == "out"

    clock.now = 21.0
    assert "working for 21 seconds" in nudges.annotate([_result("hue")])[0].content

    clock.now = 30.0
    assert nudges.annotate([_result("hue")])[0].content == "out"


def test_spoken_update_resets_silence() -> None:
    clock = _Clock()
    nudges = ProgressNudges(clock=clock)

    clock.now = 15.0
    nudges.record_update()
    clock.now = 30.0

    assert nudges.annotate([_result("hue")])[0].content == "out"
