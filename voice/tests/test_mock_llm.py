import asyncio

from voice.llm import EchoLanguageModel


def test_echo_language_model_streams_prefixed_input() -> None:
    async def run() -> list[str]:
        return [chunk async for chunk in EchoLanguageModel().respond("Hallo Cara")]

    chunks = asyncio.run(run())

    assert "".join(chunks) == "Du hast gesagt: Hallo Cara"
