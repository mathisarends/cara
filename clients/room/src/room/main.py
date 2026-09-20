import argparse
import asyncio
import logging
from pathlib import Path

import uvicorn

from room.app import create_app
from room.platform import DEFAULT_CONFIG_FILE, RoomConfig, RoomConfigError


def main() -> None:
    arguments = _parse_arguments()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    try:
        config = RoomConfig.from_yaml(arguments.config)
        asyncio.run(_run(config))
    except RoomConfigError as error:
        raise SystemExit(str(error)) from error
    except KeyboardInterrupt:
        pass


async def _run(config: RoomConfig) -> None:
    app = create_app(config)
    server_config = uvicorn.Config(
        app,
        host=config.http.host,
        port=config.http.port,
        log_level="info",
    )
    server = uvicorn.Server(server_config)
    await server.serve()


def _parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="cara-room",
        description="Run one Cara room client.",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG_FILE,
        help="room YAML configuration",
    )
    return parser.parse_args()


if __name__ == "__main__":
    main()
