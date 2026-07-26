from cara.tools import BashSandboxConfig
from cara.tools.sandbox import BashCommandPolicy


def test_bash_command_policy_allows_command_without_configured_prefixes() -> None:
    assert BashCommandPolicy(BashSandboxConfig()).check("git status --short") is None


def test_bash_command_policy_temporarily_allows_shell_syntax() -> None:
    config = BashSandboxConfig(allowed_commands=("git",))

    assert BashCommandPolicy(config).check("git status && git log") is None
