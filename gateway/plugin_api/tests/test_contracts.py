from uuid import uuid4

from agent_plugin_api import (
    AGENT_PLUGIN_API_VERSION,
    AgentChannelRef,
    AgentRunRequest,
    AgentSessionRef,
)


def test_run_request_keeps_turn_and_input_identity_separate() -> None:
    session_id = uuid4()
    turn_id = uuid4()
    input_id = uuid4()

    request = AgentRunRequest(
        session=AgentSessionRef(session_id, AgentChannelRef("voice", "local")),
        turn_id=turn_id,
        input_id=input_id,
        input="Hello",
    )

    assert request.session.id == session_id
    assert request.turn_id == turn_id
    assert request.input_id == input_id
    assert request.input == "Hello"
    assert AGENT_PLUGIN_API_VERSION == 2
