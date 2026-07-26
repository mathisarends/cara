from cara.tools.handler import BashCommandPolicy


def test_bash_command_policy_allows_command_without_configured_prefixes() -> None:
    assert BashCommandPolicy().check("git status --short") is None


def test_bash_command_policy_temporarily_allows_shell_syntax() -> None:
    assert BashCommandPolicy(("git",)).check("git status && git log") is None
