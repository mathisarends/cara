import asyncio

from transitbus import EventBus

from voice import VoiceSession


class _Responder:
    async def respond(self, text, *, on_interim_response=None):
        assert text == "Starte die Aufgabe"
        assert on_interim_response is not None
        await on_interim_response("Ich schaue das nach.")
        return "Die Aufgabe ist erledigt."


class _SpeechInput:
    def __init__(self) -> None:
        self._responses = iter(("Starte die Aufgabe", None))

    async def receive(self, **options):
        return next(self._responses)


class _SpeechOutput:
    def __init__(self) -> None:
        self.messages: list[str] = []

    async def send(self, text, *, cancel=None):
        self.messages.append(text)


class _WakeWordListener:
    async def detect_once(self, *, cancel=None):
        assert cancel is not None
        await cancel.wait()
        return None


class _Earcons:
    async def play(self, earcon):
        return None


def test_voice_session_speaks_interim_response_before_final_answer() -> None:
    async def run() -> list[str]:
        speech_output = _SpeechOutput()
        session = VoiceSession(
            agent=_Responder(),
            speech_input=_SpeechInput(),
            speech_output=speech_output,
            wake_word_listener=_WakeWordListener(),
            event_bus=EventBus(),
            earcons=_Earcons(),
        )

        await session.run_once()
        return speech_output.messages

    assert asyncio.run(run()) == [
        "Ich schaue das nach.",
        "Die Aufgabe ist erledigt.",
    ]
