from cli import commands
from cli.console import Console


def interactive() -> Console:
    return Console(color=False, interactive=True, completer=commands.suggest)


def test_the_menu_lists_every_command_matching_what_is_typed():
    console = interactive()
    for character in "/s":
        console.type(character)

    rows = console._menu_rows()

    assert [row.strip().split("  ")[0] for row in rows] == ["/session"]


def test_a_plain_message_gets_no_menu():
    console = interactive()
    console.type("hallo")

    assert console._menu_rows() == []


def test_tab_writes_the_match_into_the_input_line():
    console = interactive()
    for character in "/se":
        console.type(character)

    console.complete()

    assert console.input == "/session"


def test_further_tabs_walk_the_matches_frozen_at_the_first_one():
    console = interactive()
    console.type("/")

    console.complete()
    first = console.input
    console.complete()
    second = console.input

    assert first == commands.COMMANDS[0].name
    assert second == commands.COMMANDS[1].name


def test_tab_on_something_that_matches_nothing_leaves_the_line_alone():
    console = interactive()
    console.type("/nope")

    console.complete()

    assert console.input == "/nope"


def test_typing_after_a_tab_starts_a_fresh_cycle():
    console = interactive()
    console.type("/")
    console.complete()

    console.backspace()
    console.complete()

    assert console.input == commands.COMMANDS[0].name


def test_the_hint_stays_out_of_the_line_the_user_types_on():
    console = interactive()
    console.set_hint("type a message")

    assert console._prompt_row() == "you › "
    assert console._hint_rows() == ["  type a message"]


def test_the_hint_gives_way_as_soon_as_something_is_typed():
    console = interactive()
    console.set_hint("type a message")

    console.type("h")

    assert console._hint_rows() == []
    assert console._prompt_row() == "you › h"


def test_output_carries_no_escape_codes_without_a_terminal(capsys):
    console = Console(color=False, interactive=False)
    console.header("gateway client")
    console.field("gateway", "ws://localhost")
    console.tool_call("read_note", "Daily/2026-08-30.md")
    console.tool_result(["87 lines"], failed=False)

    printed = capsys.readouterr().out

    assert "\x1b" not in printed
    assert "gateway  ws://localhost" in printed
    assert "● read_note  Daily/2026-08-30.md" in printed
    assert "↳ 87 lines" in printed


def test_a_failed_result_is_marked_apart_from_a_successful_one(capsys):
    console = Console(color=False, interactive=False)
    console.tool_result(["boom"], failed=True)

    assert "✗ boom" in capsys.readouterr().out
