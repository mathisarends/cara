from voice.handler.command import _prepare_command
from voice.wakeword import WakeWordSettings


def test_wake_word_is_stripped_from_command_by_default() -> None:
    settings = WakeWordSettings()

    assert settings.strip_from_command is True
    assert (
        _prepare_command(
            "  Hey Mycroft, turn on the lights  ",
            "hey mycroft",
            strip_wake_word=settings.strip_from_command,
        )
        == "turn on the lights"
    )


def test_wake_word_can_be_preserved_in_command() -> None:
    settings = WakeWordSettings(strip_from_command=False)

    assert (
        _prepare_command(
            "  Hey Mycroft, turn on the lights  ",
            "hey mycroft",
            strip_wake_word=settings.strip_from_command,
        )
        == "Hey Mycroft, turn on the lights"
    )
