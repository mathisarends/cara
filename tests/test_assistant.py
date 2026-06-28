import asyncio
from pathlib import Path

from cara.assistant import AssistantConfig, AsyncOpenAIChat, VoiceAssistant


class FakeResponses:
    def __init__(self) -> None:
        self.kwargs = None

    async def create(self, **kwargs):
        self.kwargs = kwargs
        return {"output_text": "Das ist die Antwort."}


class FakeTranscriptions:
    def __init__(self) -> None:
        self.kwargs = None

    async def create(self, **kwargs):
        self.kwargs = kwargs
        return {"text": "Wie spät ist es?"}


class FakeSpeech:
    def __init__(self) -> None:
        self.kwargs = None

    async def create(self, **kwargs):
        self.kwargs = kwargs
        return b"wav-bytes"


class FakeAudio:
    def __init__(self) -> None:
        self.transcriptions = FakeTranscriptions()
        self.speech = FakeSpeech()


class FakeClient:
    def __init__(self) -> None:
        self.audio = FakeAudio()
        self.responses = FakeResponses()


class FakeRecorder:
    def __init__(self, audio_path: Path) -> None:
        self.audio_path = audio_path

    async def record_until_silence(self) -> Path:
        return self.audio_path


class FakePlayer:
    def __init__(self) -> None:
        self.played_path = None

    async def play(self, audio_path: str | Path) -> None:
        self.played_path = Path(audio_path)


def test_openai_chat_uses_responses_api() -> None:
    asyncio.run(_run_openai_chat_test())


async def _run_openai_chat_test() -> None:
    client = FakeClient()

    answer = await AsyncOpenAIChat(client, model="gpt-test").reply("Hallo", instructions="Sei kurz.")

    assert answer == "Das ist die Antwort."
    assert client.responses.kwargs == {
        "model": "gpt-test",
        "instructions": "Sei kurz.",
        "input": "Hallo",
    }


def test_voice_assistant_runs_wake_turn(tmp_path: Path) -> None:
    asyncio.run(_run_voice_assistant_test(tmp_path))


async def _run_voice_assistant_test(tmp_path: Path) -> None:
    input_path = tmp_path / "input.wav"
    input_path.write_bytes(b"fake wav")
    client = FakeClient()
    player = FakePlayer()
    assistant = VoiceAssistant(
        client=client,
        recorder=FakeRecorder(input_path),
        player=player,
        config=AssistantConfig(llm_model="gpt-test", language="de", tts_output_dir=tmp_path),
    )

    turn = await assistant.handle_wake_word()

    assert turn is not None
    assert turn.audio_path == input_path
    assert turn.transcript == "Wie spät ist es?"
    assert turn.answer == "Das ist die Antwort."
    assert turn.speech_path.read_bytes() == b"wav-bytes"
    assert player.played_path == turn.speech_path
    assert client.audio.transcriptions.kwargs["file"].name == str(input_path)
    assert client.audio.transcriptions.kwargs["language"] == "de"
    assert client.audio.speech.kwargs["input"] == "Das ist die Antwort."
    assert client.audio.speech.kwargs["response_format"] == "wav"
