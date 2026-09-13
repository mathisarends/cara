from cli import commands
from cli.chat import _headline, _result_lines


def test_the_first_argument_carries_the_call_and_the_rest_stay_named():
    headline = _headline({"query": "deploy checklist", "limit": 5, "recent": True})

    assert headline == "deploy checklist · limit=5, recent=True"


def test_a_lone_argument_is_shown_bare():
    assert _headline({"path": "Daily/2026-08-30.md"}) == "Daily/2026-08-30.md"


def test_a_call_without_arguments_has_no_headline():
    assert _headline({}) == ""


def test_a_long_result_is_cut_short_and_the_rest_counted():
    lines = _result_lines("one\ntwo\nthree\nfour\nfive\nsix")

    assert lines == ["one", "two", "three", "four", "+2 more lines"]


def test_an_empty_result_renders_nothing():
    assert _result_lines("   \n\n") == []


def test_a_non_string_result_still_renders():
    assert _result_lines({"ok": True}) == ["{'ok': True}"]


def test_every_command_the_dispatcher_knows_is_offered_and_documented():
    offered = {suggestion.value for suggestion in commands.suggest("/")}

    assert offered == {command.name for command in commands.COMMANDS}
    assert all(command.summary for command in commands.COMMANDS)


def test_aliases_resolve_to_their_command():
    assert commands.find("/q") is commands.find("/quit")
    assert commands.find("/nope") is None


def test_an_argument_stops_the_completion():
    assert commands.suggest("/history 3") == []
