import asyncio

from voice.llm import StreamingEchoLLM


def test_streaming_echo_llm_streams_input_unchanged() -> None:
    async def run() -> list[str]:
        return [chunk async for chunk in StreamingEchoLLM().stream("Hallo Cara")]

    chunks = asyncio.run(run())

    assert chunks == list("Hallo Cara")
    assert "".join(chunks) == "Hallo Cara"
