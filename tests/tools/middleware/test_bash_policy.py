from cara.tools import BashPolicy


def test_bash_policy_allows_command_without_configured_prefixes() -> None:
    assert BashPolicy().check("git status --short") is None


def test_bash_policy_temporarily_allows_shell_syntax() -> None:
    assert BashPolicy(("git",)).check("git status && git log") is None
