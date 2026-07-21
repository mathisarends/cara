from cara.tools import BashPolicy


def test_bash_policy_allows_configured_prefix() -> None:
    assert BashPolicy(("git status",)).check("git status --short") is None


def test_bash_policy_rejects_shell_syntax() -> None:
    denial = BashPolicy(("git",)).check("git status && git log")

    assert denial is not None
    assert "Shell operators" in denial.message
