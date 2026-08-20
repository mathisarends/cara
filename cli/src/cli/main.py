import argparse
import asyncio
import sys
from uuid import UUID

from cli.chat import ChatSession
from cli.console import Console
from gateway_client import GatewayClient, GatewayClientError

DEFAULT_URL = "ws://127.0.0.1:8000/v1/gateway"


def main() -> None:
    args = _parse_args()
    try:
        asyncio.run(_run(args))
    except KeyboardInterrupt:
        print()


async def _run(args: argparse.Namespace) -> None:
    console = Console(color=not args.no_color and sys.stdout.isatty())
    console.banner(args.url)
    try:
        client = await GatewayClient.connect(args.url)
    except OSError as error:
        console.error(f"cannot reach the gateway: {error}")
        raise SystemExit(1) from error

    async with client:
        chat = ChatSession(client, console, trace=args.events)
        try:
            await chat.run(args.session)
        except GatewayClientError as error:
            console.error(str(error))
            raise SystemExit(1) from error


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="cara-chat",
        description="Interactive console client for manual gateway testing.",
    )
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument(
        "--session",
        type=UUID,
        default=None,
        help="resume an existing session instead of creating one",
    )
    parser.add_argument(
        "--events",
        action="store_true",
        help="print every session event instead of the rendered chat",
    )
    parser.add_argument("--no-color", action="store_true")
    return parser.parse_args()
