import asyncio

from llmify import ChatModel
from llmify.views import ChatInvokeCompletion

from cara.assistant import VoiceAssistant
from cara.lifecycle import (
    AnswerGenerated,
    AssistantEvent,
    AssistantLifecycleListener,
    AssistantState,
    StateChanged,
    Transcribed,
    TurnCompleted,
    TurnStarted,
)


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


class FakeChat(ChatModel):
    def __init__(self) -> None:
        super().__init__(model="gpt-test")
        self.messages = None

    async def invoke(self, messages, output_format=None, **kwargs):
        self.messages = messages
        return ChatInvokeCompletion(completion="Das ist die Antwort.")

    async def stream(self, messages, tools=None, tool_choice="auto", **kwargs):
        raise NotImplementedError


class FakeRecorder:
    def __init__(self, audio: bytes) -> None:
        self.audio = audio

    async def record_until_silence(self) -> bytes:
        return self.audio


class FakePlayer:
    def __init__(self) -> None:
        self.played_audio = None

    async def play(self, audio: bytes) -> None:
        self.played_audio = audio


class RecordingListener(AssistantLifecycleListener):
    def __init__(self) -> None:
        self.events: list[AssistantEvent] = []

    async def on_event(self, event: AssistantEvent) -> None:
        self.events.append(event)


def test_voice_assistant_runs_wake_turn() -> None:
    asyncio.run(_run_voice_assistant_test())


async def _run_voice_assistant_test() -> None:
    utterance = b"fake wav bytes"
    client = FakeClient()
    chat = FakeChat()
    player = FakePlayer()
    listener = RecordingListener()
    assistant = VoiceAssistant(
        client=client,
        llm=chat,
        recorder=FakeRecorder(utterance),
        player=player,
        listeners=[listener],
        language="de",
    )

    turn = await assistant.run_turn()

    assert turn is not None
    assert turn.utterance_audio == utterance
    assert turn.transcript == "Wie spät ist es?"
    assert turn.answer == "Das ist die Antwort."
    assert turn.answer_audio == b"wav-bytes"
    assert player.played_audio == b"wav-bytes"

    sent_file = client.audio.transcriptions.kwargs["file"]
    assert sent_file == ("utterance.wav", utterance)
    assert client.audio.transcriptions.kwargs["language"] == "de"
    assert client.audio.speech.kwargs["input"] == "Das ist die Antwort."
    assert client.audio.speech.kwargs["response_format"] == "wav"
    assert [m.text for m in chat.messages] == [assistant.system_prompt, "Wie spät ist es?"]

    # Lifecycle events fire in order and end back at IDLE.
    assert isinstance(listener.events[0], TurnStarted)
    states = [e.state for e in listener.events if isinstance(e, StateChanged)]
    assert states == [
        AssistantState.LISTENING,
        AssistantState.TRANSCRIBING,
        AssistantState.THINKING,
        AssistantState.SPEAKING,
        AssistantState.IDLE,
    ]
    assert any(isinstance(e, Transcribed) and e.transcript == turn.transcript for e in listener.events)
    assert any(isinstance(e, AnswerGenerated) and e.answer == turn.answer for e in listener.events)
    assert any(isinstance(e, TurnCompleted) and e.turn is turn for e in listener.events)
    assert assistant.state is AssistantState.IDLE
