from typing import Any, cast

import pytest
from conftest import FakeConnection, FakeDeepgramClient, FlushedMessage, WarningMessage

from tts.deepgram import (
    AudioEncoding,
    TextToSpeech,
    TextToSpeechConfig,
    TextToSpeechError,
)


def build_speech(
    connection: FakeConnection, **kwargs: Any
) -> tuple[TextToSpeech, FakeDeepgramClient]:
    client = FakeDeepgramClient(connection)
    return TextToSpeech(client=cast(Any, client), **kwargs), client


async def test_stream_incremental_yields_audio_until_deepgram_flushes(
    text_stream,
) -> None:
    connection = FakeConnection([b"aud", b"io", FlushedMessage(), b"never"])
    speech, _ = build_speech(connection)

    audio = [
        chunk
        async for chunk in speech.stream_incremental(text_stream("Hallo", " Welt"))
    ]

    assert audio == [b"aud", b"io"]
    assert connection.text == ["Hallo", " Welt"]
    assert [control.type for control in connection.controls] == ["Flush"]
    assert connection.closed


async def test_stream_incremental_skips_empty_text_chunks(text_stream) -> None:
    connection = FakeConnection([FlushedMessage()])
    speech, _ = build_speech(connection)

    async for _ in speech.stream_incremental(text_stream("Hallo", "", "Welt")):
        pass

    assert connection.text == ["Hallo", "Welt"]


async def test_stream_sends_the_whole_utterance_as_one_chunk() -> None:
    connection = FakeConnection([b"audio", FlushedMessage()])
    speech, _ = build_speech(connection)

    audio = [chunk async for chunk in speech.stream("Hallo Welt")]

    assert audio == [b"audio"]
    assert connection.text == ["Hallo Welt"]


async def test_stream_sends_every_option_as_a_query_parameter() -> None:
    connection = FakeConnection([FlushedMessage()])
    speech, client = build_speech(
        connection, encoding=AudioEncoding.MULAW, sample_rate=8000
    )

    async for _ in speech.stream("Hallo"):
        pass

    assert client.v1.calls == [
        {
            "model": "aura-2-thalia-en",
            "encoding": "mulaw",
            "sample_rate": "8000",
        }
    ]


async def test_stream_prefers_the_per_call_config() -> None:
    connection = FakeConnection([FlushedMessage()])
    speech, client = build_speech(connection, sample_rate=8000)
    config = TextToSpeechConfig(model="aura-2-zeus-en", sample_rate=24000)

    async for _ in speech.stream("Hallo", config=config):
        pass

    assert client.v1.calls[0]["model"] == "aura-2-zeus-en"
    assert client.v1.calls[0]["sample_rate"] == "24000"


async def test_stream_raises_the_deepgram_warning_code() -> None:
    connection = FakeConnection(
        [WarningMessage(warn_code="TEXT_TOO_LONG", warn_msg="text was truncated")]
    )
    speech, _ = build_speech(connection)

    with pytest.raises(TextToSpeechError, match="text was truncated") as error:
        async for _ in speech.stream("Hallo"):
            pass

    assert error.value.error_code == "TEXT_TOO_LONG"


@pytest.mark.parametrize(
    ("text", "message"),
    [("   ", "must not be blank"), ("a" * 2001, "2000 characters")],
)
async def test_stream_rejects_unusable_text(text: str, message: str) -> None:
    speech, _ = build_speech(FakeConnection([]))

    with pytest.raises(ValueError, match=message):
        async for _ in speech.stream(text):
            pass


async def test_stream_incremental_rejects_a_text_stream_without_payload(
    text_stream,
) -> None:
    speech, _ = build_speech(FakeConnection([]))

    with pytest.raises(ValueError, match="at least one non-empty chunk"):
        async for _ in speech.stream_incremental(text_stream("")):
            pass


async def test_stream_incremental_propagates_a_send_failure(text_stream) -> None:
    connection = FakeConnection([], send_error=RuntimeError("socket gone"))
    speech, _ = build_speech(connection)

    with pytest.raises(RuntimeError, match="socket gone"):
        async for _ in speech.stream_incremental(text_stream("Hallo")):
            pass


def test_api_key_and_client_are_mutually_exclusive() -> None:
    client = FakeDeepgramClient(FakeConnection([]))

    with pytest.raises(ValueError, match="not both"):
        TextToSpeech("key", client=cast(Any, client))


async def test_aclose_leaves_an_injected_client_untouched() -> None:
    speech, _ = build_speech(FakeConnection([]))

    await speech.aclose()


async def test_aclose_closes_the_owned_transport() -> None:
    async with TextToSpeech("key") as speech:
        http_client = speech._http_client
        assert http_client is not None

    assert http_client.is_closed
    assert speech._http_client is None
