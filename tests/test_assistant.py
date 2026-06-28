import asyncio

from llmify import ChatModel
from llmify.views import ChatInvokeCompletion

from cara.assistant import VoiceAssistant
from cara.conversation import Conversation
from cara.events import EventBus
from cara.lifecycle import (
    AnswerGenerated,
    AssistantEvent,
    AssistantState,
    SessionEnded,
    SessionStarted,
    StateChanged,
    Transcribed,
    TurnCompleted,
    TurnStarted,
)


class FakeTranscriptions:
    def __init__(self, texts: list[str] | None = None) -> None:
        self.kwargs = None
        self._texts = texts or ["Wie spaet ist es?"]

    async def create(self, **kwargs):
        self.kwargs = kwargs
        return {"text": self._texts.pop(0)}


class FakeSpeech:
    def __init__(self) -> None:
        self.kwargs = None

    async def create(self, **kwargs):
        self.kwargs = kwargs
        return b"wav-bytes"


class FakeAudio:
    def __init__(self, texts: list[str] | None = None) -> None:
        self.transcriptions = FakeTranscriptions(texts)
        self.speech = FakeSpeech()


class FakeClient:
    def __init__(self, texts: list[str] | None = None) -> None:
        self.audio = FakeAudio(texts)


class FakeChat(ChatModel):
    def __init__(self, completions: list[str] | None = None) -> None:
        super().__init__(model="gpt-test")
        self.messages = None
        self.calls = []
        self._completions = completions or ["Das ist die Antwort."]

    async def invoke(self, messages, output_format=None, **kwargs):
        self.messages = messages
        self.calls.append(messages)
        return ChatInvokeCompletion(completion=self._completions.pop(0))

    async def stream(self, messages, tools=None, tool_choice="auto", **kwargs):
        raise NotImplementedError


class FakeRecorder:
    def __init__(self, audio: bytes | list[bytes | None]) -> None:
        self.audio = audio
        self.initial_silence_timeouts = []

    async def record_until_silence(self, *, initial_silence_timeout=None) -> bytes | None:
        self.initial_silence_timeouts.append(initial_silence_timeout)
        if isinstance(self.audio, list):
            return self.audio.pop(0)
        return self.audio


class FakePlayer:
    def __init__(self) -> None:
        self.played_audio = None

    async def play(self, audio: bytes, *, cancel=None) -> None:
        self.played_audio = audio


class RecordingEvents:
    def __init__(self, event_bus: EventBus) -> None:
        self.events: list[AssistantEvent] = []
        event_bus.subscribe_all(self.record)

    async def record(self, event: AssistantEvent) -> None:
        self.events.append(event)


def test_voice_assistant_runs_wake_turn() -> None:
    asyncio.run(_run_voice_assistant_test())


def test_event_bus_waits_for_matching_event() -> None:
    asyncio.run(_run_event_bus_wait_test())


async def _run_event_bus_wait_test() -> None:
    events = EventBus()
    waiter = asyncio.create_task(
        events.wait_for_event(
            Transcribed,
            timeout=1,
            predicate=lambda event: event.transcript == "weiter",
        )
    )
    await asyncio.sleep(0)

    await events.dispatch(Transcribed("ignorieren"))
    await events.dispatch(Transcribed("weiter"))

    assert (await waiter).transcript == "weiter"


def test_event_bus_keeps_dispatching_when_handler_fails() -> None:
    asyncio.run(_run_event_bus_handler_failure_test())


async def _run_event_bus_handler_failure_test() -> None:
    events = EventBus()
    received: list[AssistantState] = []

    async def failing_handler(event: StateChanged) -> None:
        raise RuntimeError("boom")

    async def recording_handler(event: StateChanged) -> None:
        received.append(event.state)

    events.subscribe(StateChanged, failing_handler)
    events.subscribe(StateChanged, recording_handler)

    await events.dispatch(StateChanged(AssistantState.LISTENING))

    assert received == [AssistantState.LISTENING]


async def _run_voice_assistant_test() -> None:
    utterance = b"fake wav bytes"
    client = FakeClient()
    chat = FakeChat()
    player = FakePlayer()
    events = EventBus()
    listener = RecordingEvents(events)
    assistant = VoiceAssistant(
        client=client,
        llm=chat,
        recorder=FakeRecorder(utterance),
        player=player,
        event_bus=events,
        language="de",
    )

    turn = await assistant.run_turn()

    assert turn is not None
    assert turn.utterance_audio == utterance
    assert turn.transcript == "Wie spaet ist es?"
    assert turn.answer == "Das ist die Antwort."
    assert turn.answer_audio == b"wav-bytes"
    assert player.played_audio == b"wav-bytes"

    sent_file = client.audio.transcriptions.kwargs["file"]
    assert sent_file == ("utterance.wav", utterance)
    assert client.audio.transcriptions.kwargs["language"] == "de"
    assert client.audio.speech.kwargs["input"] == "Das ist die Antwort."
    assert client.audio.speech.kwargs["response_format"] == "wav"
    assert [m.text for m in chat.messages] == [assistant.system_prompt, "Wie spaet ist es?"]

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


def test_conversation_keeps_sliding_window() -> None:
    conversation = Conversation(system_prompt="sys", max_turns=1)

    conversation.add_user("eins")
    conversation.add_assistant("zwei")
    conversation.add_user("drei")

    assert [m.text for m in conversation.to_llm_messages()] == ["sys", "zwei", "drei"]


def test_voice_assistant_runs_multi_turn_session_until_silence() -> None:
    asyncio.run(_run_voice_assistant_session_test())


async def _run_voice_assistant_session_test() -> None:
    client = FakeClient(texts=["Merke dir Berlin.", "Welche Stadt war das?"])
    chat = FakeChat(completions=["Okay.", "Berlin."])
    recorder = FakeRecorder([b"first wav", b"second wav", None])
    events = EventBus()
    listener = RecordingEvents(events)
    assistant = VoiceAssistant(
        client=client,
        llm=chat,
        recorder=recorder,
        player=FakePlayer(),
        event_bus=events,
        follow_up_timeout_seconds=6.5,
    )

    session = await assistant.run_session()

    assert [turn.transcript for turn in session.turns] == [
        "Merke dir Berlin.",
        "Welche Stadt war das?",
    ]
    assert [turn.answer for turn in session.turns] == ["Okay.", "Berlin."]
    assert recorder.initial_silence_timeouts == [None, 6.5, 6.5]
    assert [m.text for m in chat.calls[1]] == [
        assistant.system_prompt,
        "Merke dir Berlin.",
        "Okay.",
        "Welche Stadt war das?",
    ]
    assert isinstance(listener.events[0], SessionStarted)
    assert any(isinstance(e, SessionEnded) for e in listener.events)
    assert assistant.state is AssistantState.IDLE
