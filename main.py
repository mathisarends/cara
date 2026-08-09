import argparse
import asyncio
import logging
from uuid import UUID

from gateway_client import (
    ChatCompletedEvent,
    ChatDeltaEvent,
    ChatRequest,
    GatewayClient,
    GatewayError,
    SessionCreateRequest,
    ToolCallCompletedEvent,
    ToolCallStartedEvent,
)

_DEFAULT_GATEWAY_URL = "http://127.0.0.1:8000"
_EXIT_COMMANDS = frozenset({"exit", "quit", ":q"})

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)


async def main(base_url: str = _DEFAULT_GATEWAY_URL) -> None:
    async with GatewayClient(base_url) as client:
        session = await client.sessions.create_session(
            SessionCreateRequest(metadata={"channel": "terminal"})
        )
        print(f"Connected to {base_url} (session {session.id})")
        print("Type a message, or 'exit' to quit.\n")

        while True:
            text = await asyncio.to_thread(input, "You: ")
            if text.strip().lower() in _EXIT_COMMANDS:
                return
            if not text.strip():
                continue
            await _run_turn(client, session.id, text)


async def _run_turn(client: GatewayClient, session_id: UUID, text: str) -> None:
    async with client.event_stream(session_id) as events:
        await client.sessions.start_chat(session_id, ChatRequest(text=text))
        print("Cara: ", end="", flush=True)
        try:
            async for event in events:
                match event:
                    case ChatDeltaEvent(data=data):
                        print(data.text, end="", flush=True)
                    case ChatCompletedEvent():
                        print("\n")
                        return
                    case ToolCallStartedEvent(data=data):
                        print(f"\n[tool] {data.name} {data.arguments}", flush=True)
                    case ToolCallCompletedEvent(data=data):
                        status = "error" if data.is_error else "ok"
                        print(f"[tool] {data.name} -> {status}\n", flush=True)
        except KeyboardInterrupt:
            print("\n[detached from turn]\n")


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
