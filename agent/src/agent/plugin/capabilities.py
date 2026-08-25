from agent.tools.handler import GatewayConnection, GatewayReminders
from agent_plugin_api import AgentRunRequest


def turn_tool_dependencies(request: AgentRunRequest) -> tuple[object, ...]:
    """Build tool capabilities available only to gateway-driven turns."""
    connection = GatewayConnection()
    if connection.token is None:
        return ()
    return (
        GatewayReminders(
            connection,
            session_id=request.session.id,
            turn_id=request.turn_id,
        ),
    )
