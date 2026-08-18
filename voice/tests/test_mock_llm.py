import asyncio

from voice.llm import EchoAgentSession, TextDelta, TurnCompleted


def test_echo_agent_session_streams_prefixed_input() -> None:
    async def run() -> list[TextDelta | TurnCompleted]:
        events = await EchoAgentSession().start_turn("Hallo Cara")
        return [event async for event in events]

    events = asyncio.run(run())

    assert (
        "".join(event.text for event in events if isinstance(event, TextDelta))
        == "Du hast gesagt: Hallo Cara"
    )
    assert isinstance(events[-1], TurnCompleted)
