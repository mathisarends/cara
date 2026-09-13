import argparse
import asyncio
import os
import sys
from uuid import UUID

from dotenv import load_dotenv

from cli import commands
from cli.chat import ChatSession
from cli.console import Console
from cli.keyboard import Keyboard
from gateway_client import RpcClientError, connect_gateway
from gateway_client.models import SessionChannel

DEFAULT_URL = "ws://127.0.0.1:8000/v1/gateway"
DEFAULT_CHANNEL = "cli"


def main() -> None:
    # Tool markers and the prompt glyph are outside the Windows default codepage.
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    load_dotenv()
    args = _parse_args()
    try:
        asyncio.run(_run(args))
    except KeyboardInterrupt:
        print()


async def _run(args: argparse.Namespace) -> None:
    keyboard = Keyboard()
    console = Console(
        color=not args.no_color and sys.stdout.isatty(),
        interactive=keyboard.interactive and sys.stdout.isatty(),
        completer=commands.suggest,
    )
    console.header("gateway client")
    console.field("gateway", args.url)
    token = os.environ.get("CARA_GATEWAY_TOKEN")
    if not token:
        console.error("CARA_GATEWAY_TOKEN is not set")
        raise SystemExit(1)
    try:
        client = await connect_gateway(args.url, token=token)
    except OSError as error:
        console.error(f"cannot reach the gateway: {error}")
        raise SystemExit(1) from error

    channel = SessionChannel(name=args.channel, account_id=args.account)
    async with client, keyboard:
        chat = ChatSession(client, console, keyboard, channel, trace=args.events)
        try:
            await chat.run(args.session)
        except RpcClientError as error:
            console.error(str(error))
            raise SystemExit(1) from error


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="cara-chat",
        description="Interactive console client for manual gateway testing.",
    )
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument(
        "--channel",
        default=DEFAULT_CHANNEL,
        help="channel whose current session is opened",
    )
    parser.add_argument("--account", default=None, help="account id of the channel")
    parser.add_argument(
        "--session",
        type=UUID,
        default=None,
        help="attach to this session instead of the channel's current one",
    )
    parser.add_argument(
        "--events",
        action="store_true",
        help="print every session event instead of the rendered chat",
    )
    parser.add_argument("--no-color", action="store_true")
    return parser.parse_args()
