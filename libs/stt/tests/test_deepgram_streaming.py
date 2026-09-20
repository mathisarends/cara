from typing import Any, cast

import pytest
from conftest import (
    ConnectedMessage,
    FakeConnection,
    FakeDeepgramClient,
    FatalErrorMessage,
    TurnInfoMessage,
)

from stt.deepgram import (
    SpeechToText,
    SpeechToTextError,
    StreamingSpeechToTextConfig,
    StreamingSpeechToTextEncoding,
)
from stt.deepgram.events import Connected, TurnEagerEnd, TurnEnd, TurnStart, TurnUpdate


def build_listener(
    connection: FakeConnection, **kwargs: Any
) -> tuple[SpeechToText, FakeDeepgramClient]:
    client = FakeDeepgramClient(connection)
    return SpeechToText(client=cast(Any, client), **kwargs), client


async def test_stream_maps_the_turn_lifecycle_to_typed_events(audio_stream) -> None:
    connection = FakeConnection(
        [
            ConnectedMessage(request_id="request-id"),
            TurnInfoMessage(event="StartOfTurn"),
            TurnInfoMessage(event="Update", transcript="hallo"),
            TurnInfoMessage(event="EagerEndOfTurn", transcript="hallo welt"),
            TurnInfoMessage(
                event="EndOfTurn", transcript="hallo welt", end_of_turn_confidence=0.9
            ),
        ]
    )
    listener, _ = build_listener(connection)

    events = [event async for event in listener.stream(audio_stream(b"\x00\x01"))]

    assert [type(event) for event in events] == [
        Connected,
        TurnStart,
        TurnUpdate,
        TurnEagerEnd,
        TurnEnd,
    ]
    assert events[-1].transcript == "hallo welt"
    assert events[-1].end_of_turn_confidence == 0.9


async def test_stream_forwards_audio_and_closes_the_deepgram_stream(
    audio_stream,
) -> None:
    connection = FakeConnection([ConnectedMessage(request_id="request-id")])
    listener, _ = build_listener(connection)

    async for _ in listener.stream(audio_stream(b"\x00", b"", b"\x01")):
        pass

    assert connection.audio == [b"\x00", b"\x01"]
    assert [control.type for control in connection.controls] == ["CloseStream"]
    assert connection.closed


async def test_stream_sends_every_option_as_a_query_parameter(audio_stream) -> None:
    connection = FakeConnection([ConnectedMessage(request_id="request-id")])
    listener, client = build_listener(
        connection,
        encoding=StreamingSpeechToTextEncoding.MULAW,
        sample_rate=8000,
        keyterms=["Cara"],
        eot_timeout_ms=2000,
    )

    async for _ in listener.stream(audio_stream(b"\x00")):
        pass

    assert client.v2.calls == [
        {
            "model": "flux-general-en",
            "encoding": "mulaw",
            "sample_rate": "8000",
            "keyterm": ["Cara"],
            "eot_timeout_ms": "2000",
        }
    ]


async def test_stream_prefers_the_per_call_config(audio_stream) -> None:
    connection = FakeConnection([ConnectedMessage(request_id="request-id")])
    listener, client = build_listener(connection, sample_rate=8000)
    config = StreamingSpeechToTextConfig(model="flux-general-multi", sample_rate=24000)

    async for _ in listener.stream(audio_stream(b"\x00"), config=config):
        pass

    assert client.v2.calls[0]["model"] == "flux-general-multi"
    assert client.v2.calls[0]["sample_rate"] == "24000"


async def test_stream_raises_the_deepgram_error_code(audio_stream) -> None:
    connection = FakeConnection(
        [FatalErrorMessage(code="RATE_LIMIT", description="too many requests")]
    )
    listener, _ = build_listener(connection)

    with pytest.raises(SpeechToTextError, match="too many requests") as error:
        async for _ in listener.stream(audio_stream(b"\x00")):
            pass

    assert error.value.error_code == "RATE_LIMIT"


async def test_stream_rejects_an_audio_stream_without_payload(audio_stream) -> None:
    connection = FakeConnection([])
    listener, _ = build_listener(connection)

    with pytest.raises(ValueError, match="at least one non-empty chunk"):
        async for _ in listener.stream(audio_stream(b"")):
            pass


async def test_stream_propagates_a_send_failure(audio_stream) -> None:
    connection = FakeConnection([], send_error=RuntimeError("socket gone"))
    listener, _ = build_listener(connection)

    with pytest.raises(RuntimeError, match="socket gone"):
        async for _ in listener.stream(audio_stream(b"\x00")):
            pass


async def test_stream_rejects_unknown_turn_events(audio_stream) -> None:
    connection = FakeConnection([TurnInfoMessage(event="Levitation")])
    listener, _ = build_listener(connection)

    with pytest.raises(ValueError, match="Levitation"):
        async for _ in listener.stream(audio_stream(b"\x00")):
            pass


async def test_stream_rejects_unknown_message_types(audio_stream) -> None:
    connection = FakeConnection([ConnectedMessage(type="Metadata", request_id="r")])
    listener, _ = build_listener(connection)

    with pytest.raises(ValueError, match="Metadata"):
        async for _ in listener.stream(audio_stream(b"\x00")):
            pass


def test_api_key_and_client_are_mutually_exclusive() -> None:
    client = FakeDeepgramClient(FakeConnection([]))

    with pytest.raises(ValueError, match="not both"):
        SpeechToText("key", client=cast(Any, client))


async def test_aclose_leaves_an_injected_client_untouched() -> None:
    listener, _ = build_listener(FakeConnection([]))

    await listener.aclose()


async def test_aclose_closes_the_owned_transport() -> None:
    async with SpeechToText("key") as listener:
        http_client = listener._http_client
        assert http_client is not None

    assert http_client.is_closed
    assert listener._http_client is None
