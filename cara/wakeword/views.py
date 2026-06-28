from enum import StrEnum


class WakeWord(StrEnum):
    ALEXA = "alexa"
    HEY_MYCROFT = "hey mycroft"
    HEY_RHASSPY = "hey rhasspy"


WAKE_WORD_MODEL: dict[WakeWord, str] = {
    WakeWord.ALEXA: "alexa",
    WakeWord.HEY_MYCROFT: "hey_mycroft",
    WakeWord.HEY_RHASSPY: "hey_rhasspy",
}
