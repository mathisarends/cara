import argparse
import asyncio
import logging
from uuid import UUID

from experiments.terminal import TerminalRenderer, TerminalSession, TurnRunner
from gateway_client import (
    ChatCompletedEvent,
    ChatDeltaEvent,
    ChatRequest,
    GatewayClient,
    GatewayError,
    SessionCreateRequest,
    ToolCallCompletedEvent,
    ToolCallStartedEvent,
    TurnFailedEvent,
)

_DEFAULT_GATEWAY_URL = "http://127.0.0.1:8000"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)


class GatewayTurnRunner(TurnRunner):
    """Runs turns against a gateway session and renders its event stream."""

    def __init__(self, client: GatewayClient, session_id: UUID) -> None:
        self._client = client
        self._session_id = session_id

    async def run_turn(self, text: str, renderer: TerminalRenderer) -> None:
        async with self._client.event_stream(self._session_id) as events:
            await self._client.sessions.start_chat(
                self._session_id, ChatRequest(text=text)
            )
            try:
                async for event in events:
                    match event:
                        case ChatDeltaEvent(data=data):
                            renderer.show_text_delta(data.text)
                        case ChatCompletedEvent():
                            return
                        case ToolCallStartedEvent(data=data):
                            renderer.show_tool_call(data.name, data.arguments)
                        case ToolCallCompletedEvent(data=data):
                            content = str(data.result)
                            if data.is_error:
                                renderer.show_tool_error(data.name, content)
                            else:
                                renderer.show_tool_result(data.name, content)
                        case TurnFailedEvent(data=data):
                            renderer.show_notice(
                                f"turn failed — {data.code}: {data.message}"
                            )
                            return
            except KeyboardInterrupt:
                renderer.show_notice("detached from turn")


async def main(base_url: str = _DEFAULT_GATEWAY_URL) -> None:
    async with GatewayClient(base_url) as client:
        session = await client.sessions.create_session(
            SessionCreateRequest(metadata={"channel": "terminal"})
        )
        renderer = TerminalRenderer()
        renderer.show_notice(f"connected to {base_url} (session {session.id})")
        renderer.show_notice("type a message, or '/exit' to quit.\n")

        terminal = TerminalSession(
            GatewayTurnRunner(client, session.id), renderer=renderer
        )
        await terminal.run()


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Chat with Cara through the gateway.")
    parser.add_argument(
        "--url",
        default=_DEFAULT_GATEWAY_URL,
        help=f"Gateway base URL (default: {_DEFAULT_GATEWAY_URL}).",
    )
    return parser.parse_args()


if __name__ == "__main__":
    try:
        asyncio.run(main(_parse_args().url))
    except (KeyboardInterrupt, EOFError):
        print()
    except GatewayError as exc:
        raise SystemExit(f"Gateway error: {exc}") from exc
