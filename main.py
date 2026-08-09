import argparse
import asyncio

from gateway_client import (
    ChatCompletedEvent,
    ChatDeltaEvent,
    GatewayClient,
    GatewayError,
    GatewaySession,
    ToolCallCompletedEvent,
    ToolCallStartedEvent,
)

_DEFAULT_GATEWAY_URL = "http://127.0.0.1:8000"
_EXIT_COMMANDS = frozenset({"exit", "quit", ":q"})


async def main(base_url: str = _DEFAULT_GATEWAY_URL) -> None:
    async with GatewayClient(base_url) as client:
        created = await client.create_session({"channel": "terminal"})
        session = client.session(created.id)
        print(f"Connected to {base_url} (session {created.id})")
        print("Type a message, or 'exit' to quit.\n")

        while True:
            text = await asyncio.to_thread(input, "You: ")
            if text.strip().lower() in _EXIT_COMMANDS:
                return
            if not text.strip():
                continue
            await _run_turn(session, text)


async def _run_turn(session: GatewaySession, text: str) -> None:
    async with session.events() as events:
        await session.send(text)
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
            await session.cancel()
            print("\n[cancelled]\n")


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
